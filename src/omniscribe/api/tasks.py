import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, cast

from omniscribe.api.celery_app import celery_app
from omniscribe.core.translation_config import TranslationSettings

try:
    from celery import Task as _CeleryTask
except ImportError:
    _CeleryTask = object

try:
    from celery.signals import worker_process_shutdown, worker_shutdown
except ImportError:
    worker_process_shutdown = None
    worker_shutdown = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Celery worker lifecycle: release the shared httpx client on shutdown.
# ---------------------------------------------------------------------------
# Audit-secondary F28: the FastAPI lifespan calls
# ``aclose_shared_client`` in its ``finally`` block, but Celery
# workers live in their own process and never enter that lifespan.
# Without this signal, a long-running worker holds the shared httpx
# client (and its keep-alive socket) alive across event-loop
# boundaries; the next task creates a new client on a different loop
# and the old one is left to be GC'd. We register the signal handler
# at import time so it is wired before the first task runs.
#
# Two signals cover the two Celery deployment modes:
# - ``worker_process_shutdown`` fires when a child worker process
#   exits (prefork pool, the production case).
# - ``worker_shutdown`` fires when the main worker process exits
#   (solo pool, the local-dev case).
# Both are safe to register; they call the same close routine.


def _aclose_shared_client_on_celery_shutdown(**_kwargs: Any) -> None:
    """Run ``aclose_shared_client`` on a fresh event loop.

    The Celery signal handler runs synchronously on the main thread;
    the shared client is async-only. We spin up a fresh loop, run
    the close coroutine, and tear the loop down. Any failure is
    logged but never raised — the signal handler must not crash the
    worker shutdown.
    """
    try:
        from omniscribe.core.ocr.multi_format_client import aclose_shared_client
    except ImportError:
        # Optional httpx dep missing; nothing to close.
        return
    try:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(aclose_shared_client())
        finally:
            loop.close()
    except Exception:  # pragma: no cover — defensive
        logger.warning(
            "Celery shutdown: could not aclose shared httpx client; "
            "some sockets may linger briefly",
            exc_info=True,
        )


if worker_process_shutdown is not None:
    worker_process_shutdown.connect(_aclose_shared_client_on_celery_shutdown)
if worker_shutdown is not None:
    worker_shutdown.connect(_aclose_shared_client_on_celery_shutdown)


def _current_translation_settings() -> TranslationSettings:
    """Use mutable web settings when available, otherwise environment settings."""
    try:
        from omniscribe.api.routers.config import get_translation_settings
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.split(".", maxsplit=1)[0] == "fastapi":
            return TranslationSettings.from_env()
        raise

    return get_translation_settings()


