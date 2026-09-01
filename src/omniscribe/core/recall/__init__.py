"""Secondary text-recall sources merged into hybrid detection."""

from __future__ import annotations

from typing import Final

# Standard recall constants shared across recall sources (audit 3.9, 6.5, 6.25).
STRADDLE_MIN_OVERLAP: Final[float] = 0.15
MAX_RECALL_BOXES_PER_PAGE: Final[int] = 10

# Backward-compatible aliases matching source-specific historical names
_STRADDLE_MIN_OVERLAP = STRADDLE_MIN_OVERLAP
_MAX_RECALL_BOXES_PER_PAGE = MAX_RECALL_BOXES_PER_PAGE
_MAX_TEXT_LAYER_BOXES_PER_PAGE = MAX_RECALL_BOXES_PER_PAGE
_MAX_WHITESPACE_BOXES_PER_PAGE = MAX_RECALL_BOXES_PER_PAGE

__all__ = [
    "MAX_RECALL_BOXES_PER_PAGE",
    "STRADDLE_MIN_OVERLAP",
    "_MAX_RECALL_BOXES_PER_PAGE",
    "_MAX_TEXT_LAYER_BOXES_PER_PAGE",
    "_MAX_WHITESPACE_BOXES_PER_PAGE",
    "_STRADDLE_MIN_OVERLAP",
]
