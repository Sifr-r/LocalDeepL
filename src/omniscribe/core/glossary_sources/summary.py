"""Shared result types and safe diagnostics for glossary imports."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GlossaryImportSummary:
    """Normalized output from a glossary source parser."""

    entries: list[dict[str, object]]
    format: str
    source_uri: str | None = None
    encoding: str | None = None
    warnings: tuple[str, ...] = ()
    duplicates: int = 0

    @property
    def count(self) -> int:
        """Return the number of normalized entries."""
        return len(self.entries)


class FormatNotAvailableError(ImportError):
    """Raised when an optional glossary import dependency is unavailable."""


def redact_dsn(dsn: str) -> str:
    """Replace credentials and password-like DSN values before logging."""
    redacted = re.sub(r"(://)([^/@\s]+)(@)", r"\1***\3", str(dsn))
    return re.sub(
        r"(?i)(password|passwd|pwd|token|secret)\s*=\s*[^;,\s]+",
        r"\1=***",
        redacted,
    )
