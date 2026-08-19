"""Legacy compatibility shim for the old :class:`GlossaryLibrary` API.

This module bridges the new :class:`LexiconStore` Protocol to the legacy
:class:`omniscribe.core.glossary_library.GlossaryLibrary` API surface so
that callers (the ``glossary_imports`` router, the preview endpoint, the
LangGraph translation graph) can migrate at their own pace.

Lives from Phase 1 (this commit) through Phase 5 (cleanup). Deleted in
Phase 5 alongside the underlying :class:`GlossaryLibrary` class.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from ..glossary import Glossary
from .store import GlossaryMeta, LexiconEntry, LexiconStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# StoredGlossary — legacy dataclass, preserved verbatim for the adapter.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StoredGlossary:
    """Legacy shape preserved by the adapter (see :class:`GlossaryLibrary`).

    DEPRECATED: new code should use :class:`GlossaryMeta` directly. Kept
    here so existing call sites (the ``glossary_imports`` router, the
    preview endpoint) can keep working through Phase 1-4.
    """

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

    def __post_init__(self) -> None:
        import warnings

        warnings.warn(
            "StoredGlossary is deprecated and will be removed in a future release. "
            "Use GlossaryMeta from omniscribe.core.lexicon instead.",
            DeprecationWarning,
            stacklevel=2,
        )


class GlossaryNotFoundError(KeyError):
    """Raised when a requested library glossary does not exist."""


# ---------------------------------------------------------------------------
# GlossaryLibraryAdapter
# ---------------------------------------------------------------------------


def _meta_to_stored(
    meta: GlossaryMeta, entries: tuple[dict[str, object], ...]
) -> StoredGlossary:
    return StoredGlossary(
        id=meta.id,
        name=meta.name,
        format=meta.format,
        source_uri=meta.source_uri,
        encoding=meta.encoding,
        entries=entries,
        enabled=meta.enabled,
        priority=meta.priority,
        group=meta.group,
        created_at=meta.created_at.timestamp(),
        updated_at=meta.updated_at.timestamp(),
    )


def _entry_to_dict(entry: LexiconEntry) -> dict[str, object]:
    """Flatten a :class:`LexiconEntry` to the legacy dict shape used by
    :class:`Glossary.from_dict` (and downstream prompt rendering).
    """
    return {
        "source": entry.source_text,
        "target": entry.target_text,
        "case_sensitive": entry.case_sensitive,
        "notes": entry.notes,
        "group": entry.glossary_id,  # legacy callers used "group" for some
    }


def _normalize_entries(entries: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """Mirror :meth:`GlossaryLibrary._normalize_entries` — drop empties, coerce."""
    normalized: list[dict[str, object]] = []
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        candidate = dict(raw)
        src = str(candidate.get("source", "")).strip()
        tgt = str(candidate.get("target", "")).strip()
        if not src or not tgt:
            continue
        candidate["source"] = src
        candidate["target"] = tgt
        normalized.append(candidate)
    return normalized


class GlossaryLibraryAdapter:
    """Adapter that exposes the old :class:`GlossaryLibrary` API on top of
    a :class:`LexiconStore`.

    Thread-safe — the underlying :class:`LexiconStore` is process-safe
    (LanceDB handles per-process locking), and the adapter adds its own
    ``threading.Lock`` for the atomic-rename operations (``reorder``)
    that span multiple glossary updates.

    DEPRECATED: will be removed in Phase 5 cleanup alongside the
    underlying :class:`GlossaryLibrary`.
    """

    def __init__(self, store: LexiconStore) -> None:
        import warnings

        warnings.warn(
            "GlossaryLibraryAdapter is deprecated and will be removed in a future release. "
            "Use LexiconStore directly.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._store = store
        self._lock = threading.Lock()

    # --- Read surface -------------------------------------------------------

    def items(self) -> list[StoredGlossary]:
        """Return all glossaries as :class:`StoredGlossary` (sorted by
        priority DESC, group, name — matches the legacy order).
        """
        metas = self._store.list_glossaries()
        result: list[StoredGlossary] = []
        for meta in metas:
            entries = self._store.list_entries(meta.id)
            dicts = tuple(_entry_to_dict(e) for e in entries)
            result.append(_meta_to_stored(meta, dicts))
        return result

    def get(self, glossary_id: str) -> StoredGlossary | None:
        meta = self._store.get_glossary(glossary_id)
        if meta is None:
            return None
        entries = self._store.list_entries(meta.id)
        return _meta_to_stored(meta, tuple(_entry_to_dict(e) for e in entries))

    # --- Write surface ------------------------------------------------------

    def save(
        self,
        *,
        name: str,
        format: str,
        entries: Iterable[dict[str, object]],
        source_uri: str | None = None,
        encoding: str | None = None,
        group: str = "default",
        priority: int = 0,
    ) -> StoredGlossary:
        meta = self._store.save_glossary(
            name=name,
            format=format,
            entries=entries,
            source_uri=source_uri,
            encoding=encoding,
            group=group,
            priority=priority,
        )
        # Read back the entries so the returned StoredGlossary carries them
        # (matches the legacy contract).
        return self.get(meta.id)  # type: ignore[return-value]

    def toggle(self, glossary_id: str, *, enabled: bool) -> StoredGlossary:
        with self._lock:
            meta = self._store.toggle_glossary(glossary_id, enabled=enabled)
            stored = self.get(meta.id)
            if stored is None:
                raise GlossaryNotFoundError(glossary_id)
            return stored

    def reorder(self, ordered_ids: Sequence[str]) -> None:
        with self._lock:
            self._store.reorder_glossaries(ordered_ids)

    def delete(self, glossary_id: str) -> bool:
        return self._store.delete_glossary(glossary_id)

    # --- Composition helpers -----------------------------------------------

    def merged_enabled(self) -> Glossary:
        return merged_enabled_glossary(self._store)

    def preview(self) -> dict[str, object]:
        return preview(self._store)


# ---------------------------------------------------------------------------
# Module-level composition helpers
# ---------------------------------------------------------------------------


def merged_enabled_glossary(store: LexiconStore) -> Glossary:
    """Build a fully-merged :class:`Glossary` from all enabled glossaries.

    Replacement for :meth:`GlossaryLibrary.merged_enabled`. The merge is
    last-wins (later entries override earlier ones), matching the legacy
    semantics. We sort by priority ASC so that the highest-priority
    glossary is the last writer and the effective winner.
    """
    import warnings

    warnings.warn(
        "merged_enabled_glossary is deprecated and will be removed in a future release.",
        DeprecationWarning,
        stacklevel=2,
    )
    metas = [m for m in store.list_glossaries() if m.enabled]
    metas.sort(key=lambda m: m.priority)  # low → high
    seen: dict[str, Any] = {}
    for meta in metas:
        for entry in store.list_entries(meta.id):
            key = entry.source_text.lower()
            seen[key] = entry
    merged = Glossary(entries=[_legacy_entry_from_lexicon(e) for e in seen.values()])
    merged.source_format = "library"
    return merged


def preview(store: LexiconStore) -> dict[str, object]:
    """Return a conflict-detection summary, matching the legacy ``preview()``.

    For every source term that appears in more than one enabled glossary,
    return the list of distinct target translations across those glossaries.
    """
    import warnings

    warnings.warn(
        "preview is deprecated and will be removed in a future release.",
        DeprecationWarning,
        stacklevel=2,
    )
    metas = [m for m in store.list_glossaries() if m.enabled]
    by_source: dict[str, list[tuple[str, str]]] = {}
    for meta in metas:
        for entry in store.list_entries(meta.id):
            source = entry.source_text.strip()
            if not source:
                continue
            by_source.setdefault(source.casefold(), []).append(
                (meta.name, entry.target_text)
            )

    conflicts: list[dict[str, object]] = []
    for source_key, values in sorted(by_source.items()):
        if len({name for name, _target in values}) < 2:
            continue
        targets: list[str] = []
        for _name, target in values:
            if target not in targets:
                targets.append(target)
        conflicts.append({"source": source_key, "targets": targets})

    return {
        "count": sum(len(store.list_entries(m.id)) for m in metas),
        "conflicts": conflicts,
        "enabled_glossaries": [m.name for m in metas],
    }


def _legacy_entry_from_lexicon(entry: LexiconEntry) -> Any:
    """Build a :class:`GlossaryEntry` from a :class:`LexiconEntry`."""
    from ..glossary import GlossaryEntry

    return GlossaryEntry(
        source=entry.source_text,
        target=entry.target_text,
        case_sensitive=entry.case_sensitive,
        notes=entry.notes,
    )


__all__ = [
    "GlossaryLibraryAdapter",
    "GlossaryNotFoundError",
    "StoredGlossary",
    "merged_enabled_glossary",
    "preview",
]
