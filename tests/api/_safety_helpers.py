"""Shared FastAPI test-app builders for the ``tests/api`` suites.

Split out of the former monolithic ``tests/test_api_safety.py`` —
several domain suites need the same router-mounted ``TestClient``,
the canonical ``/process`` form payload, and the public-DNS stub
that satisfies the SSRF guard without network access.
"""

from __future__ import annotations

import socket

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omniscribe.api.routers import (
    artifacts,
    config,
    extraction,
    jobs,
    ocr,
    translation,
    websocket,
)
from omniscribe.api.services.envelope import register_envelope_handlers


def _api_client() -> TestClient:
    app = FastAPI()
    register_envelope_handlers(app)
    app.include_router(config.router)
    app.include_router(translation.router)
    app.include_router(extraction.router)
    app.include_router(ocr.router)
    app.include_router(websocket.router)
    app.include_router(jobs.router)
    app.include_router(artifacts.router)
    return TestClient(app)


def _public_dns(host: str, port, *args, **kwargs):
    """Stub ``socket.getaddrinfo``: only ``api.openai.com`` resolves."""
    if host == "api.openai.com":
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.18.3.161", 443))]
    raise socket.gaierror(-2, "Name or service not known")


def _process_form() -> dict[str, str]:
    return {
        "client_id": "same-client",
        "api_base": "http://api.openai.com/v1",
        "api_key": "test-key",
        "model": "openai/test-model",
        "pipeline_mode": "hybrid",
        "dpi": "200",
        "concurrency": "1",
        "dense_mode": "auto",
        "dense_threshold": "60",
        "refine": "true",
        "max_image_dim": "1024",
        "self_correction": "false",
        "binarize": "false",
        "dual_engine": "false",
        "spellcheck": "none",
        "cross_page": "false",
        "preprocess_pages": "false",
        "orientation_detection": "false",
        "deskew": "false",
        "denoise": "false",
        "normalize_contrast": "false",
        "crop_cleanup": "false",
        "quality_routing": "false",
    }


def _process_form_kwargs() -> dict[str, str]:
    """Same as :func:`_process_form` but expressed as kwargs for ``resolve_process_settings``.

    Tests that drive :func:`omniscribe.api.routers.ocr._run_ocr_pipeline`
    directly (rather than via :class:`fastapi.testclient.TestClient`) need
    a ``ProcessSettings`` instance, which means going through
    :func:`omniscribe.api.services.ocr_settings.resolve_process_settings`.
    That resolver accepts the same fields as ``_process_form`` but spread
    as keyword arguments.
    """
    form = _process_form()
    # ``client_id`` is a FastAPI form field, not a ProcessSettings field;
    # it is accepted but ignored by the resolver.
    form.pop("client_id", None)
    return form


def _pdf_upload() -> tuple[str, bytes, str]:
    return ("input.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")
