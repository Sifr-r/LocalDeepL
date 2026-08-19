"""Tests for the SSE progress stream endpoint and its drop-oldest shim.

D2-12 audit fix: the SSE push callback used to call
``queue.put_nowait`` from the event loop's scheduled-task
context, which raised ``QueueFull`` when the slow consumer
fell behind. The exception was logged-and-discarded by the
loop's default exception handler, silently dropping the
frame. The fix wraps the put in a drop-oldest helper; this
file pins the helper's contract.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from omniscribe.api.routers.events import _put_with_drop_oldest


def _drain(queue: asyncio.Queue[dict[str, object]]) -> list[dict[str, object]]:
    """Drain a queue synchronously for test assertions."""
    items: list[dict[str, object]] = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def test_put_succeeds_when_queue_has_room() -> None:
    """A put on a non-full queue lands at the tail."""
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=2)
    _put_with_drop_oldest(queue, {"a": 1})
    _put_with_drop_oldest(queue, {"a": 2})
    assert queue.qsize() == 2
    # The order is FIFO.
    assert _drain(queue) == [{"a": 1}, {"a": 2}]


def test_put_drops_oldest_when_queue_is_full() -> None:
    """A put on a full queue evicts the oldest frame to make room.

    Audit-secondary D2-12 regression: the previous code raised
    ``QueueFull`` (which the loop's default handler swallowed),
    so a slow client could not tell that progress frames were
    being dropped. The new contract: a slow client gets the
    *newest* frame instead of the oldest, so the UI's last
    visible state is the most recent state.
    """
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=2)
    _put_with_drop_oldest(queue, {"seq": 1})
    _put_with_drop_oldest(queue, {"seq": 2})
    # Queue is full. The next put drops the oldest.
    _put_with_drop_oldest(queue, {"seq": 3})
    assert queue.qsize() == 2
    # Oldest (seq=1) is gone; seq=2 and seq=3 remain, in order.
    assert _drain(queue) == [{"seq": 2}, {"seq": 3}]


def test_put_does_not_raise_on_empty_queue_race() -> None:
    """The race window between ``get_nowait`` and ``put_nowait`` is safe.

    The drop-oldest helper does ``get_nowait`` to evict the
    oldest frame, then ``put_nowait`` to add the new one. A
    second coroutine could drain the queue between the two
    calls (or put_nowait could fail for a different reason).
    The helper must not raise regardless.

    The contract: any failure in the drop-oldest path is
    suppressed silently. The frame may be added (queue had
    room after the mock), may be dropped (queue was still
    full), or may sit at the head (queue was empty after the
    mock). All three are acceptable; what is not acceptable
    is for the helper to raise.
    """
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=1)
    _put_with_drop_oldest(queue, {"seq": 1})
    # Simulate a concurrent drain by mocking get_nowait to
    # raise QueueEmpty. The original item stays in the queue;
    # the helper's subsequent put_nowait will also fail
    # (queue is still full) and the frame is dropped.
    with patch.object(queue, "get_nowait", side_effect=asyncio.QueueEmpty):
        # The function under test must NOT raise.
        _put_with_drop_oldest(queue, {"seq": 2})
    # The original item is still there; the new frame was
    # dropped (the helper saw a full queue and could not evict).
    assert queue.qsize() == 1
    assert queue.get_nowait() == {"seq": 1}
