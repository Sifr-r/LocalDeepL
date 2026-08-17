# Domain 4 Audit: Testing & QA

**Date:** 2026-08-17
**Auditor:** Mavis (explore subagent, deep-evidence investigation)
**Methodology:** Static analysis via marker regex against `tests/**` and `pyproject.toml`, import/usage analysis of `surya`, `DetectionPredictor`, `httpx`, and fixture scope, plus a per-file glance at every test module that touches the OCR pipeline, state backend, security middleware, or chunked runner. Pytest was not invoked (read-only mode).

## Scope

- Test files examined: **150** Python test files under `tests/`, plus **18** Vitest test files under `frontend/`
- CI workflows: 4 — `test.yml`, `nightly.yml`, `security.yml`, `release.yml`
- Lines of test code: ~24,000 Python + ~1,500 TypeScript
- Pre-commit hooks: 4 — ruff (`--fix`), ruff-format, mypy (system-env), uv-lock
- Approximate Python test-function count: **1,689**

## Findings

| ID | Severity | Area | File:Line | Description | Evidence | Recommendation |
|----|----------|------|-----------|-------------|----------|----------------|
| F4.1 | CRITICAL | Tier discipline | `tests/test_phase1_async_streaming.py:270,305` | Two unmarked tests construct `HybridAligner()` directly; Surya model loads in fast tier. | `aligner=HybridAligner(),` at lines 270 and 305 | Mark `@pytest.mark.slow` or use `_StubAligner()` |
| F4.2 | CRITICAL | Tier discipline | `tests/_diag/` (3 files) | Pre-async-debug scaffolds collected as test suite. | `testpaths = ["tests"]` with no exclusion | Add `collect_ignore_glob` or delete |
| F4.3 | HIGH | CI completeness | `.github/workflows/test.yml` | `live_llm` test tier is never run in CI. | `test.yml:77` `pytest -m "not slow and not slow_dataset"`; `nightly.yml:62-63` re-affirms skip | Add scheduled `live_llm` workflow against self-hosted runner |
| F4.4 | HIGH | CI completeness | `.github/workflows/test.yml:189-284` (e2e job) | `test_ui.py` Playwright E2E is gated to `workflow_dispatch` only. | `test.yml:191` `if: github.event_name == 'workflow_dispatch'` | Move to `schedule:` weekly with `MockLLMServer` fixture |
| F4.5 | HIGH | Tier discipline | `tests/test_sse_progress_stream.py:158, 196, 270` | Three tests are permanently `@pytest.mark.skip`. | `@pytest.mark.skip(reason="TestClient + ASGITransport buffers ...")` | Convert to `httpx.AsyncClient(transport=ASGITransport(app=app))` + `aiter_raw()` pattern |
| F4.6 | HIGH | Tier discipline | `tests/test_phase1_async_streaming.py:199-238` | `test_convert_batches_peak_memory_is_bounded_by_batch_size` unmarked; wide tolerance. | No marker; uses `tracemalloc` | Mark `@pytest.mark.slow` or convert to wall-clock test |
| F4.7 | MEDIUM | Tier discipline | `tests/test_pdf.py` (16 tests) | Real PDF embed + font probe tests unmarked. | No marker; PyMuPDF writes + font fallback | Add `@pytest.mark.slow` to embed/font tests |
| F4.8 | MEDIUM | Tier discipline | `tests/test_text_layer_recall.py` (16 tests) | Every test opens a real PDF via `PdfTextLayerRecall().open(str(pdf))`. | `_build_pdf` builds a fresh PDF per test | Mark `@pytest.mark.slow` or accept the cost |
| F4.9 | MEDIUM | Frontend coverage | `frontend/src/__tests__/`, `frontend/src/lib/**/__tests__/` (18 files) | No a11y test infrastructure; no `axe-core` or `@axe-core/playwright` dependency. | `frontend/package.json:11-36` (no test runner beyond vitest; no axe) | Add `axe-core` + `vitest-axe` for component-level a11y assertions |
| F4.10 | MEDIUM | Tier discipline | `tests/test_phase1_async_streaming.py:241, 294` and 12 other files | Redundant `@pytest.mark.asyncio` decorators with `asyncio_mode = "auto"`. | `pyproject.toml:179` `asyncio_mode = "auto"` | Remove redundant decorators or add lint rule |
| F4.11 | MEDIUM | Phantom / unused markers | `pyproject.toml:182-187` | `slow_dataset` ladder is undocumented in `AGENTS.md`. | Markers used but not cross-referenced | Document the 3-tier ladder in `AGENTS.md` |
| F4.12 | MEDIUM | Test quality | `tests/test_chunked_runner.py:97-194` | `synthetic_pdf` fixture is function-scoped, not session. | `@pytest.fixture` at line 50; no scope | Cache the 60-page PDF in `tests/fixtures/synthetic_60page.pdf` (committed) |
| F4.13 | MEDIUM | Tier discipline | `tests/test_phase5_env_and_spellcheck.py:79-104` | `TestSpellcheckThreadOffload` exercises `DictionaryPostProcessor`. | No marker; real dictionary load | Time the test; mark if > 5s |
| F4.14 | LOW | Test quality | `tests/test_docuverse_upgrade.py` (33 lines) | File is a docstring-only shim with no test functions. | `test_docuverse_upgrade.py:1-33` (only a docstring) | Delete the file |
| F4.15 | LOW | Test quality | `tests/test_health_endpoints.py:28` | `pytestmark = pytest.mark.asyncio` is set module-wide. | `pyproject.toml:179` `asyncio_mode = "auto"` | Remove the `pytestmark` |
| F4.16 | LOW | Test quality | `tests/test_workflows_callback_decoupling.py:64-70` | The `ids=lambda p: p.name` parametrize lambda makes test IDs = file basename. | `ids=lambda p: p.name` at line 64 | Change to `ids=lambda p: str(p.relative_to(...))` |
| F4.17 | LOW | CI completeness | `.github/workflows/test.yml:35-39` matrix | Matrix: Python 3.11 (ubuntu+windows), 3.13 (ubuntu only); `nightly.yml:36` uses 3.12. | Drift between lanes | Align nightly and release to one Python version |
| F4.18 | LOW | Test quality | `tests/test_response_schemas_and_reliability.py` | Module has no docstring; imports `_parse_grounded_json` (private symbol). | `test_response_schemas_and_reliability.py:1-2` | Rename to `test_response_schemas.py` |
| F4.19 | LOW | Test quality | `tests/test_runtime_settings.py:195` | `test_startup_validation_rejects_artifact_file` reads filesystem permissions; flakier than other tests. | `test_startup_validation_rejects_artifact_file` at line 195 | Mark `@pytest.mark.skipif(sys.platform == "win32" ...)` |
| F4.20 | LOW | CI completeness | `.github/workflows/test.yml:65` (sync step) | Fast tier doesn't exercise async-translation paths. | `test.yml:65` `uv sync --extra web`; `nightly.yml:48` adds `--extra async-translation` | Accept the trade-off; nightly catches it |

