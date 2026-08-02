# Project Software Fluency Brief — LocalDeepL

## Scope & History Boundary

| Attribute | Value |
|---|---|
| Project | `d:\OCR\LocalDeepL` — Python 3.11+ FastAPI OCR/translation service "LocalDeepL" |
| Source root | `src/local_deepl/` (111 Python files); `scripts/` (16); `frontend/` (5 TS/Svelte); `tests/` (43) |
| Build | uv + Hatchling; ruff (line-length 88, py310→py311 target); mypy (py311, strict subsets); pytest (`slow` marker, asyncio auto) |
| History | 149 commits bounded (30/90/180-day), HIGH confidence, newest `8a12d0d` |
| Working-tree diff | 149 changed files, 105,255 changed lines, diffScore 100 — **inflated by minified vendor bundles under `src/local_deepl/static/assets/*.js`**; treat as a churn risk lead, not a defect |
| Core boundary | No configured core-code boundary (status=missing; boundaryKind=inferred-core-boundary) |
| Inferred core | `core/workflows/{hybrid,grounded,base}.py`, `core/ocr/processor.py`, `api/routers/ocr.py` — the OCR pipeline trigger→engine→emit path |

All claims about tests-passed, CI status, or runtime behavior are marked **UNVERIFIED** — static declarations prove intent/presence only.

---

## Dimension 1: Context Map

### Task Entrypoint — `integrated/observed`

