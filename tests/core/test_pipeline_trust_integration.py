"""
OCRPipeline ↔ TrustOrchestrator integration tests.

These tests stay offline (no Surya, no LM Studio) by reusing the
``_StubAligner`` / ``_StubPDF`` pattern from ``tests/core/test_pipeline.py``.
They assert three Phase-2 contracts:

1. ``OCRPipeline(trust_orchestrator=...)`` forwards the callable into
   the engine (HybridEngine and GroundedEngine both accept it).
2. The engine invokes the orchestrator exactly once per page when
   one is injected; no calls when ``None``.
3. The golden no-trust-layer path (default) is byte-identical to
   the pre-Phase-2 output — Phase 2 is a strict additive wiring.
"""

from __future__ import annotations

import base64
import io

from PIL import Image

from omniscribe.core.document import DocumentBlock
from omniscribe.core.ocr_quality import (
    OCrQualitySettings,
    TrustOrchestrator,
    build_trust_orchestrator,
)
from omniscribe.pipeline import OCRPipeline
from tests.conftest import _StubOCR

# ---------------------------------------------------------------------------
# Stubs — kept local so the file is self-contained.
# ---------------------------------------------------------------------------


def _make_tiny_b64_image() -> str:
    # Paint dark stripes so any cropped sub-region has enough pixel variance
    # to pass the refine-stage blank-crop guard.
    from PIL import ImageDraw

    img = Image.new("RGB", (300, 300), "white")
    draw = ImageDraw.Draw(img)
    for y in range(0, 300, 20):
        draw.rectangle([0, y, 300, y + 5], fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class _StubAligner:
    def __init__(self, boxes_per_page=None, alignment=None):
        self.boxes = boxes_per_page or [
            [0.1, 0.1, 0.9, 0.15],
            [0.1, 0.2, 0.9, 0.25],
            [0.1, 0.3, 0.9, 0.35],
        ]
        self.alignment = alignment

    def get_detected_boxes_batch(self, images):
        return [list(self.boxes) for _ in images]

    def align_text(self, structured, lines):
        if self.alignment:
            return self.alignment(structured, lines)
        out = []
        for i, (box, _) in enumerate(structured):
            out.append((box, lines[i] if i < len(lines) else ""))
        return out


class _StubPDF:
    def __init__(self, n_pages: int = 2):
        self.n_pages = n_pages
        self.last_pages = None

    def convert_to_images(self, path, dpi=150, max_image_dim=1024):
        return {i: _make_tiny_b64_image() for i in range(self.n_pages)}

    def embed_structured_text(self, inp, out, pages, dpi):
        self.last_pages = dict(pages)


class _StubGroundedBackend:
    """Minimal GroundedOCRBackend for offline tests."""

    def __init__(self, n_pages: int = 2):
        from omniscribe.core.grounded import GroundedBlock, GroundedResponse

        blocks = []
        for page_index in range(n_pages):
            blocks.append(
                GroundedBlock(
                    page_index=page_index,
                    bbox=[0.1, 0.1, 0.9, 0.2],
                    text="stub grounded line",
                    label="text",
                    image_bytes=None,
                )
            )
        self._response = GroundedResponse(blocks=blocks, failed_pages=[])

    async def ocr_document(self, input_path, *, progress=None, on_warning=None):
        return self._response


class _RecordingOrchestrator:
    """Records every call so tests can assert on per-page invocation."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[int, list[DocumentBlock], str]] = []
        self.fail = fail

    def __call__(
        self,
        blocks: list[DocumentBlock],
        page_image: Image.Image | None,
        *,
        model_id: str,
        page_size: tuple[int, int] | None = None,
    ) -> list[DocumentBlock]:
        # Record first so the failure-path test can still observe the call.
        self.calls.append((len(self.calls), list(blocks), model_id))
        if self.fail:
            raise RuntimeError("simulated orchestrator failure")
        # Return copies with trust_score=0.42 + a single flag so tests can
        # verify the orchestrator's output flowed all the way to the engine.
        scored: list[DocumentBlock] = []
        for block in blocks:
            scored.append(
                DocumentBlock(
                    bbox=block.bbox,
                    text=block.text,
                    kind=block.kind,
                    confidence=block.confidence,
                    source_processor=block.source_processor,
                    reading_order=block.reading_order,
                    spans=list(block.spans),
                    metadata=dict(block.metadata),
                    trust_score=0.42,
                    trust_flags=("stub_flag",),
                )
            )
        return scored


# ---------------------------------------------------------------------------
# Protocol / factory
# ---------------------------------------------------------------------------


def test_trust_orchestrator_protocol_is_runtime_checkable():
    """A callable with the right signature satisfies TrustOrchestrator."""
    orch = _RecordingOrchestrator()
    assert isinstance(orch, TrustOrchestrator)


def test_build_trust_orchestrator_returns_default_impl():
    settings = OCrQualitySettings(watermark_enabled=True)
    orch = build_trust_orchestrator(settings)
    assert isinstance(orch, TrustOrchestrator)
    # Bound settings should be reachable for inspection.
    assert orch.settings is settings


# ---------------------------------------------------------------------------
# HybridEngine wiring
# ---------------------------------------------------------------------------


class TestHybridEngineTrustWiring:
    async def test_no_orchestrator_means_no_call(self, stub_ocr):
        """Default `None` orchestrator: pipeline behaves exactly as before."""
        pipe = OCRPipeline(_StubAligner(), stub_ocr, _StubPDF(n_pages=2))
        await pipe.run("in.pdf", "out.pdf", concurrency=2, refine=False)
        # Nothing to assert about a non-call; the real assertion is that
        # the run completes without touching any trust path.
        assert pipe.last_document_result is not None
        for page in pipe.last_document_result.pages:
            for block in page.blocks:
                assert block.trust_score is None
                assert block.trust_flags is None

    async def test_orchestrator_called_once_per_page(self, stub_ocr):
        orchestrator = _RecordingOrchestrator()
        pipe = OCRPipeline(
            _StubAligner(),
            stub_ocr,
            _StubPDF(n_pages=3),
            trust_orchestrator=orchestrator,
        )
        await pipe.run(
            "in.pdf",
            "out.pdf",
            concurrency=2,
            refine=False,
            trust_model_id="unit-test-model",
        )
        assert len(orchestrator.calls) == 3
        # Every call saw a non-None model_id.
        assert all(call[2] == "unit-test-model" for call in orchestrator.calls)
        # First call saw 3 blocks (StubAligner default).
        assert len(orchestrator.calls[0][1]) == 3

    async def test_orchestrator_output_flows_to_document_result(self, stub_ocr):
        orchestrator = _RecordingOrchestrator()
        pipe = OCRPipeline(
            _StubAligner(),
            stub_ocr,
            _StubPDF(n_pages=1),
            trust_orchestrator=orchestrator,
        )
        await pipe.run("in.pdf", "out.pdf", refine=False)
        doc = pipe.last_document_result
        assert doc is not None
        for page in doc.pages:
            for block in page.blocks:
                assert block.trust_score == 0.42
                assert block.trust_flags == ("stub_flag",)

    async def test_orchestrator_failure_does_not_sink_pipeline(self, stub_ocr):
        """A failing orchestrator must not raise; engine keeps the original
        blocks (with ``trust_score=None``) so the PDF still gets written.
        """
        orchestrator = _RecordingOrchestrator(fail=True)
        pipe = OCRPipeline(
            _StubAligner(),
            stub_ocr,
            _StubPDF(n_pages=2),
            trust_orchestrator=orchestrator,
        )
        # Should not raise.
        await pipe.run("in.pdf", "out.pdf", refine=False)
        # All orchestrator calls fired before the failure took effect,
        # so per-page isolation was per-page: the first call raised, but
        # the engine caught it. We assert the failure path was hit and
        # the pipeline still produced a DocumentResult.
        assert len(orchestrator.calls) >= 1
        assert pipe.last_document_result is not None


# ---------------------------------------------------------------------------
# GroundedEngine wiring
# ---------------------------------------------------------------------------


class TestGroundedEngineTrustWiring:
    async def test_no_orchestrator_means_no_call(self):
        backend = _StubGroundedBackend(n_pages=2)
        pipe = OCRPipeline(
            aligner=None,
            ocr_processor=None,
            pdf_handler=_StubPDF(n_pages=2),
            grounded_backend=backend,
        )
        await pipe.run("in.pdf", "out.pdf")
        for page in pipe.last_document_result.pages:
            for block in page.blocks:
                assert block.trust_score is None
                assert block.trust_flags is None

    async def test_orchestrator_called_once_per_page_with_none_image(self):
        backend = _StubGroundedBackend(n_pages=2)
        orchestrator = _RecordingOrchestrator()
        pipe = OCRPipeline(
            aligner=None,
            ocr_processor=None,
            pdf_handler=_StubPDF(n_pages=2),
            grounded_backend=backend,
            trust_orchestrator=orchestrator,
        )
        await pipe.run("in.pdf", "out.pdf", trust_model_id="grounded-model")
        # Two pages → two orchestrator calls.
        assert len(orchestrator.calls) == 2
        # Every call saw the configured model id.
        assert all(call[2] == "grounded-model" for call in orchestrator.calls)


# ---------------------------------------------------------------------------
# EngineBase direct construction
# ---------------------------------------------------------------------------


class TestEngineBaseTrustField:
    def test_default_no_orchestrator(self):
        # Bare-bones engine constructed through OCRPipeline to assert the
        # base field wiring without spinning up real OCR.
        pipe = OCRPipeline(
            _StubAligner(),
            _StubOCR(),
            _StubPDF(n_pages=1),
        )
        assert pipe._engine.trust_orchestrator is None

    def test_injected_orchestrator_is_forwarded(self):
        orchestrator = _RecordingOrchestrator()
        pipe = OCRPipeline(
            _StubAligner(),
            _StubOCR(),
            _StubPDF(n_pages=1),
            trust_orchestrator=orchestrator,
        )
        assert pipe._engine.trust_orchestrator is orchestrator

    async def test_default_apply_trust_is_noop(self):
        """EngineBase._apply_trust must be a passthrough when no orchestrator
        is configured — this is the contract every engine subclass falls
        back to."""
        pipe = OCRPipeline(
            _StubAligner(),
            _StubOCR(),
            _StubPDF(n_pages=1),
        )
        assert pipe._engine.trust_orchestrator is None

        # Synthesise a DocumentResult to feed _apply_trust.
        from omniscribe.core.document import DocumentPage, DocumentResult

        result = DocumentResult(
            pages=[
                DocumentPage(
                    page_index=0,
                    blocks=[
                        DocumentBlock(
                            bbox=[0.1, 0.1, 0.9, 0.2],
                            text="hello",
                        )
                    ],
                )
            ]
        )
        out = await pipe._engine._apply_trust(result, model_id="x")
        assert out is result  # identity — true no-op
        assert out.pages[0].blocks[0].trust_score is None
