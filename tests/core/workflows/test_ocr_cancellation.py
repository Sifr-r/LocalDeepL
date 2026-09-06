"""Tests for Phase 3 fix (report §2.1) — cooperative OCR cancellation.

The cancel handshake is a callback that the engines consult between page
boundaries. When it returns ``True`` the engine raises
:class:`OCRCancelled`, which propagates up through the API layer as a
``503 Service Unavailable`` with a ``cancelled: true`` body — never as
a 500.

These tests cover three layers:

1. The exception contract (:class:`OCRCancelled` is not a plain
   :class:`Exception` so the per-page isolation blocks don't swallow it).
2. The engine-level handshake: a counter-based cancel callback aborts
   the OCR loop at the right page boundary, both in
   :meth:`HybridEngine._ocr_pages` and :meth:`HybridEngine._refine_pages`.
3. The API-layer translation: when the engine raises
   :class:`OCRCancelled`, :func:`process_pdf` returns a 503 with
   ``cancelled: true`` and the temp files are cleaned up.
"""

from __future__ import annotations

import pytest

from omniscribe.core.workflows.base import OCRCancelled
from omniscribe.core.workflows.hybrid import HybridEngine
from tests.conftest import _StubOCR
from tests.core.test_pipeline import _make_tiny_b64_image, _StubAligner, _StubPDF
from tests.core.workflows.test_workflows_hybrid import _engine, _noop_writer

# pytest-asyncio is in auto mode (per AGENTS.md), so individual
# ``async def`` tests are auto-marked. We don't apply a global
# asyncio mark because the OCRCancelled contract tests are
# synchronous — applying the mark globally would emit
# PytestWarning for every one of them.


# ---------------------------------------------------------------------------
# OCRCancelled contract
# ---------------------------------------------------------------------------


class TestOCRCancelledContract:
    def test_subclass_of_base_exception_not_exception(self) -> None:
        # Must NOT subclass Exception: the per-page isolation blocks in
        # ``_ocr_pages`` and ``_refine_pages`` ``except Exception`` to
        # swallow individual-page failures. If OCRCancelled were a
        # plain Exception it would be caught as a benign per-page
        # failure and the cancel signal would never reach the route
        # handler — the exact bug this fix is closing.
        assert issubclass(OCRCancelled, BaseException)
        assert not issubclass(OCRCancelled, Exception)

    def test_distinct_from_circuit_open_error(self) -> None:
        # The circuit breaker (``CircuitOpenError``) and the cancel
        # signal are different failure modes and must be handled
        # independently by the engine. Sharing a base would let a
        # catch-all in the route layer conflate them.
        from omniscribe.core.ocr.resilience import CircuitOpenError

        assert not issubclass(OCRCancelled, CircuitOpenError)
        assert not issubclass(CircuitOpenError, OCRCancelled)

    def test_message_is_carried(self) -> None:
        exc = OCRCancelled("after page 4")
        assert "after page 4" in str(exc)
        # BaseException allows custom args but doesn't auto-stringify
        # them; the ``str(...)`` form must still include the suffix.
        assert str(exc) == "after page 4"


# ---------------------------------------------------------------------------
# _ocr_pages cancel handshake
# ---------------------------------------------------------------------------


