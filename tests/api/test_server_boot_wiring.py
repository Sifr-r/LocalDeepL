"""End-to-end test that ``server.create_app()`` wires the plugin context.

Audit-secondary F12: the new ``api/plugin/`` infrastructure has
5-of-5 seams registered at boot after Phase 6 (F2-deeper). The
boot wiring is the integration point — a future refactor that
accidentally deletes a ``plugin_ctx.mount(...)`` line would not
be caught until an operator hits a 404 in production. This test
boots the app and asserts each seam lookup returns the expected
value:

- ``JobQueue`` ("local") — wired, returns ``state.ocr_job_queue``
- ``SessionLog`` ("memory") — wired, returns a live log
- ``ConfigStore`` ("memory") — wired, returns ``state.config_store``
- ``ProgressService`` ("memory") — wired, returns ``state.progress_service``
- ``TextArtifactStore`` ("text" / "metadata" / "export") — wired,
  return the corresponding ``state.{text,metadata,export}_artifacts``
  singletons

A regression in any of the seven lookups fails the test loudly.

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


def test_create_app_wires_config_store(_reset_plugin_context) -> None:
    """Phase 6 F2-deeper: ``create_app()`` registers the
    in-process :class:`ConfigStore` at the ``"memory"`` slot, and
    the helper returns the same instance as the legacy
    ``state.config_store`` singleton.
    """
    from omniscribe.api.plugin import runtime
    from omniscribe.api.routers import state
    from omniscribe.server import create_app

    create_app()

    store = runtime.get_config_store(name="memory")
    assert store is state.config_store, (
        "ConfigStore provider must share the state.config_store instance"
    )


def test_create_app_wires_progress_service(_reset_plugin_context) -> None:
    """Phase 6 F2-deeper: ``create_app()`` registers the
    :class:`ProgressService` at the ``"memory"`` slot, and the
    helper returns the same instance as the legacy
    ``state.progress_service`` singleton.
    """
    from omniscribe.api.plugin import runtime
    from omniscribe.api.routers import state
    from omniscribe.server import create_app

    create_app()

    service = runtime.get_progress_service(name="memory")
    assert service is state.progress_service, (
        "ProgressService provider must share the state.progress_service instance"
    )


def test_create_app_wires_text_artifact_stores(_reset_plugin_context) -> None:
    """Phase 6 F2-deeper: ``create_app()`` registers the three
    :class:`TextArtifactStore` instances under their canonical
    domain names (``"text"`` / ``"metadata"`` / ``"export"``),
    and each helper returns the same instance as the legacy
    ``state.{text,metadata,export}_artifacts`` singletons.
    """
    from omniscribe.api.plugin import runtime
    from omniscribe.api.routers import state
    from omniscribe.server import create_app

    create_app()

    assert runtime.get_text_artifact_store(name="text") is state.text_artifacts
    assert runtime.get_text_artifact_store(name="metadata") is state.metadata_artifacts
    assert runtime.get_text_artifact_store(name="export") is state.export_artifacts


def test_create_app_context_is_disposable(_reset_plugin_context) -> None:
    """The boot-wired context is a real :class:`PluginContext` that
    can be inspected and disposed cleanly. Catches a regression
    where ``create_app()`` accidentally stores a stand-in or
    proxy object.
    """
    from omniscribe.api.plugin import (
        ConfigStore,
        JobQueue,
        PluginContext,
        ProgressService,
        SessionLog,
        TextArtifactStore,
        runtime,
    )
    from omniscribe.server import create_app

    create_app()

    ctx = runtime.get_plugin_context()
    assert isinstance(ctx, PluginContext)
    assert not ctx.disposed
    # All five registered seams appear in the registry under
    # their canonical names. Phase 6 (F2-deeper) closed the
    # 3-of-5 gap; the table is now 5/5 REGISTERED.
    assert "local" in ctx.service_names(JobQueue)
    assert "memory" in ctx.service_names(SessionLog)
    assert "memory" in ctx.service_names(ConfigStore)
    assert "memory" in ctx.service_names(ProgressService)
    assert "text" in ctx.service_names(TextArtifactStore)
    assert "metadata" in ctx.service_names(TextArtifactStore)
    assert "export" in ctx.service_names(TextArtifactStore)


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
