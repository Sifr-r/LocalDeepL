"""Unit tests for the glossary plugin schemas (verbatim old-contract pins)."""

from __future__ import annotations

import pydantic
import pytest

from omniscribe.plugins.glossary.schemas import (
    GlossaryFormat,
    GlossaryImportJobResponse,
    GlossaryImportSource,
    GlossaryReorderRequest,
)


def test_format_enum_vocabulary() -> None:
    assert {member.value for member in GlossaryFormat} == {
        "csv",
        "tsv",
        "xliff",
        "tbx",
        "tmx",
        "git_glossary",
        "sql_table",
        "json_pairs",
    }


def test_import_source_defaults_match_old_contract() -> None:
    source = GlossaryImportSource(format=GlossaryFormat.CSV)
    assert source.git_ref == "HEAD"
    assert source.git_path == "GLOSSARY.md"
    assert source.sql_source_col == "source"
    assert source.sql_target_col == "target"
    assert source.max_entries is None
    assert source.name is None


def test_import_source_strips_optional_strings() -> None:
    source = GlossaryImportSource(
        format=GlossaryFormat.CSV, name="  Pairs  ", encoding=" utf-8 "
    )
    assert source.name == "Pairs"
    assert source.encoding == "utf-8"


def test_import_source_rejects_unknown_fields() -> None:
    with pytest.raises(pydantic.ValidationError):
        GlossaryImportSource.model_validate({"format": "csv", "mystery": 1})


def test_max_entries_bounds() -> None:
    with pytest.raises(pydantic.ValidationError):
        GlossaryImportSource(format=GlossaryFormat.CSV, max_entries=0)
    with pytest.raises(pydantic.ValidationError):
        GlossaryImportSource(format=GlossaryFormat.CSV, max_entries=1_000_001)


def test_import_job_response_shape() -> None:
    sync = GlossaryImportJobResponse(
        glossary_id="g1",
        format=GlossaryFormat.JSON_PAIRS,
        name="N",
        entry_count=1,
        warnings=[],
        queued=False,
    )
    assert sync.job_id is None
    queued = GlossaryImportJobResponse(
        job_id="j-1",
        format=GlossaryFormat.CSV,
        name="N",
        entry_count=0,
        warnings=[],
        queued=True,
    )
    assert queued.glossary_id is None


def test_reorder_request_bounds() -> None:
    with pytest.raises(pydantic.ValidationError):
        GlossaryReorderRequest(ordered_ids=[str(i) for i in range(201)])
