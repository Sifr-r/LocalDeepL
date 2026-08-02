"""CSV and TSV glossary source adapters."""

from __future__ import annotations

import csv
import io

from ._common import decode_source, entry_dict, finalize
from .summary import GlossaryImportSummary

_OPTIONAL_COLUMNS = frozenset({"case_sensitive", "notes", "group"})


def parse_csv_tsv(
    data: bytes,
    *,
    encoding: str | None = None,
    delimiter: str | None = None,
) -> GlossaryImportSummary:
    """Parse a delimited glossary with required source and target columns."""
    text, used_encoding, warnings = decode_source(data, encoding)
    chosen = delimiter or _detect_delimiter(text)
    if len(chosen) != 1:
        raise ValueError("CSV/TSV delimiter must be exactly one character.")
    format_name = "tsv" if chosen == "\t" else "csv"
    return _parse_delimited(
        text,
        delimiter=chosen,
        format_name=format_name,
        encoding=used_encoding,
        warnings=warnings,
    )


def parse_csv(
    data: bytes,
    *,
    encoding: str | None = None,
    delimiter: str | None = None,
) -> GlossaryImportSummary:
    """Parse comma-separated glossary pairs."""
    text, used_encoding, warnings = decode_source(data, encoding)
    return _parse_delimited(
        text,
        delimiter=delimiter or ",",
        format_name="csv",
        encoding=used_encoding,
        warnings=warnings,
    )


def parse_tsv(
    data: bytes,
    *,
    encoding: str | None = None,
    delimiter: str | None = None,
) -> GlossaryImportSummary:
    """Parse tab-separated glossary pairs."""
    text, used_encoding, warnings = decode_source(data, encoding)
    return _parse_delimited(
        text,
        delimiter=delimiter or "\t",
        format_name="tsv",
        encoding=used_encoding,
        warnings=warnings,
    )


def _parse_delimited(
    text: str,
    *,
    delimiter: str,
    format_name: str,
    encoding: str,
    warnings: tuple[str, ...],
) -> GlossaryImportSummary:
    if len(delimiter) != 1:
        raise ValueError("CSV/TSV delimiter must be exactly one character.")
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    if reader.fieldnames is None:
        raise ValueError("CSV/TSV source must include a header row.")

    normalized_headers: dict[str, str] = {}
    for raw_header in reader.fieldnames:
        if raw_header is None:
            continue
        clean = raw_header.lstrip("\ufeff").strip().lower()
        if clean:
            normalized_headers[clean] = raw_header
    missing = {"source", "target"} - normalized_headers.keys()
    if missing:
        required = ", ".join(sorted(missing))
        raise ValueError(f"CSV/TSV source is missing required column(s): {required}.")

    entries: list[dict[str, object]] = []
    skipped = 0
    for row in reader:
        item = entry_dict(
            row.get(normalized_headers["source"]),
            row.get(normalized_headers["target"]),
            case_sensitive=_optional_value(row, normalized_headers, "case_sensitive"),
            notes=_optional_value(row, normalized_headers, "notes"),
            group=_optional_value(row, normalized_headers, "group"),
        )
        if item is None:
            skipped += 1
        else:
            entries.append(item)

    result_warnings = list(warnings)
    if skipped:
        result_warnings.append(f"Skipped {skipped} row(s) with empty source or target.")
    return finalize(
        entries,
        format_name=format_name,
        encoding=encoding,
        warnings=tuple(result_warnings),
    )


def _optional_value(
    row: dict[str, str | None], headers: dict[str, str], name: str
) -> str | None:
    if name not in _OPTIONAL_COLUMNS:
        return None
    header = headers.get(name)
    return row.get(header) if header is not None else None


def _detect_delimiter(text: str) -> str:
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        return "\t" if "\t" in sample else ","
    return dialect.delimiter