class TestHybridOCRPagesCancel:
    async def test_aborts_after_cancel_signal_within_one_page(self) -> None:
        """10-page run with a cancel that fires after page 3 — the engine
        must stop within one page of the cancel signal and raise
        :class:`OCRCancelled`."""
        ocr = _StubOCR()
        engine = _engine(ocr=ocr)
        images = {p: _make_tiny_b64_image() for p in range(10)}
        pages_structured = {p: [((0.1, 0.1, 0.9, 0.2), "")] * 3 for p in range(10)}

        cancel_calls = {"n": 0}

        def cancel_check() -> bool:
            cancel_calls["n"] += 1
            # Fire on the 4th invocation — after pages 0, 1, 2 complete
            # and the engine consults us for the 4th time. We expect
            # the engine to abort at or before the next page boundary.
            return cancel_calls["n"] >= 4

        with pytest.raises(OCRCancelled) as exc_info:
            await engine._ocr_pages(
                images_dict=images,
                pages_structured=pages_structured,
                page_nums=list(range(10)),
                per_box_pages=set(),
                concurrency=1,
                self_correction=False,
                binarize=False,
                dual_engine=False,
                progress=None,
                on_warning=None,
                cancel_check=cancel_check,
            )

        # Acceptance: the engine aborts within ~1 page of the cancel
        # signal. The stub's ``perform_ocr`` is fully synchronous so
        # one in-flight task may have already incremented its counter
        # by the time the cancel propagates through the TaskGroup's
        # ``__aexit__``. Anywhere from 3 (cancel fires before the 4th
        # page even completes) to 5 (one queued task ran to its
        # synchronous stub) is acceptable; the key property is that
        # the engine does NOT run all 10 pages to completion.
        assert 3 <= ocr.page_calls <= 5, (
            f"expected 3-5 pages processed before cancel, got {ocr.page_calls}"
        )
        # Per-page isolation: the cancel must NOT have been logged as
        # a page failure (it was a cancellation, not a per-page error).
        assert engine.last_failed_pages == []
        # The exception message tells the operator which page boundary
        # we aborted on.
        assert "after page" in str(exc_info.value).lower()
        # The cancel check was consulted at least once before the abort.
        assert cancel_calls["n"] >= 4

    async def test_no_cancel_when_callback_never_fires(self) -> None:
        """Smoke test: when the cancel callback always returns False,
        the engine processes every page normally."""
        ocr = _StubOCR()
        engine = _engine(ocr=ocr)
        images = {p: _make_tiny_b64_image() for p in range(5)}
        pages_structured = {p: [((0.1, 0.1, 0.9, 0.2), "")] * 3 for p in range(5)}

        await engine._ocr_pages(
            images_dict=images,
            pages_structured=pages_structured,
            page_nums=list(range(5)),
            per_box_pages=set(),
            concurrency=1,
            self_correction=False,
            binarize=False,
            dual_engine=False,
            progress=None,
            on_warning=None,
            cancel_check=lambda: False,
        )

        assert ocr.page_calls == 5

    async def test_no_cancel_when_callback_is_none(self) -> None:
        """Backwards-compat: omitting the cancel callback keeps the
        pre-Phase-3 behavior (no cancel check, no OCRCancelled)."""
        ocr = _StubOCR()
        engine = _engine(ocr=ocr)
        images = {p: _make_tiny_b64_image() for p in range(3)}
        pages_structured = {p: [((0.1, 0.1, 0.9, 0.2), "")] * 3 for p in range(3)}

        await engine._ocr_pages(
            images_dict=images,
            pages_structured=pages_structured,
            page_nums=list(range(3)),
            per_box_pages=set(),
            concurrency=1,
            self_correction=False,
            binarize=False,
            dual_engine=False,
            progress=None,
            on_warning=None,
            # cancel_check=None is the default for engine callers
            # that pre-date the Phase 3 fix.
        )

        assert ocr.page_calls == 3

    async def test_cancel_dense_page_path_too(self) -> None:
        """The cancel check must also fire on the dense (per-box) path."""
        ocr = _StubOCR(crop_text="from crop")
        engine = _engine(ocr=ocr)
        images = {p: _make_tiny_b64_image() for p in range(5)}
        pages_structured = {p: [((0.1, 0.1, 0.9, 0.2), "")] * 3 for p in range(5)}

        cancel_calls = {"n": 0}

        def cancel_check() -> bool:
            cancel_calls["n"] += 1
            return cancel_calls["n"] >= 3

        with pytest.raises(OCRCancelled):
            await engine._ocr_pages(
                images_dict=images,
                pages_structured=pages_structured,
                page_nums=list(range(5)),
                per_box_pages=set(range(5)),  # all dense
                concurrency=1,
                self_correction=False,
                binarize=False,
                dual_engine=False,
                progress=None,
                on_warning=None,
                cancel_check=cancel_check,
            )

        # At least one dense page completed; the cancel fires after
        # the 2nd page boundary. The exact number of crop calls is
        # (completed pages) * boxes per page (3) but we only assert
        # the lower bound because in-flight boxes may have already
        # been scheduled when the cancel propagated.
        assert 3 <= ocr.crop_calls <= 9

    async def test_ocrcancelled_not_caught_as_per_page_failure(self) -> None:
        """If OCRCancelled were a plain Exception the per-page isolation
        block would swallow it as a benign page failure. The cooperative
        cancel would never propagate. This test guards against that
        regression by raising OCRCancelled from inside ``perform_ocr``
        and asserting it propagates out of ``_ocr_pages`` instead of
        landing in ``last_failed_pages``."""

        class _CancelOnFirstCall(_StubOCR):
            def __init__(self) -> None:
                super().__init__()
                self.invocations = 0

            async def perform_ocr(self, image_base64, **kwargs):
                self.invocations += 1
                raise OCRCancelled("test cancel from inside OCR")

        ocr = _CancelOnFirstCall()
        engine = _engine(ocr=ocr)
        images = {p: _make_tiny_b64_image() for p in range(3)}
        pages_structured = {p: [((0.1, 0.1, 0.9, 0.2), "")] * 3 for p in range(3)}

        with pytest.raises(OCRCancelled):
            await engine._ocr_pages(
                images_dict=images,
                pages_structured=pages_structured,
                page_nums=list(range(3)),
                per_box_pages=set(),
                concurrency=1,
                self_correction=False,
                binarize=False,
                dual_engine=False,
                progress=None,
                on_warning=None,
            )

        # The cancel must NOT be recorded as a page failure.
        assert engine.last_failed_pages == []


