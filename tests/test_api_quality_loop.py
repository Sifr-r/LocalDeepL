"""P1 — API surface for the quality repair loop (spec §3.1/§3.2/§8).

Tests:

1. ``ProcessSettings`` exposes the three quality-loop knobs with the
   spec defaults and lax string coercion (form fields arrive as strings).
2. ``resolve_process_settings`` merges form overrides into a
   ``RepairOptions``-shaped triple.
3. The runtime config store seeds the three keys from the environment.
4. ``POST /api/process`` builds a ``RepairOptions`` from the resolved
   settings and passes it to ``pipeline.run`` as ``repair_options``.
5. ``build_block_callbacks`` wires the three repair callbacks to the
   WebSocket manager senders.
"""

from __future__ import annotations

import importlib
import io
import os

# SSRF guard permits localhost only when ALLOW_SSRF_LOCAL=true; the route
# tests post against a localhost LM Studio URL, so opt in here.
os.environ.setdefault("ALLOW_SSRF_LOCAL", "true")

import pytest
from PIL import Image
from pydantic import ValidationError

from omniscribe.api.routers import ocr
from omniscribe.api.schemas import ProcessSettings
from omniscribe.api.services.ocr import execution as ocr_execution
from omniscribe.core.workflows.repair import RepairOptions

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Shared form helpers (same shape as tests/test_api_quality_options.py)
# ---------------------------------------------------------------------------


def _base_form() -> dict:
    """Minimal ProcessSettings payload; every new field has a schema default."""
    return {
        "api_base": "http://localhost:1234/v1",
        "api_key": "k",
        "model": "unit-model",
        "pipeline_mode": "hybrid",
        "dpi": 200,
        "concurrency": 1,
        "dense_mode": "auto",
        "dense_threshold": 60,
        "refine": False,
        "max_image_dim": 1024,
        "self_correction": False,
        "binarize": False,
        "dual_engine": False,
        "spellcheck": "none",
        "cross_page": False,
        "preprocess_pages": False,
        "orientation_detection": False,
        "deskew": False,
        "denoise": False,
        "normalize_contrast": False,
        "crop_cleanup": False,
        "quality_routing": False,
    }


def _process_form(**extra: str) -> dict[str, str]:
    """Form fields for POST /api/process; values are strings like a real upload."""
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
    form.update(extra)
    return form


