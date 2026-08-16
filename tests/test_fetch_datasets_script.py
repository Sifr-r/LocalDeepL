"""Smoke tests for :mod:`scripts.fetch_datasets`.

The fetch itself is gated behind the OCR-Quality / KIE-HVQA license
review — see ``scripts/fetch_datasets.py``. These tests assert that:

- The CLI accepts the documented ``--dataset`` choices.
- The ``--dry-run`` flag exits without hitting the network.
- A license-gated real fetch exits with the dedicated
  ``EXIT_LICENSE_GATED`` code (nightly CI treats only that code as a
  clean skip; any other non-zero exit fails the job).
- The library surface (``fetch``) is importable.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _load_fetch_datasets():
    spec = importlib.util.spec_from_file_location(
        "_fetch_datasets_under_test", SCRIPTS_DIR / "fetch_datasets.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_is_runnable_help():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "fetch_datasets.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "ocr-quality" in result.stdout
    assert "kie-hvqa" in result.stdout


@pytest.mark.parametrize("dataset", ["ocr-quality", "kie-hvqa"])
def test_dry_run_exits_cleanly(dataset: str):
    # ``--dry-run`` must succeed without network access so CI can
    # exercise the CLI without a real dataset download.
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "fetch_datasets.py"),
            "--dataset",
            dataset,
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_unknown_dataset_exits_nonzero():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "fetch_datasets.py"),
            "--dataset",
            "unknown-dataset",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0


@pytest.mark.parametrize("dataset", ["ocr-quality", "kie-hvqa"])
def test_license_gated_fetch_exits_with_dedicated_code(dataset: str):
    """A real (non-dry-run) fetch must exit ``EXIT_LICENSE_GATED`` (77).

    Nightly CI uses this code to tell "expected license-gated skip"
    apart from genuine breakage — a generic error exit would either
    fail every nightly run or get swallowed by an ``|| true`` escape
    hatch (audit P3-12).
    """
    expected = _load_fetch_datasets().EXIT_LICENSE_GATED
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "fetch_datasets.py"),
            "--dataset",
            dataset,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected, result.stderr
    # The gate must not leave a partial fixture behind.
    suffix = (
        "ocr_quality_full.json" if dataset == "ocr-quality" else "kie_hvqa_full.json"
    )
    assert not (
        SCRIPTS_DIR.parent / "tests" / "fixtures" / "datasets" / suffix
    ).exists()
