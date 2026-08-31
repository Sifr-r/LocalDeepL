"""Tests for the env-configurable VLM timeout knobs (audit A-11).

The OCR processor's ``page_timeout_s`` / ``crop_timeout_s`` are
overridable via ``OMNISCRIBE_VLM_PAGE_TIMEOUT`` and
``OMNISCRIBE_VLM_CROP_TIMEOUT``.

Pedantic review 1.12: these env values are now resolved per-instance
in ``__init__`` rather than at module import. A long-running worker
that picks up an env-var change after import sees the new value on
the next ``OCRProcessor()`` without reloading the module. The class-
level ``PAGE_TIMEOUT_S`` / ``CROP_TIMEOUT_S`` constants are hardcoded
defaults and are the fallback for ``__new__``-built test instances
(via the ``__getattr__`` shim).
"""

from __future__ import annotations

import pytest

from omniscribe.core.ocr.processor import OCRProcessor


def _make_processor(**env: str) -> OCRProcessor:
    """Build a fresh ``OCRProcessor`` with ``env`` applied to the process.

    Resolves the env-driven timeouts via the production ``__init__``
    path; tests that need a different env just patch and call this.
    """
    import os

    previous = {k: os.environ.get(k) for k in env}
    try:
        for key, value in env.items():
            os.environ[key] = value
        return OCRProcessor(api_base="http://test.local/v1", api_key="x", model="mock")
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_default_timeouts_when_env_unset() -> None:
    """Unset env vars fall back to the documented defaults."""
    import os

    os.environ.pop("OMNISCRIBE_VLM_PAGE_TIMEOUT", None)
    os.environ.pop("OMNISCRIBE_VLM_CROP_TIMEOUT", None)
    proc = _make_processor()
    assert proc.page_timeout_s == 240.0
    assert proc.crop_timeout_s == 60.0
    # Class-level constants stay at the hardcoded default regardless of
    # env (1.12: the env is no longer read at import time).
    assert OCRProcessor.PAGE_TIMEOUT_S == 240.0
    assert OCRProcessor.CROP_TIMEOUT_S == 60.0


def test_page_timeout_override_takes_effect() -> None:
    """``OMNISCRIBE_VLM_PAGE_TIMEOUT`` overrides the page-level timeout."""
    proc = _make_processor(OMNISCRIBE_VLM_PAGE_TIMEOUT="30")
    assert proc.page_timeout_s == 30.0
    # Crop timeout is independent.
    assert proc.crop_timeout_s == 60.0


def test_crop_timeout_override_takes_effect() -> None:
    """``OMNISCRIBE_VLM_CROP_TIMEOUT`` overrides the crop-level timeout."""
    proc = _make_processor(OMNISCRIBE_VLM_CROP_TIMEOUT="15")
    assert proc.crop_timeout_s == 15.0
    assert proc.page_timeout_s == 240.0


def test_both_timeouts_can_be_overridden_simultaneously() -> None:
    """Both overrides can be applied at once."""
    proc = _make_processor(
        OMNISCRIBE_VLM_PAGE_TIMEOUT="90",
        OMNISCRIBE_VLM_CROP_TIMEOUT="20",
    )
    assert proc.page_timeout_s == 90.0
    assert proc.crop_timeout_s == 20.0


def test_env_change_after_import_picks_up_on_fresh_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pedantic 1.11/1.12 regression: an env override applied *after*
    the processor module has already been imported is visible to a
    freshly-constructed ``OCRProcessor()``. Under the old import-time
    resolution this would have required a module reload.
    """
    monkeypatch.delenv("OMNISCRIBE_VLM_PAGE_TIMEOUT", raising=False)
    first = _make_processor()
    assert first.page_timeout_s == 240.0
    # Operator tweaks the env between two pipeline runs.
    monkeypatch.setenv("OMNISCRIBE_VLM_PAGE_TIMEOUT", "75")
    second = _make_processor()
    assert second.page_timeout_s == 75.0
