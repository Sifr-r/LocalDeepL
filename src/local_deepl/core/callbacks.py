"""Callback Protocols for engine observers.

Engines emit these callbacks during execution; the API layer is
responsible for wiring them to the transport (WebSocket, in-process
listener, log line, etc.). Keeping the Protocols in ``core/`` lets the
engine import them without depending on the transport — that one-way
dependency is the whole point of this module.

Shape of each callback mirrors the corresponding WebSocket frame in
``api/routers/websocket.py`` so the default API-layer wiring is a
thin adapter (positional args in, kwargs out) rather than a structural
mapping. New transports (gRPC, an in-process queue, a log line) can
implement the same callable contract without engine changes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import NamedTuple

# Per-block event. Emitted once a block has OCR text attached. The
# `kind` and `confidence` fields are advisory: the engine fills them
# with conservative defaults ("text", a length-based heuristic) and
# downstream consumers are free to ignore them.
#
# Signature: (page_idx, block_idx, bbox, text, kind, confidence)
#   - page_idx:   0-indexed page number
#   - block_idx:  0-indexed block number on the page (reading order)
#   - bbox:       normalized [x0, y0, x1, y1] in 0..1
#   - text:       the recognized text (already stripped)
#   - kind:       block kind label, "text" by default
#   - confidence: optional 0..1 confidence proxy
BlockCallback = Callable[
    [int, int, list[float], str, str, float | None],
    Awaitable[None],
]


# Per-page event. Emitted after every page's OCR + refine + dedup pass
# completes. Used to drive the live bbox overlay in the UI; emitting
# it for failed pages too means a missing or failed page is still
# observable downstream (a UI can render "page N failed" rather than
# hanging waiting for the page_complete frame).
PageCompleteCallback = Callable[[int], Awaitable[None]]


# Per-chunk translation event. Emitted once a translated block is
# ready. The `chunk_idx` is monotonic within a single `translate_tree`
# call; consumers can use it to order frames that arrive out of order
# over an async transport.
#
# Signature matches the existing
# `manager.send_translate_chunk / build_translate_chunk_frame` wire
# shape so the default API-layer wiring is a thin positional-to-
# keyword adapter rather than a structural mapping. If you need
# to add a field (e.g. `source_block_idx` for UI highlighting),
# update `ProgressService.build_translate_chunk_frame` and the
# websocket manager in lockstep — the contract is "one frame per
# translated block."
#
# Signature: (chunk_idx, source_chars, translated_text, target_language)
TranslateChunkCallback = Callable[
    [int, int, str, str],
    Awaitable[None],
]


class BlockCallbackSet(NamedTuple):
    """Bag of optional per-block and per-page callbacks.

    NamedTuple (not dataclass) so callers can use positional construction
    in tests, and equality / hashing come for free. Default `None` for
    both fields means "engine emits no observer events," which is the
    right default for in-process programmatic use of `OCRPipeline`.
    """

    on_block: BlockCallback | None = None
    on_page_complete: PageCompleteCallback | None = None


class TranslateCallbacks(NamedTuple):
    """Bag of translation-specific callbacks.

    Kept separate from `BlockCallbackSet` so the OCR path doesn't have
    to know translation exists. The async translation workflow
    (`api/tasks.py`) wires this; the sync translation router
    (`api/routers/extraction_translation.py`) does the same.
    """

    on_translate_chunk: TranslateChunkCallback | None = None


__all__ = [
    "BlockCallback",
    "BlockCallbackSet",
    "PageCompleteCallback",
    "TranslateCallbacks",
    "TranslateChunkCallback",
]
