"""Exception hierarchy for the plugin harness."""

from __future__ import annotations


class HarnessError(Exception):
    """Base class for every exception the harness raises."""


class ServiceNotFoundError(HarnessError, LookupError):
    """Raised by ``Context.inject`` when no service matches the Protocol."""

    def __init__(self, protocol_name: str) -> None:
        self.protocol_name = protocol_name
        super().__init__(f"no service registered for protocol {protocol_name!r}")


class ContextDisposedError(HarnessError, RuntimeError):
    """Raised when a registration is attempted after ``Context.dispose``."""

    def __init__(self, operation: str) -> None:
        self.operation = operation
        super().__init__(f"context is disposed; cannot {operation}")


class PluginLoadError(HarnessError, RuntimeError):
    """Raised when a ``cordis.yml`` row fails to resolve, validate, or mount."""

    def __init__(self, *, row_id: str, reason: str) -> None:
        self.row_id = row_id
        self.reason = reason
        super().__init__(f"plugin {row_id!r} failed to load: {reason}")


class DuplicateServiceError(HarnessError, RuntimeError):
    """Raised when a service is registered under a Protocol that is already present."""


class DuplicatePluginError(HarnessError, RuntimeError):
    """Raised when a plugin ID is already mounted on the Context."""
