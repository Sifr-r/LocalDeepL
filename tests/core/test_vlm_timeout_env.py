"""Tests for the env-configurable VLM timeout knobs (audit A-11).

The OCR processor's ``PAGE_TIMEOUT_S`` and ``CROP_TIMEOUT_S`` are now
overridable via ``OMNISCRIBE_VLM_PAGE_TIMEOUT`` and
``OMNISCRIBE_VLM_CROP_TIMEOUT``. These tests pin the override contract
without reloading the module (which would mask any future regression
where the env var stops being read).
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def reload_ocr_processor(monkeypatch: pytest.MonkeyPatch):
    """Reload the processor module after applying the supplied env var set.

    Forces the module-level ``os.getenv`` calls to re-execute so the
    test reflects what a fresh worker process would see. Returns the
    reloaded module so callers can read the resolved class attributes.
    """

    def _reload(**env: str) -> object:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        # Drop any cached module so the env vars re-evaluate.
        for mod_name in list(__import__("sys").modules):
            if mod_name.startswith("omniscribe.core.ocr."):
                del __import__("sys").modules[mod_name]
        return importlib.import_module("omniscribe.core.ocr.processor")

    return _reload


def test_default_timeouts_when_env_unset(reload_ocr_processor) -> None:
    """Unset env vars fall back to the documented defaults."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.delenv("OMNISCRIBE_VLM_PAGE_TIMEOUT", raising=False)
        monkeypatch.delenv("OMNISCRIBE_VLM_CROP_TIMEOUT", raising=False)
        mod = reload_ocr_processor()
        assert mod.OCRProcessor.PAGE_TIMEOUT_S == 240.0
        assert mod.OCRProcessor.CROP_TIMEOUT_S == 60.0
    finally:
        monkeypatch.undo()


def test_page_timeout_override_takes_effect(reload_ocr_processor) -> None:
    """``OMNISCRIBE_VLM_PAGE_TIMEOUT`` overrides the page-level timeout."""
    mod = reload_ocr_processor(OMNISCRIBE_VLM_PAGE_TIMEOUT="30")
    assert mod.OCRProcessor.PAGE_TIMEOUT_S == 30.0
    # Crop timeout is independent.
    assert mod.OCRProcessor.CROP_TIMEOUT_S == 60.0


def test_crop_timeout_override_takes_effect(reload_ocr_processor) -> None:
    """``OMNISCRIBE_VLM_CROP_TIMEOUT`` overrides the crop-level timeout."""
    mod = reload_ocr_processor(OMNISCRIBE_VLM_CROP_TIMEOUT="15")
    assert mod.OCRProcessor.CROP_TIMEOUT_S == 15.0
    assert mod.OCRProcessor.PAGE_TIMEOUT_S == 240.0


def test_both_timeouts_can_be_overridden_simultaneously(reload_ocr_processor) -> None:
    """Both overrides can be applied at once."""
    mod = reload_ocr_processor(
        OMNISCRIBE_VLM_PAGE_TIMEOUT="90",
        OMNISCRIBE_VLM_CROP_TIMEOUT="20",
    )
    assert mod.OCRProcessor.PAGE_TIMEOUT_S == 90.0
    assert mod.OCRProcessor.CROP_TIMEOUT_S == 20.0
