"""Typed event payloads for the audit event bus.

Each event is a frozen dataclass with a stable name and field set. Events
are emitted by routers / services via :meth:`PluginContext.emit` (or
:meth:`PluginContext.waterfall` for middleware-style around-events) and
consumed by recorder plugins.

Why frozen dataclasses
----------------------

Frozen so a listener cannot mutate the payload after dispatch (which
would surprise later listeners). The dataclass shape is part of the
event's public contract; changing a field is a breaking change to every
listener that cares.

Event naming
------------

All event names are dotted strings: ``<domain>.<verb>`` or
``<domain>.<subject>.<verb>``. The names are emitted as the
``event_name`` field on every payload so listeners can route on the
name (in addition to the typed payload).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Centralized so every event payload uses the same serialization
    (down to microsecond precision and a trailing ``+00:00``).
    """
    return datetime.now(UTC).isoformat()


# -- Job queue events --------------------------------------------------------


@dataclass(frozen=True)
class JobSubmittedEvent:
    """A new OCR job was submitted to the queue."""

    event_name: str = "ocr.job.submitted"
    job_id: str = ""
    filename: str = ""
    submitted_at: str = field(default_factory=_utc_now_iso)
    request_channel_id: str | None = None


@dataclass(frozen=True)
class JobCompletedEvent:
    """An OCR job finished (success or error)."""

    event_name: str = "ocr.job.completed"
    job_id: str = ""
    filename: str = ""
    status: str = ""  # "complete" | "error" | "cancelled"
    duration_s: float | None = None
    text_artifact_id: str | None = None
    error: str | None = None
    completed_at: str = field(default_factory=_utc_now_iso)


@dataclass(frozen=True)
class JobCancelledEvent:
    """A client explicitly cancelled a job via the cancel endpoint."""

    event_name: str = "ocr.job.cancelled"
    job_id: str = ""
    cancelled_at: str = field(default_factory=_utc_now_iso)


# -- Translation events ------------------------------------------------------


@dataclass(frozen=True)
class TranslationRequestedEvent:
    """A translation request was accepted by the API."""

    event_name: str = "translation.requested"
    request_id: str = ""
    source_lang: str | None = None
    target_lang: str | None = None
    mode: str = ""  # "sync" | "async" | "tree" | "nllb"
    char_count: int | None = None
    requested_at: str = field(default_factory=_utc_now_iso)


# -- Artifact events ---------------------------------------------------------


@dataclass(frozen=True)
class ArtifactCreatedEvent:
    """A new text / metadata / export artifact was created."""

    event_name: str = "artifact.created"
    artifact_id: str = ""
    kind: str = ""  # "text" | "metadata" | "export" | "docx"
    token: str = ""
    created_at: str = field(default_factory=_utc_now_iso)


# -- Provider events ---------------------------------------------------------


@dataclass(frozen=True)
class ProviderSwitchedEvent:
    """The active LLM provider was switched."""

    event_name: str = "provider.switched"
    from_provider_id: str | None = None
    to_provider_id: str = ""
    switched_at: str = field(default_factory=_utc_now_iso)


# -- HTTP request lifecycle events -------------------------------------------


@dataclass(frozen=True)
class RequestReceivedEvent:
    """A new HTTP request was received. Emitted early in the middleware chain.

    Listeners can attach request-scoped state via the context (a later
    phase will add scoped contexts); the immediate use is to record the
    request in the audit log.
    """

    event_name: str = "http.request.received"
    method: str = ""
    path: str = ""
    received_at: str = field(default_factory=_utc_now_iso)
    query: dict[str, Any] = field(default_factory=dict)


# -- All event types --------------------------------------------------------


ALL_EVENT_TYPES: tuple[type, ...] = (
    JobSubmittedEvent,
    JobCompletedEvent,
    JobCancelledEvent,
    TranslationRequestedEvent,
    ArtifactCreatedEvent,
    ProviderSwitchedEvent,
    RequestReceivedEvent,
)


__all__ = [
    "ALL_EVENT_TYPES",
    "ArtifactCreatedEvent",
    "JobCancelledEvent",
    "JobCompletedEvent",
    "JobSubmittedEvent",
    "ProviderSwitchedEvent",
    "RequestReceivedEvent",
    "TranslationRequestedEvent",
]
