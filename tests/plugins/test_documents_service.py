"""Unit tests for the documents plugin service (no HTTP layer)."""

from __future__ import annotations

from omniscribe.plugins.documents.service import (
    EXPORT_MEDIA_TYPES,
    build_document_export,
    build_tree,
    load_pages,
)


def test_load_pages_splits_joined_lines_and_ignores_non_numeric_keys() -> None:
    raw = {"0": "a\nb", "1": "c", "x": "ignored", "2": ""}
    pages = load_pages(raw)
    assert pages == {0: ["a", "b"], 1: ["c"], 2: [""]}
    # Deterministic page ordering for downstream builders.
    assert sorted(pages) == [0, 1, 2]


def test_load_pages_handles_non_string_values() -> None:
    assert load_pages({"0": None}) == {0: [""]}


def test_build_tree_produces_pages_in_order() -> None:
    tree = build_tree({1: ["b"], 0: ["a"]})
    assert [page.page_idx for page in tree.pages] == [0, 1]


def test_export_media_types_cover_all_formats() -> None:
    assert EXPORT_MEDIA_TYPES["json"] == "application/json"
    assert EXPORT_MEDIA_TYPES["markdown"] == "text/markdown; charset=utf-8"
    assert EXPORT_MEDIA_TYPES["text"] == "text/plain; charset=utf-8"
    assert EXPORT_MEDIA_TYPES["docling"] == "application/json"
    assert EXPORT_MEDIA_TYPES["mineru"] == "application/json"


def test_build_document_export_markdown() -> None:
    payload = build_document_export(
        page_text={0: ["hello", "world"], 1: ["next"]},
        metadata=None,
        export_format="markdown",
    )
    assert isinstance(payload, str)
    assert payload.startswith("## Page 1\n\nhello\nworld")
    assert "## Page 2\n\nnext" in payload
    assert payload.endswith("\n")


def test_build_document_export_text() -> None:
    payload = build_document_export(
        page_text={0: ["a", "b"], 1: ["c"]},
        metadata=None,
        export_format="text",
    )
    assert payload == "a\nb\n\nc"


def test_build_document_export_json_shape() -> None:
    payload = build_document_export(
        page_text={0: ["a"]},
        metadata={"k": "v"},
        export_format="json",
    )
    assert payload == {
        "pages": [{"page_index": 0, "lines": ["a"], "text": "a"}],
        "metadata": {"k": "v"},
    }


def test_build_document_export_docling_and_mineru_schema_tags() -> None:
    docling = build_document_export(
        page_text={0: ["a"]}, metadata=None, export_format="docling"
    )
    assert isinstance(docling, dict)
    assert docling["schema"] == "docling_compatible"
    assert docling["document"][0]["page_index"] == 0

    mineru = build_document_export(
        page_text={0: ["a"]}, metadata=None, export_format="mineru"
    )
    assert isinstance(mineru, dict)
    assert mineru["schema"] == "mineru_compatible"
    assert mineru["pages"][0]["page_index"] == 0


def test_build_document_export_rejects_unknown_format() -> None:
    try:
        build_document_export(page_text={0: ["a"]}, metadata=None, export_format="pdf")
    except Exception as exc:
        assert "Unsupported export format" in str(exc)
    else:
        raise AssertionError("expected unsupported format to raise")
