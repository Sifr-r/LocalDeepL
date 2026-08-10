"""OCrQualitySettings — single source of truth for trust-layer knobs.

Pydantic v2 ``BaseModel`` with ``extra="forbid"`` so typos in the API
schema fail fast instead of silently disabling a flag. Defaults match
Phase 1 of the rollout plan: every sub-module off, full passthrough.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OCrQualitySettings(BaseModel):
    """Workspace / per-run configuration for the trust layer."""

    model_config = ConfigDict(extra="forbid")

    # Per-sub-module on/off switches. Phase 1 ships with every switch off;
    # Phase 2 flips watermark / script_detect / hallucination / calibration
    # to True at the field-default level.
    watermark_enabled: bool = False
    watermark_aggressiveness: float = Field(default=0.5, ge=0.0, le=1.0)

    script_detect_enabled: bool = False

    hallucination_enabled: bool = False
    hallucination_cross_check: bool = False  # second VLM call, off by default
    hallucination_cross_check_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    hallucination_repetition_window: int = Field(default=6, ge=2, le=64)
    hallucination_length_plausibility_min: float = Field(
        default=0.0001, ge=0.0, le=1.0
    )

    calibration_enabled: bool = False

    # Auto-flag block in UI when trust_score < this threshold.
    trust_flag_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    # Soft-rollout flags. Phase 2 / Phase 3 keep the new defaults behind a
    # per-workspace toggle so existing setups see no behaviour change.
    phase2_default: bool = False
    phase3_default: bool = False

    def any_submodule_enabled(self) -> bool:
        """Return True if at least one sub-module is on.

        The orchestrator uses this to short-circuit before touching any
        page image or block — keeps the disabled-path overhead at one
        boolean check.
        """
        return (
            self.watermark_enabled
            or self.script_detect_enabled
            or self.hallucination_enabled
            or self.calibration_enabled
        )


__all__ = ["OCrQualitySettings"]
