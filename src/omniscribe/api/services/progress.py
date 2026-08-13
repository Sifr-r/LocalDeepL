"""Token-bound progress channel + per-block events.

The protocol now supports two frame kinds, both sent over the same WebSocket:

1. Progress frame (legacy): ``{"status", "percent", "stage", "warning?"}``
2. Block frame (new): ``{"type": "block_complete", "page_idx", "block_idx",
   "bbox", "text", "kind", "confidence"}``
3. Translation frame (new): ``{"type": "translate_chunk_complete",
   "chunk_idx", "source_chars", "translated_text"}``

Process-lifetime boundary
-------------------------

:class:`ProgressService` is itself stateless: every frame builder and
helper here is a pure function of its arguments. The "in-memory state"
it participates in is the tokens it creates and validates on behalf of
process-bound WebSocket channels:

- :meth:`ProgressService.create_channel` mints a ``channel_id`` and
  ``session_token`` pair from ``secrets.token_urlsafe``. Those tokens
  are only meaningful while the current process is alive; a restart
  yields fresh tokens and any client that tries to reconnect with the
  old pair will fail :meth:`ProgressService.validate_channel_id` /
  :meth:`validate_session_token` because the active-channel registry
  lives in :class:`ConnectionManager` (in
  :mod:`omniscribe.api.routers.websocket`), not here.
- :meth:`ProgressService.is_bound` compares inbound tokens against
  expected tokens via ``hmac.compare_digest``; the *expected* token is
  whatever the :class:`ConnectionManager` last stored for that channel.

The ``ProgressService`` instance is held as ``state.progress_service``
on the :class:`LocalStateBackend` singleton and as
``_progress_service`` in :mod:`omniscribe.api.routers.websocket`. Because
the service is stateless, swapping the backend does not affect progress
math, but the channel IDs it validates are still bound to whatever
process minted them.

See the *Known Tech Debt* section of ``AGENTS.md`` for the project-level
acknowledgement: "Job/artifact state is in-memory only
(``api/routers/state.py`` singletons) — restarts lose history; no
horizontal scaling."
"""

from __future__ import annotations

import hmac
import re
import secrets
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, cast


class Stage(StrEnum):
    CONVERT = "convert"
    DETECT = "detect"
    OCR = "ocr"
    REFINE = "refine"
    EMBED = "embed"
    TRANSLATE = "translate"


class FrameType(StrEnum):
    PROGRESS = "progress"
    BLOCK = "block_complete"
    PAGE = "page_complete"
    TRANSLATE_CHUNK = "translate_chunk_complete"
    CHUNK_INIT = "chunk_init"
    CHUNK_COMPLETE = "chunk_complete"
    CANCELLED = "cancelled"
    GLOSSARY_IMPORT = "glossary_import"
    BLOCK_RETRY = "block_retry"
    BLOCK_REVISED = "block_revised"
    QUALITY_SUMMARY = "quality_summary"


CHANNEL_TOKEN_BYTES: Final = 24
SESSION_TOKEN_BYTES: Final = 32
_TOKEN_RE: Final = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_DISPLAY_ID_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_STAGE_WEIGHTS: Final[dict[Stage, tuple[int, int]]] = {
    Stage.CONVERT: (0, 15),
    Stage.DETECT: (15, 25),
    Stage.OCR: (25, 75),
    Stage.REFINE: (75, 90),
    Stage.EMBED: (90, 100),
    Stage.TRANSLATE: (0, 100),  # translation is a separate job, full 0..100
}


@dataclass(frozen=True)
class ProgressChannel:
    """Opaque channel and session tokens for websocket/process binding."""

    channel_id: str
    session_token: str
    display_client_id: str | None = None


