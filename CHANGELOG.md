# Changelog

All notable changes to OmniScribe are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **SECURITY.md** — vulnerability disclosure policy, threat model,
  hardening checklist. (D1)
- **DEPLOYMENT.md** — three deployment profiles (local, LAN, public)
  with Caddy + docker-compose reference. (D1)
- **CHANGELOG.md** — this file. (D1)
- `OMNISCRIBE_AUTH_TOKEN`, `OMNISCRIBE_OCR_AUTH_TOKEN`,
  `OMNISCRIBE_TRANSLATION_AUTH_TOKEN` reject well-known placeholder
  values at startup (e.g. `change-me-in-prod`). (M10)
- `AuthTokenUpdate.auth_token` field carries `min_length=32` and a
  custom weak-pattern check. (M1)
- `urllib` redirect handler validates every `Location` hop through
  `is_ssrf_target` (no more silent walk to `169.254.169.254`).
  (M2)
- `OMNISCRIBE_MAX_UPLOAD_MB` default bumped to 10 GB; absolute
  ceiling 100 GB.
- `MaxUploadSizeMiddleware` rejects oversized chunked uploads
  (cumulative byte accounting; was per-chunk before). (T2 / H2)
- `MaxUploadSizeMiddleware` is now wrapped around `send()` so a
  detected overflow actually emits a 413, not the inner app's
  empty-body 422. (T2 / H2)
- `BearerAuthMiddleware` accepts per-service tokens
  (`OMNISCRIBE_OCR_AUTH_TOKEN`, `OMNISCRIBE_TRANSLATION_AUTH_TOKEN`)
  for OCR- and translation-only routes.
- Dockerfile base image is digest-pinned. (M7)
- Dockerfile uv install is version-pinned. (M8)
- Dockerfile HEALTHCHECK against `/api/health`. (M11)
- `compose.yaml` binds the API + Redis to `127.0.0.1` only. (M9)
- `_emit` writes a terminal error progress frame if the output
  writer raises, so the UI does not appear stuck. (E3)
- `test_size_limits.py` covers chunked-upload overflow (single chunk
  and cumulative). (T2)
- `test_http_fetch.py` covers urllib SSRF redirect blocking. (T2)
- `test_websocket_handler.py` covers `/api/progress/cancel`
  session-token binding (missing header, wrong token, unbound
  channel, success). (T2)

### Changed

- `process_pdf` / `process_pdf_async` share a single
  `_prepare_process_request` helper (was duplicated ~60 lines of
  validation/upload). (Q1)
- `Any`-typed `manager_send_block` / `manager_send_page_complete`
  callbacks replaced by a `ConnectionManagerLike` Protocol. (Q2)
- Runner dependencies lifted from routers to a factory module
  (`ocr_pipeline_factory.py`). (Q3)
- Synchronous `json.load` / `open` calls inside async handlers are
  wrapped in `asyncio.to_thread`. (Q4)
- `_convert_pages` tautology guard simplified to `if pages:`. (Q5)
- `_ai_error_response` deduplicated to one definition in
  `common.py`. (Q6)
- TrOCR dual-engine fallback catches `LLMCallError` separately so
  the page-isolation boundary sees secondary-VLM failures as
  engine-down signals instead of swallowing them. (E2)
- `OCRProcessor` no longer uses `getattr(self, "handwriting_mode",
  False)` — the attribute is unconditionally set in `__init__`.
  (E4)
- `_PYMUPDF_AGPL_NOTICE_EMITTED` race documented as acceptable
  (logging-only idempotent). (E5)
- Dependency upper pins tightened across `pyproject.toml` and
  `frontend/package.json`:
  - `pillow>=11.3,<13`
  - `httpx>=0.27.2,<0.29` (CVE-2025-43859 floor)
  - `requests>=2.32.0` (CVE-2024-35195 floor)
  - `openai>=2.11.0,<3`
  - `fastapi>=0.124,<1.0`
  - `pymupdf>=1.27,<2`
  - `torch>=2.0,<3`
  - `redis>=5.0,<9`
  - `langgraph>=0.1,<2`
  - `chromadb>=0.5,<2`
- `block_metadata_overlays` typed as `Mapping[...]` so the
  `_cross_page_merge` cast is gone. (A5)
- `ARCHITECTURE.md` adds the missing `/api/config/ocr`,
  `/api/config/translation`, `/api/models/ocr`,
  `/api/models/translation`, `/api/models/all`, and
  `/api/glossary/library/*` routes. (D1)

### Removed

- `markdown-it` frontend dependency (no imports — dead). (Deps)
- `@types/markdown-it` frontend dev dependency. (Deps)
- Vite `manualChunks` branch for `markdown-it`. (Deps)

### Deferred

- A1 — ASGI middleware is intentional for pre-routing enforcement;
  per-router `dependencies=[Depends(...)]` is no safer in practice.
- A2 — module-level state singletons are the right shape until the
  Redis backend ships.
- A3 — frontend store consolidation is out of scope for the backend
  audit.
- A4 — lazy imports are intentional for cold-start perf.

## [0.1.0] — Initial public release

- Hybrid OCR pipeline (Surya detection + VLM OCR + DP align + refine).
- Grounded OCR path (`grounded_backend=`).
- WebSocket-bound progress with token-bound channels.
- Glossary RAG for translation (`async-translation` + `memory` extras).
- Svelte 5 + Tailwind CSS v4 workstation UI.
- Single-worker FastAPI server with optional Celery background jobs.

[Unreleased]: https://github.com/Sifr-r/OmniScribe/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Sifr-r/OmniScribe/releases/tag/v0.1.0