[AGENTS.md](file:///d:/OCR/LocalDeepL/AGENTS.md) (180 lines) is the authoritative agent instruction file. It provides:
- **Quick Start**: 3-step `uv sync` → `uv run local-deepl-server --port 8000` with explicit note that real OCR requires an OpenAI-compatible VLM endpoint (LM Studio default at `http://localhost:1234/v1`).
- **Validation**: exact commands for pytest (fast/slow), ruff, mypy, and frontend (npm build/test).
- **Pipeline Paths**: ASCII diagrams for both hybrid and grounded paths, with stage-by-stage annotations.
- **Key Files table**: 60+ entries mapping every source file to its single responsibility.
- **Known Tech Debt**: explicitly lists synchronous OCR blocking, in-memory-only state, `pages_structured` legacy format, and bootstrapped ground-truth fixtures.
- **Recovery**: 4-step route documenting chunked-run interruption, chunk-size tuning, and the Redis-backend scale-out path.

[ARCHITECTURE.md](file:///d:/OCR/LocalDeepL/ARCHITECTURE.md) (448 lines) provides the system shape, pipeline diagrams, a directory-responsibility table, extension points, shared-state/artifact surface, a non-exhaustive Web API table, and a **Change Blueprint** with dated entries from 2026-06-02 through 2026-07-29 documenting every major refactoring (god-module decomposition, engine split, frontend migration, API aliases).

### Context & Boundary Map — `integrated`

The inferred core boundary is well-delineated:
- **Trigger**: `POST /api/process` → [ocr.py](file:///d:/OCR/LocalDeepL/src/local_deepl/api/routers/ocr.py) (thin orchestrator: validate → build_pipeline → verify_backend_model → `_dispatch_ocr_run` → record job → build response).
- **Engine selection**: [pipeline.py](file:///d:/OCR/LocalDeepL/src/local_deepl/pipeline.py) facade picks `HybridEngine` or `GroundedEngine` based on injected components.
- **Engine contract**: [base.py](file:///d:/OCR/LocalDeepL/src/local_deepl/core/workflows/base.py) `EngineBase` provides `_reset_run_state`, `_cross_page_merge`, `_run_spellcheck`, `_build_document_result`, `_emit` — the single emit point where `last_document_result` is assigned and the output writer is invoked.
- **OCR calls**: [processor.py](file:///d:/OCR/LocalDeepL/src/local_deepl/core/ocr/processor.py) `OCRProcessor` with pre-flight model check, retry, circuit breaker.
- **Dependency direction invariant**: [test_workflows_callback_decoupling.py](file:///d:/OCR/LocalDeepL/tests/test_workflows_callback_decoupling.py) mechanically enforces via AST scan that no `core/*` file imports from `local_deepl.api` — 25 core files checked parametrically.

### Risk & Next-Step Route — `integrated`

AGENTS.md "Known Tech Debt" and "Recovery" sections provide an explicit risk→next-step map:
- Synchronous OCR on uvicorn worker → documented; async path via `OCRJobQueue` (single-worker asyncio) exists for `/api/process/async`.
- In-memory state loss on restart → documented; Redis-backed `StateBackend` is the documented scale-out path.
- No auto-resume for interrupted chunked runs → documented; re-submit + lower `LOCAL_DEEPL_CHUNK_PAGES`.

---

## Dimension 2: Environment Readiness

### Environment Readiness Entry — `integrated`

Multiple entry points for different audiences:
- **Developer**: `uv sync --extra web` → `uv run local-deepl-server` (AGENTS.md Quick Start).
- **Windows end-user**: `install.bat` (bootstraps uv, syncs web extra, creates shortcuts) → `start_app.vbs` (boots Redis + Celery + uvicorn hidden) → `stop_app.bat`.
- **Docker**: [Dockerfile](file:///d:/OCR/LocalDeepL/Dockerfile) (python:3.12-slim, `web` + `async-translation` extras, non-root user, port 8000) + `compose.yaml` (`api` + `redis`, `--profile async` for Celery worker).
- **Environment config**: [.env.example](file:///d:/OCR/LocalDeepL/.env.example) (150 lines documenting every env var with safe defaults and comments). The app reads `.env` via a homegrown zero-dependency parser ([utils/env.py](file:///d:/OCR/LocalDeepL/src/local_deepl/utils/env.py) `load_dotenv`).

### Run & Doctor Command Surface — `runnable baseline`

[Makefile](file:///d:/OCR/LocalDeepL/Makefile) (35 lines) exposes: `help`, `setup`, `run`, `test`, `lint`, `typecheck`, `build-frontend`, `dev-frontend`, `clean`, `doctor`.

`make doctor` delegates to [scripts/dev.py](file:///d:/OCR/LocalDeepL/scripts/dev.py) `doctor()` which checks:
- **uv**: presence + version (core — ERROR if missing).
- **Python**: `sys.version_info >= (3, 11)` (core — ERROR if below).
- **Redis**: TCP socket connect to `REDIS_URL` (optional — WARN).
- **Model server**: HTTP GET `{api_base}/models` with model count (optional — WARN).

`make clean` removes `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `build`, `dist`, `htmlcov`, `__pycache__`, `.coverage*` — safe reset without touching venv or source.

### State Reset & Isolation — `partial/declarative`

- **App state reset**: restart the process (all in-memory singletons are lost). No `make reset` or admin endpoint for partial state clearing — `DELETE /api/jobs` clears job history + text artifacts but not metadata/export artifacts or the job queue.
- **Test isolation**: [conftest.py](file:///d:/OCR/LocalDeepL/tests/conftest.py) provides `_StubOCR` (canned OCR without LM Studio), `surya_aligner` (session-scoped real Surya load for slow tests), `example_pdfs` (on-disk fixtures). Tests use `monkeypatch`, `tmp_path`, and stubs. No dedicated test database or docker-compose isolation harness.
- **Chunk isolation**: per-chunk temp dir under `tempfile.mkdtemp(prefix="ocr_chunk_")`, cleaned in `finally` ([ocr_chunked_runner.py](file:///d:/OCR/LocalDeepL/src/local_deepl/api/services/ocr_chunked_runner.py) line 340).

---

## Dimension 3: Fast Feedback

### Validation Signal Layers — `integrated`

| Layer | Command | Gate | Speed |
|---|---|---|---|
| Fast tests | `uv run pytest -m "not slow"` | CI (every PR/push) + `make test` | "well under two minutes" per CI comment |
| Slow tests | `uv run pytest -m slow` | CI nightly (03:00 UTC) + manual | Loads Surya (~500MB HF Hub); HF cache pinned to locked surya version |
| Lint | `uv run ruff check src tests --no-fix` | CI + `make lint` + pre-commit (with `--fix`) | Seconds |
| Format | `uv run ruff format src tests --check` | CI + pre-commit | Seconds |
| Type | `uv run mypy src` | CI + `make typecheck` + pre-commit (manual stage) | Seconds–minutes |
| Coverage | `--cov=src/local_deepl --cov-branch` | CI (report only, `--cov-fail-under=0`) | Bundled with fast tests |
| JS contract | `npm test` (vitest) | CI (gated on frontend/ diff) + pre-commit (manual) | Seconds |
| Frontend build | `npm run build --prefix frontend` | `make build-frontend` only — **not in CI** | Seconds |
| E2E/browser | `python test_ui.py` (Playwright) | **Not in any CI workflow** | Requires running server + VLM |

### Signal Speed & Actionability — `integrated`

- CI [test.yml](file:///d:/OCR/LocalDeepL/.github/workflows/test.yml) runs on every PR + push to main with `concurrency: cancel-in-progress: true` — stale runs are cancelled.
- Matrix: Python 3.11 (floor) + 3.13 (catch version-specific regressions).
- Nightly [nightly.yml](file:///d:/OCR/LocalDeepL/.github/workflows/nightly.yml) uploads a timing artifact (`--durations=0`) for trend inspection and a failure artifact (lastfailed + log).
- Fast tier runs ruff, mypy, and pytest in sequence within the same job — a lint failure fails fast before tests run.

### Affected Check Routing — `partial`

- **JS gating**: [test.yml](file:///d:/OCR/LocalDeepL/.github/workflows/test.yml) `detect-noop` job uses `dorny/paths-filter@v3` to gate the `js` vitest job on `frontend/**` changes — a docs-only push never pays npm-install cost.
- **Python broad**: the fast pytest job "intentionally stays broad" per CI comment — no per-file affected-test routing (no pytest-testmon, no `--testmon`).
- **No frontend-build-in-CI drift check**: `npm run build` is not run in CI, so stale committed bundles in `static/` are not detected (see Finding 5).

---

## Dimension 4: Quality Gates

### Rule Coverage — `integrated`

- **Ruff**: E, W, F, I, B, C4, UP, SIM, RUF, G (flake8-logging-format). Per-file ignores are documented with reasons (e.g., `RUF001` in `filters.py` for intentional curly-quote stripping). `extend-exclude` removes `.opencode/tmp`, `.mavis`, `scripts/` from the lint surface — measures code that reaches users, not throwaway tooling.
- **Mypy**: `py311`, `warn_unused_configs`, `warn_redundant_casts`, `warn_unused_ignores`, `strict_equality`, `extra_checks`, `check_untyped_defs`, `warn_return_any`. Per-module override: `disallow_untyped_defs = true` for `local_deepl.api.*`, `local_deepl.core.*`, `local_deepl.pipeline` — the production hot path requires explicit annotations.
- **Dependency-direction invariant**: AST scan test enforces core→api import direction.
- **Prompt drift guard**: [test_ocr.py](file:///d:/OCR/LocalDeepL/tests/test_ocr.py) `TestPromptConstants` asserts the canonical OlmOCR prompt string is unchanged.
- **Security**: SSRF fail-closed by default, bearer auth (constant-time `secrets.compare_digest`), upload size limits, rate limiting (per-IP 60s sliding window), token-bound artifact access (opaque IDs).

### Enforcement Gate Strength — `integrated` (CI) / `partial` (pre-commit)

- **CI is authoritative**: ruff check + format check + mypy + pytest on every PR. `fail-fast: false` on the matrix.
- **Pre-commit is opt-in**: `.pre-commit-config.yaml` runs ruff (fix + format) and `uv-lock` on commit. mypy, pytest, and vitest are `stages: [manual]` — they don't run on every commit, only on demand via `pre-commit run --hook-stage manual`.
- **Coverage gate disabled**: `--cov-fail-under=0` in CI means branch coverage is reported but never gates (see Finding 1).
- **No schema/migration gate**: no database, no ORM migrations — not applicable.
- **No generated-artifact drift gate**: frontend compiles to `static/` but CI doesn't verify committed bundles match a fresh build (see Finding 5).

### Rule Repair Path — `integrated`

- Ruff `--fix` available via pre-commit; `--no-fix` in Makefile/CI for reporting.
- Per-file ignores in `pyproject.toml` are each documented with a reason and a deferred-cleanup note.
- mypy `ignore_missing_imports` for optional deps (torch, surya, transformers, etc.) scoped to specific modules.

---

## Dimension 5: Change Safety

### Agent Lifecycle Guardrails — `integrated`

- AGENTS.md documents deprecated paths (`local-deepl` CLI script removed; do not restore), conventions (bbox normalization `[x0,y0,x1,y1]` in `0..1` until `embed_structured_text`; `tqdm_patch.apply()` ordering), and extension points (injected `aligner`, `ocr_processor`, `pdf_handler`, `output_writer`, `grounded_backend`, `document_processors`, `page_preprocessor`).
- The dependency-direction AST scan test prevents core→api coupling regressions.
- `EngineBase._reset_run_state()` is called at the top of every `execute()` — run-scoped state is always fresh.
- Per-page exception isolation: `_stage_ocr` catches per-page exceptions, logs them, and returns the exception object for `_stage_align` to handle (record to `last_failed_pages`, fire `on_warning`).

### Merge Acceptance Path — `integrated`

- CI gates on ruff + mypy + pytest for every PR.
- [release.yml](file:///d:/OCR/LocalDeepL/.github/workflows/release.yml) auto-releases on version bump in `pyproject.toml`: reads version, validates PEP 440, checks tag uniqueness, builds wheel+sdist **before** tagging (broken build → no tag), updates README pin, tags, creates GitHub release with wheel attached.
- `concurrency: cancel-in-progress: true` on test.yml prevents redundant CI runs.

### Side-Effect / Permission / Recovery Boundary — `integrated`

- **In-memory state**: [state_backend.py](file:///d:/OCR/LocalDeepL/src/local_deepl/api/services/state_backend.py) `LocalStateBackend` — module docstring: "All state is lost on restart." Documented in AGENTS.md, ARCHITECTURE.md, and [ocr_jobs.py](file:///d:/OCR/LocalDeepL/src/local_deepl/api/services/ocr_jobs.py) ("Restart loses pending jobs is intentional and documented").
- **Chunked recovery**: [ocr_chunked_runner.py](file:///d:/OCR/LocalDeepL/src/local_deepl/api/services/ocr_chunked_runner.py) — per-chunk failures don't abort the whole run; failed pages rolled into `X-Failed-Pages`. Per-chunk temp dir cleaned in `finally`. Merged output is **not checkpointed between chunks** — no auto-resume. Cancel propagates between chunks via `manager.is_cancelled()`.
- **VLM resilience**: [resilience.py](file:///d:/OCR/LocalDeepL/src/local_deepl/core/ocr/resilience.py) — retry-on-transient (429/5xx/connection resets) with exponential backoff; per-endpoint circuit breaker (closed/open/half-open) fails fast after `LOCAL_DEEPL_CB_FAILURE_THRESHOLD` (default 5) consecutive failures. Shared via `CircuitBreakerRegistry` keyed by `(api_base, model)`.
- **Job cancel**: pending jobs removed from queue; processing jobs marked `ERROR` ("cancelled by client") — the running pipeline cannot be safely interrupted (no asyncio task handle).
- **Upload safety**: streaming upload byte limits, content-signature detection, temp-file cleanup in `finally`.
- **SSRF**: fail-closed by default; `ALLOW_SSRF_LOCAL=true` is the dev default, must be `false` for untrusted users.

---

## Strongest Capabilities

1. **Exceptional context map**: AGENTS.md + ARCHITECTURE.md provide a complete, dated, responsibility-mapped blueprint. An agent can reach the right file, understand its boundary, identify the risk, and find the next step without guessing. The Change Blueprint creates an auditable trail of every architectural decision.

2. **Mechanical dependency-direction enforcement**: the AST scan test in [test_workflows_callback_decoupling.py](file:///d:/OCR/LocalDeepL/tests/test_workflows_callback_decoupling.py) makes the core→api import invariant enforceable — 25 files checked parametrically. This is an `observed/auditable` gate.

3. **Layered VLM resilience**: retry + circuit breaker + pre-flight model check compose to handle the most common local-VLM failure modes (transient 5xx, dead endpoint, silent model fallback). Env-tunable, documented, and unit-tested ([test_ocr_resilience.py](file:///d:/OCR/LocalDeepL/tests/test_ocr_resilience.py), [test_circuit_breaker_registry.py](file:///d:/OCR/LocalDeepL/tests/test_circuit_breaker_registry.py)).

4. **Chunked OCR runner with per-chunk fault isolation**: large documents are sliced into bounded chunks; per-chunk failures are collected, not fatal. The recovery route (re-submit, lower chunk size, Redis backend) is explicitly documented.

5. **Affected-check routing for JS**: the `detect-noop` + `dorny/paths-filter` pattern in CI gates the vitest job on frontend changes — a Python-only push skips the npm install entirely.

---

## Core Risks

1. **In-memory-only state with no persistence or checkpoint** — all job/artifact/progress state lives in process-local singletons. An interrupt mid-chunked-run has no resume capability; a restart loses everything. This is the project's largest operational risk, explicitly acknowledged as known tech debt with a documented but unimplemented Redis-backend path.

2. **Synchronous OCR on the uvicorn worker** — `POST /api/process` runs the full pipeline synchronously; long jobs block other requests on the same worker. The async queue (`/api/process/async`) is single-worker and also in-memory. No horizontal scaling.

3. **Large uncommitted working-tree diff** — 149 changed files / 105,255 lines, largely inflated by minified vendor bundles committed to `static/`. This obscures real source churn and makes review harder.

4. **No coverage gate** — branch coverage is reported in CI but `--cov-fail-under=0` means it never blocks a merge.

5. **Dead code on the hybrid execute path** — `HybridEngine.execute()` uses refactored staged methods (`_stage_ocr`, `_stage_align`, `_stage_postprocess`, `_stage_finalize`), but the legacy monolithic methods (`_ocr_pages`, `_finalize`) remain in the file and are directly tested by [test_workflows_hybrid.py](file:///d:/OCR/LocalDeepL/tests/test_workflows_hybrid.py). Tests validate code that is not on the production path.

---

## Test & Observability Coverage

### Test coverage for the core change-risk path

| Path stage | Test file | Coverage type |
|---|---|---|
| `HybridEngine.execute()` end-to-end | [test_pipeline.py](file:///d:/OCR/LocalDeepL/tests/test_pipeline.py), [test_workflows_callback_decoupling.py](file:///d:/OCR/LocalDeepL/tests/test_workflows_callback_decoupling.py) | E2e with stubs (stub aligner, stub OCR, stub PDF) |
| `HybridEngine` per-phase (legacy methods) | [test_workflows_hybrid.py](file:///d:/OCR/LocalDeepL/tests/test_workflows_hybrid.py) | Per-phase unit (convert, detect, select_dense, ocr_pages, refine, finalize) — **see Finding 3** |
| `EngineBase` (cross-page merge, spellcheck, emit, state lifecycle) | [test_workflows_base.py](file:///d:/OCR/LocalDeepL/tests/test_workflows_base.py) | Per-method unit including state reset, metadata overlay |
| `GroundedEngine` | [test_grounded.py](file:///d:/OCR/LocalDeepL/tests/test_grounded.py), [test_grounded_block_callbacks.py](file:///d:/OCR/LocalDeepL/tests/test_grounded_block_callbacks.py) | Pipeline routing, bbox preservation, failed-page propagation, callback emission |
| `OCRProcessor` (prompts, filters, model check) | [test_ocr.py](file:///d:/OCR/LocalDeepL/tests/test_ocr.py) | YAML strip, runaway repetition, hallucination filter, model-loaded pre-flight (no LLM calls) |
| VLM resilience (retry, circuit breaker) | [test_ocr_resilience.py](file:///d:/OCR/LocalDeepL/tests/test_ocr_resilience.py), [test_circuit_breaker_registry.py](file:///d:/OCR/LocalDeepL/tests/test_circuit_breaker_registry.py) | Transient classification, fail-fast, half-open probe, shared registry |
| `POST /api/process` router | [test_api_safety.py](file:///d:/OCR/LocalDeepL/tests/test_api_safety.py), [test_integration.py](file:///d:/OCR/LocalDeepL/tests/test_integration.py) | SSRF, upload validation, stable errors, alias routes, form processing |
| Chunked runner | [test_chunked_runner.py](file:///d:/OCR/LocalDeepL/tests/test_chunked_runner.py) | Chunk splitting, merge, per-chunk failure continuation |
| Negative/recovery cases | Multiple | OCR failure recording + warning callback, chunk failure continuation, circuit breaker fail-fast, empty OCR response, thin/tiny box skip |

### Observability

- **Logging**: Python stdlib `logging.getLogger(__name__)` throughout core and API modules. Warning-level for per-page OCR failures, chunk failures, circuit-breaker state transitions, parser failures. Exception-level for unrecoverable OCR processing failures. `G` (flake8-logging-format) ruff rule active to catch f-strings in logger calls.
- **Progress transport**: token-bound WebSocket (`/ws/{channel_id}?token=...`) with stage→percent mapping, per-block/per-page events, chunk_complete frames, cancel propagation.
- **Job history**: `JobHistory` with per-page failure tracking, duration, status — retrievable via `GET /api/jobs`.
- **No structured logging sink**: stdout/stderr only. No metrics, tracing, or log aggregation configured.
- **No runtime smoke in CI**: `test_ui.py` (Playwright) requires a running server + VLM endpoint; not wired into CI.

---

## Potential Findings

### Finding 1: Coverage gate disabled — branch coverage reported but never enforced

**Consequence**: A regression that drops coverage below an acceptable floor still merges. The CI invests in branch-coverage reporting (`--cov-branch`) but sets `--cov-fail-under=0`, making the data informational only. An agent modifying the core change-risk path gets no mechanical signal that its changes reduced coverage.

**Evidence**: [test.yml](file:///d:/OCR/LocalDeepL/.github/workflows/test.yml) line 65: `uv run --with pytest-cov pytest -m "not slow" --cov=src/local_deepl --cov-branch --cov-report=term --cov-fail-under=0`. The CI comment explicitly calls out "the delta between line and branch coverage is the cheapest proxy for exercising every arm of if/elif chains" — but the gate is off.

**Owner boundary**: `.github/workflows/test.yml` + `pyproject.toml` `[tool.pytest.ini_options]`.

**Uncertainty**: The threshold may be intentionally zero during active development (the project is `Development Status :: 4 - Beta`). A floor may not be appropriate until the codebase stabilizes. UNVERIFIED whether coverage is trending or monitored outside CI.

---

### Finding 2: HybridEngine retains and tests dead code paths not called by `execute()`

**Consequence**: `HybridEngine.execute()` (lines 66–173) was refactored to call staged methods (`_stage_ocr`, `_stage_align`, `_stage_postprocess`, `_stage_finalize`), but the legacy monolithic methods (`_ocr_pages` lines 522–625, `_finalize` lines 657–695) remain in the file. [test_workflows_hybrid.py](file:///d:/OCR/LocalDeepL/tests/test_workflows_hybrid.py) tests `_ocr_pages` and `_finalize` directly — these methods are **not on the production execute path**. An agent modifying the staged methods (the live path) may believe the existing tests cover their changes, but they do not. Conversely, changes to the legacy methods are tested but irrelevant to production behavior. This is a churn risk on the 30-day hottest file (6 commits, churn 238).

**Evidence**: [hybrid.py](file:///d:/OCR/LocalDeepL/src/local_deepl/core/workflows/hybrid.py): `execute()` calls `_stage_ocr` (lines 209–259, own implementation with `process_page_ocr`) and `_stage_align` (lines 261–326, own implementation), not `_ocr_pages` (lines 522–625, different implementation with `completed_lock` and inline callback emission). `execute()` calls `_stage_postprocess` (lines 354–381) + `_stage_finalize` (lines 383–399), not `_finalize` (lines 657–695). [test_workflows_hybrid.py](file:///d:/OCR/LocalDeepL/tests/test_workflows_hybrid.py) `TestHybridOCRPages` tests `_ocr_pages` and `TestHybridFinalize` tests `_finalize`.

**Owner boundary**: `src/local_deepl/core/workflows/hybrid.py` + `tests/test_workflows_hybrid.py`.

**Uncertainty**: The legacy methods may be retained intentionally for backward compatibility with in-process programmatic callers who invoke them directly (bypassing `execute()`). However, AGENTS.md states `OCRPipeline` is the facade and the CLI is deprecated — there is no documented public API for calling `_ocr_pages` directly. The staged methods and legacy methods have materially different implementations (different concurrency structure, different callback emission timing), so they are not equivalent.

---

### Finding 3: E2E/browser smoke test not wired into CI

**Consequence**: The Playwright smoke test ([test_ui.py](file:///d:/OCR/LocalDeepL/test_ui.py)) is documented in AGENTS.md and ARCHITECTURE.md as the "headless Playwright smoke test against the running web UI" but is not run in any GitHub Actions workflow. The recent Svelte 5 + Tailwind v4 frontend migration (2026-07-29) is protected only by vitest contract tests (sentinel/streaming behavior), not by an actual browser smoke against `examples/dense.pdf`. A UI regression that passes vitest but breaks the browser interaction surface would merge undetected.

**Evidence**: No workflow file references `test_ui.py`. [test.yml](file:///d:/OCR/LocalDeepL/.github/workflows/test.yml) `js` job runs `npm test` (vitest) only. `test_ui.py` requires a running server + VLM endpoint, which CI does not provision.

**Owner boundary**: `.github/workflows/test.yml` + `test_ui.py`.

**Uncertainty**: The test may be intentionally excluded from CI because it requires a running server and a VLM endpoint (LM Studio), which are not available in the CI environment. A mocked version could close this gap but does not exist.

---

### Finding 4: In-memory state with no persistence, checkpoint, or horizontal-scaling path

**Consequence**: All job/artifact/progress state lives in process-local singletons ([state_backend.py](file:///d:/OCR/LocalDeepL/src/local_deepl/api/services/state_backend.py) `LocalStateBackend`). A server restart drops the merged PDF, merged text artifact, in-flight job record, job history, and all token-bound artifacts. An interrupted chunked OCR run has no auto-resume — the merged output is not checkpointed between chunks. There is no horizontal scaling: a second worker process has no shared state. This is the project's largest operational risk.

**Evidence**: `LocalStateBackend` module docstring: "All state is lost on restart." [ocr_jobs.py](file:///d:/OCR/LocalDeepL/src/local_deepl/api/services/ocr_jobs.py) class docstring: "Restart loses pending jobs." [ocr_chunked_runner.py](file:///d:/OCR/LocalDeepL/src/local_deepl/api/services/ocr_chunked_runner.py): merged output path "is not checkpointed between chunks in this iteration, so an interrupted run does not resume automatically." AGENTS.md Recovery section documents the path: swap `LocalStateBackend` for a Redis-backed `StateBackend`.

**Owner boundary**: `src/local_deepl/api/services/state_backend.py` + `src/local_deepl/api/routers/state.py` + `src/local_deepl/api/services/ocr_jobs.py` + `src/local_deepl/api/services/ocr_chunked_runner.py`.

**Uncertainty**: This is explicitly acknowledged as known tech debt with a documented but unimplemented scale-out path. The `StateBackend` Protocol and `LocalStateBackend` dataclass are designed for swap-in — the architecture is ready; the implementation is not. The project is `Development Status :: 4 - Beta` and targets local-desktop deployment, where single-process in-memory state may be acceptable.

---

### Finding 5: No generated-artifact drift gate for committed frontend bundles

**Consequence**: The Svelte 5 frontend compiles to `src/local_deepl/static/` via Vite, and the compiled minified bundles are committed to the repo (a major contributor to the 105,255-line working-tree diff). No CI step runs `npm run build` and diffs the output against the committed `static/` directory. A stale or hand-edited frontend bundle can ship in a wheel without detection — the Python package build (`uv build`) packages whatever is in `static/` regardless of whether it matches the current frontend source.

**Evidence**: [test.yml](file:///d:/OCR/LocalDeepL/test.yml) has no `npm run build` step. [Makefile](file:///d:/OCR/LocalDeepL/Makefile) has `build-frontend` but it is not called by CI. [ARCHITECTURE.md](file:///d:/OCR/LocalDeepL/ARCHITECTURE.md) documents: "Frontend source code resides in `frontend/` and compiles via Vite directly into `src/local_deepl/static/`." The [Dockerfile](file:///d:/OCR/LocalDeepL/Dockerfile) does not rebuild the frontend — it packages the committed `static/` as-is.

**Owner boundary**: `.github/workflows/test.yml` + `frontend/vite.config.ts` + `src/local_deepl/static/`.

**Uncertainty**: The committed bundles may be intentionally the source of truth for wheel builds (zero runtime Node.js dependency for end users). A drift check would add CI time (npm install + build). The risk is lower if the frontend is rebuilt manually before every release, but this is not mechanically enforced.

---

## Missing Evidence

- **Tests-passed / CI status**: UNVERIFIED. No tests were executed during this review. CI pass/fail status is not available from static inspection.
- **Runtime behavior**: UNVERIFIED. No server was started; no OCR pipeline was run.
- **Coverage trend**: the `.coverage` file exists in the repo root, but its contents and trend were not inspected.
- **`openapi.json`**: exists in `tests/` — not inspected for schema completeness or drift against the actual API.
- **`compose.yaml`**: not read — the Docker Compose service topology (api + redis + optional celery worker) is documented but not verified.
- **Frontend test coverage**: `frontend/` vitest tests were not inspected — only their existence and CI gating were verified.
- **`scripts/` debug tools**: 16 scripts exist but are excluded from ruff lint and were not individually inspected beyond `dev.py`.

---

## Claims the Lead Must NOT Make from This Evidence

1. **Do NOT claim tests pass or CI is green** — no tests were executed; CI status was not checked.
2. **Do NOT claim the OCR pipeline produces correct output at runtime** — only static structure and test declarations were inspected.
3. **Do NOT claim the circuit breaker or retry logic works under load** — the implementation is present and unit-tested with stubs, but no live VLM endpoint was exercised.
4. **Do NOT claim the frontend bundles in `static/` are stale or correct** — no build-and-diff was performed; only the absence of a drift gate was identified.
5. **Do NOT claim the dead code in `hybrid.py` is safe to delete** — the legacy methods may have undocumented callers (in-process programmatic use, scripts, or tests not inspected); removal requires a usage audit.
6. **Do NOT claim the in-memory state loss is a defect** — it is explicitly documented as intentional known tech debt with a designed swap-in path; whether it is acceptable depends on the deployment context (local-desktop vs. server).
7. **Do NOT assign severity, scores, or prescriptive repairs** — this brief identifies evidence and consequences only; prioritization requires the lead's broader context.
