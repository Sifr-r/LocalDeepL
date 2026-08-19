"""End-to-end test that ``server.create_app()`` wires the plugin context.

Audit-secondary F12: the new ``api/plugin/`` infrastructure has
2-of-5 seams registered at boot, 3 unregistered. The boot wiring
is the integration point — a future refactor that accidentally
deletes a ``plugin_ctx.mount(...)`` line would not be caught
until an operator hits a 404 in production. This test boots the
app and asserts each seam lookup returns the expected value:

- ``JobQueue`` ("local") — wired, returns ``state.ocr_job_queue``
- ``SessionLog`` ("memory") — wired, returns a live log
- ``ConfigStore`` ("memory") — unregistered, returns ``None``
- ``ProgressService`` ("memory") — unregistered, returns ``None``
- ``TextArtifactStore`` ("text") — unregistered, returns ``None``

A regression in any of the five lookups fails the test loudly.

The test is run in isolation (not as part of the in-process
``server.create_app`` lifespan) so a failure here does not
interfere with other tests that mount a private context.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def _reset_plugin_context():
    """Save + restore ``runtime._plugin_context`` so this test does
    not leak state into other tests.
    """
    from omniscribe.api.plugin import runtime

    saved = runtime.get_plugin_context()
    runtime.set_plugin_context(None)
    try:
        yield
    finally:
        runtime.set_plugin_context(saved)


def test_create_app_wires_job_queue(_reset_plugin_context) -> None:
    """``create_app()`` registers the in-process JobQueue at the
    ``"local"`` slot, and the helper returns the same instance
    as the legacy ``state.ocr_job_queue`` singleton.
    """
    from omniscribe.api.plugin import runtime
    from omniscribe.api.routers import state
    from omniscribe.server import create_app

    create_app()

    ctx = runtime.get_plugin_context()
    assert ctx is not None
    assert ctx.name == "omniscribe"

    queue = runtime.get_job_queue(name="local")
    assert queue is state.ocr_job_queue, (
        "JobQueue provider must share the state.ocr_job_queue instance"
    )


def test_create_app_wires_session_log(_reset_plugin_context) -> None:
    """``create_app()`` registers the in-memory SessionLog at the
    ``"memory"`` slot, and ``emit`` on the context appends to it.
    """
    from omniscribe.api.plugin import runtime
    from omniscribe.server import create_app

    create_app()

    log = runtime.get_session_log(name="memory")
    assert log is not None
    initial_len = len(log)

    runtime.get_plugin_context().emit("test.event", foo="bar")
    assert len(log) == initial_len + 1
    # The event name is stored on the LogEvent's ``kind`` field,
    # not as ``event_name`` inside the payload. The payload is a
    # verbatim copy of the kwargs the caller passed to ``emit``.
    last = log.list()[-1]
    assert last.kind == "test.event"
    assert last.payload == {"foo": "bar"}


def test_create_app_does_not_wire_unregistered_seams(_reset_plugin_context) -> None:
    """The 3 unregistered seams (ConfigStore / ProgressService /
    TextArtifactStore) return ``None`` from their helpers, even
    after boot. Locking in the migration-window contract.
    """
    from omniscribe.api.plugin import runtime
    from omniscribe.server import create_app

    create_app()

    assert runtime.get_config_store() is None
    assert runtime.get_progress_service() is None
    assert runtime.get_text_artifact_store() is None


def test_create_app_context_is_disposable(_reset_plugin_context) -> None:
    """The boot-wired context is a real :class:`PluginContext` that
    can be inspected and disposed cleanly. Catches a regression
    where ``create_app()`` accidentally stores a stand-in or
    proxy object.
    """
    from omniscribe.api.plugin import (
        JobQueue,
        PluginContext,
        SessionLog,
        runtime,
    )
    from omniscribe.server import create_app

    create_app()

    ctx = runtime.get_plugin_context()
    assert isinstance(ctx, PluginContext)
    assert not ctx.disposed
    # The two registered seams appear in the registry under
    # their canonical names.
    assert "local" in ctx.service_names(JobQueue)
    assert "memory" in ctx.service_names(SessionLog)


def test_create_app_repeated_calls_do_not_leak_contexts(_reset_plugin_context) -> None:
    """Two ``create_app()`` calls do not stack contexts. The second
    call replaces the first; the first context is not auto-disposed
    (the lifespan owns that) but a warning is logged.

    The test pins the documented behaviour from
    ``runtime.set_plugin_context`` and keeps a future refactor from
    silently leaking contexts.
    """
    from omniscribe.api.plugin import runtime
    from omniscribe.server import create_app

    app1 = create_app()
    ctx1 = runtime.get_plugin_context()

    app2 = create_app()
    ctx2 = runtime.get_plugin_context()

    # Two distinct apps; two distinct contexts; the second
    # call's context is the live one.
    assert app1 is not app2
    assert ctx1 is not ctx2
    assert runtime.get_plugin_context() is ctx2
    # ctx1 was replaced (not disposed by the second call). It
    # is still a live PluginContext, not disposed.
    assert not ctx1.disposed
