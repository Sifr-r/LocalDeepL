"""Tests for :mod:`omniscribe.core.ocr_quality.script_detector`."""

from __future__ import annotations

from omniscribe.core.ocr_quality import script_detector


class TestLatin:
    def test_plain_latin(self):
        hint = script_detector.detect("Hello, world!")
        assert hint is not None
        assert hint.script == "Latin"
        assert hint.confidence >= 0.7

    def test_with_punctuation(self):
        hint = script_detector.detect("Hello.\nNew paragraph here.")
        assert hint is not None
        assert hint.script == "Latin"


class TestCJK:
    def test_kanji_dominant(self):
        # Pure CJK ideographs → confidence 1.0.
        hint = script_detector.detect("日本語漢字")
        assert hint is not None
        assert hint.script == "CJK"
        assert hint.confidence == 1.0

    def test_kanji_with_kana_still_cjk(self):
        hint = script_detector.detect("日本語テキスト漢字")
        assert hint is not None
        assert hint.script == "CJK"
        assert hint.confidence >= 0.5

    def test_hangul_groups_as_cjk(self):
        hint = script_detector.detect("안녕하세요 세계")
        assert hint is not None
        assert hint.script == "CJK"


class TestMixed:
    def test_latin_majority(self):
        hint = script_detector.detect("Hello world 你好")
        assert hint is not None
        assert hint.script == "Latin"

    def test_cjk_majority(self):
        hint = script_detector.detect("日本語 日本語 日本語 A")
        assert hint is not None
        assert hint.script == "CJK"


class TestOtherScripts:
    def test_arabic(self):
        hint = script_detector.detect("مرحبا بالعالم")
        assert hint is not None
        assert hint.script == "Arabic"

    def test_devanagari(self):
        hint = script_detector.detect("नमस्ते दुनिया")
        assert hint is not None
        assert hint.script == "Devanagari"

    def test_cyrillic(self):
        hint = script_detector.detect("Привет мир")
        assert hint is not None
        assert hint.script == "Cyrillic"


class TestEdgeCases:
    def test_empty_returns_none(self):
        assert script_detector.detect("") is None

    def test_none_returns_none(self):
        assert script_detector.detect(None) is None

    def test_punctuation_only_returns_none(self):
        assert script_detector.detect("!?,.;:") is None
