# Changelog

All notable changes to OmniScribe are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Windows quick-start robustness (install.ps1 + start_app.vbs)** —
  the Windows one-click launcher no longer silently fails on
  re-launch. `start_app.vbs` now writes a timestamped log to
  `start_app.log` next to itself, pre-checks that `uv` is on PATH
  (pops a clear "log out so PATH updates" dialog if not),
  reuses the existing `redis-local-ocr` container via
  `docker start` or creates a new one with `--rm`, skips
  Redis + Celery gracefully if the Docker daemon is not
  reachable (async translation is the only thing that
  breaks), and polls `http://localhost:8000` until uvicorn
  actually responds (max 60 s) before opening the browser.
  `install.ps1` now wraps the `uv` installer in a try/catch,
  fails fast on `uv sync` errors via `$LASTEXITCODE`, runs
  `uv run python --version` to verify the venv is usable, and
  prints a clear "log out so PATH updates" callout at the end.
- **Speech transcription endpoint** — new
  `POST /api/transcribe` route plus
  `GET/POST /api/config/transcription` and
  `GET /api/models/transcription` for the transcription
  provider; gated by the new `OMNISCRIBE_TRANSCRIPTION_AUTH_TOKEN`
  env var (falls back to the global `OMNISCRIBE_AUTH_TOKEN`).
  Bypasses bearer auth on `/health`, `/healthz`, `/ready`,
  `/readyz` regardless of token configuration.

### Fixed

- **Documentation drift**:
  `/api/health` is not a real route; the liveness probe is
  `GET /health` (alias `/healthz`), with `GET /ready` (alias
  `/readyz`) for readiness. `DEPLOYMENT.md` and the
  `Dockerfile` healthcheck block now point at `/health`.
  `ARCHITECTURE.md` listed `/api/models/all`; the real
  combined route is `GET /api/models` (with
  `/api/models/ocr` and `/api/models/translation` siblings).
  `SECURITY.md` referenced a non-existent
  `OMNISCRIBE_CANCEL_SECRET` env var; cancel is an
  in-process `asyncio.Event` per `channel_id`, no signature.
  `DEPLOYMENT.md` documented third-party VLMs under
  `LLM_API_BASE` / `LLM_API_KEY`; the actual env vars are
  `OMNISCRIBE_LLM_API_BASE` / `OMNISCRIBE_LLM_API_KEY`
  (with `OMNISCRIBE_LLM_MODEL`).

- **OCR quality trust layer (Phase 1, foundation)** — new
  `omniscribe.core.ocr_quality` package ships six sub-modules
  (`watermark`, `script_detector`, `hallucination`, `calibration`,
  `trust_scorer`, `orchestrator`) plus an `events` log channel. Every
  sub-module defaults to **off** and fails open — no behavioural change
  for existing callers. `DocumentBlock` gains optional
  `trust_score: float | None` and `trust_flags: tuple[str, ...] | None`
  fields (always `None` until the layer is enabled).
  - New `OCrQualitySettings` Pydantic config (`extra="forbid"`).
  - `pyproject.toml` gains `[tool.omniscribe.ocr_quality]` workspace
    defaults, a `slow_dataset` pytest marker, and a `hypothesis` dev
    dependency for property tests on the pure trust formula.
  - New user-facing docs at `docs/ocr_quality.md`. Phase 2 (defaults on,
    Web UI Trust panel) and Phase 3 (calibration training, dataset
    regression) are planned but not yet shipped.
- **OCR quality trust layer (Phase 2, defaults on)** — wires the trust
  orchestrator into both engines and the `/api/process` route.
  - `OCRPipeline.__init__` accepts `trust_orchestrator=`; the
    `TrustOrchestrator` runtime-checkable Protocol in
    `omniscribe.core.ocr_quality.orchestrator` documents the
    `(blocks, page_image, *, model_id, page_size=None)` contract.
  - `EngineBase` gains `trust_orchestrator` and a no-op default
    `_apply_trust`; `HybridEngine` and `GroundedEngine` override it
    per page (Hybrid decodes the page image from base64; Grounded
    passes `None` because it has no page image in scope). Failures
    in the orchestrator log at DEBUG and fall back to the input
    blocks (design §7 fail-open contract).
  - `ProcessSettings.quality_options: OCrQualitySettings | None` with
    a `field_validator(mode="before")` that accepts `None`, a dict, a
    JSON-encoded string (multipart form), or an existing
    `OCrQualitySettings` instance.
  - `_form_param_keys()` and `process_pdf` / `process_pdf_async` carry
    the new `quality_options` form field through `resolve_process_settings`.
  - `ocr_pipeline_factory.build_pipeline` instantiates the
    orchestrator via `build_trust_orchestrator(settings.quality_options)`
    (returns `None` when every sub-module is off). Both pipeline
    branches pass it to `OCRPipeline(trust_orchestrator=...)`.
  - `/api/process` forwards `trust_model_id=settings.model` to
    `pipeline.run(...)` so calibration picks the right per-model JSON.
  - New `X-Document-Trust` response header carries a compact JSON
    summary (`block_count`, `scored_count`, `flagged_count`,
    `average`, 5-bin `histogram`, `flag_counts`) — emitted only when
    at least one block has a `trust_score`. The header is omitted
    entirely when the layer is off, keeping the no-orchestrator
    default byte-identical.
  - Phase 2 / Phase 3 keep the new defaults behind per-workspace
    toggles (`phase2_default: bool = False`,
    `phase3_default: bool = False`) so existing setups see no
    behaviour change.
- **OCR quality trust layer (Phase 3, calibration + dataset regression)**.
  - `scripts/calibrate_model.py` — CLI that fits Platt scaling
    `sigmoid(a * raw + b)` from an OCR-Quality-format JSON fixture
    via pure-numpy bounded gradient descent with backtracking
    line-search (`omniscribe.core.ocr_quality.calibration_fit.fit_platt`).
    Default `--train-fraction 0.8`, `--min-records 50`, `--seed 42`.
    Reports ECE (Expected Calibration Error, 10-bin weighted) on the
    held-out 20%; the acceptance criterion is ≥ 20% drop vs. raw.
  - `scripts/fetch_datasets.py` — downloads OCR-Quality and KIE-HVQA
    fixtures under `tests/fixtures/datasets/`. Datasets are not
    bundled in the repo (license review pending); the
    `slow_dataset` regression tests skip cleanly when absent.
  - `src/omniscribe/resources/calibration/qwen2_5_vl_72b.json` —
    shipped pre-trained calibration file fit on
    `tests/fixtures/datasets/ocr_quality_synthetic_qwen.json` (500
    records). ECE drop: 0.0999 → 0.0783 (21.6%, exceeds the ≥ 20%
    acceptance).
  - `tests/test_ocr_quality_calibration_regression.py`,
    `tests/test_kie_hvqa_hallucination_regression.py`,
    `tests/test_calibrate_model_script.py`,
    `tests/test_fetch_datasets_script.py`,
    `tests/test_ocr_quality_calibration_fit.py` — dataset-driven
    regression tests (12 Platt-fit, 6 calibration, 3 dataset-script,
    7 calibrate-script tests). Full-fixture paths are `slow_dataset`-
    gated; the `slow_dataset` mini-fixture smoke tests run with the
    fast suite.
  - `.github/workflows/nightly.yml` gains the calibration regression
    job (03:00 UTC) that runs `pytest -m slow_dataset` against the
    fetched datasets with cached HF Hub snapshots.
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