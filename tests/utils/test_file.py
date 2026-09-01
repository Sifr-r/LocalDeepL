"""``utils.file.write_atomic`` — temp-file-then-rename with fsync.

Pedantic 3.16 / coverage gap: the function had zero direct tests
(it is re-exported from ``omniscribe.utils.__init__`` and called
from a handful of plugin paths, but none of them exercised the
error path or the JSON-encoding branch). Coverage was 29% in the
fast tier, dragging the project total under the 85% gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omniscribe.utils.file import write_atomic


def test_write_atomic_string(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    write_atomic(target, "hello world")
    assert target.read_text(encoding="utf-8") == "hello world"


def test_write_atomic_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deeper" / "out.txt"
    write_atomic(target, "x")
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == "x"


def test_write_atomic_json_mapping(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    payload = {"b": 2, "a": 1, "nested": {"k": "v"}}
    write_atomic(target, payload)
    # json.dump with sort_keys=True gives a stable shape; the
    # function is documented to use ensure_ascii=False so unicode
    # survives as-is.
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk == payload
    raw = target.read_text(encoding="utf-8")
    # sort_keys=True means the ``a`` key appears before ``b``.
    assert raw.index('"a"') < raw.index('"b"')
    # ensure_ascii=False keeps non-ASCII as-is.
    target.write_text('{"k": "café"}', encoding="utf-8")
    write_atomic(target, {"k": "café"})
    assert "café" in target.read_text(encoding="utf-8")


def test_write_atomic_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    target.write_text("old", encoding="utf-8")
    write_atomic(target, "new")
    assert target.read_text(encoding="utf-8") == "new"


def test_write_atomic_cleans_up_tmp_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If ``os.replace`` fails after the temp file was written,
    the helper must unlink the orphan temp so the next call
    starts clean. The cleanup is the documented failure contract.
    """
    target = tmp_path / "out.txt"

    real_replace = __import__("os").replace
    calls = {"n": 0}

    def boom(src: str, dst: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated replace failure")
        real_replace(src, dst)

    monkeypatch.setattr("os.replace", boom)

    with pytest.raises(OSError, match="simulated replace failure"):
        write_atomic(target, "data")

    # The target was never created (the replace failed) and the
    # orphan temp file was unlinked by the except branch.
    assert not target.exists()
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith("tmp_atomic")]
    assert leftovers == []
