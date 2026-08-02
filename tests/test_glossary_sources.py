"""Tests for the multi-source glossary parsers.

Each parser returns a `GlossaryImportSummary` that flows into
`Glossary.from_dict` so we can verify the IR converges on the same shape.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omniscribe.core.glossary import Glossary
from omniscribe.core.glossary_sources import (
    FormatNotAvailableError,
    GlossaryImportLimitError,
    parse,
    redact_dsn,
)

FIXTURES = Path(__file__).parent / "fixtures" / "glossary"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_parse_csv_pairs() -> None:
    summary = parse(format="csv", data=_read("pairs.csv"))
    assert summary.format == "csv"
    assert len(summary.entries) == 4
    by_source = {entry["source"]: entry["target"] for entry in summary.entries}
    assert by_source["Hello"] == "Hola"
    assert by_source["Acme Corp"] == "Acme Sociedad"


def test_parse_tsv_pairs() -> None:
    summary = parse(format="tsv", data=_read("pairs.tsv"))
    assert summary.format == "tsv"
    assert len(summary.entries) == 3
    targets = {entry["source"]: entry["target"] for entry in summary.entries}
    assert targets["Hello"] == "Hola"
    assert targets["World"] == "Mundo"


def test_parse_xliff_minimal() -> None:
    summary = parse(format="xliff", data=_read("xliff_minimal.xlf"))
    assert summary.format == "xliff"
    pairs = {entry["source"]: entry["target"] for entry in summary.entries}
    assert pairs["Hello"] == "Hola"
    assert pairs["Goodbye"] == "Adi\u00f3s"


def test_parse_tbx_minimal() -> None:
    summary = parse(format="tbx", data=_read("tbx_minimal.tbx"))
    assert summary.format == "tbx"
    pairs = {entry["source"]: entry["target"] for entry in summary.entries}
    assert pairs["Hello"] == "Hola"


def test_parse_tmx_minimal() -> None:
    summary = parse(format="tmx", data=_read("tmx_minimal.tmx"))
    assert summary.format == "tmx"
    pairs = {entry["source"]: entry["target"] for entry in summary.entries}
    assert pairs["Hello"] == "Hola"


def test_parse_json_pairs_routes_via_glossary() -> None:
    summary = parse(format="json_pairs", data=_read("json_pairs.json"))
    assert summary.format == "json_pairs"
    assert len(summary.entries) == 3
    by_source = {entry["source"]: entry["target"] for entry in summary.entries}
    assert by_source["FastAPI"] == "FastAPI"


def test_parse_dispatches_inline_json_text() -> None:
    payload = json.dumps(
        {
            "entries": [
                {"source": "Hi", "target": "Salut"},
            ]
        }
    ).encode("utf-8")
    summary = parse(format="json_pairs", data=payload)
    assert summary.entries[0]["source"] == "Hi"
    assert summary.entries[0]["target"] == "Salut"


def test_parse_unknown_format_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse(format="not_a_format", data=b"foo")


def test_parse_missing_data_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse(format="csv")


def test_max_entries_zero_rejected() -> None:
    with pytest.raises(ValueError):
        parse(format="csv", data=_read("pairs.csv"), max_entries=0)


def test_max_entries_over_limit_raises_413() -> None:
    with pytest.raises(GlossaryImportLimitError) as excinfo:
        parse(format="csv", data=_read("pairs.csv"), max_entries=2)
    assert excinfo.value.limit == 2


def test_parsers_yield_glossary_compatible_dicts() -> None:
    """Every entry list must round-trip through `Glossary.from_dict`."""
    for fmt, fname in (
        ("csv", "pairs.csv"),
        ("tsv", "pairs.tsv"),
        ("xliff", "xliff_minimal.xlf"),
        ("tbx", "tbx_minimal.tbx"),
        ("tmx", "tmx_minimal.tmx"),
        ("json_pairs", "json_pairs.json"),
    ):
        summary = parse(format=fmt, data=_read(fname))
        glossary = Glossary.from_dict({"entries": summary.entries})
        assert glossary.entries, f"{fmt} produced no entries"


def test_format_not_available_error_is_import_error() -> None:
    """`FormatNotAvailableError` must be an ImportError subclass so callers
    can distinguish missing optional dependencies from bad input."""
    assert issubclass(FormatNotAvailableError, ImportError)


def test_redact_dsn_masks_credentials() -> None:
    assert "user:secret@" not in redact_dsn("postgres://user:secret@host/db")
    assert "***" in redact_dsn("postgres://user:secret@host/db")
    # Password-like query params also get scrubbed.
    assert "password=***" in redact_dsn("postgres://host/db?password=top")
