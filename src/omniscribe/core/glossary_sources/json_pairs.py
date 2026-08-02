"""JSON-pairs glossary source adapter."""

from __future__ import annotations

import json
from typing import Any

from omniscribe.core.glossary import Glossary

from ._common import decode_source, require_bytes
from .summary import GlossaryImportSummary


def parse_json_pairs(
    data: bytes | str,
    *,
    encoding: str | None = None,
    **kwargs: Any,
) -> GlossaryImportSummary:
    """Parse ``{"entries": [{"source": ..., "target": ...}]}`` JSON.

    ``encoding`` is accepted for symmetry with the other parsers but is
    detected internally from the data itself (e.g. UTF-8 BOM). Extra kwargs
    are ignored.
    """
    raw = require_bytes(data)
    _encoding = encoding
    text, used_encoding, warnings = decode_source(raw)
    del _encoding  # explicit: kept for API symmetry; we trust decode_source.
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON glossary source: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON glossary source must be an object.")
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("JSON glossary source must contain an 'entries' list.")

    glossary = Glossary.from_dict_with_metadata(payload)
    if not glossary.entries:
        raise ValueError("JSON glossary source contains no valid entries.")
    normalized_entries: list[dict[str, object]] = []
    raw_typed_entries: object = glossary.to_dict().get("entries", [])
    if isinstance(raw_typed_entries, list):
        for raw_entry in raw_typed_entries:
            if isinstance(raw_entry, dict):
                normalized_entries.append(dict(raw_entry))
    if not normalized_entries:
        raise ValueError("JSON glossary source contains no valid entries.")
    return GlossaryImportSummary(
        entries=normalized_entries,
        format=str(payload.get("source_format") or "json_pairs"),
        source_uri=_optional_string(payload.get("source_uri")),
        encoding=_optional_string(payload.get("encoding")) or used_encoding,
        warnings=warnings,
    )


def _optional_string(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)
