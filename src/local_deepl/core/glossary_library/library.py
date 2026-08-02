"""Persistent named glossary library."""

from __future__ import annotations

import copy
import json
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from local_deepl.core.glossary import Glossary
from local_deepl.utils import write_atomic


@dataclass(frozen=True, slots=True)
class StoredGlossary:
    id: str
    name: str
    format: str
    source_uri: str | None = None
    encoding: str | None = None
    entries: tuple[dict[str, object], ...] = ()
    enabled: bool = True
    priority: int = 0
    group: str = "default"
    created_at: float = 0.0
    updated_at: float = 0.0


class GlossaryNotFoundError(KeyError):
    """Raised when a requested library glossary does not exist."""


class GlossaryLibrary:
    """Thread-safe JSON-on-disk glossary collection."""

    def __init__(
        self,
        *,
        artifact_dir: Path,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._artifact_dir = Path(artifact_dir).expanduser().resolve()
        self._library_dir = self._artifact_dir / "glossary_library"
        self._path = self._library_dir / "library.json"
        self._clock = clock or time.time
        self._lock = threading.Lock()
        self._items: dict[str, StoredGlossary] = {}
        self._load()

    @property
    def path(self) -> Path:
        """Return the canonical persistence path."""
        return self._path

    def items(self) -> list[StoredGlossary]:
        with self._lock:
            copied: list[StoredGlossary] = []
            for item in self._sorted_items():
                copied_item = self._copy_item(item)
                if copied_item is not None:
                    copied.append(copied_item)
            return copied

    def get(self, glossary_id: str) -> StoredGlossary | None:
        with self._lock:
            item = self._items.get(str(glossary_id))
            return self._copy_item(item) if item is not None else None

    def save(
        self,
        *,
        name: str,
        format: str,
        entries: Iterable[Mapping[str, object]],
        source_uri: str | None = None,
        encoding: str | None = None,
        group: str = "default",
        priority: int = 0,
    ) -> StoredGlossary:
        clean_name = str(name).strip()
        clean_format = str(format).strip().lower()
        clean_group = str(group).strip() or "default"
        if not clean_name:
            raise ValueError("Glossary name is required.")
        if len(clean_name) > 200:
            raise ValueError("Glossary name must be at most 200 characters.")
        if not clean_format:
            raise ValueError("Glossary format is required.")
        if isinstance(priority, bool):
            raise ValueError("Glossary priority must be an integer.")
        try:
            clean_priority = int(priority)
        except (TypeError, ValueError) as exc:
            raise ValueError("Glossary priority must be an integer.") from exc
        normalized_entries: tuple[dict[str, object], ...] = tuple(
            self._normalize_entries(entries)
        )
        if not normalized_entries:
            raise ValueError("Glossary must contain at least one valid entry.")

        now = float(self._clock())
        item = StoredGlossary(
            id=uuid.uuid4().hex,
            name=clean_name,
            format=clean_format,
            source_uri=str(source_uri) if source_uri else None,
            encoding=str(encoding) if encoding else None,
            entries=normalized_entries,
            enabled=True,
            priority=clean_priority,
            group=clean_group,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._items[item.id] = item
            self._write_unlocked()
        copied = self._copy_item(item)
        assert copied is not None
        return copied

    def toggle(self, glossary_id: str, *, enabled: bool) -> StoredGlossary:
        with self._lock:
            item = self._require_unlocked(glossary_id)
            updated = replace(
                item, enabled=bool(enabled), updated_at=float(self._clock())
            )
            self._items[item.id] = updated
            self._write_unlocked()
            copied = self._copy_item(updated)
            assert copied is not None
            return copied

    def reorder(self, ordered_ids: Sequence[str]) -> None:
        ordered_list = list(ordered_ids)
        if not ordered_list:
            return
        with self._lock:
            current = self._sorted_items()
            current_ids = {item.id for item in current}
            requested = [str(item_id) for item_id in ordered_list]
            if len(requested) != len(set(requested)):
                raise ValueError("ordered_ids must not contain duplicates.")
            unknown = set(requested) - current_ids
            if unknown:
                raise GlossaryNotFoundError(next(iter(unknown)))
            final_ids = [item_id for item_id in requested if item_id in current_ids]
            final_ids += [item.id for item in current if item.id not in requested]
            total = len(final_ids)
            now = float(self._clock())
            for index, item_id in enumerate(final_ids):
                item = self._items[item_id]
                self._items[item_id] = replace(
                    item,
                    priority=total - index,
                    updated_at=now,
                )
            self._write_unlocked()

    def delete(self, glossary_id: str) -> bool:
        with self._lock:
            if str(glossary_id) not in self._items:
                return False
            del self._items[str(glossary_id)]
            self._write_unlocked()
            return True

    def merged_enabled(self) -> Glossary:
        with self._lock:
            enabled = [item for item in self._sorted_items() if item.enabled]
            # Glossary.merge is last-wins; feed low priority first so the
            # highest priority glossary is the effective winner.
            enabled_for_merge = list(reversed(enabled))
            glossaries = [
                Glossary.from_dict({"entries": list(item.entries)})
                for item in enabled_for_merge
            ]
            merged = Glossary.merge(glossaries)
            merged.source_format = "library"
            return merged

    def preview(self) -> dict[str, object]:
        with self._lock:
            enabled = [item for item in self._sorted_items() if item.enabled]
            by_source: dict[str, list[tuple[str, object]]] = {}
            for item in enabled:
                for entry in item.entries:
                    source = str(entry.get("source", "")).strip()
                    target = entry.get("target", "")
                    if source:
                        by_source.setdefault(source.casefold(), []).append(
                            (item.name, target)
                        )
            conflicts: list[dict[str, object]] = []
            for source_key, values in sorted(by_source.items()):
                if len({name for name, _target in values}) < 2:
                    continue
                targets: list[object] = []
                for _name, target in values:
                    if target not in targets:
                        targets.append(target)
                conflicts.append({"source": source_key, "targets": targets})
            merged = self._merged_unlocked(enabled)
            return {
                "count": len(merged.entries),
                "conflicts": conflicts,
                "enabled_glossaries": [item.name for item in enabled],
            }

    def _load(self) -> None:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return
        raw_items_raw: Any = (
            payload.get("glossaries", []) if isinstance(payload, dict) else payload
        )
        if not isinstance(raw_items_raw, list):
            return
        raw_items = raw_items_raw
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            try:
                item = self._item_from_mapping(raw)
            except (TypeError, ValueError):
                continue
            self._items[item.id] = item

    def _item_from_mapping(self, raw: Mapping[str, Any]) -> StoredGlossary:
        raw_entries = raw.get("entries", [])
        if not isinstance(raw_entries, (list, tuple)):
            raise ValueError("entries must be a list")
        entries = tuple(self._normalize_entries(raw_entries))
        return StoredGlossary(
            id=str(raw["id"]),
            name=str(raw["name"]),
            format=str(raw.get("format", "json_pairs")),
            source_uri=_optional_text(raw.get("source_uri")),
            encoding=_optional_text(raw.get("encoding")),
            entries=entries,
            enabled=bool(raw.get("enabled", True)),
            priority=int(raw.get("priority", 0)),
            group=str(raw.get("group", "default")) or "default",
            created_at=float(raw.get("created_at", 0.0)),
            updated_at=float(raw.get("updated_at", 0.0)),
        )

    def _normalize_entries(
        self, entries: Iterable[Mapping[str, object]]
    ) -> list[dict[str, object]]:
        normalized: list[dict[str, object]] = []
        for raw in entries:
            if not isinstance(raw, Mapping):
                continue
            candidate = dict(raw)
            glossary = Glossary.from_dict({"entries": [candidate]})
            if not glossary.entries:
                continue
            item = glossary.entries[0].to_dict()
            if candidate.get("group"):
                item["group"] = str(candidate["group"])
            normalized.append(item)
        return normalized

    def _sorted_items(self) -> list[StoredGlossary]:
        return sorted(
            self._items.values(),
            key=lambda item: (
                -item.priority,
                item.group.casefold(),
                item.name.casefold(),
                item.id,
            ),
        )

    def _merged_unlocked(self, enabled: list[StoredGlossary]) -> Glossary:
        return Glossary.merge(
            [
                Glossary.from_dict({"entries": list(item.entries)})
                for item in reversed(enabled)
            ]
        )

    def _require_unlocked(self, glossary_id: str) -> StoredGlossary:
        item = self._items.get(str(glossary_id))
        if item is None:
            raise GlossaryNotFoundError(str(glossary_id))
        return item

    def _write_unlocked(self) -> None:
        payload = {
            "glossaries": [self._serialize(item) for item in self._items.values()]
        }
        write_atomic(self._path, payload, prefix=".glossary_library.")

    @staticmethod
    def _serialize(item: StoredGlossary) -> dict[str, object]:
        return {
            "id": item.id,
            "name": item.name,
            "format": item.format,
            "source_uri": item.source_uri,
            "encoding": item.encoding,
            "entries": [copy.deepcopy(entry) for entry in item.entries],
            "enabled": item.enabled,
            "priority": item.priority,
            "group": item.group,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    @staticmethod
    def _copy_item(item: StoredGlossary | None) -> StoredGlossary | None:
        if item is None:
            return None
        return replace(
            item, entries=tuple(copy.deepcopy(entry) for entry in item.entries)
        )


def _optional_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)
