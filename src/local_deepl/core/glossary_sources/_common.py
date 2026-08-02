"""Internal normalization helpers for glossary source adapters."""

from __future__ import annotations

import base64
import binascii
import re
import xml.etree.ElementTree as ElementTree
from collections import Counter
from typing import Any

from .encoding import decode_bytes
from .summary import GlossaryImportSummary

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def require_bytes(data: bytes | bytearray | str | None) -> bytes:
    """Normalize parser input to bytes without guessing a text encoding."""
    if data is None:
        raise ValueError("Glossary source data is required.")
    if isinstance(data, str):
        return data.encode("utf-8")
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    raise ValueError("Glossary source must be bytes or text.")


def decode_source(
    data: bytes | bytearray | str,
    encoding: str | None = None,
) -> tuple[str, str, tuple[str, ...]]:
    """Decode source data and normalize a possible encoding warning."""
    raw = require_bytes(data)
    if encoding is None:
        from .encoding import detect_encoding

        used, warning = detect_encoding(raw)
        text, _used, _ignored = decode_bytes(raw, used)
    else:
        used = encoding
        warning = ""
        text, _used, _ignored = decode_bytes(raw, encoding)
    warnings = (warning,) if warning else ()
    return text, used, warnings


def entry_dict(
    source: Any,
    target: Any,
    *,
    case_sensitive: Any = False,
    notes: Any = "",
    group: Any = None,
) -> dict[str, object] | None:
    """Normalize one pair and discard empty or non-scalar values."""
    if source is None or target is None:
        return None
    source_text = str(source).strip()
    target_text = str(target).strip()
    if not source_text or not target_text:
        return None
    item: dict[str, object] = {
        "source": source_text,
        "target": target_text,
        "case_sensitive": parse_bool(case_sensitive),
        "notes": "" if notes is None else str(notes).strip(),
    }
    if group is not None and str(group).strip():
        item["group"] = str(group).strip()
    return item


def parse_bool(value: Any) -> bool:
    """Parse common CSV/JSON boolean spellings without truthiness surprises."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def finalize(
    entries: list[dict[str, object]],
    *,
    format_name: str,
    encoding: str | None = None,
    warnings: tuple[str, ...] = (),
    source_uri: str | None = None,
) -> GlossaryImportSummary:
    """Create a summary and count repeated source terms."""
    counts = Counter(
        str(item.get("source", "")).casefold() for item in entries if item.get("source")
    )
    duplicates = sum(count - 1 for count in counts.values() if count > 1)
    return GlossaryImportSummary(
        entries=entries,
        format=format_name,
        source_uri=source_uri,
        encoding=encoding,
        warnings=warnings,
        duplicates=duplicates,
    )


def local_name(tag: str) -> str:
    """Return an XML tag's local name, independent of namespace."""
    return tag.rsplit("}", 1)[-1].lower()


def iter_text(element: ElementTree.Element | None) -> str:
    """Collect text from an XML element, including inline child elements."""
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def language_matches(value: str | None, wanted: str) -> bool:
    """Compare language tags by exact tag or base language."""
    if not value:
        return False
    actual = value.replace("_", "-").split("-", 1)[0].lower()
    expected = wanted.replace("_", "-").split("-", 1)[0].lower()
    return actual == expected


def decode_base64(value: str) -> bytes:
    """Decode a strict inline base64 payload."""
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("inline_bytes_b64 is not valid base64.") from exc


def validate_identifier(value: str, field_name: str) -> str:
    """Validate a SQL identifier before it is quoted into a statement."""
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid SQL identifier for {field_name}.")
    return value


def safe_xml_root(data: bytes) -> ElementTree.Element:
    """Parse XML while rejecting DTD/entity declarations and external hints."""
    upper = data[:1_000_000].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper or b"SYSTEM" in upper:
        raise ValueError("DTD and external entities are not allowed in glossary XML.")
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ValueError(f"Invalid glossary XML: {exc}") from exc
