"""Unit tests for the documents plugin service (no HTTP layer)."""

from __future__ import annotations

import pytest

from omniscribe.config import RuntimeSettings
from omniscribe.plugins.documents import service as documents_service
from omniscribe.plugins.documents.schemas import ExtractionRequest
from omniscribe.plugins.documents.service import (
    EXPORT_MEDIA_TYPES,
    DocumentsError,
    build_document_export,
    build_tree,
    load_pages,
)
from omniscribe.utils.security import SSRFCheckResult


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


# ---------------------------------------------------------------------------
# Task-3 review hardening pins
# ---------------------------------------------------------------------------


def test_build_tree_fabricates_zero_bboxes_and_classifies_headers() -> None:
    tree = build_tree({0: ["SECTION HEADING", "A body paragraph with many words."]})
    lines = tree.pages[0].children
    assert all(tuple(child.bbox) == (0.0, 0.0, 0.0, 0.0) for child in lines), (
        "zero bboxes expected on stored-artifact trees"
    )
    assert lines[0].block_type.name == "SECTION_HEADER"


def test_build_document_export_docling_and_mineru_metadata_none_pinned() -> None:
    docling = build_document_export(
        page_text={0: ["a"]}, metadata=None, export_format="docling"
    )
    assert isinstance(docling, dict)
    assert docling["metadata"] is None
    mineru = build_document_export(
        page_text={0: ["a"]}, metadata=None, export_format="mineru"
    )
    assert isinstance(mineru, dict)
    assert mineru["metadata"] is None


def test_build_document_export_unknown_format_raises_documents_error() -> None:
    with pytest.raises(DocumentsError) as excinfo:
        build_document_export(page_text={0: ["a"]}, metadata=None, export_format="pdf")
    assert excinfo.value.status_code == 400
    assert excinfo.value.error == "bad_request"


# ---------------------------------------------------------------------------
# Extraction runner
# ---------------------------------------------------------------------------


def _settings() -> RuntimeSettings:
    # Adapted from the plan draft: RuntimeSettings._require_non_empty rejects
    # an empty llm_api_key, so the helper uses a non-empty placeholder.
    return RuntimeSettings(
        llm_api_base="http://localhost:1234/v1",
        llm_api_key="lm-studio",
        llm_model="test-model",
    )


async def test_run_extraction_valid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm(**kwargs: object) -> str:
        captured.update(kwargs)
        return '{"vendor_name": "Acme"}'

    monkeypatch.setattr(documents_service, "call_llm", fake_call_llm)
    result = await documents_service.run_extraction(
        ExtractionRequest(text="Invoice from Acme, total 10 USD.", template="invoice"),  # type: ignore[arg-type]
        _settings(),
    )
    assert result == {"vendor_name": "Acme"}
    assert captured["model"] == "test-model"
    assert captured["api_base"] == "http://localhost:1234/v1"
    assert captured["system_prompt"] == documents_service.EXTRACTION_SYSTEM_MESSAGE
    prompt = captured["messages"][0]["content"]  # type: ignore[index]
    assert "'invoice_number'" in prompt
    assert "Invoice from Acme" in prompt


async def test_run_extraction_request_overrides_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Hermetic: patch the SSRF guard so the request-level api_base does not
    # hit real DNS (the only remaining real-DNS call site before this pin).
    monkeypatch.setattr(
        documents_service,
        "check_ssrf_target_sync",
        lambda url: SSRFCheckResult(
            allowed=True, resolved_ip="93.184.216.34", reason=None
        ),
    )
    captured: dict[str, object] = {}

    async def fake_call_llm(**kwargs: object) -> str:
        captured.update(kwargs)
        return "{}"

    monkeypatch.setattr(documents_service, "call_llm", fake_call_llm)
    await documents_service.run_extraction(
        ExtractionRequest(
            text="x",
            api_base="http://example.com/v1",
            api_key=" k ",
            model=" m ",
        ),
        _settings(),
    )
    assert captured["api_base"] == "http://example.com/v1"
    assert captured["api_key"] == "k"
    assert captured["model"] == "m"


async def test_run_extraction_invalid_json_returns_empty_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call_llm(**kwargs: object) -> str:
        return "not json at all"

    monkeypatch.setattr(documents_service, "call_llm", fake_call_llm)
    result = await documents_service.run_extraction(
        ExtractionRequest(text="x"), _settings()
    )
    assert result == {}


async def test_run_extraction_non_dict_json_returns_empty_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call_llm(**kwargs: object) -> str:
        return "[1, 2, 3]"

    monkeypatch.setattr(documents_service, "call_llm", fake_call_llm)
    result = await documents_service.run_extraction(
        ExtractionRequest(text="x"), _settings()
    )
    assert result == {}


async def test_run_extraction_empty_text_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_call_llm(**kwargs: object) -> str:
        raise AssertionError("LLM must not be called for empty text")

    monkeypatch.setattr(documents_service, "call_llm", fail_call_llm)
    result = await documents_service.run_extraction(
        ExtractionRequest(text="   "), _settings()
    )
    assert result == {}


async def test_run_extraction_ssrf_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_call_llm(**kwargs: object) -> str:
        raise AssertionError("LLM must not be called for blocked api_base")

    monkeypatch.setattr(documents_service, "call_llm", fail_call_llm)
    with pytest.raises(documents_service.DocumentsError) as excinfo:
        await documents_service.run_extraction(
            ExtractionRequest(
                text="x",
                # Cloud-metadata range: blocked even with ALLOW_SSRF_LOCAL=true.
                api_base="http://169.254.169.254/latest",
            ),
            _settings(),
        )
    assert excinfo.value.status_code == 403
    assert excinfo.value.error == "ssrf_blocked"


async def test_run_extraction_provider_failure_is_ai_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(**kwargs: object) -> str:
        raise RuntimeError("connection reset")

    monkeypatch.setattr(documents_service, "call_llm", boom)
    with pytest.raises(documents_service.DocumentsError) as excinfo:
        await documents_service.run_extraction(ExtractionRequest(text="x"), _settings())
    assert excinfo.value.status_code == 502
    assert excinfo.value.error == "ai_error"
