"""Public types for the OCR quality trust layer.

Frozen dataclasses for cross-module handoff and two ``StrEnum``s
(``TrustFlag``, ``HallucinationRisk``). Everything is hashable so the
trust layer can be memoised on stable block signatures.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TrustFlag(StrEnum):
    """Why a block's trust score was reduced.

    Stored on ``DocumentBlock.trust_flags`` and ``BlockTrust.flags``.
    String-valued so JSON-serialisation is trivial and consumers don't
    need to import the enum to render badges.
    """

    HALLUCINATION_RISK = "hallucination_risk"
    WATERMARK_HIT = "watermark_hit"
    SCRIPT_MISMATCH = "script_mismatch"
    LOW_CALIBRATED_CONF = "low_calibrated_conf"
    LENGTH_PLAUSIBILITY = "length_plausibility"


class HallucinationRisk(StrEnum):
    """How likely a block's text was fabricated by the VLM.

    The trust formula multiplies confidence by ``(1 - 0.5 * risk_value)``
    where ``risk_value`` is :data:`_RISK_VALUE` (NONE/LOW carry zero
    penalty by design — see spec §5.3).
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_RISK_VALUE: dict[HallucinationRisk, float] = {
    HallucinationRisk.NONE: 0.0,
    HallucinationRisk.LOW: 0.0,
    HallucinationRisk.MEDIUM: 0.5,
    HallucinationRisk.HIGH: 1.0,
}


def hallucination_risk_value(risk: HallucinationRisk) -> float:
    """Return the numeric weight for :class:`HallucinationRisk`.

    Centralised so the trust formula and tests share one source of truth.
    """
    return _RISK_VALUE[risk]


@dataclass(slots=True, frozen=True)
class WatermarkHit:
    """Result of watermark detection on a single page.

    ``bbox`` is ``None`` when nothing was detected (passthrough case).
    ``confidence`` is the detector's own score in ``[0, 1]``.
    """

    bbox: tuple[float, float, float, float] | None
    confidence: float


@dataclass(slots=True, frozen=True)
class ScriptHint:
    """Script classification of a page (or block).

    ``script`` is a Unicode script name (``"Latin"``, ``"CJK"``,
    ``"Arabic"``, ``"Devanagari"``, ``"Cyrillic"``). ``bbox`` is
    ``None`` for whole-page detection.
    """

    script: str
    confidence: float
    bbox: tuple[float, float, float, float] | None = None


@dataclass(slots=True, frozen=True)
class BlockTrust:
    """Per-block trust verdict.

    ``score`` ∈ ``[0, 1]`` — calibrated confidence after penalties.
    ``flags`` are sorted, deduplicated, and ordered for stable JSON.
    ``explanations`` are short human-readable strings suitable for UI
    tooltips.
    """

    score: float
    flags: tuple[TrustFlag, ...]
    explanations: tuple[str, ...]


__all__ = [
    "BlockTrust",
    "HallucinationRisk",
    "ScriptHint",
    "TrustFlag",
    "WatermarkHit",
    "hallucination_risk_value",
]
