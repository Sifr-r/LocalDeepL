"""Phase 3d tests — ArtifactStoreProjection + dual-write shim.

Covers:

1. Empty log → empty list / ``None`` get.
2. Single ``artifact.created`` event → one record with the right
   handle-shaped fields.
3. Two events for the same ``artifact_id`` (re-put) → the second
   overwrites the first, matching :meth:`TextArtifactStore.put`
   semantics.
4. Two events for different ``artifact_id`` → both appear in
   ``list()``, newest first.
5. Newest-first ordering is stable when timestamps collide
   (same-monotonic-tick regression coverage, mirroring
   :class:`JobHistoryProjection`).
6. ``get(artifact_id)`` returns the matching handle, or ``None``
   for an unknown id.
7. The dual-write shim: calling :meth:`TextArtifactStore.put` (and
   :meth:`TextArtifactStore.create`) emits an
   :class:`ArtifactCreatedEvent` to the plugin context with the
   correct ``kind`` (text / metadata / export).
8. The projection's output shape matches the legacy
   :class:`TextArtifactHandle` field-for-field for the four
   fields both expose (``artifact_id`` / ``token`` / ``path`` /
   ``expires_at``).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from omniscribe.api.plugin import (
    ArtifactStoreProjection,
    InMemoryLogStore,
    PluginContext,
    in_memory_session_log_provider,
)
from omniscribe.api.plugin.session_log import LogEvent
from omniscribe.api.services.artifacts import TextArtifactHandle, TextArtifactStore

# -- Empty log --------------------------------------------------------------


def test_empty_log_yields_empty_list() -> None:
    log = InMemoryLogStore()
    proj = ArtifactStoreProjection(log)
    assert proj.list() == []


def test_empty_log_get_returns_none() -> None:
    log = InMemoryLogStore()
    proj = ArtifactStoreProjection(log)
    assert proj.get("nonexistent") is None


# -- Single event -----------------------------------------------------------


def test_single_artifact_event_yields_handle_dict() -> None:
    log = InMemoryLogStore()
    log.append(
        LogEvent(
            kind="artifact.created",
            payload={
                "artifact_id": "a" * 32,
                "kind": "text",
                "token": "tok-1",
                "path": "/tmp/text_a.json",
                "expires_at": 1700000000.0,
                "created_at": "2026-08-17T10:00:00+00:00",
            },
        )
    )
    proj = ArtifactStoreProjection(log)
    records = proj.list()
    assert len(records) == 1
    rec = records[0]
    assert rec["artifact_id"] == "a" * 32
    assert rec["kind"] == "text"
    assert rec["token"] == "tok-1"
    assert rec["path"] == "/tmp/text_a.json"
    assert rec["expires_at"] == 1700000000.0
    assert rec["created_at"] == "2026-08-17T10:00:00+00:00"
    # Internal sort key must be stripped.
    assert "__sort_key" not in rec
    assert "__position" not in rec


def test_get_returns_matching_handle() -> None:
    log = InMemoryLogStore()
    for i in range(3):
        log.append(
            LogEvent(
                kind="artifact.created",
                payload={
                    "artifact_id": f"a{i}" + "0" * 29,
                    "kind": "text",
                    "token": f"tok-{i}",
                    "path": f"/tmp/text_{i}.json",
                    "expires_at": 1700000000.0 + i,
                },
            )
        )
    proj = ArtifactStoreProjection(log)
    rec = proj.get("a1" + "0" * 29)
    assert rec is not None
    assert rec["token"] == "tok-1"
    assert rec["path"] == "/tmp/text_1.json"


# -- Re-put overwrites previous event ---------------------------------------


def test_reput_overwrites_previous_event() -> None:
    """Two events for the same artifact_id → second wins, matches
    :meth:`TextArtifactStore.put` semantics (a re-put replaces
    the entry)."""
    log = InMemoryLogStore()
    aid = "a" * 32
    log.append(
        LogEvent(
            kind="artifact.created",
            payload={
                "artifact_id": aid,
                "kind": "text",
                "token": "tok-old",
                "path": "/tmp/old.json",
                "expires_at": 1700000000.0,
            },
        )
    )
    log.append(
        LogEvent(
            kind="artifact.created",
            payload={
                "artifact_id": aid,
                "kind": "text",
                "token": "tok-new",
                "path": "/tmp/new.json",
                "expires_at": 1700001000.0,
            },
        )
    )
    proj = ArtifactStoreProjection(log)
    records = proj.list()
    assert len(records) == 1
    assert records[0]["token"] == "tok-new"
    assert records[0]["path"] == "/tmp/new.json"
    assert records[0]["expires_at"] == 1700001000.0
    # ``get`` returns the latest too.
    assert proj.get(aid)["token"] == "tok-new"


# -- Newest-first ordering --------------------------------------------------


def test_newest_first_ordering() -> None:
    log = InMemoryLogStore()
    for i in range(3):
        log.append(
            LogEvent(
                kind="artifact.created",
                payload={
                    "artifact_id": f"a{i}" + "0" * 29,
                    "kind": "text",
                    "token": f"tok-{i}",
                    "path": f"/tmp/{i}.json",
                    "expires_at": 0.0,
                },
            )
        )
    proj = ArtifactStoreProjection(log)
    records = proj.list()
    assert [r["artifact_id"] for r in records] == [
        "a2" + "0" * 29,
        "a1" + "0" * 29,
        "a0" + "0" * 29,
    ]


def test_newest_first_stable_for_same_timestamp() -> None:
    """Same-monotonic-tick regression: when two events have the
    same timestamp (fast test scenario), insertion order is the
    tiebreaker. Mirrors the JobHistoryProjection regression."""
    log = InMemoryLogStore()
    fixed_ts = 12345.0
    for i in range(3):
        ev = LogEvent(
            kind="artifact.created",
            payload={
                "artifact_id": f"a{i}" + "0" * 29,
                "kind": "text",
                "token": f"tok-{i}",
                "path": f"/tmp/{i}.json",
                "expires_at": 0.0,
            },
        )
        # Force the same monotonic timestamp for all three.
        object.__setattr__(ev, "timestamp", fixed_ts)
        log.append(ev)
    proj = ArtifactStoreProjection(log)
    records = proj.list()
    # Newest by insertion order: a2, a1, a0.
    assert [r["artifact_id"] for r in records] == [
        "a2" + "0" * 29,
        "a1" + "0" * 29,
        "a0" + "0" * 29,
    ]


# -- Dual-write shim --------------------------------------------------------


def _mount_log() -> tuple[InMemoryLogStore, Any]:
    """Mount an in-memory log on a fresh plugin context, set it as
    the live context, and return ``(log, ctx)``."""
    from omniscribe.api.plugin import runtime

    log = InMemoryLogStore()
    ctx = PluginContext("test")
    ctx.mount(in_memory_session_log_provider(log=log, name="memory"))
    runtime.set_plugin_context(ctx)
    return log, ctx


def test_text_artifact_store_put_emits_event(tmp_path: Path) -> None:
    """``put`` on a text-kind store emits ``artifact.created`` with kind=text."""
    log, _ = _mount_log()
    store = TextArtifactStore(artifact_dir=tmp_path, kind="text")
    aid = "a" * 32
    token = store.issue_token()
    handle = store.put(artifact_id=aid, token=token, path=tmp_path / "text_a.json")
    # The file may or may not exist on disk depending on the
    # implementation, but the event must be in the log.
    events = log.list()
    assert len(events) == 1
    assert events[0].kind == "artifact.created"
    assert events[0].payload["artifact_id"] == aid
    assert events[0].payload["kind"] == "text"
    assert events[0].payload["token"] == handle.token
    assert events[0].payload["path"] == handle.path
    assert events[0].payload["expires_at"] == handle.expires_at


def test_metadata_store_emits_kind_metadata(tmp_path: Path) -> None:
    log, _ = _mount_log()
    store = TextArtifactStore(artifact_dir=tmp_path, kind="metadata")
    aid = "b" * 32
    store.put(artifact_id=aid, token=store.issue_token(), path=tmp_path / "m1.json")
    events = log.list()
    assert events[0].payload["kind"] == "metadata"


def test_export_store_emits_kind_export(tmp_path: Path) -> None:
    log, _ = _mount_log()
    store = TextArtifactStore(artifact_dir=tmp_path, kind="export")
    aid = "c" * 32
    store.put(artifact_id=aid, token=store.issue_token(), path=tmp_path / "e1.json")
    events = log.list()
    assert events[0].payload["kind"] == "export"


def test_create_emits_event(tmp_path: Path) -> None:
    """``create`` (the async page-text path) routes through ``put``,
    so the event is emitted automatically."""
    log, _ = _mount_log()
    store = TextArtifactStore(artifact_dir=tmp_path, kind="text")
    handle = asyncio.run(store.create({0: ["first page"], 1: ["second page"]}))
    events = log.list()
    assert len(events) == 1
    assert events[0].payload["artifact_id"] == handle.artifact_id
    assert events[0].payload["kind"] == "text"


def test_put_without_plugin_context_does_not_raise(tmp_path: Path) -> None:
    """The dual-write shim is a no-op when the plugin context is
    unset (e.g. tests that don't mount the context). The primary
    write must still succeed."""
    from omniscribe.api.plugin import runtime

    runtime.set_plugin_context(None)
    store = TextArtifactStore(artifact_dir=tmp_path, kind="text")
    aid = "d" * 32
    handle = store.put(
        artifact_id=aid, token=store.issue_token(), path=tmp_path / "a.json"
    )
    assert handle.artifact_id == aid


# -- Projection shape compatibility ----------------------------------------


def test_projection_output_matches_text_artifact_handle_fields(
    tmp_path: Path,
) -> None:
    """The four :class:`TextArtifactHandle` fields
    (``artifact_id`` / ``token`` / ``path`` / ``expires_at``) are
    preserved by the projection. ``kind`` and ``created_at`` are
    additive (useful for list views) and don't break the
    swap-with-handle contract."""
    log, _ = _mount_log()
    store = TextArtifactStore(artifact_dir=tmp_path, kind="text")
    aid = "e" * 32
    handle = store.put(
        artifact_id=aid, token=store.issue_token(), path=tmp_path / "a.json"
    )
    proj = ArtifactStoreProjection(log)
    rec = proj.list()[0]
    # All four handle fields are present and equal.
    assert rec["artifact_id"] == handle.artifact_id
    assert rec["token"] == handle.token
    assert rec["path"] == handle.path
    assert rec["expires_at"] == handle.expires_at
    # The handle dataclass has only those four fields — the
    # projection's extras (kind, created_at) are additive.
    handle_keys = set(TextArtifactHandle.__dataclass_fields__.keys())
    projection_keys = set(rec.keys())
    assert handle_keys.issubset(projection_keys)


def test_full_pipeline_dual_writes_fold_into_projection(tmp_path: Path) -> None:
    """End-to-end: a text artifact created via ``create`` shows up
    in the log, and the projection can recover the handle from
    the log alone (without going back to the store)."""
    log, _ = _mount_log()
    store = TextArtifactStore(artifact_dir=tmp_path, kind="text")
    handle = asyncio.run(store.create({0: ["page one"], 1: ["page two"]}))

    proj = ArtifactStoreProjection(log)
    recovered = proj.get(handle.artifact_id)
    assert recovered is not None
    assert recovered["token"] == handle.token
    assert recovered["path"] == handle.path
    assert recovered["expires_at"] == handle.expires_at
    assert recovered["kind"] == "text"


def test_state_backend_uses_per_kind_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The state backend wires text/metadata/export stores with
    the right ``kind`` so the audit log distinguishes them."""
    from omniscribe.api.services.state_backend import LocalStateBackend

    backend = LocalStateBackend()
    assert backend.text_artifacts._kind == "text"  # type: ignore[attr-defined]
    assert backend.metadata_artifacts._kind == "metadata"  # type: ignore[attr-defined]
    assert backend.export_artifacts._kind == "export"  # type: ignore[attr-defined]


# -- Audit-secondary F16: per-id fold cache --------------------------------


def test_get_caches_fold_until_log_changes(monkeypatch) -> None:
    """Repeated ``get()`` calls reuse the cached fold.

    Audit-secondary F16: a single ``get()`` used to walk the
    entire log (O(N) fold + O(1) dict lookup). A UI rendering
    50 artifacts does 50 full walks. The cache means 50 cache
    lookups (O(1)) instead.
    """
    log = InMemoryLogStore()
    for i in range(5):
        log.append(
            LogEvent(
                kind="artifact.created",
                payload={
                    "artifact_id": f"{i:032x}",
                    "kind": "text",
                    "token": f"tok-{i}",
                    "path": f"/tmp/a{i}.json",
                    "expires_at": 1700000000.0 + i,
                },
            )
        )
    proj = ArtifactStoreProjection(log)

    fold_calls = 0
    original_fold_all = proj._fold_all

    def counting_fold_all():
        nonlocal fold_calls
        fold_calls += 1
        return original_fold_all()

    monkeypatch.setattr(proj, "_fold_all", counting_fold_all)

    # 5 distinct get() calls within the same log version: one fold.
    for i in range(5):
        rec = proj.get(f"{i:032x}")
        assert rec is not None
        assert rec["token"] == f"tok-{i}"
    assert fold_calls == 1

    # list() also uses the same cache — no second fold.
    records = proj.list()
    assert len(records) == 5
    assert fold_calls == 1

    # Append a new event: cache invalidated.
    log.append(
        LogEvent(
            kind="artifact.created",
            payload={
                "artifact_id": "f" * 32,
                "kind": "text",
                "token": "tok-f",
                "path": "/tmp/af.json",
                "expires_at": 1700000010.0,
            },
        )
    )
    proj.get("f" * 32)
    assert fold_calls == 2
    assert len(proj.list()) == 6
    assert fold_calls == 2  # list() reused the fold from the get()


def test_get_cache_returns_none_for_unknown_id() -> None:
    """An unknown artifact id returns None without breaking the cache.

    Audit-secondary F16 regression: a None result must still
    populate the cache so a sidebar of 50 known + 1 unknown
    artifact does not re-fold on the unknown one.
    """
    log = InMemoryLogStore()
    log.append(
        LogEvent(
            kind="artifact.created",
            payload={
                "artifact_id": "a" * 32,
                "kind": "text",
                "token": "tok-1",
                "path": "/tmp/a1.json",
                "expires_at": 1700000000.0,
            },
        )
    )
    proj = ArtifactStoreProjection(log)
    assert proj.get("a" * 32) is not None
    assert proj.get("b" * 32) is None
    # Cache must survive the None lookup.
    assert proj.get("a" * 32) is not None
    assert proj.get("b" * 32) is None
