import asyncio
import logging

from local_deepl.api.celery_app import celery_app
from local_deepl.core.translation_config import TranslationSettings

logger = logging.getLogger(__name__)


def _current_translation_settings() -> TranslationSettings:
    """Use mutable web settings when available, otherwise environment settings."""
    try:
        from local_deepl.api.routers.config import get_translation_settings
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.split(".", maxsplit=1)[0] == "fastapi":
            return TranslationSettings.from_env()
        raise

    return get_translation_settings()


@celery_app.task(bind=True, name="process_translation")
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
    self.update_state(
        state="PROGRESS",
        meta={"progress": 0, "status": "Loading DocumentTree"},
    )

    from local_deepl.api.routers import state

    try:
        path = asyncio.run(state.text_artifacts.get(artifact_id, token))
    except Exception as exc:
        raise ValueError(f"Could not load artifact {artifact_id}") from exc

    import os

    from local_deepl.api.services.tree_artifact import (
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

    from local_deepl.core.glossary import Glossary
    from local_deepl.core.translation_tree import translate_tree

    glossary = Glossary()
    if glossary_entries:
        glossary = Glossary.from_dict({"entries": glossary_entries})

    # Initialize translation graph
    from local_deepl.core.translation import run_translation

    async def translator_fn(prompt: str, lang: str) -> str:
        # Re-use run_translation wrapper for now (which is sync inside run_translation,
        # wait! run_translation uses the graph which is sync).
        # We can just call run_translation synchronously.
        return run_translation(
            prompt,
            target_language=lang,
            settings=_current_translation_settings(),
        )

    self.update_state(
        state="PROGRESS",
        meta={"progress": 10, "status": "Translating DocumentTree blocks"},
    )

    # Phase C (review M1) — build the translate_chunk callback that
    # forwards into the WebSocket manager, then pass it to translate_tree
    # instead of the (pre-fix) `channel_id=None` kwarg that the function
    # never accepted. The auth check happens here once, not per chunk,
    # because the per-chunk emissions otherwise re-validate on every
    # block (cheap, but pointless).
    from local_deepl.api.routers.websocket import manager

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
        bound = (
            channel_id
            and session_token
            and manager.is_authorized(channel_id, session_token)
        )
        if bound:
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

    from local_deepl.api.services.tree_artifact import write_tree_atomic

    translated_tree_path = f"{path}_translated.tree.json"
    write_tree_atomic(translated_tree, Path(translated_tree_path))

    self.update_state(
        state="PROGRESS",
        meta={"progress": 100, "status": "Translation complete"},
    )

    # Return summary dict for status polling
    return {
        "artifact_id": artifact_id,
        "translated_tree_path": translated_tree_path,
        "blocks_translated": len(translated_tree.pages),
    }


@celery_app.task(bind=True, name="process_glossary_import")
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

    from local_deepl.api.routers import state
    from local_deepl.api.routers.websocket import manager
    from local_deepl.core.glossary_sources import parse

    self.update_state(
        state="PROGRESS",
        meta={"progress": 10, "status": "Loading glossary source"},
    )

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

    self.update_state(
        state="PROGRESS",
        meta={"progress": 80, "status": "Saving glossary to library"},
    )

    library = state.glossary_library
    stored = library.save(
        name=glossary_name or f"{format_name.upper()} import",
        format=format_name,
        entries=summary.entries,
        source_uri=summary.source_uri,
        encoding=summary.encoding,
    )

    terminal_frame = state.progress_service.build_glossary_import_frame(
        glossary_id=stored.id,
        name=stored.name,
        format_label=format_name,
        entry_count=len(summary.entries),
        warnings=list(summary.warnings),
        status="complete",
    )

    async def _emit() -> None:
        if channel_id and manager.is_authorized(channel_id, session_token):
            await manager.send(channel_id, terminal_frame)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        loop.create_task(_emit())
    else:
        asyncio.run(_emit())

    self.update_state(
        state="PROGRESS",
        meta={"progress": 100, "status": "Glossary import complete"},
    )

    return {
        "glossary_id": stored.id,
        "name": stored.name,
        "format": format_name,
        "entry_count": len(summary.entries),
        "warnings": list(summary.warnings),
    }
