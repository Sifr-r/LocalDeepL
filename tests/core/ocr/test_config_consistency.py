"""Regression test for H2/H4: ``__init__`` must read env via load_settings().

The audit found that ``OCRProcessor.__init__`` and ``PromptedGroundedOCR.__init__``
read ``os.getenv("LLM_API_BASE")`` etc. directly, bypassing the centralised
``omniscribe.config.load_settings()``. This module pins the contract: the
``__init__`` MUST consult ``load_settings()`` (and the F1.9 audit comment
on the same module prohibits raw ``os.getenv`` for these fields).
"""
from __future__ import annotations

from unittest.mock import patch


def test_H2_OCRProcessor_init_uses_load_settings() -> None:
    """OCRProcessor.__init__ must call load_settings() and use its values.

    We patch ``load_settings`` so we can assert it was consulted, and so the
    test is independent of the actual process environment.
    """
    from unittest.mock import MagicMock

    from omniscribe.core.ocr.processor import OCRProcessor

    # Build a sentinel that mimics the RuntimeSettings fields the
    # processor reads. AsyncOpenAI validates that base_url is a str, so
    # we must set explicit string values (MagicMock auto-attrs are MagicMock
    # instances, not strings, and would fail the type check inside httpx).
    sentinel = MagicMock()
    sentinel.llm_api_base = "http://from-settings:9999/v1"
    sentinel.llm_api_key = "from-settings-key"
    sentinel.llm_model = "from-settings-model"
    # F1.9 settings (timeout/retries) — also consumed in __init__.
    sentinel.vlm_page_timeout = 240.0
    sentinel.vlm_crop_timeout = 60.0
    sentinel.llm_max_retries = 2
    sentinel.llm_retry_base_delay = 1.0

    with patch(
        "omniscribe.core.ocr.processor.load_settings", return_value=sentinel
    ) as mock_load:
        # Construct WITHOUT overriding api_base/api_key/model.
        proc = OCRProcessor(
            api_base=None,
            api_key=None,
            model=None,
        )

    # load_settings() was consulted.
    assert mock_load.called, (
        "H2 regression: OCRProcessor.__init__ must call load_settings() "
        "rather than os.getenv()."
    )
    # The processor picked up the values from the sentinel.
    assert proc.api_base == "http://from-settings:9999/v1"
    assert proc.api_key == "from-settings-key"
    assert proc.model == "from-settings-model"