class _CeleryTaskBase(_CeleryTask):
    """Mixin consolidating boilerplate shared by every Celery task in this app.

    Two patterns repeat across ``process_translation_task`` and
    ``process_glossary_import_task``:

    1. **Progress reporting** — ``self.update_state(state="PROGRESS",
       meta={"progress": <int>, "status": <str>})`` is called at several
       well-known phases (start, mid, done). The :meth:`emit_progress`
       helper wraps the boilerplate so callers write a single line per
       phase and the meta-key names live in exactly one place.

    2. **WebSocket channel authorization** — both tasks optionally accept
       ``(channel_id, session_token)`` to stream frames back to a UI.
       The auth check (``manager.is_authorized``) is invoked identically;
       :meth:`is_authorized_channel` centralizes it and returns ``False``
       for any malformed pair so callers don't have to repeat the
       short-circuit logic.

    Why a Python mixin (not a ``celery.Task`` subclass registered with
    ``@celery_app.task(base=...)``): Celery only supports a single
    ``base`` class, but multiple tasks already inherit distinct binding
    configurations (``bind=True``). A separate mixin keeps each task's
    decorator as-is while still extracting the duplicated logic.
    """

    def emit_progress(self, progress_pct: int, status: str) -> None:
        """Update the Celery task state with a percent + status payload.

        Equivalent to the inline ``self.update_state(state="PROGRESS",
        meta={"progress": <pct>, "status": <str>})`` boilerplate that
        previously appeared at every progress tick.
        """
        self.update_state(
            state="PROGRESS",
            meta={"progress": progress_pct, "status": status},
        )

    @staticmethod
    def is_authorized_channel(
        channel_id: str | None, session_token: str | None
    ) -> bool:
        """Return ``True`` iff ``(channel_id, session_token)`` is a bound channel.

        Short-circuits to ``False`` when either argument is falsy or when
        the WebSocket manager rejects the binding, so callers don't have
        to repeat the null-check + ``is_authorized`` dance.
        """
        if not channel_id or not session_token:
            return False
        from omniscribe.api.routers.websocket import manager

        return manager.is_authorized(channel_id, session_token)

    def run_async_or_schedule(self, coro_factory: Callable[[], Awaitable[Any]]) -> Any:
        """Run a coroutine factory in whichever async context is available.

        Celery workers run inside their own event loop; tests sometimes
        don't have one yet. Try to schedule the coroutine on an existing
        loop (``loop.create_task``), otherwise fall back to ``asyncio.run``
        so the task is still completed synchronously.
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
        coro = cast(Coroutine[Any, Any, Any], coro_factory())
        if loop is not None and loop.is_running():
            return loop.create_task(coro)
        return asyncio.run(coro)


class _TranslationTask(_CeleryTaskBase):
    """Apply the mixin to the translation task via dynamic inheritance."""


class _GlossaryTask(_CeleryTaskBase):
    """Apply the mixin to the glossary import task via dynamic inheritance."""


class _OCRTask(_CeleryTaskBase):
    """Apply the mixin to the OCR task via dynamic inheritance."""


@celery_app.task(bind=True, name="process_translation", base=_TranslationTask)
def process_translation_task(
    self,
    artifact_id: str,
    token: str,
    target_language: str,
    glossary_entries: list,
    channel_id: str | None = None,
    session_token: str | None = None,
):
    """
    Background task to run the LangGraph translation workflow on a DocumentTree.

    `channel_id` and `session_token` are optional. When both are
    supplied, the task streams `translate_chunk_complete` WebSocket
    frames back to the bound progress channel as each block is
    translated. The auth check (token must match the channel's
    binding) is performed once at task entry; subsequent emissions
    are unconditional — a binding-checked callback would otherwise
    re-validate on every chunk.
    """
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        raise ValueError("artifact_id must be a non-empty string")

    logger.info(f"Starting tree translation task for artifact_id={artifact_id}")

    # Update state to started
    self.emit_progress(0, "Loading DocumentTree")

    from omniscribe.api.routers import state

    try:
        path = asyncio.run(state.text_artifacts.get(artifact_id, token))
    except Exception as exc:
        raise ValueError(f"Could not load artifact {artifact_id}") from exc

    import os

    from omniscribe.api.services.tree_artifact import (
        TreeArtifactError,
        read_tree,
    )

    tree_path = f"{path}.tree.json"
    if not os.path.exists(tree_path):
        raise ValueError(f"DocumentTree not found at {tree_path}")

    from pathlib import Path

    try:
        tree = read_tree(Path(tree_path))
    except TreeArtifactError as exc:
        raise ValueError(f"DocumentTree at {tree_path} is unreadable: {exc}") from exc

    from omniscribe.core.glossary import Glossary
    from omniscribe.core.translation_tree import translate_tree

    glossary = Glossary()
    if glossary_entries:
        glossary = Glossary.from_dict({"entries": glossary_entries})

    # Initialize translation graph
    from omniscribe.core.translation import run_translation

    async def translator_fn(prompt: str, lang: str) -> str:
        # ``run_translation`` is a sync function that runs the compiled
        # translation graph; offload to a thread to keep the event loop
        # responsive while it executes.
        return await asyncio.to_thread(
            run_translation,
            prompt,
            target_language=lang,
            settings=_current_translation_settings(),
        )

    self.emit_progress(10, "Translating DocumentTree blocks")

    # Phase C (review M1) — build the translate_chunk callback that
    # forwards into the WebSocket manager, then pass it to translate_tree
    # instead of the (pre-fix) `channel_id=None` kwarg that the function
    # never accepted. The auth check happens here once, not per chunk,
    # because the per-chunk emissions otherwise re-validate on every
    # block (cheap, but pointless).
    from omniscribe.api.routers.websocket import manager

    async def _emit_chunk(
        chunk_idx: int,
        source_chars: int,
        translated_text: str,
        target_language: str,
    ) -> None:
        # The binding check is satisfied by the task-init time check
        # below; once the callback is constructed we don't re-validate
        # per chunk.
        await manager.send_translate_chunk(
            channel_id,
            chunk_idx=chunk_idx,
            source_chars=source_chars,
            translated_text=translated_text,
            target_language=target_language,
        )

    # `on_translate_chunk` is either the per-chunk emitter (when the
    # channel binding is verified) or `None` (the no-observer default).
    # Plain assignment (no annotation) because mypy rejects a function
    # definition used as a type hint.
    on_translate_chunk = None
    if channel_id:
        # Verify the channel is bound and the supplied session_token
        # matches before emitting anything. If not bound, drop the
        # callback silently — the WS frames would error out anyway,
        # but a no-op callback keeps the rest of the run working.
        if self.is_authorized_channel(channel_id, session_token):
            on_translate_chunk = _emit_chunk
        else:
            logger.warning(
                "Translation task received unbound channel_id=%s; "
                "no progress frames will be emitted",
                channel_id,
            )

    translated_tree = asyncio.run(
        translate_tree(
            tree,
            target_language=target_language,
            translator=translator_fn,
            glossary=glossary,
            dual_translate=False,
            on_translate_chunk=on_translate_chunk,
        )
    )

    # Save the translated tree back to the artifact path. Phase D
    # (review M4) — the artifact is now JSON, matching the loader
    # above and the `api/routers/ocr.py` write site.
    from pathlib import Path

    from omniscribe.api.services.tree_artifact import write_tree_atomic

    translated_tree_path = f"{path}_translated.tree.json"
    write_tree_atomic(translated_tree, Path(translated_tree_path))

    self.emit_progress(100, "Translation complete")

    # Return summary dict for status polling
    return {
        "artifact_id": artifact_id,
        "translated_tree_path": translated_tree_path,
        "blocks_translated": len(translated_tree.pages),
    }


@celery_app.task(bind=True, name="process_glossary_import", base=_GlossaryTask)
def process_glossary_import_task(
    self,
    source_dict: dict,
    glossary_name: str,
    channel_id: str | None = None,
    session_token: str | None = None,
):
    """Background task for large glossary imports.

    Re-runs the selected parser via the JSON-safe ``source_dict`` payload,
    saves the result to the on-disk library, and emits a terminal
    ``glossary_import`` WebSocket frame.
    """

    import base64

    from omniscribe.api.routers import state
    from omniscribe.api.routers.websocket import manager
    from omniscribe.core.glossary_sources import parse

    self.emit_progress(10, "Loading glossary source")

    if not isinstance(source_dict, dict):
        raise ValueError("source_dict must be a dict.")
    format_name = str(source_dict.get("format", "")).strip().lower()
    if not format_name:
        raise ValueError("source_dict.format is required.")

    kwargs: dict = {key: value for key, value in source_dict.items() if key != "format"}
    if isinstance(kwargs.get("inline_bytes_b64"), str):
        kwargs["data"] = base64.b64decode(kwargs.pop("inline_bytes_b64"), validate=True)
    if "data" in kwargs and isinstance(kwargs["data"], str):
        kwargs["data"] = kwargs["data"].encode("utf-8")

    summary = parse(format=format_name, source_uri=None, **kwargs)

    self.emit_progress(80, "Saving glossary to library")

    store = state.lexicon_store
    meta = store.save_glossary(
        name=glossary_name or f"{format_name.upper()} import",
        format=format_name,
        entries=summary.entries,
        source_uri=summary.source_uri,
        encoding=summary.encoding,
    )

    terminal_frame = state.progress_service.build_glossary_import_frame(
        glossary_id=meta.id,
        name=meta.name,
        format_label=format_name,
        entry_count=len(summary.entries),
        warnings=list(summary.warnings),
        status="complete",
    )

    async def _emit() -> None:
        if self.is_authorized_channel(channel_id, session_token):
            await manager.send(channel_id, terminal_frame)

    self.run_async_or_schedule(_emit)

    self.emit_progress(100, "Glossary import complete")

    return {
        "glossary_id": meta.id,
        "name": meta.name,
        "format": format_name,
        "entry_count": len(summary.entries),
        "warnings": list(summary.warnings),
    }


@celery_app.task(bind=True, name="process_ocr", base=_OCRTask)
def process_ocr_task(
    self,
    job_id: str,
    file_path: str,
    settings_dict: dict[str, Any],
    channel_id: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    """Background task to run the full OCR pipeline on an uploaded file."""
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("job_id must be a non-empty string")
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("file_path must be a non-empty string")
    if not isinstance(settings_dict, dict):
        raise ValueError("settings_dict must be a dict")

    import os
    import tempfile
    import time

    from omniscribe.api.routers.ocr import (
        _emit_job_started,
        _execute_ocr_pipeline,
        _record_job,
    )
    from omniscribe.api.schemas import ProcessSettings

    if channel_id is None:
        channel_id = settings_dict.get("progress_channel")
    if session_token is None:
        session_token = settings_dict.get("progress_token")

    self.emit_progress(0, "Initializing OCR pipeline")

    t_start = time.monotonic()
    try:
        clean_settings = {
            k: v
            for k, v in settings_dict.items()
            if k not in ("progress_channel", "progress_token")
        }
        settings = ProcessSettings(**clean_settings)
        output_path = os.path.join(tempfile.gettempdir(), f"output_{job_id}.pdf")

        _emit_job_started(
            job_id,
            model=settings.model,
            pipeline_mode=settings.pipeline_mode,
            pages=settings.pages,
        )

        (
            pipeline,
            artifact_handle,
            metadata_handle,
            text_path,
            failed_pages,
        ) = asyncio.run(
            _execute_ocr_pipeline(
                settings=settings,
                input_path=file_path,
                output_path=output_path,
                progress_target=channel_id,
            )
        )

        duration_s = time.monotonic() - t_start
        _record_job(
            job_id=job_id,
            filename=os.path.basename(file_path),
            model=settings.model,
            pipeline_mode=settings.pipeline_mode,
            pages=settings.pages,
            duration_s=duration_s,
            status="complete",
            failed_pages=failed_pages,
            text_artifact_id=artifact_handle.artifact_id,
        )
        self.emit_progress(100, "OCR complete")
        return {
            "job_id": job_id,
            "status": "complete",
            "text_artifact_id": artifact_handle.artifact_id,
            "text_artifact_token": artifact_handle.token,
            "output_pdf_path": output_path,
            "failed_pages": list(failed_pages),
        }
    except Exception as exc:
        duration_s = time.monotonic() - t_start
        model = (
            settings.model
            if "settings" in locals()
            else str(settings_dict.get("model", "unknown"))
        )
        pipeline_mode = (
            settings.pipeline_mode
            if "settings" in locals()
            else str(settings_dict.get("pipeline_mode", "hybrid"))
        )
        pages = settings.pages if "settings" in locals() else settings_dict.get("pages")
        _record_job(
            job_id=job_id,
            filename=os.path.basename(file_path),
            model=model,
            pipeline_mode=pipeline_mode,
            pages=pages,
            duration_s=duration_s,
            status="error",
            error=str(exc),
        )
        self.emit_progress(0, f"Error: {exc}")
        raise
