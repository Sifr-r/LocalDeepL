"""Encoding detection helpers shared by glossary source parsers."""

from __future__ import annotations

import codecs
import importlib
from typing import Any, cast


def detect_encoding(data: bytes) -> tuple[str, str]:
    """Return ``(encoding, warning)`` for a byte payload.

    UTF-8 with and without a BOM is preferred.  ``chardet`` is used when it is
    installed and sufficiently confident; latin-1 is the final lossless
    fallback, with a warning so callers can surface the decision to users.
    """
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", ""

    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    else:
        return "utf-8", ""

    chardet_module: Any = None
    try:
        chardet_module = importlib.import_module("chardet")
    except ImportError:
        chardet_module = None

    if chardet_module is not None:
        detect_callable = getattr(chardet_module, "detect", None)
        if callable(detect_callable):
            detected = detect_callable(data)
            candidate = detected.get("encoding") if isinstance(detected, dict) else None
            confidence = (
                detected.get("confidence", 0.0) if isinstance(detected, dict) else 0.0
            )
            if (
                isinstance(candidate, str)
                and isinstance(confidence, (int, float))
                and confidence >= 0.60
                and cast(Any, candidate) is not None
            ):
                try:
                    codecs.lookup(candidate)
                except LookupError:
                    pass
                else:
                    return candidate, f"Detected source encoding as {candidate}."

    return "latin-1", "Source was not valid UTF-8; decoded as latin-1."


def decode_bytes(data: bytes, encoding: str | None = None) -> tuple[str, str, str]:
    """Decode bytes and return text, encoding used, and a warning."""
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("Glossary source must be bytes.")
    raw = bytes(data)
    used = encoding
    warning = ""
    if used is None:
        used, warning = detect_encoding(raw)
    try:
        text = raw.decode(used)
    except (LookupError, UnicodeDecodeError) as exc:
        if isinstance(exc, LookupError):
            raise ValueError(f"Unknown encoding: {used}") from exc
        raise ValueError(f"Could not decode glossary source as {used}.") from exc
    return text, used, warning