def _stub_png_bytes() -> bytes:
    img = Image.new("RGB", (40, 40), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _api_client() -> TestClient:
    app = FastAPI()
    app.include_router(ocr.router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# ProcessSettings fields
# ---------------------------------------------------------------------------


class TestProcessSettingsQualityLoop:
    def test_defaults_match_spec(self) -> None:
        settings = ProcessSettings.model_validate(_base_form())
        assert settings.quality_loop_enabled is True
        assert settings.quality_target == pytest.approx(0.98)
        assert settings.quality_max_retries == 2

    def test_form_style_strings_coerce(self) -> None:
        payload = _base_form()
        payload.update(
            quality_loop_enabled="false",
            quality_target="0.9",
            quality_max_retries="1",
        )
        settings = ProcessSettings.model_validate(payload)
        assert settings.quality_loop_enabled is False
        assert settings.quality_target == pytest.approx(0.9)
        assert settings.quality_max_retries == 1

    def test_target_bounds_enforced(self) -> None:
        payload = _base_form()
        payload["quality_target"] = "1.5"
        with pytest.raises(ValidationError):
            ProcessSettings.model_validate(payload)

    def test_max_retries_bounds_enforced(self) -> None:
        payload = _base_form()
        payload["quality_max_retries"] = "6"
        with pytest.raises(ValidationError):
            ProcessSettings.model_validate(payload)


class TestResolveQualityLoopSettings:
    def test_form_params_reach_settings(self) -> None:
        from omniscribe.api.services.ocr.settings import resolve_process_settings

        # The required ProcessSettings fields (api_base, pipeline_mode, ...)
        # have no schema defaults, so the base form supplies them; the
        # three quality-loop overrides are the fields under test.
        settings = resolve_process_settings(
            settings_store={},
            pages=None,
            **_base_form(),
            quality_loop_enabled="false",
            quality_target="0.95",
            quality_max_retries="3",
        )
        assert settings.quality_loop_enabled is False
        assert settings.quality_target == pytest.approx(0.95)
        assert settings.quality_max_retries == 3

    def test_config_store_fallback(self) -> None:
        from omniscribe.api.services.ocr.settings import resolve_process_settings

        settings = resolve_process_settings(
            settings_store={
                **_base_form(),
                "quality_loop_enabled": False,
                "quality_target": 0.9,
                "quality_max_retries": 1,
            },
            pages=None,
        )
        assert settings.quality_loop_enabled is False
        assert settings.quality_target == pytest.approx(0.9)
        assert settings.quality_max_retries == 1


# ---------------------------------------------------------------------------
# Runtime config seeds (spec §8)
# ---------------------------------------------------------------------------


class TestConfigEnvSeeds:
    def test_defaults_when_env_unset(self, monkeypatch) -> None:
        monkeypatch.delenv("OMNISCRIBE_QUALITY_LOOP", raising=False)
        monkeypatch.delenv("OMNISCRIBE_QUALITY_TARGET", raising=False)
        monkeypatch.delenv("OMNISCRIBE_QUALITY_MAX_RETRIES", raising=False)
        from omniscribe.api.routers import config as config_mod

        # Capture the shared dict BEFORE reload: importlib.reload rebinds
        # ``config_mod._config`` to a new object, and restoring the module
        # attribute in ``finally`` keeps identity with every ``from``
        # importer (e.g. ``ocr._config``) intact for the rest of the run.
        orig = config_mod._config
        importlib.reload(config_mod)
        try:
            assert config_mod._config["quality_loop_enabled"] is True
            assert config_mod._config["quality_target"] == pytest.approx(0.98)
            assert config_mod._config["quality_max_retries"] == 2
        finally:
            config_mod._config = orig

    def test_env_overrides(self, monkeypatch) -> None:
        monkeypatch.setenv("OMNISCRIBE_QUALITY_LOOP", "false")
        monkeypatch.setenv("OMNISCRIBE_QUALITY_TARGET", "0.9")
        monkeypatch.setenv("OMNISCRIBE_QUALITY_MAX_RETRIES", "4")
        from omniscribe.api.routers import config as config_mod

        orig = config_mod._config  # see test_defaults_when_env_unset
        importlib.reload(config_mod)
        try:
            assert config_mod._config["quality_loop_enabled"] is False
            assert config_mod._config["quality_target"] == pytest.approx(0.9)
            assert config_mod._config["quality_max_retries"] == 4
        finally:
            monkeypatch.delenv("OMNISCRIBE_QUALITY_LOOP", raising=False)
            monkeypatch.delenv("OMNISCRIBE_QUALITY_TARGET", raising=False)
            monkeypatch.delenv("OMNISCRIBE_QUALITY_MAX_RETRIES", raising=False)
            config_mod._config = orig


class TestConfigEnvSeedBounds:
    """Out-of-range env values must fall back to the spec defaults.

    The seeded store always wins over the Pydantic schema defaults for
    omitted form fields, so an unchecked out-of-range seed would make
    every plain ``/api/process`` request fail validation with 422.
    """

    def _seeded(self, monkeypatch, **env: str) -> dict:
        from omniscribe.api.routers import config as config_mod

        for key in (
            "OMNISCRIBE_QUALITY_LOOP",
            "OMNISCRIBE_QUALITY_TARGET",
            "OMNISCRIBE_QUALITY_MAX_RETRIES",
        ):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        orig = config_mod._config  # see TestConfigEnvSeeds
        importlib.reload(config_mod)
        try:
            return dict(config_mod._config)
        finally:
            config_mod._config = orig

    def test_target_above_range_falls_back_to_default(self, monkeypatch) -> None:
        seeded = self._seeded(monkeypatch, OMNISCRIBE_QUALITY_TARGET="1.5")
        assert seeded["quality_target"] == pytest.approx(0.98)

    def test_target_below_range_falls_back_to_default(self, monkeypatch) -> None:
        seeded = self._seeded(monkeypatch, OMNISCRIBE_QUALITY_TARGET="0.2")
        assert seeded["quality_target"] == pytest.approx(0.98)

    def test_non_finite_target_falls_back_to_default(self, monkeypatch) -> None:
        seeded = self._seeded(monkeypatch, OMNISCRIBE_QUALITY_TARGET="nan")
        assert seeded["quality_target"] == pytest.approx(0.98)

    def test_max_retries_above_range_falls_back_to_default(self, monkeypatch) -> None:
        seeded = self._seeded(monkeypatch, OMNISCRIBE_QUALITY_MAX_RETRIES="9")
        assert seeded["quality_max_retries"] == 2

    def test_negative_max_retries_falls_back_to_default(self, monkeypatch) -> None:
        seeded = self._seeded(monkeypatch, OMNISCRIBE_QUALITY_MAX_RETRIES="-1")
        assert seeded["quality_max_retries"] == 2

    def test_in_range_env_values_still_apply(self, monkeypatch) -> None:
        seeded = self._seeded(
            monkeypatch,
            OMNISCRIBE_QUALITY_TARGET="0.5",
            OMNISCRIBE_QUALITY_MAX_RETRIES="5",
        )
        assert seeded["quality_target"] == pytest.approx(0.5)
        assert seeded["quality_max_retries"] == 5


# ---------------------------------------------------------------------------
# Route wiring: form fields -> RepairOptions -> pipeline.run
# ---------------------------------------------------------------------------


class TestProcessRouteRepairOptions:
    def _stub_route(self, monkeypatch) -> None:
        """Replace every step after settings resolution with stubs."""

        async def no_verify(*a, **kw) -> None:
            return None

        monkeypatch.setattr(ocr_execution, "verify_backend_model", no_verify)

        from fastapi.responses import JSONResponse

        def fake_response(*a, **kw):
            return JSONResponse({"stub": True})

        monkeypatch.setattr(ocr, "build_ocr_file_response", fake_response)

    def test_form_fields_build_repair_options(self, monkeypatch) -> None:
        self._stub_route(monkeypatch)
        from omniscribe.pipeline import OCRPipeline

        seen: dict = {}

        async def stub_run(self, input_path, output_path, **kwargs):
            seen["repair_options"] = kwargs.get("repair_options")
            return {0: ["stub"]}

        monkeypatch.setattr(OCRPipeline, "run", stub_run)

        client = _api_client()
        body = _process_form(
            quality_loop_enabled="true",
            quality_target="0.9",
            quality_max_retries="3",
        )
        response = client.post(
            "/api/process",
            data=body,
            files={"file": ("test.png", _stub_png_bytes(), "image/png")},
        )
        assert response.status_code == 200
        opts = seen["repair_options"]
        assert isinstance(opts, RepairOptions)
        assert opts.enabled is True
        assert opts.target == pytest.approx(0.9)
        assert opts.max_retries == 3

    def test_omitted_fields_use_api_defaults(self, monkeypatch) -> None:
        self._stub_route(monkeypatch)
        from omniscribe.pipeline import OCRPipeline

        # The runtime config store is always seeded with the three keys,
        # so drop them for this test: omitted form fields must fall
        # through the store to the ProcessSettings schema defaults —
        # the true API-level defaults (env-independent).
        for key in ("quality_loop_enabled", "quality_target", "quality_max_retries"):
            monkeypatch.delitem(ocr._config, key, raising=False)

        seen: dict = {}

        async def stub_run(self, input_path, output_path, **kwargs):
            seen["repair_options"] = kwargs.get("repair_options")
            return {0: ["stub"]}

        monkeypatch.setattr(OCRPipeline, "run", stub_run)

        client = _api_client()
        response = client.post(
            "/api/process",
            data=_process_form(),  # no quality_* fields
            files={"file": ("test.png", _stub_png_bytes(), "image/png")},
        )
        assert response.status_code == 200
        opts = seen["repair_options"]
        assert isinstance(opts, RepairOptions)
        # API-level default is ON with the spec's 0.98 / 2 bounds.
        assert opts.enabled is True
        assert opts.target == pytest.approx(0.98)
        assert opts.max_retries == 2

    def test_disabled_toggle_passes_disabled_options(self, monkeypatch) -> None:
        self._stub_route(monkeypatch)
        from omniscribe.pipeline import OCRPipeline

        seen: dict = {}

        async def stub_run(self, input_path, output_path, **kwargs):
            seen["repair_options"] = kwargs.get("repair_options")
            return {0: ["stub"]}

        monkeypatch.setattr(OCRPipeline, "run", stub_run)

        client = _api_client()
        body = _process_form(quality_loop_enabled="false")
        response = client.post(
            "/api/process",
            data=body,
            files={"file": ("test.png", _stub_png_bytes(), "image/png")},
        )
        assert response.status_code == 200
        assert seen["repair_options"].enabled is False

    def test_out_of_bounds_target_is_rejected_with_422(self, monkeypatch) -> None:
        # HTTP-level counterpart of ``test_target_bounds_enforced``: the
        # route maps the Pydantic ValidationError from settings
        # resolution to a stable 422 envelope before any pipeline work.
        self._stub_route(monkeypatch)

        client = _api_client()
        response = client.post(
            "/api/process",
            data=_process_form(quality_target="1.5"),
            files={"file": ("test.png", _stub_png_bytes(), "image/png")},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Factory callback wiring: repair callbacks -> manager senders
# ---------------------------------------------------------------------------


class TestFactoryRepairCallbackWiring:
    def _senders(self) -> tuple[dict, dict]:
        calls: dict[str, list] = {"retry": [], "revised": [], "summary": []}
        senders: dict = {}

        async def send_retry(
            channel, *, page_idx, block_idx, attempt, confidence, target
        ):
            calls["retry"].append((channel, page_idx, block_idx, attempt))

        async def send_revised(
            channel, *, page_idx, block_idx, attempt, bbox, text, kind, confidence
        ):
            calls["revised"].append((channel, page_idx, block_idx, text))

        async def send_summary(
            channel,
            *,
            scope,
            target,
            avg_confidence,
            repaired_count,
            below_target_count,
            page_idx=None,
        ):
            calls["summary"].append((channel, scope, page_idx))

        senders["manager_send_block_retry"] = send_retry
        senders["manager_send_block_revised"] = send_revised
        senders["manager_send_quality_summary"] = send_summary
        return calls, senders

    async def test_bound_channel_forwards_repair_frames(self) -> None:
        from omniscribe.api.services.ocr.pipeline_factory import build_block_callbacks

        async def noop_block(*a, **kw) -> None:
            return None

        async def noop_page(*a, **kw) -> None:
            return None

        calls, senders = self._senders()
        cb = build_block_callbacks(
            progress_target="chan-1",
            manager_send_block=noop_block,
            manager_send_page_complete=noop_page,
            **senders,
        )
        assert cb.on_block_retry is not None
        assert cb.on_block_revised is not None
        assert cb.on_quality_summary is not None

        await cb.on_block_retry(0, 2, 1, 0.5, 0.98)
        await cb.on_block_revised(
            0, 2, 1, [0.1, 0.1, 0.2, 0.2], "new text", "text", 0.99
        )
        await cb.on_quality_summary("page", 0, 0.98, 0.97, 1, 0)

        assert calls["retry"] == [("chan-1", 0, 2, 1)]
        assert calls["revised"] == [("chan-1", 0, 2, "new text")]
        assert calls["summary"] == [("chan-1", "page", 0)]

    async def test_no_channel_is_a_noop(self) -> None:
        from omniscribe.api.services.ocr.pipeline_factory import build_block_callbacks

        async def noop_block(*a, **kw) -> None:
            return None

        async def noop_page(*a, **kw) -> None:
            return None

        calls, senders = self._senders()
        cb = build_block_callbacks(
            progress_target=None,
            manager_send_block=noop_block,
            manager_send_page_complete=noop_page,
            **senders,
        )
        await cb.on_block_retry(0, 0, 1, 0.5, 0.98)
        await cb.on_block_revised(0, 0, 1, [0.0, 0.0, 0.1, 0.1], "t", "text", 0.99)
        await cb.on_quality_summary("job", None, 0.98, 0.97, 0, 0)
        assert calls["retry"] == []
        assert calls["revised"] == []
        assert calls["summary"] == []
