"""Job event types for the OCR plugin.

Canonical definitions live in :mod:`omniscribe.plugins.jobs` (lifecycle
events) and :mod:`omniscribe.plugins.progress` (:class:`ProgressFrame`) so
the queue never imports its producer; this module is the OCR-side re-export
surface used by the service, the SSE route, and tests.
"""

from __future__ import annotations

from omniscribe.plugins.jobs import (
    JobCancelled,
    JobCompleted,
    JobFailed,
    JobQueued,
    JobStarted,
)
from omniscribe.plugins.progress import ProgressFrame

__all__ = [
    "JobCancelled",
    "JobCompleted",
    "JobFailed",
    "JobQueued",
    "JobStarted",
    "ProgressFrame",
]
