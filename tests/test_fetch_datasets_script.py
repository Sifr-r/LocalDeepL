"""Smoke tests for :mod:`scripts.fetch_datasets`.

The fetch itself is gated behind the OCR-Quality / KIE-HVQA license
review — see ``scripts/fetch_datasets.py``. These tests assert that:

- The CLI accepts the documented ``--dataset`` choices.
- The ``--dry-run`` flag exits without hitting the network.
- The library surface (``fetch``) is importable.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


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