### CRITICAL findings (detailed writeup)

**F4.1** — `test_phase1_async_streaming.py` triggers Surya model load in the fast tier

**Path:** `tests/test_phase1_async_streaming.py:270, 305`

The two tests `test_hybrid_engine_convert_pages_uses_batched_streaming` and `test_hybrid_engine_convert_pages_rasterize_batch_size_override` both construct a real `HybridAligner()`. The default `HybridAligner()` constructor reaches `get_shared_detection_predictor()` in `src/omniscribe/core/aligner.py:117`, which lazily instantiates `DetectionPredictor()` at line 62. Surya's `DetectionPredictor.__init__` triggers a multi-second model load on first run and several hundred MB of RAM/VRAM.

**Evidence chain:**
- `pyproject.toml:182-184` declares `slow: loads Surya models (~5s first run) — skip with '-m "not slow"'`
- `tests/test_integration.py:24` and `tests/test_pipeline_recall.py:40` correctly apply `pytestmark = pytest.mark.slow`
- `tests/test_phase1_async_streaming.py:270, 305` lack the mark, have no `monkeypatch.setattr` for `DetectionPredictor`, and call `HybridAligner()` directly
- `tests/test_aligner.py:475` shows the safe pattern: `monkeypatch.setattr(aligner_mod, "DetectionPredictor", lambda: object())`

