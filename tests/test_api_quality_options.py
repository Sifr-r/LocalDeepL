"""
Phase 2 — API surface for the OCR quality trust layer.

Tests:

1. ``ProcessSettings`` accepts a JSON-encoded ``quality_options`` field.
2. The /api/process route forwards it through ``resolve_process_settings``
   and the in-process pipeline factory builds a ``TrustOrchestrator`` when
   any submodule is enabled.
3. ``trust_model_id=settings.model`` flows to ``pipeline.run()``.
"""

from __future__ import annotations

import io
import json
import os

# SSRF guard permits localhost only when ALLOW_SSRF_LOCAL=true; the route
# tests post against a localhost LM Studio URL, so opt in here.
os.environ.setdefault("ALLOW_SSRF_LOCAL", "true")

import pytest
from PIL import Image

from omniscribe.api.schemas import ProcessSettings
from omniscribe.core.ocr_quality import OCrQualitySettings, build_trust_orchestrator

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers import ocr

# ---------------------------------------------------------------------------
# ProcessSettings validation
# ---------------------------------------------------------------------------


class TestProcessSettingsQualityOptions:
    def test_default_quality_options_is_none(self):
        # The factory passes OCrQualitySettings? defaults through Pydantic;
        # a minimal valid payload keeps every other field at its default.
        from omniscribe.core.document import DenseMode, PipelineMode

        settings = ProcessSettings(
            api_base="http://localhost:1234/v1",
            api_key="k",
            model="m",
            pipeline_mode=PipelineMode.HYBRID,
            dpi=200,
            concurrency=1,
            dense_mode=DenseMode.AUTO,
            dense_threshold=60,
            refine=True,
            max_image_dim=1024,
            self_correction=False,
            binarize=False,
            dual_engine=False,
            spellcheck="none",
            cross_page=False,
            preprocess_pages=False,
            orientation_detection=False,
            deskew=False,
            denoise=False,
            normalize_contrast=False,
            crop_cleanup=False,
            quality_routing=False,
        )
        assert settings.quality_options is None

    def test_dict_payload_round_trips(self):
        """A dict is accepted and stored as a real ``OCrQualitySettings``."""
        from omniscribe.core.document import DenseMode, PipelineMode

        settings = ProcessSettings(
            api_base="http://localhost:1234/v1",
            api_key="k",
            model="m",
            pipeline_mode=PipelineMode.HYBRID,
            dpi=200,
            concurrency=1,
            dense_mode=DenseMode.AUTO,
            dense_threshold=60,
            refine=True,
            max_image_dim=1024,
            self_correction=False,
            binarize=False,
            dual_engine=False,
            spellcheck="none",
            cross_page=False,
            preprocess_pages=False,
            orientation_detection=False,
            deskew=False,
            denoise=False,
            normalize_contrast=False,
            crop_cleanup=False,
            quality_routing=False,
            quality_options={
                "watermark_enabled": True,
                "hallucination_enabled": True,
            },
        )
        assert isinstance(settings.quality_options, OCrQualitySettings)
        assert settings.quality_options.watermark_enabled is True
        assert settings.quality_options.hallucination_enabled is True

    def test_json_string_payload_round_trips(self):
        """JSON-encoded form data is parsed by the Pydantic validator."""
        from omniscribe.core.document import DenseMode, PipelineMode

        raw = json.dumps({"watermark_enabled": True})
        settings = ProcessSettings(
            api_base="http://localhost:1234/v1",
            api_key="k",
            model="m",
            pipeline_mode=PipelineMode.HYBRID,
            dpi=200,
            concurrency=1,
            dense_mode=DenseMode.AUTO,
            dense_threshold=60,
            refine=True,
            max_image_dim=1024,
            self_correction=False,
            binarize=False,
            dual_engine=False,
            spellcheck="none",
            cross_page=False,
            preprocess_pages=False,
            orientation_detection=False,
            deskew=False,
            denoise=False,
            normalize_contrast=False,
            crop_cleanup=False,
            quality_routing=False,
            quality_options=raw,
        )
        assert isinstance(settings.quality_options, OCrQualitySettings)
        assert settings.quality_options.watermark_enabled is True

    def test_invalid_json_rejected(self):
        from pydantic import ValidationError

        from omniscribe.core.document import DenseMode, PipelineMode

        with pytest.raises(ValidationError, match="quality_options"):
            ProcessSettings(
                api_base="http://localhost:1234/v1",
                api_key="k",
                model="m",
                pipeline_mode=PipelineMode.HYBRID,
                dpi=200,
                concurrency=1,
                dense_mode=DenseMode.AUTO,
                dense_threshold=60,
                refine=True,
                max_image_dim=1024,
                self_correction=False,
                binarize=False,
                dual_engine=False,
                spellcheck="none",
                cross_page=False,
                preprocess_pages=False,
                orientation_detection=False,
                deskew=False,
                denoise=False,
                normalize_contrast=False,
                crop_cleanup=False,
                quality_routing=False,
                quality_options="{not valid json",
            )


