"""Tests for the OCR response builder — metadata redaction and headers.

Covers Phase 3 fix for report finding 1.8 (MEDIUM): page.metadata values
that flow into the ``X-Document-Quality`` / ``-Structure`` / ``-Sections``
response headers must not leak sensitive data and must not balloon the
header to multi-MB.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from omniscribe.api.services.ocr_response import (
    _METADATA_HEADER_FIELDS,
    _METADATA_VALUE_MAX_CHARS,
    _SENSITIVE_KEY_TOKENS,
    _TRUNCATED_SUFFIX,
    _document_metadata_header,
    _metadata_headers_from_pipeline,
    _redact_metadata,
)

# ---------------------------------------------------------------------------
# Test doubles — small in-memory stand-ins for the bits of OCRPipeline the
# response builder actually reads (``last_document_result.pages`` and
# ``page.metadata``).
# ---------------------------------------------------------------------------


class _FakePage:
    def __init__(self, page_index: int, metadata: dict | None) -> None:
        self.page_index = page_index
        self.metadata = metadata


class _FakeDocument:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages


class _FakePipeline:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.last_document_result = _FakeDocument(pages)


# ---------------------------------------------------------------------------
# Redaction helper — direct unit tests.
# ---------------------------------------------------------------------------


class TestRedactMetadata:
    def test_redacts_top_level_sensitive_key_preserves_others(self) -> None:
        """Spec test 1: top-level ``path`` becomes ``[redacted]`` and
        a non-sensitive sibling like ``quality_score`` survives."""
        result = _redact_metadata({"path": "/etc/passwd", "quality_score": 0.95})
        assert result == {"path": "[redacted]", "quality_score": 0.95}

    def test_truncates_long_string_to_cap_plus_marker(self) -> None:
        """Spec test 2: a 10 KiB string is truncated to 4 KiB + the
        ``\u2026[truncated]`` marker."""
        long_value = "x" * (10 * 1024)
        result = _redact_metadata({"body": long_value})
        body = result["body"]
        assert isinstance(body, str)
        assert body.endswith(_TRUNCATED_SUFFIX)
        assert body.startswith("x" * _METADATA_VALUE_MAX_CHARS)
        assert len(body) == _METADATA_VALUE_MAX_CHARS + len(_TRUNCATED_SUFFIX)
        # The original oversized value must not survive intact.
        assert body != long_value

    def test_recursively_redacts_nested_sensitive_key(self) -> None:
        """Spec test 3: a sensitive key nested inside a child dict is
        still redacted by the recursive walk."""
        result = _redact_metadata({"outer": {"file_path": "/etc/foo", "label": "ok"}})
        assert result == {"outer": {"file_path": "[redacted]", "label": "ok"}}

    def test_header_omitted_when_redacted_payload_empty(self) -> None:
        """Spec test 4: the X-Document-Quality header is omitted when
        no page carries that metadata (preserves the current
        short-circuit behavior in ``_document_metadata_header``)."""
        pipeline = _FakePipeline(
            [
                _FakePage(0, {"structure": {"foo": "bar"}}),
                _FakePage(1, None),
            ]
        )
        # No page has ``quality`` metadata → header is None → omitted.
        assert _document_metadata_header(pipeline, "quality") is None

    # ----- Defensive extras covering the same redaction surface -----

    def test_substring_match_redacts_underscored_key(self) -> None:
        """The ``key`` token is a substring — ``api_key`` / ``public_key``
        style names must be redacted too."""
        result = _redact_metadata({"api_key": "abc", "public_key": "xyz", "score": 1})
        assert result == {
            "api_key": "[redacted]",
            "public_key": "[redacted]",
            "score": 1,
        }

    def test_list_items_are_recursed_not_blindly_kept(self) -> None:
        """A list of dicts still walks into each element so a sensitive
        key in any element is redacted."""
        result = _redact_metadata(
            {"items": [{"token": "secret", "ok": 1}, {"token": "x"}]}
        )
        assert result == {
            "items": [
                {"token": "[redacted]", "ok": 1},
                {"token": "[redacted]"},
            ]
        }

    def test_string_at_or_below_cap_is_preserved_unchanged(self) -> None:
        """Boundary: strings shorter than the cap pass through with
        no truncation suffix."""
        result = _redact_metadata({"label": "a" * _METADATA_VALUE_MAX_CHARS})
        assert result["label"] == "a" * _METADATA_VALUE_MAX_CHARS
        assert not result["label"].endswith(_TRUNCATED_SUFFIX)

    def test_non_string_primitives_pass_through(self) -> None:
        """Numbers, bools, and None survive the walk unchanged — only
        strings are truncated, and only sensitive-keyed values are
        replaced with ``[redacted]``."""
        result = _redact_metadata(
            {
                "score": 0.5,
                "is_valid": True,
                "nothing": None,
                "path": 123,  # sensitive key, value type is not str
            }
        )
        assert result == {
            "score": 0.5,
            "is_valid": True,
            "nothing": None,
            "path": "[redacted]",
        }


# ---------------------------------------------------------------------------
# End-to-end: the redacted payload is what lands in the response header.
# ---------------------------------------------------------------------------


class TestDocumentMetadataHeaderEndToEnd:
    def test_header_payload_contains_redacted_field(self) -> None:
        pipeline = _FakePipeline(
            [
                _FakePage(
                    0,
                    {
                        "quality": {
                            "path": "/etc/passwd",
                            "filename": "leak.txt",
                            "score": 0.9,
                        }
                    },
                ),
                _FakePage(
                    1,
                    {
                        "quality": {
                            "score": 0.7,
                            "api_key": "abcdef",
                        }
                    },
                ),
            ]
        )
        header = _document_metadata_header(pipeline, "quality")
        assert header is not None
        decoded = json.loads(header)
        assert decoded == {
            "pages": [
                {
                    "page_index": 0,
                    "quality": {
                        "path": "[redacted]",
                        "filename": "[redacted]",
                        "score": 0.9,
                    },
                },
                {
                    "page_index": 1,
                    "quality": {
                        "score": 0.7,
                        "api_key": "[redacted]",
                    },
                },
            ]
        }

    def test_header_truncates_long_string_before_serialization(self) -> None:
        long_value = "A" * (10 * 1024)
        pipeline = _FakePipeline([_FakePage(0, {"quality": {"body": long_value}})])
        header = _document_metadata_header(pipeline, "quality")
        assert header is not None
        decoded = json.loads(header)
        body = decoded["pages"][0]["quality"]["body"]
        assert body.endswith(_TRUNCATED_SUFFIX)
        assert len(body) == _METADATA_VALUE_MAX_CHARS + len(_TRUNCATED_SUFFIX)

    def test_header_omitted_when_no_document(self) -> None:
        pipeline = SimpleNamespace(last_document_result=None)
        assert _document_metadata_header(pipeline, "quality") is None

    def test_metadata_headers_from_pipeline_skips_missing_fields(self) -> None:
        """Only the populated fields land in the header dict — the
        short-circuit per ``_METADATA_HEADER_FIELDS`` is preserved."""
        pipeline = _FakePipeline([_FakePage(0, {"structure": {"score": 0.5}})])
        headers = _metadata_headers_from_pipeline(pipeline)
        # Only ``structure`` is populated, not quality or sections.
        assert set(headers) == {"X-Document-Structure"}
        assert "X-Document-Quality" not in headers
        assert "X-Document-Sections" not in headers
        decoded = json.loads(headers["X-Document-Structure"])
        assert decoded == {"pages": [{"page_index": 0, "structure": {"score": 0.5}}]}


# ---------------------------------------------------------------------------
# Sanity: the module-level constants are well-formed.
# ---------------------------------------------------------------------------


class TestMetadataConstants:
    def test_value_max_chars_is_4kib(self) -> None:
        assert _METADATA_VALUE_MAX_CHARS == 4 * 1024

    def test_truncated_suffix_starts_with_ellipsis(self) -> None:
        # The marker uses U+2026 (\u2026), not three ASCII dots.
        assert _TRUNCATED_SUFFIX.startswith("\u2026")
        assert _TRUNCATED_SUFFIX == "\u2026[truncated]"

    def test_sensitive_tokens_include_required_terms(self) -> None:
        for required in ("path", "filename", "email", "token", "key"):
            assert required in _SENSITIVE_KEY_TOKENS

    @pytest.mark.parametrize("field", _METADATA_HEADER_FIELDS)
    def test_all_header_fields_have_redaction_path(self, field: str) -> None:
        """Every field in ``_METADATA_HEADER_FIELDS`` flows through
        :func:`_document_metadata_header` and therefore through
        :func:`_redact_metadata`."""
        pipeline = _FakePipeline([_FakePage(0, {field: {"path": "/leak", "ok": 1}})])
        header = _document_metadata_header(pipeline, field)
        assert header is not None
        decoded = json.loads(header)
        assert decoded["pages"][0][field]["path"] == "[redacted]"
