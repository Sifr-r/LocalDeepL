"""Documents service: artifact parsing, tree building, export builders.

Pure functions only — no FastAPI imports, so the whole module is
unit-testable without HTTP. The extraction runner is added in Task 4.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from omniscribe.core.block_tree import DocumentTree

# Typed as `dict[str, str]` so callers can look up by string literal — the
# StrEnum members are str subclasses, so hash-equal lookup works either way.
EXPORT_MEDIA_TYPES: dict[str, str] = {
    "json": "application/json",
    "markdown": "text/markdown; charset=utf-8",
    "text": "text/plain; charset=utf-8",
    "docling": "application/json",
    "mineru": "application/json",
}


class DocumentsError(Exception):
    """User-facing documents error carrying the envelope wire fields."""

    def __init__(self, status_code: int, error: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.error = error
        self.detail = detail


def load_pages(raw: Mapping[str, Any]) -> dict[int, list[str]]:
    """Parse a stored text artifact blob into ``{page: [lines]}``.

    Stored shape is ``{"<page_index>": "<lines joined by \\n>"}``
    (``plugins/ocr/service.py``). Non-numeric page keys are ignored —
    artifacts are machine-generated, so anything else is corruption.
    """
    pages: dict[int, list[str]] = {}
    for key, value in raw.items():
        try:
            page = int(key)
        except (TypeError, ValueError):
            continue
        text = value if isinstance(value, str) else ""
        pages[page] = text.split("\n")
    return pages


def build_tree(pages: dict[int, list[str]]) -> DocumentTree:
    """Build a DocumentTree on demand from parsed pages.

    Stored text artifacts carry no bboxes, so every line gets a zero
    bbox — this is the pre-harness code's "legacy fallback" path; block
    types come from ``_classify_simple`` text heuristics.
    """
    from omniscribe.core.block_tree import from_pages_data

    # Annotated with the exact parameter type of ``from_pages_data`` —
    # ``dict`` is invariant in its value type, so a ``list``-valued
    # annotation would not be assignable.
    pages_data: dict[int, Sequence[tuple[Sequence[float], str]]] = {
        page: [([0.0, 0.0, 0.0, 0.0], line) for line in lines]
        for page, lines in pages.items()
    }
    return from_pages_data(pages_data)


def build_document_export(
    *,
    page_text: Mapping[int, list[str]],
    metadata: Mapping[str, Any] | None,
    export_format: str,
) -> str | dict[str, Any]:
    """Build the export payload for one format.

    Verbatim re-home of the pre-harness ``build_document_export``, keyed
    by int page.
    """
    match export_format:
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
            raise DocumentsError(
                400, "bad_request", f"Unsupported export format: {export_format}"
            )


def _pages_json(page_text: Mapping[int, list[str]]) -> list[dict[str, Any]]:
    return [
        {"page_index": page, "lines": list(lines), "text": "\n".join(lines)}
        for page, lines in sorted(page_text.items())
    ]


def _plain_text(page_text: Mapping[int, list[str]]) -> str:
    return "\n\n".join("\n".join(lines) for _page, lines in sorted(page_text.items()))


def _markdown(page_text: Mapping[int, list[str]]) -> str:
    chunks = []
    for page, lines in sorted(page_text.items()):
        chunks.append(f"## Page {page + 1}\n\n" + "\n".join(lines))
    return "\n\n".join(chunks).strip() + "\n"
