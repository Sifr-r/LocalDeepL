"""Liveness and readiness probes for the OmniScribe web app.

These endpoints exist so container orchestrators (Docker, Kubernetes,
Nomad) and reverse proxies can decide whether to route traffic to the
worker. They are deliberately cheap:

* ``GET /health`` (alias: ``GET /healthz``) — liveness probe. Returns
  ``{"status": "ok"}`` if the process is alive and FastAPI is serving.
  Never touches downstream services, never acquires locks, never reads
  artifact state. Designed to be polled every few seconds.
* ``GET /ready`` (alias: ``GET /readyz``) — readiness probe. Reports
  whether the artifact stores are usable and the OCR job queue is
  running. Touches in-memory state only; safe to poll once per second.

Auth is intentionally not applied to these endpoints: a probe must
work for the orchestrator even when it doesn't know the bearer token.
Because the endpoints leak no business state and only return
``status`` + a few counters, the failure mode is "load balancer
detects the server is broken", not "attacker learns something useful".
The probe routes are added to the app *outside* the auth middleware
chain (see ``server.py``) so a missing/invalid bearer header on a
probe request still returns the liveness JSON.

Designed against audit findings:

* **C-25** — No ``/health`` or ``/readiness`` endpoint.
* **A-20** — No ``/health`` or ``/readiness`` endpoint.
* **S-14** — Container ``HEALTHCHECK`` instruction can now point at
  ``http://127.0.0.1:8000/health`` instead of relying on the
  container exit code.
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from omniscribe.api.routers import state
from omniscribe.api.schemas.responses import HealthResponse, ReadinessResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check service liveness",
)
@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Check service liveness",
)
async def liveness() -> JSONResponse:
    """Liveness probe — returns 200 if the worker is responding to HTTP.

    No dependencies, no locks, no I/O. Safe to poll at any frequency.
    """
    return JSONResponse(status_code=HTTPStatus.OK, content={"status": "ok"})


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Check service readiness",
)
@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    summary="Check service readiness",
)
async def readiness() -> JSONResponse:
    """Readiness probe — 200 if artifact stores are usable.

    Inspects the in-memory artifact-store lengths and the OCR job
    queue's running flag. Both are O(1) — touching this endpoint does
    not trigger an artifact-store cleanup sweep and does not block on
    any external service.

    Returns 503 if any subsystem reports unhealthy so orchestrators can
    route traffic away without parsing JSON.
    """
    reasons: list[str] = []
    try:
        text_len = len(state.text_artifacts or ())
        meta_len = len(state.metadata_artifacts or ())
        export_len = len(state.export_artifacts or ())
    except Exception as exc:  # pragma: no cover - defensive
        reasons.append(f"artifact stores unreachable: {exc!r}")
        text_len = meta_len = export_len = -1

    queue_running = bool(getattr(state.ocr_job_queue, "running", False))
    if not queue_running:
        reasons.append("ocr_job_queue not running")

    payload: dict[str, object] = {
        "status": "ok" if not reasons else "degraded",
        "artifacts": {
            "text_entries": text_len,
            "metadata_entries": meta_len,
            "export_entries": export_len,
        },
        "ocr_job_queue_running": queue_running,
    }
    if reasons:
        payload["reasons"] = reasons

    status_code = HTTPStatus.OK if not reasons else HTTPStatus.SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=payload)


__all__ = ["router"]
