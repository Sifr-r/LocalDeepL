from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from local_deepl.api.schemas.requests import DocumentExportFormat
from local_deepl.api.services.artifacts import (
    InvalidArtifactPayloadError,
    InvalidArtifactReferenceError,
    is_opaque_artifact_id,
)
from local_deepl.utils import write_atomic

# Re-export so callers that historically imported it from this module keep working.
__all__ = ["EXPORT_MEDIA_TYPES", "DocumentExportFormat", "build_document_export"]

# Typed as `dict[str, str]` (not `dict[DocumentExportFormat, str]`) so callers
# can look up by string literal — the enum members are str subclasses, so
# hash-equal lookup works at runtime either way.
EXPORT_MEDIA_TYPES: dict[str, str] = {
    DocumentExportFormat.JSON: "application/json",
    DocumentExportFormat.MARKDOWN: "text/markdown; charset=utf-8",
    DocumentExportFormat.TEXT: "text/plain; charset=utf-8",
    DocumentExportFormat.DOCLING: "application/json",
    DocumentExportFormat.MINERU: "application/json",
}

# Runtime whitelist derived from the canonical StrEnum so the schema
# (requests.py) stays the single source of truth.
_SUPPORTED_FORMATS: frozenset[str] = frozenset(DocumentExportFormat)


def _coerce_format(value: str) -> str:
    if value not in _SUPPORTED_FORMATS:
        raise InvalidArtifactPayloadError(f"Unsupported export format: {value}")
    return value


def build_document_export(
    *,
    page_text: Mapping[str, list[str]],
    metadata: Mapping[str, Any] | None,
    export_format: str,
) -> str | dict[str, Any]:
    # `export_format` is typed as plain `str` so callers may pass either a
    # ``DocumentExportFormat`` StrEnum (e.g. ``body.export_format.value``) or
    # a raw literal string. The runtime whitelist check below rejects any
    # other value, so the Literal type remains the source of truth for
    # what's actually supported.
    format_name = _coerce_format(export_format)
    match format_name:
        case "text":
            return _plain_text(page_text)
        case "markdown":
            return _markdown(page_text)
        case "json":
            return {"pages": _pages_json(page_text), "metadata": metadata}
        case "docling":
            return {
                "schema": "docling_compatible",
                "document": _pages_json(page_text),
                "metadata": metadata,
            }
        case "mineru":
            return {
                "schema": "mineru_compatible",
                "pages": _pages_json(page_text),
                "metadata": metadata,
            }
        case _:
            # Unreachable — _coerce_format raises first.
            raise InvalidArtifactPayloadError(
                f"Unsupported export format: {format_name}"
            )


def write_document_export_atomic(
    payload: str | Mapping[str, Any],
    *,
    directory: str | os.PathLike[str] | None = None,
    artifact_id: str,
    export_format: str,
) -> str:
    if not is_opaque_artifact_id(artifact_id):
        raise InvalidArtifactReferenceError(
            "Artifact ID must be a 32-character hex string."
        )

    format_name = _coerce_format(export_format)
    artifact_dir = Path(directory or tempfile.gettempdir()).resolve()
    suffix = (
        "md"
        if format_name == "markdown"
        else "txt"
        if format_name == "text"
        else "json"
    )
    target = artifact_dir / f"export_{artifact_id}.{suffix}"

    write_atomic(target, payload, prefix=f".export_{artifact_id}.")
    return str(target)


def load_json_file(path: str) -> Any:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def _pages_json(page_text: Mapping[str, list[str]]) -> list[dict[str, Any]]:
    return [
        {"page_index": int(page), "lines": list(lines), "text": "\n".join(lines)}
        for page, lines in sorted(page_text.items(), key=lambda item: int(item[0]))
    ]


def _plain_text(page_text: Mapping[str, list[str]]) -> str:
    return "\n\n".join(
        "\n".join(lines)
        for _page, lines in sorted(page_text.items(), key=lambda item: int(item[0]))
    )


def _markdown(page_text: Mapping[str, list[str]]) -> str:
    chunks = []
    for page, lines in sorted(page_text.items(), key=lambda item: int(item[0])):
        chunks.append(f"## Page {int(page) + 1}\n\n" + "\n".join(lines))
    return "\n\n".join(chunks).strip() + "\n"