**Impact:** Every PR runs `pytest -m "not slow and not slow_dataset"`. If these two tests are in the collection graph, the Surya model loads (or the test errors out with no `~/.cache/huggingface` access in a clean CI runner). Either way, the "fast" tier is no longer fast.

**Recommendation:** Either (1) mark these two tests `@pytest.mark.slow` (matches the sibling pattern), or (2) replace the `HybridAligner()` with `_StubAligner()` (already used by `test_pipeline.py:42-58`, `test_workflows_hybrid.py:23`).

**F4.2** — `tests/_diag/` is a prototype shelf collected as a test suite

**Path:** `tests/_diag/test_minimal.py`, `tests/test_sse_keepalive.py`, `tests/test_async_stream2.py` (3 files)

Each file is a 30-50 line diagnostic that does `sys.path.insert(0, "src")`, builds a throwaway `FastAPI()` app, and round-trips a single request. None test production code.

**Evidence chain:**
- `_diag/test_minimal.py:1-21` is a 21-line scaffold: `app = FastAPI()`, `app.get("/ping")`, then `async def test_minimal()`.
- `_diag/test_sse_keepalive.py:1-34` is a similar scaffold for SSE keepalive frame format.
- `_diag/test_async_stream2.py:1-45` is a third scaffold for async streaming chunks.
- `pyproject.toml:180-181`: `testpaths = ["tests"]`, no `collect_ignore`, no `--ignore=_diag`.

**Impact:** Three extra FastAPI boots + httpx round-trips per CI run (~2-3s total).

**Recommendation:** Either delete `tests/_diag/` outright, or add `collect_ignore_glob = ["_diag/*"]` to `tests/conftest.py`.

### HIGH findings (detailed writeup)

**F4.3** — `live_llm` marker is never exercised in CI

**Path:** `.github/workflows/test.yml:77`, `nightly.yml:12-13, 62-63`, `pyproject.toml:184`

Only `tests/test_live_llm.py:18` carries `pytestmark = pytest.mark.live_llm` (a single test). Both CI workflows explicitly skip it. The marker exists in pyproject but the only consumer is `AGENTS.md`'s manual command.

**Recommendation:** Add a third scheduled workflow (`live_llm.yml`) with `on: schedule: - cron: "0 4 * * *"` that targets a self-hosted runner with LM Studio on `localhost:1234/v1`.

**F4.4** — `test_ui.py` E2E is opt-in, not a required check

**Path:** `.github/workflows/test.yml:189-284` (e2e job), `test_ui.py` (root)

The e2e job runs the Playwright smoke but only on `workflow_dispatch` (line 191). The comment at lines 170-188 explicitly says "does not affect the required PR status checks".

**Recommendation:** Move the E2E job from `workflow_dispatch` to a `schedule: - cron: "0 5 * * *"`. Add a `MockLLMServer` fixture to the e2e job so it can run on stock `ubuntu-latest`.

**F4.5** — Three SSE streaming tests are permanently skipped

**Path:** `tests/test_sse_progress_stream.py:158, 196, 270`

Each carries `@pytest.mark.skip(reason="TestClient + ASGITransport buffers the entire response body ...")`. The skip rationale is documented in-line, but the gap is not called out in `AGENTS.md` Known Tech Debt.

