"""Tests for the persistent glossary library."""

from __future__ import annotations

from pathlib import Path

from local_deepl.core.glossary_library import (
    GlossaryLibrary,
    GlossaryNotFoundError,
)


def _new_library(tmp_path: Path) -> GlossaryLibrary:
    artifact = tmp_path / "artifacts"
    artifact.mkdir(exist_ok=True)
    return GlossaryLibrary(artifact_dir=artifact)


def test_save_round_trip(tmp_path: Path) -> None:
    lib = _new_library(tmp_path)
    stored = lib.save(
        name="Inline",
        format="json_pairs",
        entries=[{"source": "Hi", "target": "Salut"}],
        source_uri="inline",
        encoding="utf-8",
    )
    assert stored.id
    assert stored.format == "json_pairs"
    assert stored.source_uri == "inline"
    assert stored.encoding == "utf-8"

    # Restart: persistence must survive re-instantiation.
    lib2 = _new_library(tmp_path)
    fetched = lib2.get(stored.id)
    assert fetched is not None
    assert fetched.name == "Inline"
    assert fetched.entries[0]["source"] == "Hi"
    assert fetched.entries[0]["target"] == "Salut"


def test_save_rejects_empty_entries(tmp_path: Path) -> None:
    import pytest

    lib = _new_library(tmp_path)
    with pytest.raises(ValueError):
        lib.save(name="Empty", format="json_pairs", entries=[])


def test_toggle_disables_glossary(tmp_path: Path) -> None:
    lib = _new_library(tmp_path)
    stored = lib.save(
        name="g",
        format="json_pairs",
        entries=[{"source": "A", "target": "1"}],
    )
    updated = lib.toggle(stored.id, enabled=False)
    assert updated.enabled is False
    assert lib.get(stored.id).enabled is False


def test_toggle_unknown_id_raises(tmp_path: Path) -> None:
    import pytest

    lib = _new_library(tmp_path)
    with pytest.raises(GlossaryNotFoundError):
        lib.toggle("missing-id", enabled=False)


def test_delete_removes_entry(tmp_path: Path) -> None:
    lib = _new_library(tmp_path)
    stored = lib.save(
        name="g",
        format="json_pairs",
        entries=[{"source": "A", "target": "1"}],
    )
    assert lib.delete(stored.id) is True
    assert lib.get(stored.id) is None
    assert lib.delete(stored.id) is False


def test_reorder_assigns_descending_priority(tmp_path: Path) -> None:
    lib = _new_library(tmp_path)
    a = lib.save(
        name="a", format="json_pairs", entries=[{"source": "A", "target": "1"}]
    )
    b = lib.save(
        name="b", format="json_pairs", entries=[{"source": "B", "target": "2"}]
    )
    lib.reorder([b.id, a.id])
    by_id = {item.id: item for item in lib.items()}
    assert by_id[b.id].priority > by_id[a.id].priority


def test_reorder_unknown_raises(tmp_path: Path) -> None:
    import pytest

    lib = _new_library(tmp_path)
    with pytest.raises(GlossaryNotFoundError):
        lib.reorder(["missing"])


def test_reorder_duplicates_raise_value_error(tmp_path: Path) -> None:
    import pytest

    lib = _new_library(tmp_path)
    lib.save(name="a", format="json_pairs", entries=[{"source": "A", "target": "1"}])
    with pytest.raises(ValueError):
        lib.reorder(["x", "x"])


def test_merged_enabled_combines_glossaries(tmp_path: Path) -> None:
    lib = _new_library(tmp_path)
    lib.save(
        name="alpha",
        format="json_pairs",
        entries=[{"source": "Hello", "target": "Hola"}],
        priority=2,
    )
    lib.save(
        name="beta",
        format="json_pairs",
        entries=[{"source": "Hello", "target": "Bonjour"}],
        priority=1,
    )
    merged = lib.merged_enabled()
    targets = {e.source: e.target for e in merged.entries}
    # Last-wins (highest priority) means alpha overrides beta for "Hello".
    assert targets["Hello"] == "Hola"


def test_disabled_glossaries_excluded_from_merge(tmp_path: Path) -> None:
    lib = _new_library(tmp_path)
    stored = lib.save(
        name="only",
        format="json_pairs",
        entries=[{"source": "Hello", "target": "Hola"}],
    )
    lib.toggle(stored.id, enabled=False)
    merged = lib.merged_enabled()
    assert merged.entries == []


def test_preview_reports_conflicts(tmp_path: Path) -> None:
    lib = _new_library(tmp_path)
    lib.save(
        name="a",
        format="json_pairs",
        entries=[{"source": "Hello", "target": "Hola"}],
    )
    lib.save(
        name="b",
        format="json_pairs",
        entries=[{"source": "Hello", "target": "Bonjour"}],
    )
    preview = lib.preview()
    assert preview["count"] == 1
    assert preview["enabled_glossaries"] == ["a", "b"]
    assert any(conflict["source"] == "hello" for conflict in preview["conflicts"])


def test_persistence_file_created(tmp_path: Path) -> None:
    lib = _new_library(tmp_path)
    lib.save(
        name="g",
        format="json_pairs",
        entries=[{"source": "A", "target": "1"}],
    )
    assert lib.path.exists()
    assert lib.path.read_text(encoding="utf-8").strip().startswith("{")