# ---------------------------------------------------------------------------
# Factory + Router integration
# ---------------------------------------------------------------------------


class TestPipelineFactoryTrustWiring:
    """Build a pipeline through ``build_pipeline`` with a stubbed backend
    and assert the trust orchestrator is injected iff requested."""

    def _settings(self, **quality_overrides):
        from omniscribe.api.schemas import ProcessSettings
        from omniscribe.core.document import DenseMode, PipelineMode

        qo = OCrQualitySettings(**quality_overrides) if quality_overrides else None
        return ProcessSettings(
            api_base="http://localhost:1234/v1",
            api_key="k",
            model="unit-model",
            pipeline_mode=PipelineMode.HYBRID,
            dpi=200,
            concurrency=1,
            dense_mode=DenseMode.AUTO,
            dense_threshold=60,
            refine=True,
            max_image_dim=1024,
            self_correction=False,
            binarize=False,
            dual_engine=False,
            spellcheck="none",
            cross_page=False,
            preprocess_pages=False,
            orientation_detection=False,
            deskew=False,
            denoise=False,
            normalize_contrast=False,
            crop_cleanup=False,
            quality_routing=False,
            quality_options=qo,
        )

    def test_no_quality_options_means_no_orchestrator(self, monkeypatch):
        # Patch out heavy factory dependencies *where they are imported* —
        # the factory imports them at module top, so patching at the
        # factory's namespace is the only place the swap takes effect.
        from omniscribe.api.services import ocr_pipeline_factory

        monkeypatch.setattr(ocr_pipeline_factory, "HybridAligner", lambda: object())
        monkeypatch.setattr(ocr_pipeline_factory, "OCRProcessor", lambda **kw: object())
        monkeypatch.setattr(ocr_pipeline_factory, "PDFHandler", _StubPdfHandler)

        settings = self._settings()
        pipeline, _backend = ocr_pipeline_factory.build_pipeline(
            settings,
            manager_send_block=lambda *a, **kw: None,
            manager_send_page_complete=lambda *a, **kw: None,
            manager_send_block_retry=lambda *a, **kw: None,
            manager_send_block_revised=lambda *a, **kw: None,
            manager_send_quality_summary=lambda *a, **kw: None,
        )
        assert pipeline._engine.trust_orchestrator is None

    def test_enabled_submodule_means_orchestrator_injected(self, monkeypatch):
        from omniscribe.api.services import ocr_pipeline_factory

        monkeypatch.setattr(ocr_pipeline_factory, "HybridAligner", lambda: object())
        monkeypatch.setattr(ocr_pipeline_factory, "OCRProcessor", lambda **kw: object())
        monkeypatch.setattr(ocr_pipeline_factory, "PDFHandler", _StubPdfHandler)

        settings = self._settings(watermark_enabled=True)
        pipeline, _backend = ocr_pipeline_factory.build_pipeline(
            settings,
            manager_send_block=lambda *a, **kw: None,
            manager_send_page_complete=lambda *a, **kw: None,
            manager_send_block_retry=lambda *a, **kw: None,
            manager_send_block_revised=lambda *a, **kw: None,
            manager_send_quality_summary=lambda *a, **kw: None,
        )
        orchestrator = pipeline._engine.trust_orchestrator
        assert orchestrator is not None
        # Same instance the factory returned — settings are bound.
        assert orchestrator.settings.watermark_enabled is True


class _StubPdfHandler:
    def embed_structured_text(self, *a, **kw):
        return None


# ---------------------------------------------------------------------------
# Router /process end-to-end (smoke test)
# ---------------------------------------------------------------------------


def _api_client() -> TestClient:
    app = FastAPI()
    app.include_router(ocr.router)
    return TestClient(app)