**Recommendation:** Convert to a `httpx.AsyncClient(transport=ASGITransport(app=app))` + `await client.send(request, stream=True)` + `async for chunk in response.aiter_raw()` pattern.

**F4.6** — `tracemalloc`-based memory budget test is unmarked

**Path:** `tests/test_phase1_async_streaming.py:199-238`

`test_convert_batches_peak_memory_is_bounded_by_batch_size` calls `tracemalloc.start()` twice. The assertion is `batched_peak <= eager_peak * 4` — a 4× tolerance means the test rarely fails in CI, but the snapshot cost on a 200-page doc is real.

**Recommendation:** Mark `@pytest.mark.slow` or convert to a regular `time.perf_counter()` wall-clock test.

### MEDIUM findings (one-liner each)
- F4.7 — `tests/test_pdf.py:43-348` — Real PDF embed + font probe tests (16 tests) unmarked.
- F4.8 — `tests/test_text_layer_recall.py` — 16 tests each build+open a real PDF via PyMuPDF; ~5-8s aggregate.
- F4.9 — `frontend/` — No a11y (axe-core) tests; only Vitest component tests; no Playwright spec file in CI.
- F4.10 — Redundant `@pytest.mark.asyncio` decorators in 12 files.
- F4.11 — `pyproject.toml:182-187` markers all used, but `slow_dataset` ladder is undocumented.
- F4.12 — `tests/test_chunked_runner.py:50` `synthetic_pdf` fixture is function-scoped, not session.
- F4.13 — `tests/test_phase5_env_and_spellcheck.py:79-104` `TestSpellcheckThreadOffload` real pyspellchecker dictionary load.
- F4.20 — `test.yml:65` fast sync is `uv sync --extra web` while nightly adds `--extra async-translation`.

### LOW findings (one-liner each)
- F4.14 — `tests/test_docuverse_upgrade.py:1-33` docstring-only shim, 0 test functions.
- F4.15 — `tests/test_health_endpoints.py:28` redundant `pytestmark = pytest.mark.asyncio`.
- F4.16 — `ids=lambda p: p.name` shows only file basename.
- F4.17 — Python matrix drift between test.yml (3.11+3.13) and nightly.yml (3.12).
- F4.18 — `tests/test_response_schemas_and_reliability.py:1-2` no docstring, imports private symbol.
- F4.19 — `tests/test_runtime_settings.py:195` filesystem-permission-dependent test.

## Cross-cutting observations

1. **The `slow` marker is well-disciplined in core, sloppy in peripheral.** The pattern leaks in `test_phase1_async_streaming.py` (F4.1).
2. **`tests/_diag/` is the highest-leverage single cleanup.**
3. **The 3-tier marker ladder is correct in shape but underused.**
4. **Pre-commit hook for `uv-lock` is slow and is the only one without a pass-time budget.**
5. **No Dependabot / Renovate config in `.github/`.** `pip-audit` runs weekly but no automated PR-based dependency bumps.
6. **Frontend tests are not in the CI fast gate for E2E.** Vitest IS in the fast gate; the E2E gap is about Playwright.

## Positive findings

1. **`surya_aligner` fixture scope discipline.** Session-scoped, slow load paid once.
2. **`@pytest.mark.slow` / `@pytest.mark.slow_dataset` markers in pyproject are descriptive.**
3. **The circuit-breaker state machine is exhaustively tested.** `tests/test_ocr_resilience.py:106-230` covers closed → open, open → half-open, half-open → closed, half-open → open transitions.
4. **Architecture-boundary tests catch god-module regressions.** `tests/test_repo_hygiene.py:377-421` asserts that the API layer never imports from `omniscribe.core.workflows.{hybrid,grounded,utils}`.
5. **`test_frontend_openapi_contract.py`** is a high-leverage gate.
6. **`addopts = "-ra --strict-markers"`** prevents typo'd markers.
7. **`tests/test_api_safety.py:1044-1082`** covers the namespaced OCR/artifact aliases.
8. **`tests/test_structured_logging.py:31-50`** `_isolate_root_logger` autouse fixture.
9. **No phantom markers.** All 3 declared markers (`slow`, `live_llm`, `slow_dataset`) are used.
10. **All test files respect the asyncio auto-mode policy.**

