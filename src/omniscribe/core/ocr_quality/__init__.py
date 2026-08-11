"""Public API for the OCR quality trust layer.

Re-exports the small surface most callers need:

- :class:`OCrQualitySettings` — configuration model
- :func:`run` — orchestrator entry point (alias for ``run_trust_scored_blocks``)
- :func:`run_trust_scored_blocks` — explicit name retained for spec compatibility
- :class:`TrustOrchestrator` — runtime-checkable Protocol for the per-page
  scorer (``OCR Pipeline`` wires one in once any sub-module is enabled)
- :func:`build_trust_orchestrator` — factory that returns the default
  orchestrator bound to :class:`OCrQualitySettings`, or ``None`` when every
  sub-module is off
- Types — :class:`BlockTrust`, :class:`TrustFlag`, :class:`HallucinationRisk`,
  :class:`WatermarkHit`, :class:`ScriptHint`

The package is intentionally small; everything else lives in the
sub-modules. All sub-modules default to **off** — the package is a
no-op until the caller enables at least one flag.
"""

from __future__ import annotations

from .config import OCrQualitySettings
from .orchestrator import (
    TrustOrchestrator,
    _DefaultTrustOrchestrator,
    build_trust_orchestrator,
)
from .orchestrator import (
    run as _run,
)
from .types import (
    BlockTrust,
    HallucinationRisk,
    ScriptHint,
    TrustFlag,
    WatermarkHit,
    hallucination_risk_value,
)


def run_trust_scored_blocks(
    *args: object, **kwargs: object
) -> object:  # pragma: no cover - alias
    """Spec-named alias for :func:`omniscribe.core.ocr_quality.orchestrator.run`."""
    return _run(*args, **kwargs)  # type: ignore[arg-type]


__all__ = [
    "BlockTrust",
    "HallucinationRisk",
    "OCrQualitySettings",
    "ScriptHint",
    "TrustFlag",
    "TrustOrchestrator",
    "WatermarkHit",
    "_DefaultTrustOrchestrator",
    "build_trust_orchestrator",
    "hallucination_risk_value",
    "run",
    "run_trust_scored_blocks",
]
