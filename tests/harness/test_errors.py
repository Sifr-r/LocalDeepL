"""Harness error hierarchy."""

from __future__ import annotations

import pytest

from omniscribe.harness.errors import (
    ContextDisposedError,
    HarnessError,
    PluginLoadError,
    ServiceNotFoundError,
)


def test_all_errors_subclass_harness_error() -> None:
    for cls in (ServiceNotFoundError, ContextDisposedError, PluginLoadError):
        assert issubclass(cls, HarnessError)


def test_service_not_found_carries_protocol_name() -> None:
    err = ServiceNotFoundError("OCRService")
    assert err.protocol_name == "OCRService"
    assert "OCRService" in str(err)


def test_context_disposed_carries_operation() -> None:
    err = ContextDisposedError("unload")
    assert err.operation == "unload"
    assert "unload" in str(err)


def test_plugin_load_error_carries_row_id_and_reason() -> None:
    err = PluginLoadError(row_id="ocr", reason="missing dependency: state_backend")
    assert err.row_id == "ocr"
    assert err.reason == "missing dependency: state_backend"
    assert "ocr" in str(err)


@pytest.mark.parametrize(
    "exc",
    [
        ServiceNotFoundError("X"),
        ContextDisposedError("y"),
        PluginLoadError(row_id="z", reason="r"),
    ],
)
def test_catchable_as_harness_error(exc: Exception) -> None:
    with pytest.raises(HarnessError):
        raise exc
