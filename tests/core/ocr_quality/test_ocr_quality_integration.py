"""Golden integration test for the OCR quality trust layer."""

from __future__ import annotations

from PIL import Image

from omniscribe.core.document import DocumentBlock
from omniscribe.core.ocr_quality import (
    BlockTrust,
    HallucinationRisk,
    OCrQualitySettings,
    ScriptHint,
    TrustFlag,
    hallucination_risk_value,
    run_trust_scored_blocks,
)


class TestPublicImports:
    def test_all_symbols_importable(self):
        # Just constructing them is enough — covers the public API.
        settings = OCrQualitySettings()
        flag = TrustFlag.WATERMARK_HIT
        risk = HallucinationRisk.LOW
        hint = ScriptHint(script="Latin", confidence=0.9)
        trust = BlockTrust(score=0.5, flags=(flag,), explanations=("x",))
        assert isinstance(hallucination_risk_value(risk), float)
        assert settings.any_submodule_enabled() is False
        assert hint.script == "Latin"
        assert trust.score == 0.5


class TestPassthroughGolden:
    def test_default_settings_passthrough(self):
        block = DocumentBlock(bbox=(0.0, 0.0, 0.5, 0.05), text="Hello", confidence=0.9)
        out = run_trust_scored_blocks(
            [block],
            Image.new("RGB", (200, 200), (255, 255, 255)),
            OCrQualitySettings(),
            model_id="nonexistent-xyz",
        )
        # Passthrough: trust_score is None, every other field preserved.
        assert len(out) == 1  # type: ignore[arg-type]
        result = out[0]  # type: ignore[index]
        assert result.text == "Hello"
        assert result.confidence == 0.9
        assert result.trust_score is None
        assert result.trust_flags is None

    def test_enabled_settings_populate_trust(self):
        block = DocumentBlock(
            bbox=(0.0, 0.0, 0.5, 0.05),
            text="Hello world",
            confidence=0.8,
        )
        settings = OCrQualitySettings(calibration_enabled=True)
        out = run_trust_scored_blocks(
            [block],
            Image.new("RGB", (200, 200), (255, 255, 255)),
            settings,
            model_id="identity",  # ships with calibration/identity.json
        )
        result = out[0]  # type: ignore[index]
        assert result.trust_score is not None
        # Identity calibration at conf=0.8 → calibrated ≈ 0.8.
        assert abs(result.trust_score - 0.8) < 0.1