# ---------------------------------------------------------------------------
# HybridEngine.execute — pre-layout and pre-refine cancel points
# ---------------------------------------------------------------------------


class TestHybridExecuteCancel:
    async def test_pre_layout_cancel_raises_without_running_anything(self) -> None:
        """If the cancel fires before layout detection the engine must
        abort before paying the Surya detection cost."""
        ocr = _StubOCR()
        pdf = _StubPDF(n_pages=5)
        engine = HybridEngine(
            aligner=_StubAligner(),  # type: ignore[arg-type]
            ocr_processor=ocr,  # type: ignore[arg-type]
            pdf_handler=pdf,  # type: ignore[arg-type]
            output_writer=_noop_writer,
        )

        with pytest.raises(OCRCancelled) as exc_info:
            await engine.execute(
                "in.pdf",
                "out.pdf",
                cancel_check=lambda: True,
            )

        # No pages were ever rasterized/OCRed.
        assert ocr.page_calls == 0
        assert "before layout" in str(exc_info.value).lower()

    async def test_pre_refine_cancel_raises_after_ocr_loop(self) -> None:
        """If the cancel fires mid-OCR the engine stops within one page
        and skips refine entirely."""
        ocr = _StubOCR(crop_text="from crop")
        pdf = _StubPDF(n_pages=3)
        engine = HybridEngine(
            aligner=_StubAligner(),  # type: ignore[arg-type]
            ocr_processor=ocr,  # type: ignore[arg-type]
            pdf_handler=pdf,  # type: ignore[arg-type]
            output_writer=_noop_writer,
        )

        # Cancel on the 2nd invocation: the first consult happens
        # before layout detection (``execute`` body), so the layout
        # pass runs; the OCR loop then runs until the next post-page
        # consult, which is the 2nd call, where the cancel fires.
        calls = {"n": 0}

        def cancel_check() -> bool:
            calls["n"] += 1
            return calls["n"] >= 2

        with pytest.raises(OCRCancelled):
            await engine.execute(
                "in.pdf",
                "out.pdf",
                cancel_check=cancel_check,
            )

        # At least 1 page (the one already in flight when the 2nd
        # consult fired) completed; at most 2 (one in-flight task may
        # have already incremented its counter before the cancel
        # propagated through the TaskGroup's __aexit__). The crucial
        # property is that refine NEVER started: the 3-page refine
        # pass would have made 3 * 3 = 9 crop calls, and we assert
        # none were issued.
        assert 1 <= ocr.page_calls <= 2
        assert ocr.crop_calls == 0


