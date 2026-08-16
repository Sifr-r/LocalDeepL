"""Tests for :mod:`omniscribe.core.nllb_engine`."""

from __future__ import annotations

from omniscribe.core.nllb_engine import LANGUAGE_CODE_MAP, resolve_nllb_code


def test_nllb_resolve_nllb_code_known():
    assert resolve_nllb_code("French") == "fra_Latn"
    assert resolve_nllb_code("english") == "eng_Latn"
    assert resolve_nllb_code("Chinese") == "zho_Hans"
    # Already a code
    assert resolve_nllb_code("deu_Latn") == "deu_Latn"
    # Unknown -> default to English
    assert resolve_nllb_code("Klingon") == "eng_Latn"


def test_nllb_language_code_map_has_basics():
    for name in ("english", "spanish", "french", "german", "chinese", "japanese"):
        assert name in LANGUAGE_CODE_MAP
        assert "_" in LANGUAGE_CODE_MAP[name]
