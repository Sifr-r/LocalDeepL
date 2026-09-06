"""Verification that re-homed PDF test fixtures exist (remediation plan §6.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import EXAMPLE_PDF_NAMES

ROOT = Path(__file__).resolve().parents[2]
FIXTURES_PDF_DIR = ROOT / "tests" / "fixtures" / "pdfs"


def test_fixtures_pdfs_directory_exists() -> None:
    assert FIXTURES_PDF_DIR.is_dir(), f"Missing fixtures directory: {FIXTURES_PDF_DIR}"


@pytest.mark.parametrize("filename", EXAMPLE_PDF_NAMES)
def test_fixture_pdf_present(filename: str) -> None:
    path = FIXTURES_PDF_DIR / filename
    assert path.is_file(), f"Missing fixture PDF: {filename} in {FIXTURES_PDF_DIR}"
    assert path.stat().st_size > 0, f"Fixture PDF is empty: {filename}"