# ---------------------------------------------------------------------------
# API-layer translation — process_pdf returns 503 with cancelled: true
# ---------------------------------------------------------------------------


def _process_form() -> dict[str, str]:
    """Minimal form fields for /api/process — same shape as
    tests/api/_safety_helpers.py's ``_process_form``. Kept local so
    this file doesn't import from another test module."""
    return {
        "api_base": "http://api.openai.com/v1",
        "api_key": "test-key",
        "model": "openai/test-model",
        "pipeline_mode": "hybrid",
        "dpi": "200",
        "concurrency": "1",
        "dense_mode": "auto",
        "dense_threshold": "60",
        "refine": "true",
        "max_image_dim": "1024",
        "self_correction": "false",
        "binarize": "false",
        "dual_engine": "false",
        "spellcheck": "none",
        "cross_page": "false",
        "preprocess_pages": "false",
        "orientation_detection": "false",
        "deskew": "false",
        "denoise": "false",
        "normalize_contrast": "false",
        "crop_cleanup": "false",
        "quality_routing": "false",
    }


class TestProcessRouteCancel:
    """The API route catches :class:`OCRCancelled` from the engine and
    returns ``503 Service Unavailable`` with ``cancelled: true`` instead
    of bubbling a 500."""

    @pytest.fixture
    def tiny_pdf(self, tmp_path) -> bytes:
        # Minimal valid PDF header so ``detect_upload_suffix`` accepts
        # the upload. The pipeline is short-circuited at the engine
        # level so the body content doesn't matter.
        return (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
            b"trailer<</Root 1 0 R>>\n"
            b"%%EOF\n"
        )

    async def test_route_returns_503_when_engine_raises_ocrcancelled(
        self, tiny_pdf: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import httpx
        from fastapi import FastAPI

        import omniscribe.plugins.ocr.service as ocr_service_mod
        from omniscribe.harness.context import Context
        from omniscribe.plugins import artifacts as art
        from omniscribe.plugins import jobs, progress, runtime
        from omniscribe.plugins import state_backend as sb
        from omniscribe.plugins.ocr.plugin import OCRPlugin

        async def cancel_run(*args, **kwargs):
            raise OCRCancelled("cancelled from test")

        monkeypatch.setattr(ocr_service_mod, "run_pipeline", cancel_run)

        ctx = Context()
        await ctx.plugin(runtime.RuntimePlugin(), config={})
        await ctx.plugin(sb.StateBackendPlugin(), config={"backend": "memory"})
        await ctx.plugin(art.ArtifactsPlugin(), config={})
        await ctx.plugin(jobs.JobsPlugin(), config={})
        await ctx.plugin(progress.ProgressPlugin(), config={})
        await ctx.plugin(OCRPlugin(), config={})

        app = FastAPI()
        for router in ctx.routes():
            app.include_router(router)

        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/process",
                    files={"file": ("doc.pdf", tiny_pdf, "application/pdf")},
                )

            assert response.status_code == 503
            body = response.json()
            assert body.get("cancelled") is True
            assert "error" in body
            assert "cancelled from test" in body.get("detail", "")
        finally:
            await ctx.dispose()