class ProgressService:
    """Progress math, channel validation, and frame builders."""

    def stage_to_percent(self, stage: str, current: int, total: int) -> int:
        return stage_to_percent(stage, current, total)

    def create_channel(self, display_client_id: str | None = None) -> ProgressChannel:
        return ProgressChannel(
            channel_id=secrets.token_urlsafe(CHANNEL_TOKEN_BYTES),
            session_token=secrets.token_urlsafe(SESSION_TOKEN_BYTES),
            display_client_id=sanitize_display_client_id(display_client_id),
        )

    def validate_channel_id(self, channel_id: str) -> str:
        return validate_channel_id(channel_id)

    def validate_session_token(self, session_token: str) -> str:
        return validate_session_token(session_token)

    def is_bound(
        self,
        *,
        channel_id: str,
        session_token: str,
        expected_channel_id: str,
        expected_session_token: str,
    ) -> bool:
        channel = validate_channel_id(channel_id)
        token = validate_session_token(session_token)
        expected_channel = validate_channel_id(expected_channel_id)
        expected_token = validate_session_token(expected_session_token)
        return hmac.compare_digest(channel, expected_channel) and hmac.compare_digest(
            token, expected_token
        )

    # ---- frame builders ---------------------------------------------------
    @staticmethod
    def build_progress_frame(
        message: str, percent: int, stage: str = "", warning: bool = False
    ) -> dict[str, Any]:
        # Legacy progress frame: no `type` field, just {status, percent, stage}
        # (optionally warning=True). This preserves backward compatibility with
        # the existing UI which routes on shape (no `type` => progress).
        # The new block / translate-chunk / cancelled frames add a `type`
        # discriminator; progress frames stay legacy on purpose.
        frame: dict[str, Any] = {
            "status": message,
            "percent": percent,
            "stage": stage,
        }
        if warning:
            frame["warning"] = True
        return frame

    @staticmethod
    def build_block_frame(
        *,
        page_idx: int,
        block_idx: int,
        bbox: list[float],
        text: str,
        kind: str = "text",
        confidence: float | None = None,
    ) -> dict[str, Any]:
        return {
            "type": FrameType.BLOCK.value,
            "page_idx": page_idx,
            "block_idx": block_idx,
            "bbox": list(bbox),
            "text": text,
            "kind": kind,
            "confidence": confidence,
        }

    @staticmethod
    def build_block_retry_frame(
        *,
        page_idx: int,
        block_idx: int,
        attempt: int,
        confidence: float,
        target: float,
    ) -> dict[str, Any]:
        """Emitted when the repair loop flags a below-target block for re-OCR."""
        return {
            "type": FrameType.BLOCK_RETRY.value,
            "page_idx": page_idx,
            "block_idx": block_idx,
            "attempt": int(attempt),
            "confidence": confidence,
            "target": target,
        }

    @staticmethod
    def build_block_revised_frame(
        *,
        page_idx: int,
        block_idx: int,
        attempt: int,
        bbox: list[float],
        text: str,
        kind: str = "text",
        confidence: float | None = None,
    ) -> dict[str, Any]:
        """Emitted when a re-OCR pass produced an accepted result.

        Same shape as ``block_complete`` plus ``attempt`` so the UI can
        swap the streamed line and mark it "revised".
        """
        return {
            "type": FrameType.BLOCK_REVISED.value,
            "page_idx": page_idx,
            "block_idx": block_idx,
            "attempt": int(attempt),
            "bbox": list(bbox),
            "text": text,
            "kind": kind,
            "confidence": confidence,
        }

    @staticmethod
    def build_quality_summary_frame(
        *,
        scope: str,
        target: float,
        avg_confidence: float,
        repaired_count: int,
        below_target_count: int,
        page_idx: int | None = None,
    ) -> dict[str, Any]:
        """End-of-page / end-of-job repair statistics (spec §3.1)."""
        frame: dict[str, Any] = {
            "type": FrameType.QUALITY_SUMMARY.value,
            "scope": scope,
            "target": target,
            "avg_confidence": avg_confidence,
            "repaired_count": int(repaired_count),
            "below_target_count": int(below_target_count),
        }
        if page_idx is not None:
            frame["page_idx"] = page_idx
        return frame

    @staticmethod
    def build_page_complete_frame(
        *,
        page_idx: int,
    ) -> dict[str, Any]:
        return {
            "type": FrameType.PAGE.value,
            "page_idx": page_idx,
        }

    @staticmethod
    def build_translate_chunk_frame(
        *,
        chunk_idx: int,
        source_chars: int,
        translated_text: str,
        target_language: str,
    ) -> dict[str, Any]:
        return {
            "type": FrameType.TRANSLATE_CHUNK.value,
            "chunk_idx": chunk_idx,
            "source_chars": source_chars,
            "translated_text": translated_text,
            "target_language": target_language,
        }

    @staticmethod
    def build_chunk_init_frame(
        *,
        total_chunks: int,
        chapters: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Pre-amble emitted at the start of a chunked OCR run.

        ``chapters`` is part of the P1 schema but populated from P5
        onward; until then every frame carries an empty list.
        """
        return {
            "type": FrameType.CHUNK_INIT.value,
            "total_chunks": int(total_chunks),
            "chapters": list(chapters) if chapters else [],
        }

    @staticmethod
    def build_chunk_complete_frame(
        *,
        chunk_idx: int,
        total_chunks: int,
        page_range: str,
        source_pages: list[int],
        text_chars_so_far: int,
        overall_percent: int | None = None,
        chapters: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Per-chunk terminal frame emitted after a chunk finishes."""
        frame: dict[str, Any] = {
            "type": FrameType.CHUNK_COMPLETE.value,
            "chunk_idx": int(chunk_idx),
            "total_chunks": int(total_chunks),
            "page_range": page_range,
            "source_pages": [int(p) for p in source_pages],
            "text_chars_so_far": int(text_chars_so_far),
            "chapters": list(chapters) if chapters else [],
        }
        if overall_percent is not None:
            frame["overall_percent"] = int(overall_percent)
        return frame

    @staticmethod
    def build_cancelled_frame(message: str = "Cancelled by user.") -> dict[str, Any]:
        return {
            "type": FrameType.CANCELLED.value,
            "status": message,
            "percent": 0,
            "stage": "cancelled",
        }

    @staticmethod
    def build_glossary_import_frame(
        *,
        glossary_id: str,
        name: str,
        format_label: str,
        entry_count: int,
        warnings: list[str],
        status: str = "complete",
    ) -> dict[str, Any]:
        """Terminal frame emitted after a glossary import finishes."""
        return {
            "type": FrameType.GLOSSARY_IMPORT.value,
            "status": status,
            "glossary_id": glossary_id,
            "name": name,
            "format": format_label,
            "entry_count": entry_count,
            "warnings": list(warnings),
        }


def stage_to_percent(stage: str, current: int, total: int) -> int:
    """Map a pipeline stage + sub-progress into a 0-100 overall percent."""
    clean_stage = _clean_stage(stage)
    if clean_stage in _STAGE_WEIGHTS:
        lo, hi = _STAGE_WEIGHTS[cast(Stage, clean_stage)]
    else:
        lo, hi = (0, 100)
    clean_total = _clean_progress_count(total, "total")
    if clean_total <= 0:
        return lo
    clean_current = min(_clean_progress_count(current, "current"), clean_total)
    return lo + int((clean_current / clean_total) * (hi - lo))


def validate_stage(stage: str) -> Stage:
    clean_stage = _clean_stage(stage)
    if clean_stage not in _STAGE_WEIGHTS:
        raise ValueError(
            "stage must be one of: convert, detect, ocr, refine, embed, translate."
        )
    return Stage(clean_stage)


def sanitize_display_client_id(client_id: str | None) -> str | None:
    if client_id is None:
        return None
    if not isinstance(client_id, str):
        raise TypeError("display client ID must be a string.")
    cleaned = client_id.strip()
    if not cleaned:
        return None
    if not _DISPLAY_ID_RE.fullmatch(cleaned):
        raise ValueError("display client ID contains invalid characters.")
    return cleaned


def validate_channel_id(channel_id: str) -> str:
    return _validate_token(channel_id, "channel_id")


def validate_session_token(session_token: str) -> str:
    return _validate_token(session_token, "session_token")


def _clean_stage(stage: str) -> str:
    if not isinstance(stage, str):
        raise TypeError("stage must be a string.")
    return stage.strip().lower()


def _clean_progress_count(value: int, field_name: str) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    return max(value, 0)


def _validate_token(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    cleaned = value.strip()
    if not _TOKEN_RE.fullmatch(cleaned):
        raise ValueError(f"{field_name} is not a valid opaque token.")
    return cleaned
