"""Tests for the Phase 5 polish:

- ``OMNISCRIBE_VLM_PAGE_MAX_TOKENS`` / ``OMNISCRIBE_VLM_CROP_MAX_TOKENS``
  env vars override the OCRProcessor's hard-coded token budgets.
- ``_run_spellcheck`` runs each page's correction on a worker thread
  (off the event loop).
"""

from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

from omniscribe.core.workflows.base import (
    EngineBase,
    _spellcheck_page_sync,
)

# --- max_tokens env override --------------------------------------------


class TestMaxTokensEnvOverride:
    """Phase 5 fix: PAGE_MAX_TOKENS / CROP_MAX_TOKENS used to be hard-coded.
    Both now read from env at instance construction time (pedantic 1.11)
    so operators can tune tail latency without patching the code and
    without reloading the module."""

    @staticmethod
    def _make_processor(monkeypatch: pytest.MonkeyPatch) -> object:
        from omniscribe.core.ocr.processor import OCRProcessor

        return OCRProcessor(api_base="http://test.local/v1", api_key="x", model="mock")

    def test_page_max_tokens_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OMNISCRIBE_VLM_PAGE_MAX_TOKENS", raising=False)
        from omniscribe.core.ocr import processor as proc_mod

        proc = self._make_processor(monkeypatch)
        # Pedantic 1.11/1.12: env is read per-instance, so the class
        # constant stays at the hardcoded default and the instance picks
        # up the (unset) env fallback.
        assert proc_mod.OCRProcessor.PAGE_MAX_TOKENS == 6144
        assert proc.page_max_tokens == 6144

    def test_page_max_tokens_env_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OMNISCRIBE_VLM_PAGE_MAX_TOKENS", "2048")
        from omniscribe.core.ocr import processor as proc_mod

        proc = self._make_processor(monkeypatch)
        assert proc.page_max_tokens == 2048
        # Class-level default is unchanged because env is no longer
        # read at import time.
        assert proc_mod.OCRProcessor.PAGE_MAX_TOKENS == 6144
        # restore default
        monkeypatch.delenv("OMNISCRIBE_VLM_PAGE_MAX_TOKENS", raising=False)

    def test_crop_max_tokens_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OMNISCRIBE_VLM_CROP_MAX_TOKENS", raising=False)
        from omniscribe.core.ocr import processor as proc_mod

        proc = self._make_processor(monkeypatch)
        assert proc_mod.OCRProcessor.CROP_MAX_TOKENS == 256
        assert proc.crop_max_tokens == 256

    def test_crop_max_tokens_env_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OMNISCRIBE_VLM_CROP_MAX_TOKENS", "512")
        from omniscribe.core.ocr import processor as proc_mod

        proc = self._make_processor(monkeypatch)
        assert proc.crop_max_tokens == 512
        assert proc_mod.OCRProcessor.CROP_MAX_TOKENS == 256
        monkeypatch.delenv("OMNISCRIBE_VLM_CROP_MAX_TOKENS", raising=False)


# --- spellcheck thread offload -----------------------------------------


class TestSpellcheckThreadOffload:
    """Phase 5 fix: spellcheck's per-block ``correct_text`` was running
    synchronously on the event loop. It now runs in a worker thread
    via :func:`asyncio.to_thread`."""

    async def test_spellcheck_runs_off_event_loop(self) -> None:
        """The ``correct_text`` call must be invoked from a thread that
        is NOT the one running the test (i.e. the asyncio thread)."""
        seen_threads: list[int] = []
        main_thread = threading.get_ident()

        class _FakeProcessor:
            def __init__(self, *_a, **_kw) -> None:
                pass

            async def ensure_loaded(self) -> None:
                return None

            def correct_text(self, text: str) -> str:
                seen_threads.append(threading.get_ident())
                return text.upper()

        engine = EngineBase(output_writer=lambda *_a, **_kw: None)
        pages = {
            0: [
                ((0.0, 0.0, 1.0, 0.1), "hello"),
                ((0.0, 0.1, 1.0, 0.2), "world"),
            ],
            1: [((0.0, 0.0, 1.0, 0.1), "again")],
        }

        with patch(
            "omniscribe.core.postprocess.DictionaryPostProcessor",
            _FakeProcessor,
        ):
            await engine._run_spellcheck(pages, [0, 1], "en")

        # Every correct_text call should be on a different thread than
        # the event loop (which is the main test thread here).
        assert seen_threads, "correct_text was never called"
        assert all(tid != main_thread for tid in seen_threads), (
            "correct_text ran on the event-loop thread; expected worker"
        )
        # The corrected text made it through.
        assert [text for _, text in pages[0]] == ["HELLO", "WORLD"]
        assert [text for _, text in pages[1]] == ["AGAIN"]

    async def test_spellcheck_page_sync_helper_preserves_empty_blocks(self) -> None:
        """The offloaded helper skips ``""`` blocks (so an empty
        placeholder never gets replaced) but still passes truthy
        whitespace through to ``correct_text`` (matches the pre-Phase 5
        behaviour byte-for-byte)."""

        class _SpyProcessor:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def correct_text(self, text: str) -> str:
                self.calls.append(text)
                return f"corrected:{text}"

        proc = _SpyProcessor()
        result = _spellcheck_page_sync(
            proc,  # type: ignore[arg-type]
            [
                ((0.0, 0.0, 1.0, 0.1), "hello"),
                ((0.0, 0.1, 1.0, 0.2), ""),
                ((0.0, 0.2, 1.0, 0.3), "   "),
            ],
        )
        # Empty string skips; whitespace (truthy) goes through.
        assert proc.calls == ["hello", "   "]
        assert [text for _, text in result] == [
            "corrected:hello",
            "",
            "corrected:   ",
        ]