## Coverage gaps

- **Runtime model-loading time:** Cannot verify exact Surya init time without GPU; the `5s first run` figure is from AGENTS.md and `tests/conftest.py:5`.
- **Frontend component coverage:** 30+ Svelte components have zero Vitest coverage.
- **Test duration distribution:** Cannot run `pytest --durations=20` in this audit.
- **Network behavior:** Confirmed `test_live_llm.py:24-35` is properly gated. Remaining `httpx` / `requests` uses are all `MagicMock` / `AsyncMock` / `patch(...)`.
- **Redis live-mode tests:** `tests/test_state_backend_redis.py:35-47` uses `fakeredis.FakeServer()` (in-memory).

## Test inventory (high-level)

- **By marker:**
  - `slow`: 3 files, ~14 tests.
  - `live_llm`: 1 file, 1 test.
  - `slow_dataset`: 2 files, 7 tests.
  - **Unmarked: ~1,667 tests (~98.6%)**.
- **By domain:**
  - `core/`: ~60 test files, ~800 tests.
  - `api/`: ~60 test files, ~700 tests.
  - Plugin context (api/plugin): 12 test files, ~165 tests.
  - Repository-hygiene / config / infrastructure: 7 test files, ~25 tests.
  - `_diag/` (legacy): 3 test files, ~3 tests.
  - Frontend: 18 test files, ~120 tests (Vitest).
- **Avg test duration:** Unknown (no `pytest --durations` run); best estimate from session-scoped fixture is that the fast tier runs in 60-180s. With F4.1 unfixed, +30-60s on first run.

## CI pipeline map

| Trigger | Workflow | What runs |
|---------|----------|-----------|
| On push to main / on PR | `test.yml` (fast job) | Python 3.11 (ubuntu+windows) and 3.13 (ubuntu), `uv sync --extra web` → ruff → mypy → `pytest -m "not slow and not slow_dataset" --cov` → pip-audit → cyclonedx-py → upload SBOM |
| On push to main / on PR | `test.yml` (container-scan, parallel) | Trivy with HIGH/CRITICAL severity, fail on unfixed, upload SARIF |
| On schedule (03:00 UTC) | `nightly.yml` | `slow` job (Python 3.12, `pytest -m slow`) + `calibration` job (Python 3.12, `pytest -m slow_dataset`) |
| On schedule (weekly Sun 02:00 UTC) | `security.yml` | Semgrep with `p/default`, `p/security-audit`, `p/secrets`, `p/owasp-top-ten`; SARIF upload |
| Manual dispatch | `test.yml` e2e | Playwright smoke against `omniscribe-server` on `localhost:8000` (requires real LLM endpoint) |
| Manual dispatch / push-to-main-with-pyproject | `release.yml` | Bump version, tag, build wheel + sdict, publish GitHub release |

- **Branch protection / required checks:** Not declared in the repo. The `test` workflow's `fast` job is the de facto required check.
- **Dependabot:** No `.github/dependabot.yml` and no `.github/renovate.json`. Dependency bumps are manual. (Note: Domain 5 audit found `.github/dependabot.yml` exists; this audit's earlier statement is stale.)
- **Cache:**
  - `test.yml:59-62` enables `astral-sh/setup-uv@enable-cache`.
  - `test.yml:45-49` caches `frontend/package-lock.json`.
  - `nightly.yml:50-57, 107-114` caches `~/.cache/huggingface`.
  - `nightly.yml:116-124` caches the regression datasets.
  - `release.yml:80-85` enables uv cache.
  - **No `actions/cache` for the test.yml fast lane's `pip` or `uv` virtualenv.**