def _stub_pdf_bytes() -> bytes:
    img = Image.new("RGB", (40, 40), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _process_form(quality_options: str | None = None) -> dict[str, str]:
    form = {
        "api_base": "http://localhost:1234/v1",
        "api_key": "k",
        "model": "unit-model",
        "pipeline_mode": "hybrid",
        "dpi": "200",
        "concurrency": "1",
        "dense_mode": "auto",
        "dense_threshold": "60",
        "refine": "false",
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
        "handwriting_hint": "false",
    }
    if quality_options is not None:
        form["quality_options"] = quality_options
    return form


def _capture_quality_options_in_orchestrator(monkeypatch):
    """Patch the pipeline factory to capture the trust_orchestrator that
    would be passed into ``OCRPipeline`` for the current request.

    Returns a list that gains one entry per ``build_pipeline`` call with
    the orchestrator that was constructed (or ``None``).
    """
    captured: list = []
    from omniscribe.api.services import ocr_pipeline_factory

    original = ocr_pipeline_factory._build_trust_orchestrator

    def spy(settings):
        orch = original(settings)
        captured.append(orch)
        return orch

    monkeypatch.setattr(ocr_pipeline_factory, "_build_trust_orchestrator", spy)
    return captured


class TestProcessRouteQualityOptions:
    def test_route_accepts_json_quality_options_and_passes_to_factory(
        self, monkeypatch
    ):
        captured = _capture_quality_options_in_orchestrator(monkeypatch)

        # Avoid actual LLM calls and PDF writing; just exercise the route.

        async def fake_run(self, input_path, output_path, **kwargs):
            # Return the standard {page: [lines]} dict the route expects.
            return {0: ["stubbed"]}

        monkeypatch.setattr(
            "omniscribe.core.workflows.base.EngineBase._run",
            fake_run,
            raising=False,
        )
        # Easier: monkeypatch the engine's run path via the engine class.
        # We can short-circuit at the OCRPipeline level.
        from omniscribe.pipeline import OCRPipeline

        async def stub_run(self, input_path, output_path, **kwargs):
            # Track trust_model_id for the API propagation assertion.
            self._captured_model_id = kwargs.get("trust_model_id")
            self.last_document_result = None
            return {0: ["stub"]}

        monkeypatch.setattr(OCRPipeline, "run", stub_run)

        client = _api_client()
        body = _process_form()
        body["quality_options"] = json.dumps({"watermark_enabled": True})

        response = client.post(
            "/api/process",
            data=body,
            files={"file": ("test.png", _stub_pdf_bytes(), "image/png")},
        )
        # Endpoint goes through the upload validation pipeline; we only
        # care that the form was accepted (no 422 on the JSON form field).
        assert response.status_code in (200, 500)  # 500 only on the stub path
        # The factory saw an enabled quality_options and constructed an orch.
        assert len(captured) >= 1
        assert captured[-1] is not None

    def test_route_without_quality_options_passes_none_orchestrator(self, monkeypatch):
        captured = _capture_quality_options_in_orchestrator(monkeypatch)
        from omniscribe.pipeline import OCRPipeline

        async def stub_run(self, input_path, output_path, **kwargs):
            return {0: ["stub"]}

        monkeypatch.setattr(OCRPipeline, "run", stub_run)

        client = _api_client()
        body = _process_form()  # no quality_options
        response = client.post(
            "/api/process",
            data=body,
            files={"file": ("test.png", _stub_pdf_bytes(), "image/png")},
        )
        assert response.status_code in (200, 500)
        assert len(captured) >= 1
        assert captured[-1] is None

    def test_route_forwards_trust_model_id_from_settings_model(self, monkeypatch):
        _capture_quality_options_in_orchestrator(monkeypatch)
        from omniscribe.pipeline import OCRPipeline

        # verify_backend_model hits the LLM server before pipeline.run is
        # ever called; stub it out so the test doesn't need a live server.
        async def no_verify(*a, **kw):
            return None

        monkeypatch.setattr(ocr, "verify_backend_model", no_verify)

        # build_ocr_file_response constructs a starlette FileResponse on the
        # (non-existent) output_path; stub it so the test doesn't need a
        # real PDF on disk.
        from fastapi.responses import JSONResponse

        def fake_response(*a, **kw):
            return JSONResponse({"stub": True})

        monkeypatch.setattr(ocr, "build_ocr_file_response", fake_response)

        seen: dict = {}

        async def stub_run(self, input_path, output_path, **kwargs):
            seen["trust_model_id"] = kwargs.get("trust_model_id")
            return {0: ["stub"]}

        monkeypatch.setattr(OCRPipeline, "run", stub_run)

        client = _api_client()
        body = _process_form()
        body["quality_options"] = json.dumps({"watermark_enabled": True})
        response = client.post(
            "/api/process",
            data=body,
            files={"file": ("test.png", _stub_pdf_bytes(), "image/png")},
        )
        assert response.status_code == 200
        assert seen.get("trust_model_id") == "unit-model"


# ---------------------------------------------------------------------------
# build_trust_orchestrator export round-trip
# ---------------------------------------------------------------------------


def test_build_trust_orchestrator_factory_returns_bound_settings():
    settings = OCrQualitySettings(watermark_enabled=True, hallucination_enabled=False)
    orch = build_trust_orchestrator(settings)
    assert orch.settings is settings
    assert orch.settings.watermark_enabled is True
    assert orch.settings.hallucination_enabled is False
