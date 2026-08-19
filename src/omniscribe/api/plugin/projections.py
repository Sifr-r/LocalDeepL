"""Read-only projections over the :class:`SessionLog`.

A **projection** is a derived view of the session log: it reads
events, folds them into a stable shape, and caches the result
for cheap re-reads. The canonical state in Phase 3c/3d is the
log; ``JobHistory`` and ``TextArtifactStore`` (and any other
read-mostly view) become projections over it.

Why projections
---------------

- **Single source of truth.** The log is the only place where
  the server's history is stored. Every other view is a fold
  over the same events, so two views cannot disagree about
  what happened.
- **Replayable.** A future ``SQLite`` / ``JSONL`` log provider
  is drop-in: the projections do not need to change.
- **Cheap to swap.** The legacy ``JobHistory`` in-memory
  ``deque`` and the new projection read from different places;
  during the migration window a shim writes to both, so
  consumers can flip from one to the other without a flag day.
- **Easy to test.** Each projection is a pure function of
  the log's events — given the same events, the same
  JobRecord comes out. No hidden state, no surprise caches.

Current projections
--------------------

- :class:`JobHistoryProjection` — folds
  ``ocr.job.submitted`` / ``ocr.job.started`` /
  ``ocr.job.completed`` / ``ocr.job.cancelled`` events into
  ``JobRecord`` snapshots matching the legacy
  :class:`JobHistory` API exactly (same field names, same
  status values, same newest-first ordering, same optional
  ``failed_pages`` field).

Phase 3d will add :class:`ArtifactStoreProjection`.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, cast

from omniscribe.api.plugin.session_log import LogEvent, SessionLog, SessionLogQuery


def _payload_str(payload: dict[str, Any], key: str, default: str = "") -> str:
    value = payload.get(key, default)
    return value if isinstance(value, str) else default


def _payload_optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _payload_float(payload: dict[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _payload_list_int(payload: dict[str, Any], key: str) -> list[int]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        return []
    out: list[int] = []
    for x in value:
        if isinstance(x, bool):
            continue
        if isinstance(x, (int, float)):
            out.append(int(x))
    return out


def _iso_from_monotonic(ts: float, *, now_fn: Callable[[], datetime]) -> str:
    """Convert a ``time.monotonic()`` stamp to an ISO-8601 UTC string.

    The legacy :class:`JobHistory` records wall-clock ISO
    timestamps; the log uses monotonic timestamps for ordering
    across restarts. For the projection we synthesise a
    wall-clock timestamp at read time so the field stays
    human-readable in the API response. A persistent log
    provider will use wall-clock directly and this helper
    becomes a no-op fallback.
    """
    # Best-effort: just use ``now()`` (read time) for the
    # ``timestamp`` field. The monotonic stamp is preserved
    # separately if a consumer needs ordering.
    return now_fn().astimezone(UTC).isoformat()


def _sort_newest_first(
    records: list[dict[str, Any]], sort_key: str
) -> list[dict[str, Any]]:
    """Stable newest-first sort, breaking ties by insertion position.

    The log uses :func:`time.monotonic` for ``event.timestamp``;
    events appended in the same monotonic tick (common in fast
    tests, possible in real bursts) get identical stamps, which
    would make a plain :func:`sorted` non-deterministic. The
    position is stamped during fold (insertion order of the
    per-id accumulator) and used as a secondary key so the
    newest-by-insertion tiebreaker is stable.
    """
    for pos, r in enumerate(records):
        r["__position"] = pos
    records.sort(
        key=lambda r: (r[sort_key], r["__position"]),
        reverse=True,
    )
    return records


class JobHistoryProjection:
    """Read-only projection of OCR job events into legacy ``JobRecord``-shaped dicts.

    The projection walks the log for events whose
    :attr:`LogEvent.kind` matches one of the four OCR-job
    kinds (``ocr.job.submitted`` / ``started`` / ``completed``
    / ``cancelled``) and folds them per ``job_id`` into the
    final state. Events arrive in insertion order so the fold
    is straightforward: each event updates one or two fields
    on the record under construction.

    The returned dict shape matches the legacy
    :meth:`JobHistory.list` contract exactly so a shim can
    swap the source from the in-memory deque to the log
    without changing any consumer:

    - field names: ``id`` (not ``job_id``), ``timestamp``
      (ISO-8601, not monotonic), ``status`` uses the legacy
      :class:`JobStatus` literal (``"complete" | "error"``)
    - ordering: newest first (by submitted timestamp)
    - optional ``failed_pages`` only present when non-empty

    The projection is **read-only** — there is no ``record``
    method. Appends go through :meth:`SessionLog.append`
    directly; the legacy ``JobHistory`` in-memory deque is
    decommissioned in a follow-up phase (3c keeps the deque
    behind a shim for the migration window).
    """

    #: Newest-first cap; matches the legacy ``JobHistory`` default.
    DEFAULT_MAX_JOBS: int = 1000

    def __init__(
        self,
        log: SessionLog,
        *,
        max_jobs: int = DEFAULT_MAX_JOBS,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._log = log
        self._max_jobs = max_jobs
        self._now_fn: Callable[[], datetime] = now_fn or (lambda: datetime.now(UTC))
        # Cache: (log_version, sorted_records_with_internal_fields).
        # ``log_version`` is the event count at the time of the
        # fold; any subsequent ``log.append`` invalidates the
        # cache by changing ``len(self._log)``. The fold +
        # position-stamp + sort is the expensive part (O(N log
        # N)); the dict-comprehension emit is cheap and runs at
        # read time so the ``timestamp`` field stays current.
        self._cache: tuple[int, builtins.list[dict[str, Any]]] | None = None

    def list(self) -> builtins.list[dict[str, Any]]:
        """Return the projected JobRecord dicts, newest first.

        Mirrors :meth:`JobHistory.list` — the legacy contract
        was ``list[dict]`` with no JobRecord import needed.

        Performance (audit-secondary F15): the fold + sort is
        cached against the log's event count. The first call
        after any ``log.append`` re-folds; subsequent calls
        within the same log version reuse the cached sort. The
        emit (dict-comprehension + ``max_jobs`` cap) runs on
        every call so the returned ``timestamp`` reflects the
        current time, not the cache-population time.
        """
        version = len(self._log)
        cached = self._cache
        if cached is None or cached[0] != version:
            records = self._fold_all()
            # Stamp each record with its insertion position so the
            # sort has a strict total order. ``time.monotonic()``
            # can return identical values for events appended in
            # the same monotonic tick (common in fast tests and
            # not impossible in real bursts), which would make the
            # sort non-deterministic. The position comes from the
            # order ``by_id`` saw the job — which itself mirrors
            # the log's insertion order — so newest-by-insertion
            # is the natural tiebreaker.
            for pos, r in enumerate(records):
                r["__position"] = pos
            # Newest first: by submitted (created_at) monotonic
            # timestamp, then by insertion position. Both
            # descending so the strictly-newer record wins. The
            # resulting tuple order is what ``reverse=True``
            # inverts element-wise.
            records.sort(
                key=lambda rec: (rec["__sort_key"], rec["__position"]),
                reverse=True,
            )
            self._cache = (version, records)
            records = self._cache[1]
        else:
            records = cached[1]
        # Build the output, applying the max_jobs cap AFTER
        # sort so the cap drops the oldest records (matching
        # the legacy ``deque(maxlen=N)`` semantics).
        out: builtins.list[dict[str, Any]] = []
        for r in records[: self._max_jobs]:
            out.append({k: v for k, v in r.items() if not k.startswith("__")})
        return out

    def _fold_all(self) -> builtins.list[dict[str, Any]]:
        """Fold every OCR job event in the log into a JobRecord-shaped dict.

        Walks the log once; events for the same ``job_id`` are
        accumulated in a per-job dict. A ``completed`` or
        ``cancelled`` event finalises the record. The record
        is still returned for in-flight jobs (status
        ``PENDING``/``PROCESSING``) so the UI can show
        progress; this is slightly more than the legacy
        contract (which only stored terminal jobs) but
        matches the audit-replay model the projection is
        meant to support.
        """
        by_id: dict[str, dict[str, Any]] = {}
        kinds = (
            "ocr.job.submitted",
            "ocr.job.started",
            "ocr.job.completed",
            "ocr.job.cancelled",
        )
        query = SessionLogQuery(kinds=frozenset(kinds))
        for event in self._log.list(query):
            self._apply(by_id, event)
        return list(by_id.values())

    def _apply(self, by_id: dict[str, dict[str, Any]], event: LogEvent) -> None:
        """Apply one event to the per-job accumulator dict."""
        job_id = _payload_str(event.payload, "job_id")
        if not job_id:
            return
        # The submitted event is the canonical "when did this
        # job enter the system" marker — use its monotonic
        # timestamp as the sort key, and only set it on
        # ``setdefault`` (never overwrite on later events).
        rec = by_id.setdefault(
            job_id,
            {
                "id": job_id,
                "filename": "",
                "model": "",
                "pipeline_mode": "",
                "pages": None,
                "duration_s": None,
                "timestamp": _iso_from_monotonic(event.timestamp, now_fn=self._now_fn),
                "status": "pending",
                # Internal: monotonic timestamp for stable
                # newest-first sorting. Stripped from the
                # output by ``list()`` before returning.
                "__sort_key": event.timestamp,
            },
        )
        kind = event.kind
        if kind == "ocr.job.submitted":
            rec["filename"] = _payload_str(event.payload, "filename")
            rec["status"] = "pending"
        elif kind == "ocr.job.started":
            rec["model"] = _payload_str(event.payload, "model")
            rec["pipeline_mode"] = _payload_str(event.payload, "pipeline_mode")
            pages = _payload_optional_str(event.payload, "pages")
            if pages is not None:
                rec["pages"] = pages
            rec["status"] = "processing"
        elif kind == "ocr.job.completed":
            status = _payload_str(event.payload, "status")
            # Map the audit-event status values to the legacy
            # ``JobStatus`` literal. ``complete`` -> ``complete``,
            # ``error`` / ``cancelled`` -> ``error`` (the legacy
            # enum has no ``cancelled``; the deque stored
            # ``error`` for cancellations via the OCRJobQueue's
            # worker code).
            if status in ("error", "cancelled"):
                rec["status"] = "error"
            else:
                rec["status"] = "complete"
            duration = _payload_float(event.payload, "duration_s")
            if duration is not None:
                rec["duration_s"] = round(duration, 2)
            artifact_id = _payload_optional_str(event.payload, "text_artifact_id")
            if artifact_id is not None:
                rec["text_artifact_id"] = artifact_id
            err = _payload_optional_str(event.payload, "error")
            if err is not None:
                rec["error"] = err
            failed = _payload_list_int(event.payload, "failed_pages")
            if failed:
                # ``failed_pages`` is a list (matches the
                # legacy :class:`JobRecord.to_dict` contract
                # and the existing test suite that compares
                # against ``[3, 7, 9]``). The field is
                # omitted from the dict when empty so the
                # common no-failure case preserves the wire
                # format.
                rec["failed_pages"] = list(cast(Sequence[int], failed))
        elif kind == "ocr.job.cancelled":
            rec["status"] = "error"
            rec["error"] = "cancelled by client"
            rec.setdefault("duration_s", 0.0)


class ArtifactStoreProjection:
    """Read-only projection of ``artifact.created`` events into ``TextArtifactHandle``-shaped dicts.

    The legacy :class:`TextArtifactStore` is access-oriented: a
    caller must know both the artifact id AND the bearer token to
    fetch the file. The projection adds a *metadata* view: given
    only the id, a consumer can recover the handle (including the
    token) from the log. This is the read-side complement to the
    :class:`TextArtifactStore` write path; the legacy store still
    owns the file access.

    Output shape (a single record)::

        {
            "artifact_id": str,
            "kind": str,         # "text" | "metadata" | "export" | "docx"
            "token": str,        # bearer token, mirrors the legacy handle
            "path": str,         # absolute path on disk
            "expires_at": float, # wall-clock seconds (time.time() base)
            "created_at": str,   # ISO-8601 UTC, from the event
        }

    The :attr:`TextArtifactHandle` fields (``artifact_id``,
    ``token``, ``path``, ``expires_at``) are all preserved, so a
    caller that already holds a :class:`TextArtifactHandle` can
    swap one for the other without code changes. The ``kind`` and
    ``created_at`` fields are additive — they come from the event
    payload and are useful for "list recent artifacts" views.
    """

    def __init__(self, log: SessionLog) -> None:
        self._log = log
        # Cache: (log_version, per_id_folded_dict). The fold is
        # shared between ``list()`` and ``get()``; either method
        # invalidates the cache via ``len(self._log)``. See
        # :class:`JobHistoryProjection` for the same pattern.
        self._cache: tuple[int, dict[str, dict[str, Any]]] | None = None

    def _get_folded(self) -> dict[str, dict[str, Any]]:
        """Return the cached per-id accumulator, recomputing on log change.

        Both :meth:`list` and :meth:`get` route through this helper so
        a single ``log.append`` invalidates both call paths.
        """
        version = len(self._log)
        cached = self._cache
        if cached is None or cached[0] != version:
            folded = self._fold_all()
            self._cache = (version, folded)
            return folded
        return cached[1]

    def list(self) -> list[dict[str, Any]]:
        """Return every ``artifact.created`` event as a dict, newest first.

        Unlike :class:`JobHistoryProjection` there is no cap; the
        legacy store has its own eviction policy
        (``max_entries`` + TTL) but the projection is purely a
        read view, so the caller decides whether to apply one.

        Performance (audit-secondary F16): the fold is cached.
        First call after any ``log.append`` re-folds; subsequent
        calls reuse the cache.
        """
        records = list(self._get_folded().values())
        _sort_newest_first(records, "__sort_key")
        return [{k: v for k, v in r.items() if not k.startswith("__")} for r in records]

    def get(self, artifact_id: str) -> dict[str, Any] | None:
        """Return the artifact handle for ``artifact_id``, or ``None`` if unknown.

        This is the projection's answer to "what's the token for
        this id?" — a use case the legacy
        :meth:`TextArtifactStore.get` does not support (it
        requires the token to be supplied).

        Performance (audit-secondary F16): a single ``get()``
        used to walk the entire log; the cache means a UI
        rendering 50 artifacts in a sidebar does 50 cache
        lookups (O(1) each) instead of 50 full log walks.
        """
        rec = self._get_folded().get(artifact_id)
        if rec is None:
            return None
        return {k: v for k, v in rec.items() if not k.startswith("__")}

    def _fold_all(self) -> dict[str, dict[str, Any]]:
        """Walk the log once and build a per-id accumulator dict.

        The accumulator uses the event's monotonic timestamp as
        the sort key and the insertion position as the tiebreaker
        (see :func:`_sort_newest_first`). Because ``put`` is
        idempotent against the legacy store (a same-id re-put
        overwrites the previous entry and emits a new event),
        the projection naturally reflects the latest event for
        each artifact id.
        """
        by_id: dict[str, dict[str, Any]] = {}
        query = SessionLogQuery(kinds=frozenset({"artifact.created"}))
        for event in self._log.list(query):
            self._apply(by_id, event)
        return by_id

    @staticmethod
    def _apply(by_id: dict[str, dict[str, Any]], event: LogEvent) -> None:
        """Fold one ``artifact.created`` event into the accumulator.

        Each event fully describes the handle, so the fold is a
        straight copy: the per-id dict is replaced by a new dict
        built from the latest event for that id (this is the
        behaviour the legacy :meth:`TextArtifactStore.put` has
        when called twice with the same id — the second put
        overwrites the first).
        """
        artifact_id = _payload_str(event.payload, "artifact_id")
        if not artifact_id:
            return
        rec: dict[str, Any] = {
            "artifact_id": artifact_id,
            "kind": _payload_str(event.payload, "kind", default="text"),
            "token": _payload_str(event.payload, "token"),
            "path": _payload_str(event.payload, "path"),
            "expires_at": _payload_float(event.payload, "expires_at") or 0.0,
            "created_at": _payload_str(event.payload, "created_at"),
            # Internal: monotonic timestamp for stable newest-first
            # sort. Stripped from the output by ``list()`` / ``get``
            # before returning.
            "__sort_key": event.timestamp,
        }
        by_id[artifact_id] = rec


__all__ = ["ArtifactStoreProjection", "JobHistoryProjection"]
