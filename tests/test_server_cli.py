"""Tests for the ``omniscribe-server`` CLI flags (audit A-28)."""

from __future__ import annotations

import pytest

from omniscribe import server


def _parse(value: str) -> int:
    return server._parse_workers(value)


def test_parse_workers_accepts_one():
    assert _parse("1") == 1


def test_parse_workers_accepts_multiple():
    assert _parse("8") == 8


def test_parse_workers_rejects_non_integer():
    with pytest.raises(Exception, match="workers must be an integer"):
        _parse("eight")


def test_parse_workers_rejects_zero():
    with pytest.raises(Exception, match="workers must be between 1 and 64"):
        _parse("0")


def test_parse_workers_rejects_negative():
    with pytest.raises(Exception, match="workers must be between 1 and 64"):
        _parse("-1")


def test_parse_workers_rejects_too_large():
    with pytest.raises(Exception, match="workers must be between 1 and 64"):
        _parse("999999")


def test_main_rejects_reload_with_multiple_workers(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit):
        server.main(["--reload", "--workers", "4"])
    captured = capsys.readouterr()
    assert "--reload cannot be combined with --workers > 1" in captured.err
