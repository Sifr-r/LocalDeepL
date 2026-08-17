"""In-process SSE broker for progress events.

Subscribers register a per-job callback; the broker calls all
callbacks for a given ``job_id`` when a producer publishes a frame.

This is intentionally per-process: a horizontally-scalable
multi-worker deployment will need a Redis pub/sub adapter
(see the spec's §3 for the follow-up design). The single-process
design here is sufficient for the audit's P2 #11 fix because
the user is on a workstation deployment (single uvicorn worker
by default).

Thread/loop safety: producers may publish from any thread
(notably the ``/api/process`` worker thread, which runs
``pipeline.run`` under its own ``asyncio.run()`` loop). The
broker's :meth:`publish` snapshot is taken under a
:class:`threading.Lock` and the actual callback invocation
happens outside the lock so a slow subscriber cannot block a
concurrent ``subscribe``/``unsubscribe`` on another thread. A
subscriber that raises an exception is logged and skipped — a
broken subscriber must not break the producer.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any

_logger = logging.getLogger(__name__)


Subscriber = Callable[[dict[str, Any]], None]


class SSEBroker:
    """Per-process fan-out for SSE progress frames."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Subscriber]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, job_id: str, callback: Subscriber) -> None:
        """Register ``callback`` to receive every frame for ``job_id``."""
        with self._lock:
            self._subs[job_id].append(callback)

    def unsubscribe(self, job_id: str, callback: Subscriber) -> None:
        """Remove ``callback`` from ``job_id``'s subscriber list.

        A no-op if the callback was never registered (idempotent
        teardown). The ``job_id`` entry is removed once its list is
        empty so the registry stays bounded.
        """
        with self._lock:
            subs = self._subs.get(job_id)
            if subs is None:
                return
            if callback in subs:
                subs.remove(callback)
            if not subs:
                del self._subs[job_id]

    def publish(self, job_id: str, frame: dict[str, Any]) -> None:
        """Fan ``frame`` out to every subscriber registered for ``job_id``.

        The subscriber list is snapshotted under the lock so a
        concurrent :meth:`unsubscribe` on the same job does not
        mutate the iteration. Subscriber exceptions are logged at
        ``warning`` and swallowed — a broken subscriber must not
        break the producer (which is the OCR / translation worker
        in production).
        """
        with self._lock:
            callbacks = list(self._subs.get(job_id, ()))
        for cb in callbacks:
            try:
                cb(frame)
            except Exception:  # subscriber errors must not break the producer
                _logger.warning(
                    "sse broker subscriber raised; dropping frame for job_id=%r",
                    job_id,
                    exc_info=True,
                )


_broker = SSEBroker()


def get_broker() -> SSEBroker:
    """Return the module-level broker singleton.

    Centralising the singleton behind a function keeps the broker
    swappable for tests (monkeypatch ``_broker`` and call
    :func:`get_broker` to read the patched instance).
    """
    return _broker
