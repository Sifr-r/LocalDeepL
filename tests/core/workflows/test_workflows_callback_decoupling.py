"""Decoupling tests for the BlockCallback extraction (review M2).

The engine used to import the FastAPI WebSocket manager directly,
inverting the core→api dependency. After Phase B the engine only
sees a `BlockCallbackSet`; the API layer is responsible for wiring
those callbacks to the transport.

Two angles of coverage:
  1. Static AST scan — `core/workflows/hybrid.py` must not import
     from `omniscribe.api`. This is the cheap invariant test that
     makes the dependency direction enforceable going forward.
  2. Behavioral — a `HybridEngine` built with a recording callback
     set emits per-block and per-page events for the right blocks.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from omniscribe.core.callbacks import BlockCallbackSet

# ---------------------------------------------------------------------------
# 1. Static dependency-direction check
# ---------------------------------------------------------------------------

# Files in `core/` must not import anything from `api/`. The reverse
# (api importing core) is fine and expected. After the god-module
# decomposition, `core/ocr.py` and `core/grounded.py` became
# sub-packages; each member file is included individually so a
# regression in any one of them surfaces a clear failure.
_CORE_FILES_TO_CHECK = [
    Path("src/omniscribe/core/workflows/hybrid.py"),
    Path("src/omniscribe/core/workflows/grounded.py"),
    Path("src/omniscribe/core/workflows/base.py"),
    Path("src/omniscribe/core/ocr/client.py"),
    Path("src/omniscribe/core/ocr/exceptions.py"),
    Path("src/omniscribe/core/ocr/filters.py"),
    Path("src/omniscribe/core/ocr/processor.py"),
    Path("src/omniscribe/core/ocr/prompts.py"),
    Path("src/omniscribe/core/grounded/models.py"),
    Path("src/omniscribe/core/grounded/parsers.py"),
    Path("src/omniscribe/core/grounded/prompted.py"),
    Path("src/omniscribe/core/grounded/rasterize.py"),
    Path("src/omniscribe/core/pdf/rasterizer.py"),
    Path("src/omniscribe/core/pdf/embedder.py"),
    Path("src/omniscribe/core/pdf/handler.py"),
    Path("src/omniscribe/core/aligner.py"),
    Path("src/omniscribe/core/processors/base.py"),
    Path("src/omniscribe/core/processors/reading_order.py"),
    Path("src/omniscribe/core/processors/quality.py"),
    Path("src/omniscribe/core/processors/structure.py"),
    Path("src/omniscribe/core/processors/section.py"),
    Path("src/omniscribe/core/processors/layout.py"),
    Path("src/omniscribe/core/processors/table.py"),
    Path("src/omniscribe/core/block_tree.py"),
    Path("src/omniscribe/core/document.py"),
    Path("src/omniscribe/core/translate/tree.py"),
]


@pytest.mark.parametrize(
    "path",
    _CORE_FILES_TO_CHECK,
    # F4.16 audit fix: show ``processors/section.py`` instead of
    # ``section.py`` so two modules that share a basename
    # (e.g. ``layout.py`` under ``core/processors/`` and under
    # another tree) don't collide in the test ID. The leading
    # ``src/omniscribe/core/`` prefix is dropped because every
    # entry in ``_CORE_FILES_TO_CHECK`` carries it identically.
    ids=lambda p: str(p.relative_to("src/omniscribe/core")),
)
def test_core_file_does_not_import_from_api(path: Path):
    """core/* must not import from api/* — the dependency direction
    is one-way. Pre-Phase-B this caught `hybrid.py` importing
    `omniscribe.api.routers.websocket.manager` to push per-block
    WebSocket frames, which made the engine un-importable in pure-core
    contexts (tests, in-process programmatic use)."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    offenders: list[str] = []
    for node in ast.walk(tree):
        module: str | None
        if isinstance(node, ast.ImportFrom):
            module = node.module
        elif isinstance(node, ast.Import):
            # `import omniscribe.api.routers.websocket` shows up here.
            module = node.names[0].name if node.names else None
        else:
            continue
        if module and "omniscribe.api" in module:
            offenders.append(f"line {node.lineno}: {module}")
    assert not offenders, (
        f"{path} imports from omniscribe.api — core must not depend on api:\n"
        + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# 2. Behavioral: callback set is invoked for the right blocks
# ---------------------------------------------------------------------------


class _RecordingCallbacks:
    """Records every per-block and per-page call into in-memory lists.

    Plain class (not a fixture) so it lives across the test
    coroutine. We construct fresh instances per test to keep
    assertions hermetic.
    """

    def __init__(self) -> None:
        self.blocks: list[tuple[int, int, list[float], str, str, float | None]] = []
        self.pages: list[int] = []

    async def on_block(
        self,
        page_idx: int,
        block_idx: int,
        bbox: list[float],
        text: str,
        kind: str,
        confidence: float | None,
    ) -> None:
        self.blocks.append((page_idx, block_idx, bbox, text, kind, confidence))

    async def on_page_complete(self, page_idx: int) -> None:
        self.pages.append(page_idx)

    def as_callback_set(self) -> BlockCallbackSet:
        return BlockCallbackSet(
            on_block=self.on_block,
            on_page_complete=self.on_page_complete,
        )


def _build_minimal_ocr_processor_stub():
    """Build a stub OCRProcessor that yields the input boxes as text.

    Avoids loading Surya / LiteLLM in a unit test. The engine under
    test (`HybridEngine._ocr_pages`) calls `self.ocr_processor
    .perform_ocr(...)` and feeds the result to `aligner.align_text`
    or `_ocr_per_box`. We bypass all of that by constructing the
    engine with mocks; the per-block emission path doesn't depend
    on the OCR result content — only that some non-empty text lands
    in `aligned[i]`.
    """
    from unittest.mock import AsyncMock, MagicMock

    aligner = MagicMock()
    aligner.get_detected_boxes_batch = MagicMock(
        return_value=[[[0.0, 0.0, 1.0, 0.1], [0.0, 0.2, 1.0, 0.3]]]
    )
    aligner.align_text = MagicMock(
        side_effect=lambda boxes, lines: [
            (b, t) for (b, _), t in zip(boxes, lines, strict=True)
        ]
    )
    ocr_processor = MagicMock()
    ocr_processor.perform_ocr = AsyncMock(return_value=["line one", "line two"])
    ocr_processor.perform_ocr_on_crop = AsyncMock(return_value="crop text")
    pdf_handler = MagicMock()
    pdf_handler.convert_to_images = MagicMock(
        return_value={
            0: b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        }
    )
    pdf_handler.embed_structured_text = MagicMock()
    return aligner, ocr_processor, pdf_handler


async def test_hybrid_engine_invokes_per_block_callback(tmp_path):
    """The engine must call `on_block` once per non-empty block on
    each page, with a strictly monotonic `block_idx`."""
    from omniscribe.core.workflows.hybrid import HybridEngine

    aligner, ocr_processor, pdf_handler = _build_minimal_ocr_processor_stub()

    rec = _RecordingCallbacks()
    engine = HybridEngine(
        aligner=aligner,
        ocr_processor=ocr_processor,
        pdf_handler=pdf_handler,
        output_writer=lambda *args, **kwargs: None,
        block_callbacks=rec.as_callback_set(),
    )

    # Run end-to-end. The fixture OCR stub returns 2 lines, matching
    # the 2 boxes the aligner stub produces, so both blocks should
    # be emitted.
    await engine.execute(
        input_path="ignored.pdf",
        output_path=str(tmp_path / "out.pdf"),
        concurrency=1,
        refine=False,
    )

    # One page, two blocks.
    assert len(rec.blocks) == 2
    # block_idx is monotonic within the page.
    assert [b[1] for b in rec.blocks] == [0, 1]
    # The text we passed through the stub arrived intact.
    assert {b[3] for b in rec.blocks} == {"line one", "line two"}
    # One page_complete event for page 0.
    assert rec.pages == [0]


async def test_hybrid_engine_skips_callbacks_when_not_provided(tmp_path):
    """Default `block_callbacks=None` means no observer traffic.
    Pre-fix the engine imported the WS manager unconditionally,
    so even programmatic users (no WS) paid the import cost. The
    new code path is gated by `if cb.on_block is not None`."""
    from omniscribe.core.workflows.hybrid import HybridEngine

    aligner, ocr_processor, pdf_handler = _build_minimal_ocr_processor_stub()
    engine = HybridEngine(
        aligner=aligner,
        ocr_processor=ocr_processor,
        pdf_handler=pdf_handler,
        output_writer=lambda *args, **kwargs: None,
    )

    # No exceptions, no callbacks invoked. (The `as_completed` loop
    # would call into the manager if the old code path were still
    # in place; with the new design, the call is short-circuited.)
    await engine.execute(
        input_path="ignored.pdf",
        output_path=str(tmp_path / "out.pdf"),
        concurrency=1,
        refine=False,
    )
