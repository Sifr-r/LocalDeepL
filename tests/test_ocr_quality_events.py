"""Tests for :mod:`omniscribe.core.ocr_quality.events`."""

from __future__ import annotations

import logging

from omniscribe.core.ocr_quality import events


class TestEmit:
    def test_emit_does_not_raise(self, caplog):
        caplog.set_level(logging.DEBUG, logger="omniscribe.core.ocr_quality.events")
        events.emit(
            "watermark",
            doc_id="doc-1",
            page=3,
            duration_ms=12,
            decision="hit",
            fallback_used=False,
        )
        assert any("watermark" in rec.message for rec in caplog.records)

    def test_emit_with_missing_fields_does_not_raise(self, caplog):
        caplog.set_level(logging.DEBUG, logger="omniscribe.core.ocr_quality.events")
        events.emit(
            "calibration",
            doc_id="",
            page=-1,
            duration_ms=0,
            decision="identity",
            fallback_used=True,
        )
        # Should not have raised.

    def test_extra_payload_attached(self, caplog):
        caplog.set_level(logging.DEBUG, logger="omniscribe.core.ocr_quality.events")
        events.emit(
            "trust_scorer",
            doc_id="d",
            page=7,
            duration_ms=42,
            decision="scored",
            fallback_used=False,
        )
        record = next(
            (r for r in caplog.records if "trust_scorer" in r.message),
            None,
        )
        assert record is not None
        assert getattr(record, "ocr_quality_sub_module", None) == "trust_scorer"
        assert getattr(record, "ocr_quality_page", None) == 7
        assert getattr(record, "ocr_quality_duration_ms", None) == 42
        assert getattr(record, "ocr_quality_fallback_used", None) is False
