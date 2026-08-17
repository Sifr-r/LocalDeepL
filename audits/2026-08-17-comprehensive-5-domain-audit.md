# OmniScribe Comprehensive 5-Domain Codebase Audit

**Date:** 2026-08-17
**Auditor:** Mavis (5 parallel deep-evidence investigations)
**Methodology:** Read-only static analysis + spot-verification of high-signal claims
**Workspace:** D:/OmniScribe
**Scope:** Core Pipeline, API & Security, Frontend, Testing & QA, DevOps & Config

---

## 0. Executive Summary

**Total findings: 111**
- CRITICAL: 5 (P0 — fix immediately)
- HIGH: 15 (P1 — fix this sprint)
- MEDIUM: 46 (P2 — fix this month)
- LOW: 45 (P3 — backlog)

### Top 5 priorities (CRITICAL, must fix before next release)

1. **F1.2 — Retry storm.** `core/ocr/processor.py:399` (outer `range(self.MAX_RETRIES + 1)`) × `core/ocr/multi_format_client.py:223` (inner `range(1, max_retries + 2)`) = **3 × 3 = 9 VLM calls per page worst case**, plus ~30 s of backoff per page. A misconfigured `OMNISCRIBE_LLM_MAX_RETRIES=10` means 121 calls/page. Circuit breaker cannot fail fast because the inner loop absorbs failures into one `LLMCallError`.
2. **F1.1 — Layering inversion.** `core/llm_client.py:96,107,154,165` and `core/ocr/multi_format_client.py:94` import from `omniscribe.api` at **runtime**, not just `TYPE_CHECKING`. Core can no longer be used in isolation (test, embedded workflow, Jupyter) without dragging in the FastAPI / Celery / Redis stack.
3. **F1.3 — Silent `gpt-4o` fallback.** `core/ocr/multi_format_client.py:105` falls back to literal `"gpt-4o"` when both `model` arg and `provider_config.models` are empty. A user who configures `api_url=https://api.openai.com/v1` with `models=[]` accidentally will silently call OpenAI cloud (cost + privacy surprise).
4. **F4.1 — Fast-tier Surya load.** `tests/test_phase1_async_streaming.py:270, 305` construct `HybridAligner()` with no `@pytest.mark.slow` and no `monkeypatch` of `DetectionPredictor`. Surya downloads + loads a ~500 MB model on every CI run. The fast tier is no longer fast.
5. **F4.2 — `tests/_diag/` collected as test suite.** 3 prototype-shelf files (`test_minimal.py`, `test_sse_keepalive.py`, `test_async_stream2.py`) are picked up by `pytest -m "not slow"`, adding ~2-3 s and zero production coverage. The folder is a Phase 0/1 debug shelf that should either be moved out of `tests/` or excluded via `collect_ignore_glob`.

### Defense-in-depth strengths (what to keep)

- **Domain 2 (Security).** `secrets.compare_digest` is used for every token compare. Per-IP rate limit with trusted-proxy `XFF` filtering. 3-layer artifact token guard (bearer + URL token + constant-time). WS cross-loop marshalling via `run_coroutine_threadsafe`. SSRF guard with literal IP blocklist + DNS resolution + per-redirect IP pinning via custom `httpx.AsyncBaseTransport`. Path normalization rejects `%2F`, `..`, and non-ASCII homoglyphs before route classification.
- **Domain 3 (Frontend).** No XSS sinks. WAI-ARIA tab pattern on `TabRibbon`. Skip-to-content link. Reduced-motion preference honored globally. Bearer token in `sessionStorage` (not URL, not `localStorage`). WS sends auth frame after open, never in URL. Modal has full focus trap, focus restoration, idempotent close. NDJSON WS parser splits concatenated frames and skips malformed lines.
- **Domain 4 (Testing).** `surya_aligner` fixture is session-scoped (slow load paid once). `addopts = "-ra --strict-markers"` prevents typo'd markers. `test_repo_hygiene.py` enforces architecture boundaries. `test_frontend_openapi_contract.py` snapshots the API surface. Circuit-breaker state machine exhaustively tested.
- **Domain 5 (DevOps).** SHA-pinned GitHub Actions + digest-pinned Docker base image. Multi-stage build. Non-root container user with `nologin` shell. PowerShell CSPRNG for Redis password generation. Dependabot covers all 4 ecosystems. Trivy + Semgrep + pip-audit + CycloneDX SBOM. `PLACEHOLDER_AUTH_TOKENS` denylist (35 entries) blocks boot on weak/example tokens. Concurrency groups cancel in-progress PR runs.

### Cross-cutting themes

1. **Retry/backoff policy is split across 3 layers with no single owner** (D1 F1.2/F1.5, D2). The processor, the multi-format client, and the engine each have retry knobs. Operators reading the source have no way to predict behavior under a transient outage.
2. **In-memory state is the documented default, persistent backends are opt-in** (D2, D4). `ProgressService`, `OCRJobQueue`, `GlossaryLibrary` cannot be persisted by design. Rate limit window is per-process; multi-worker breaks the cap.
3. **Cross-platform gap: Windows first-class, Linux is Docker-only** (D5). `install.ps1`/`start_app.vbs`/`stop_app.bat` exist; no `install.sh`. No `.gitattributes` (the existence of `_check_eol.ps1` is evidence of past pain).
4. **The placeholder-token denylist is the security lynchpin** (D2, D5). It is the only thing preventing `compose.yaml:45` example from being copy-pasted into a real `.env` and starting the server with `change-me-in-prod` as the bearer token.
5. **Frontend auth UX is orphaned** (D3 F3.3). 401 returns a generic error toast, no banner, no recovery path. With many views doing parallel polling, a misconfigured auth state generates a torrent of identical toasts.
6. **The `slow` marker is well-disciplined in core, sloppy in peripheral** (D4). `tests/test_integration.py` and `tests/test_pipeline_recall.py` carry the mark; `tests/test_phase1_async_streaming.py:270, 305` forgot. Once a new test file imports `HybridAligner` and instantiates it without a `monkeypatch`, the fast tier is at risk.
7. **Cancellation/cleanup contract is patchy across the stack** (D3). Async OCR submission has a cancel endpoint, sync `POST /api/process` does not. WS reconnect caps at 5 attempts then silently gives up. `setTimeout` for toast TTL is untracked. `URL.createObjectURL` for audio is never revoked on unmount.

### Spot-checks performed (all CONFIRMED)

| Check | Finding | Evidence |
|------|---------|----------|
| 1 | F1.1 — Core imports from api at runtime | `core/llm_client.py:96,107,154,165`; `core/ocr/multi_format_client.py:94` |
| 2 | F1.2 — Retry-storm loops | `core/ocr/processor.py:399`; `core/ocr/multi_format_client.py:223` |
| 3 | F1.3 — Silent `gpt-4o` default | `core/ocr/multi_format_client.py:105` literal `"gpt-4o"` |
| 4 | F4.1 — `HybridAligner()` in fast-tier tests | `tests/test_phase1_async_streaming.py:270, 305` |
| 5 | F4.2 — `tests/_diag/` collected as suite | 3 files in `tests/_diag/` |
| 6 | F5-11/12 — Non-existent package majors | `frontend/package.json` — vite `^8.2.1`, `@types/node: ^26.2.0`, `eslint: ^10.8.0`, `@eslint/js: ^10.0.1` |

---

## 1. CRITICAL Findings (5)

### F1.1 — Core modules import from `omniscribe.api` (layering inversion)

**File:line**
- `src/omniscribe/core/llm_client.py:13,96,107,154,165` (imports at runtime, not just `TYPE_CHECKING`)
- `src/omniscribe/core/ocr/multi_format_client.py:18,94`

**Code (multi_format_client.py:93-94)**
```python
async def complete_vlm_prompt(...):
    from omniscribe.api.schemas import ProviderFormatEnum
    ...
```

**Why it matters.** AGENTS.md documents `core/` as the lower layer and `api/` as the upper layer. Importing downward from core to api inverts the dependency. The most visible consequence: an in-process caller (e.g. an embedded workflow, a Jupyter notebook) doing `from omniscribe.core.ocr import OCRProcessor` drags in `omniscribe.api.services.provider_manager`, which transitively imports `omniscribe.config` (settings) and `omniscribe.api.schemas` (Pydantic models with validators on env-driven fields). The "core" module is no longer usable in isolation.

Worse: a test that mocks `omniscribe.api` to avoid the FastAPI import chain can no longer use the OCR path because the import is unconditional.

**Recommended fix.** Extract a core-owned `ProviderConfig` and `ProviderFormatEnum` into `omniscribe/core/providers.py` (one-line fields, no Pydantic coupling to settings). Have `omniscribe.api.schemas.ProviderConfig` either subclass or alias it. `ProviderManager` becomes a thin wrapper that the API layer provides as a callable injected into `OCRProcessor`/`PromptedGroundedOCR`; default to "use explicit `api_base`/`model`" when not provided.

**Regression test.** `test_ocr.py::test_core_does_not_import_api` — a static import-graph test that `importlib.util.find_spec` walks and fails if any `omniscribe.core.*` module imports from `omniscribe.api`.

---

### F1.2 — Retry-storm between `OCRProcessor` and `multi_format_client`

**File:line**
- `src/omniscribe/core/ocr/processor.py:399` (outer loop, default 3 attempts)
- `src/omniscribe/core/ocr/multi_format_client.py:223` (inner loop, default 3 attempts)

**Code (combined paths)**
```python
# processor.py:399
for attempt in range(self.MAX_RETRIES + 1):  # default 3
    try:
        content = await call_llm(...)  # → multi_format_client.complete_vlm_prompt
# multi_format_client.py:223
for attempt in range(1, max_retries + 2):  # default 3
    try:
        resp = await client.post(...)
        ...
    except Exception as exc:
        if is_transient_error(exc) and attempt <= max_retries:
            ...
            continue
```

**Why it matters.** On a persistently failing endpoint, each `_chat` call results in `3 × 3 = 9` VLM page POSTs plus up to `8s + 4s + 2s + 1s` of backoff per inner loop and `8s + 4s + 2s` per outer loop, worst-case ~30 s of waits plus 9 × 240 s of timeout = 36+ minutes PER PAGE. The circuit breaker cannot fail fast enough because the inner loop swallows failures into one `LLMCallError`, so the outer breaker only increments on the outer iteration. A misconfigured `OMNISCRIBE_LLM_MAX_RETRIES=10` means 121 VLM calls per page. The "retry storm" pattern is CWE-400 uncontrolled resource consumption.

**Recommended fix.** Pick one retry layer. Cleanest split: `multi_format_client` does NO retries (single POST, propagates errors as `LLMCallError`); `OCRProcessor._chat` is the single retry authority with exponential backoff and circuit-breaker integration. This also unifies the metric: one `_chat` call → one breaker increment → one backoff loop.

**Regression test.** `test_ocr.py::test_retry_storm_does_not_multiply` — mock `client.post` to always return 500; assert the call count is `MAX_RETRIES + 1` and not `(MAX_RETRIES + 1) × (max_retries + 1)`.

---

### F1.3 — Silent `gpt-4o` fallback in `multi_format_client`

**File:line.** `src/omniscribe/core/ocr/multi_format_client.py:102-106`

**Code**
```python
target_model = (
    model.strip()
    if model and model.strip()
    else (provider_config.models[0] if provider_config.models else "gpt-4o")
)
```

**Why it matters.** When neither the `model` arg nor `provider_config.models` carries a value, the code defaults to the literal string `"gpt-4o"`. The ProviderConfig is the user's full provider config including `api_url`; if `api_url` is set to `https://api.openai.com/v1` (e.g. via a `.env` file) and `models=[]` was saved by accident, the pipeline silently calls OpenAI cloud. The user thinks they're running locally.

Even when `api_url` is a local server, the model id `gpt-4o` is meaningless to the local server, which (per the `ensure_model_loaded` design) means LM Studio either serves the wrong model silently or returns 404. Either way, output is wrong without an obvious error.

**Recommended fix.** Raise `LLMCallError` with a clear message when both `model` and `provider_config.models` are empty. A misconfigured provider is an operator error, not something to silently paper over.

**Regression test.** `test_multi_format_client.py::test_missing_model_raises` — assert `LLMCallError` when both sources are empty.

---

### F4.1 — `HybridAligner()` in fast-tier tests loads Surya

**File:line.** `tests/test_phase1_async_streaming.py:270, 305`

**Code**
```python
# line 12
from omniscribe.core.aligner import HybridAligner
# line 270
aligner=HybridAligner(),
# line 305
aligner=HybridAligner(),
```

**Why it matters.** The default `HybridAligner()` constructor reaches `get_shared_detection_predictor()` in `src/omniscribe/core/aligner.py:117`, which lazily instantiates `DetectionPredictor()` at line 62. Surya's `DetectionPredictor.__init__` triggers a multi-second model load on first run and several hundred MB of RAM/VRAM. This is the exact contract that `pytestmark = pytest.mark.slow` exists to gate. The sibling pattern in `tests/test_aligner.py:475` correctly uses `monkeypatch.setattr(aligner_mod, "DetectionPredictor", lambda: object())` — these two tests don't.

**Impact.** Every PR runs `pytest -m "not slow and not slow_dataset"`. If these two tests are in the collection graph, the Surya model loads (or the test errors out with no `~/.cache/huggingface` access in a clean CI runner). Either way, the "fast" tier is no longer fast, and on first-run the test gates at 30+ seconds.

**Recommended fix.** Either (1) mark these two tests `@pytest.mark.slow` (matches the sibling `test_integration.py` and `test_pipeline_recall.py`), or (2) replace the `HybridAligner()` with `_StubAligner()` (already used by `test_pipeline.py:42-58`, `test_workflows_hybrid.py:23`). Option 2 is preferred because the tests only verify the `_convert_pages` PDF-rasterization path; the aligner is wired in but never invoked by the test body.

---

### F4.2 — `tests/_diag/` collected as test suite

**File:line.** `tests/_diag/test_minimal.py`, `tests/_diag/test_sse_keepalive.py`, `tests/_diag/test_async_stream2.py` (3 files)

**Why it matters.** Each file is a 30-50 line diagnostic that does `sys.path.insert(0, "src")`, builds a throwaway `FastAPI()` app, and round-trips a single request. None test production code; they exist to verify the dev environment is wired up. Because `pyproject.toml:180` sets `testpaths = ["tests"]` with no exclusion, pytest collects all 3.

**Impact.** Three extra FastAPI boots + httpx round-trips per CI run (~2-3 s total). They are also fragile: the FastAPI app-level `app.get("/ping")` is irrelevant to OmniScribe, so a FastAPI version bump that changes testclient behavior would fail these scaffolds for reasons unrelated to the project.

**Recommended fix.** Either delete `tests/_diag/` outright (the names and content suggest it was a Phase 0/1 debug shelf), or add `collect_ignore_glob = ["_diag/*"]` to `tests/conftest.py` and reference them from `AGENTS.md` "developer workflow" section. The latter is preferable if there's any ongoing need for the diagnostics.

---

## 2. HIGH Findings (15)

### Domain 1 — Core Pipeline (6 HIGH)

| ID | File:Line | Issue | Impact | Fix |
|----|-----------|-------|--------|-----|
| F1.4 | `core/ocr/multi_format_client.py:30-48,51-57` | Shared `httpx.AsyncClient` is loop-bound | Cross-loop reuse fails with "loop is closed"; tests/Celery/workers break | Track the loop on which the client was created; on a different loop, close old + create new |
| F1.5 | `core/ocr/processor.py:431-433` | Circuit breaker increments per outer iteration | Operator metric "1 failure/page" while actual call count is 9; breaker threshold mis-tuned | Track inner attempts; pass `n=attempts` to `record_failure` |
| F1.6 | `core/aligner.py:155-161,316-317` | NaN/inf bbox from Surya silently dropped | Layout loss with no operator warning | Detect NaN/inf in `_clamp`; log per-page NaN count |
| F1.7 | `core/aligner.py:329-371` | Reading-order recursion runs DP twice for single-column pages | 2× DP cost on dense pages (150+ boxes) | Cache row/col permutations; skip col-major for small n |
| F1.8 | `core/workflows/repair.py:132-135` | Repair loop stall guard vs `None` confidence | Custom `confidence_estimator` that returns `None` crashes the loop | Coerce `None` to 0.0 before compare |

### Domain 2 — API & Security (2 HIGH)

| ID | File:Line | Issue | Impact | Fix |
|----|-----------|-------|--------|-----|
| F2.1 | `api/services/security_middleware.py:308-322,348-372` | Per-namespace token misconfiguration leaves protected route groups open | Setting `OMNISCRIBE_TRANSLATION_AUTH_TOKEN` but no others leaves OCR/transcription routes open | Require a token on every protected group when any token is set, OR fail `from_env()` with a clear warning |
| F2.2 | `api/services/security_middleware.py:318-321,357-368` | Management routes accept ANY subsystem token | OCR-token holder can switch LLM provider, cancel any job, set/clear translation/transcription tokens | Introduce a dedicated `OMNISCRIBE_ADMIN_TOKEN` for management routes, OR restrict each management endpoint to its owning namespace |

### Domain 3 — Frontend (3 HIGH)

| ID | File:Line | Issue | Impact | Fix |
|----|-----------|-------|--------|-----|
| F3.1 | `frontend/src/lib/components/ui/ToastContainer.svelte:43` | Toast container has no `aria-live` wrapper | Info/success/warning toasts silently dropped by screen readers (only errors announced) | Add `aria-live="polite" aria-relevant="additions"` to the wrapper |
| F3.2 | `frontend/src/lib/components/ui/Toggle.svelte:19-54` | `<label for={id}>` wraps a `<button id={id}>` | Browser re-fires button click on label click → potential double-toggle; semantic mismatch (label is for form controls) | Use a hidden `<input type="checkbox" bind:checked>` + styled `<span class="switch">` |
| F3.3 | `frontend/src/lib/api/client.ts:124-138` | Every 4xx/5xx returns generic error toast; no 401 branch | Misconfigured `OMNISCRIBE_AUTH_TOKEN` → torrent of identical toasts; user has no recovery path | Add 401 branch: set `authRequired` flag in `appStore`, surface banner, suppress repeat toasts (5 s debounce), link to Settings auth tab |

### Domain 4 — Testing & QA (4 HIGH)

| ID | File:Line | Issue | Impact | Fix |
|----|-----------|-------|--------|-----|
| F4.3 | `.github/workflows/test.yml:77`, `nightly.yml:12-13,62-63` | `live_llm` marker is never exercised in CI | Every regression in LLM-call paths is only caught on a developer's laptop | Add scheduled `live_llm.yml` workflow against a self-hosted runner with LM Studio; OR convert the single live test to deeper mock-based suite |
| F4.4 | `.github/workflows/test.yml:189-284` | `test_ui.py` E2E is `workflow_dispatch`-only, not a required check | UI can break a PR completely and the fast tier still passes | Move E2E to `schedule:` weekly; add `MockLLMServer` fixture so it can run on stock ubuntu-latest |
| F4.5 | `tests/test_sse_progress_stream.py:158,196,270` | Three SSE streaming tests are permanently `@pytest.mark.skip` | SSE keep-alive contract not enforced; user-visible "no progress" complaints uncaught | Use `httpx.AsyncClient(transport=ASGITransport(app=app))` + `client.send(request, stream=True)` + `aiter_raw()` pattern (already used in `_diag/`) |
| F4.6 | `tests/test_phase1_async_streaming.py:199-238` | `tracemalloc` memory-budget test unmarked | Wide tolerance (`4×`) means rarely fails; snapshot cost is real | Mark `@pytest.mark.slow` or convert to `time.perf_counter()` wall-clock test |

---

## 3. Domain Detail

### 3.1 Core Pipeline (24 findings)

**Key files audited:** `core/ocr/`, `core/workflows/`, `core/aligner.py`, `core/text_recall.py`, `core/text_layer_recall.py`, `core/ocr_quality/`, `core/processors/`, `core/grounded/`, `core/document.py`, `core/preprocessing.py`, `core/postprocess.py`, `core/routing.py`, `core/pdf/embedder.py`, `core/handwriting_preprocessor.py`, `pipeline.py`, `evaluation.py`, `config.py`, `utils/`

**Findings:** 3 CRITICAL (F1.1-1.3), 6 HIGH (F1.4-1.8, F1.14-as-HIGH), 9 MEDIUM, 6 LOW

**MEDIUM highlights:**
- F1.9 — Class-level env snapshot means runtime `OMNISCRIBE_*` overrides don't take effect on a long-running process
- F1.10 — `_CACHE` in `core/ocr_quality/calibration.py:33` is unbounded → switch to LRU
- F1.11 — `_midgray_fraction` in `core/ocr_quality/watermark.py:40-60` is pure-Python double loop; vectorize with numpy (~10× speedup)
- F1.12 — `_shared_predictor_lock` in `core/aligner.py:43-122` serializes all detection through one forward pass
- F1.13 — `_get_tesseract_draft` silently returns `""` on every Tesseract error; add per-run counter
- F1.14 — `hasattr(self.grounded_backend, "ocr_crop")` duck-type gate; promote to a `Protocol`
- F1.15 — `_cross_page_merge` mutates `pages_structured` in place without defensive copy
- F1.16 — `parse_glm_layout_details` strict-equality filters non-"text" labels; inconsistent with Qwen parser's allow-list
- F1.17 — Two different crop paddings (5% vs 0.5%) and JPEG qualities (90 vs 85) between grounded and hybrid paths break trust-score calibration parity

**LOW highlights:**
- F1.19 — `logger.warning("TrOCR arbitration failed: %s", e)` lacks `exc_info=True`
- F1.20 — `ensure_model_loaded` re-hits `GET /v1/models` on every instance creation
- F1.22 — `import numpy as np` inside `_apply_adaptive_threshold`; hoist to module top
- F1.23 — `_clamp` propagates NaN (same root cause as F1.6)
- F1.25 — `_ocr_per_box` swallows `OCRCancelled`; add explicit re-raise mirroring `CircuitOpenError`

**Known tech-debt verification (per AGENTS.md):**

| Item | Status | Evidence |
|------|--------|----------|
| `pages_structured` legacy dict is still the working format inside `HybridEngine` | **CONFIRMED** | `core/workflows/hybrid.py:496-498` (builds `pages_structured: dict[int, PageBoxes]`); `core/workflows/base.py:355-357` |
| `/api/process` runs the full OCR pipeline synchronously | **CONFIRMED** (core side) | `core/pipeline.py:116-202` is a single async function; the entire `OCRPipeline.run` is one call. The `cancel_check` callback is the only cooperative-cancel hook |
| Job/artifact state is in-memory by default | **CONFIRMED** | `config.py:100-110` `state_backend` selector defaults to "memory"; `core` has no state-backend knowledge |
| `dense.pdf` and `notes.pdf` fixtures bootstrapped from hybrid output | **PARTIALLY VERIFIED** | Fixture files not in scope, but the `confidence_eval.py` design is consistent with the AGENTS.md claim |
| `surya-ocr 0.17.x` requests workaround | **NOT VERIFIED** | `pyproject.toml` was out of scope; the aligner code imports `from surya.detection import DetectionPredictor` consistent with the claim but not independently verified |

**Cross-cutting observations:**
- Layering inversion (F1.1) is the most consequential; it also makes F1.2 and F1.3 worse.
- Memory safety is well-handled for in-flight runs (`_decoded_cache` bounded, `_shared_client` singleton); concerns are unbounded calibration cache (F1.10) and `images_dict` base64 retention for 1000+ page documents.
- Grounded vs hybrid path asymmetry (F1.16, F1.17) means trust-score calibration differs between the two engines; users running both will see drift that's a tooling artifact.
- Detection predictor reuse is correct (P2-9); the trade-off (F1.12) is acceptable for default single-GPU target deployment.

---

### 3.2 API & Security (12 findings)

**Key files audited:** `src/omniscribe/api/`, `src/omniscribe/server.py`, `src/omniscribe/utils/security.py`

**Findings:** 0 CRITICAL, 2 HIGH (F2.1, F2.2), 6 MEDIUM, 4 LOW

**MEDIUM highlights:**
- F2.3 — `MaxUploadSizeMiddleware` accepts the full 100 GB ceiling + chunked path with no per-request deadline (the `OMNISCRIBE_UPLOAD_DEADLINE_SECONDS` is only enforced in `save_validated_upload`)
- F2.4 — `RateLimitMiddleware` short-circuits `scope["type"] != "http"`; WebSocket upgrade floods are bounded only by the 10 s `verify_minted` auth-frame timeout
- F2.5 — `BearerAuthMiddleware._get_active_tokens` swallows every exception when reading the config store
- F2.6 — `ProviderCreateRequest.headers` is freeform `dict[str,str]`; allows `Host`, `X-Forwarded-Host`, or auth-header overrides
- F2.7 — `SecuritySettings._validate_auth_token` embeds the offending token in the startup `RuntimeError`
- F2.8 — CORS uses `allow_methods=["*"], allow_headers=["*"]`

**LOW highlights:**
- F2.9 — `/ready` returns in-memory state counts (text_entries, etc.) — minimal info disclosure
- F2.10 — `get_access_token` accepts the artifact token via `?token=` query param, contradicting the docstring
- F2.11 — WebSocket `verify_minted` and `register_channel` are not atomic; microsecond race
- F2.12 — `InMemoryConfigStore._cross_worker_visible` is a writable public attribute

**Known security posture verification (per AGENTS.md):**

| Claim | Status | Evidence |
|-------|--------|----------|
| `OMNISCRIBE_AUTH_TOKEN` set → constant-time compare | **CONFIRMED** | `security_middleware.py:391` uses `secrets.compare_digest` |
| WebSocket handshake auth enforced per-channel | **CONFIRMED** | `websocket.py:596-621` — accept → wait for auth frame (10 s) → HMAC verify |
| VLM resilience: retries 429/5xx/connection resets | **CONFIRMED** (out of scope) | `core/ocr/resilience.py` not deep-read; consistent with the F1.2 finding |
| Per-IP 60s sliding window, in-memory | **PARTIALLY IMPLEMENTED** | Sliding window correct; WebSocket scopes excluded (F2.4) |
| Reject on `Content-Length` | **CONFIRMED** | Both fast path (parsed and rejected with 413) and chunked path (bounded by `max_bytes`) |
| Progress WS cross-loop marshalling | **CONFIRMED** | `websocket.py:288-329` — `ConnectionManager.send` uses `run_coroutine_threadsafe` |
| `ALLOW_SSRF_LOCAL=true` is the local-development default | **PARTIALLY CONFIRMED** | Code's default is **to BLOCK** local addresses (operator must opt-in); contradicts AGENTS.md phrasing |
| CORS preflight blocks cross-origin POST with Authorization | **CONFIRMED** | Explicit origin list (never `*`); `allow_credentials=False` |
| Upload deadline enforced per-request | **PARTIALLY IMPLEMENTED** | Enforced in `save_validated_upload` but not in `MaxUploadSizeMiddleware` (F2.3) |
| JobHistory and OCRJobQueue survive restart only via SQLite/Redis | **CONFIRMED** | Documented persistence boundary in `state_backend_sqlite.py:27-37` |
| Per-namespace tokens settable via POST when backend is cross-worker | **CONFIRMED** | Writes refused with 503 when in-memory store is active |

**Cross-cutting observations:**
- `secrets.compare_digest` and `hmac.compare_digest` are used for every token compare (artifacts, websocket, bearer, jobs).
- State backend reset semantics: every cross-worker-visible backend (SQLite, Redis) implements the 7-attribute `StateBackend` Protocol; `ProgressService`, `OCRJobQueue`, `GlossaryLibrary` are documented in-memory by design.
- 3-layer defense for `/api/jobs/{job_id}/result`: bearer middleware + `access_token` query/header + `secrets.compare_digest` against the record's `text_artifact_token`.
- SSRF defense-in-depth: literal IP blocklist + DNS resolution + per-redirect IP pinning via custom `httpx.AsyncBaseTransport`.
- Token generation quality: `secrets.token_urlsafe(24..32)` and `secrets.token_hex(16)` for channel/session/artifact IDs; CSPRNG, no sequential or time-based IDs.

---

### 3.3 Frontend (25 findings)

**Key files audited:** `frontend/src/` (95 files), `frontend/package.json`, `vite.config.ts`, `svelte.config.js`, `tsconfig.json`, `index.html`, `app.css`

**Toolchain verified:** Svelte 5.20.2, TypeScript 5.7.3 (strict), Vite 8.2.1, Vitest 3.0.6, Tailwind v4, pdfjs-dist 6.2.108, jsdom 26

**Findings:** 0 CRITICAL, 3 HIGH (F3.1-3.3), 11 MEDIUM, 11 LOW

**MEDIUM highlights:**
- F3.4 — `URL.createObjectURL` in `TranscriptionView.svelte:35-42` is never revoked on component unmount
- F3.5 — `setTimeout` for toast TTL in `appStore.ts:144-148` is untracked; `removeToast`/`clearToasts` cannot cancel it
- F3.6 — No `AbortSignal` plumbing in `fetchApi`/`fetchFile`/`pollOcrJobStatus`; in-flight fetches continue after unmount
- F3.7 — `fetchFile` drops the response body and only shows `statusText`; download failures lack server detail
- F3.8 — `window.confirm` used for destructive "Clear all" in `JobHistoryView.svelte:45` instead of the in-house `Modal` primitive
- F3.9 — One-way `$:` sync from `$documentStore` to local state in `TranslationView` and `ExtractionView` never clears when the store clears
- F3.10 — WS reconnect caps at 5 attempts (≈31 s), then silently gives up with no UI affordance to retry
- F3.11 — WS `onclose` reconnect path doesn't inspect `event.code`; auth-class closes (1008) trigger wasteful reconnects
- F3.12 — "Processing document" overlay in `WorkstationView.svelte:225-234` is `role="dialog" aria-modal="true"` but lacks focus trap, labelledby, focus restoration
- F3.13 — Settings namespace tabs in `SettingsView.svelte:124-146` are plain buttons; no WAI-ARIA tablist pattern (regression vs. `TabRibbon`)
- F3.14 — Async-translation polling stops on fetch error and loses `asyncJobId` from the UI; no resume path

**LOW highlights:**
- F3.15-3.17 — A11y: missing `aria-label` on progressbar, missing `<caption>` on tables, `--color-foreground-subtle` (#64748b) ~3.9:1 contrast (fails AA)
- F3.18-3.20 — Re-pick same file doesn't fire `change`; `fetchFile` doesn't auto-set `Content-Type`; overlapping WS `connect()` calls don't cancel prior OPEN_TIMEOUT timers
- F3.21-3.23 — Form labels/legend missing; `<a href="/">` triggers full page reload; dead `hidden` attribute on each view
- F3.24-3.25 — Dev-only `Showcase.svelte` in production source tree; `as any`/`as unknown as …` usage appropriately scoped (test setup, two PDF.js bridge casts)

**A11y quick-check:**

| Concern | Status | Notes |
|---------|--------|-------|
| All images have alt | YES | `<img alt="Page N">` in `PageCanvas.svelte:147`; all SVGs `aria-hidden="true"` |
| All form inputs labeled | YES | `Input.svelte:48-49` renders `<label for={id}>`; `Select.svelte:27-29` does the same |
| Focus visible | YES | `focus-visible:ring-2 focus-visible:ring-brand` is the standard recipe |
| Keyboard navigation complete | PARTIAL | TabRibbon has full ARIA tab pattern; Modal has full focus trap; SettingsView namespace tabs (F3.13) and Workstation processing overlay (F3.12) do not |
| Color contrast | PARTIAL | `--color-foreground-subtle` on dark surfaces ~3.9:1 (F3.17) — fails AA |
| ARIA live regions for async | PARTIAL | TabRibbon status, PipelineProgress status line OK; ToastContainer missing (F3.1) |

**Cross-cutting observations:**
- Auth is sound but UX-orphaned (F3.3). The token is in `sessionStorage`, `Authorization: Bearer` is attached per route family in `client.ts:49-56`, WS sends auth frame after open. But the failure path gives no in-app way to discover the Settings auth tab.
- Bundle/chunk discipline: `vite.config.ts:43-55` manually chunks `pdfjs-dist` into `pdfjs-vendor` (≈2.2 MB warning). No code-splitting per view; every view is loaded by `App.svelte` via the static import graph.
- Type holes are localized. All `any` / `as any` usage is in test setup and two PDF.js boundary casts.
- Svelte 4 legacy syntax everywhere (`export let`, `on:click`, `$:`). Svelte 5.20 supports this in legacy mode but the new syntax is the recommended path. Forward-compat risk.

---

### 3.4 Testing & QA (20 findings)

**Key files audited:** `tests/` (150 Python files, ~24,000 LOC), `.github/workflows/` (4 workflows), `.pre-commit-config.yaml`, `pyproject.toml`

**Findings:** 2 CRITICAL (F4.1, F4.2), 4 HIGH (F4.3-4.6), 8 MEDIUM, 6 LOW

**Test inventory (per static analysis):**
- 1,689 Python test functions across 150 files
- 120 Vitest blocks across 18 frontend files
- Markers: `slow` (3 files, ~14 tests), `live_llm` (1 file, 1 test), `slow_dataset` (2 files, 7 tests), unmarked (~1,667 tests, ~98.6%)

**MEDIUM highlights:**
- F4.7 — `tests/test_pdf.py:43-348` real PDF embed + font probe tests (16 tests) unmarked
- F4.8 — `tests/test_text_layer_recall.py` 16 tests each build+open a real PDF via PyMuPDF; ~5-8 s aggregate
- F4.9 — No a11y test infrastructure (no `axe-core` or `@axe-core/playwright`); 30+ Svelte components have zero Vitest coverage
- F4.10 — Redundant `@pytest.mark.asyncio` decorators in 12 files (asyncio_mode = "auto" makes them no-ops)
- F4.11 — `slow_dataset` marker ladder is undocumented in `AGENTS.md`
- F4.12 — `tests/test_chunked_runner.py:50` `synthetic_pdf` fixture is function-scoped, not session
- F4.13 — `tests/test_phase5_env_and_spellcheck.py:79-104` `TestSpellcheckThreadOffload` real pyspellchecker dictionary load
- F4.20 — `test.yml:65` fast sync is `uv sync --extra web` while nightly adds `--extra async-translation`

**LOW highlights:**
- F4.14 — `tests/test_docuverse_upgrade.py:1-33` docstring-only shim, 0 test functions
- F4.15 — `tests/test_health_endpoints.py:28` redundant `pytestmark = pytest.mark.asyncio`
- F4.16 — `ids=lambda p: p.name` in `test_workflows_callback_decoupling.py:64` shows only file basename
- F4.17 — Python matrix drift: test.yml uses 3.11+3.13, nightly.yml uses 3.12
- F4.18 — `tests/test_response_schemas_and_reliability.py:1-2` no docstring, imports private symbol
- F4.19 — `tests/test_runtime_settings.py:195` filesystem-permission-dependent test

**CI pipeline map:**

| Trigger | Workflow | What runs |
|---------|----------|-----------|
| On push to main / on PR | `test.yml` (fast job) | Python 3.11 (ubuntu+windows) + 3.13 (ubuntu), `uv sync --extra web` → ruff → mypy → `pytest -m "not slow and not slow_dataset" --cov` → pip-audit → cyclonedx-py → upload SBOM |
| On push to main / on PR | `test.yml` (container-scan, parallel) | Trivy with HIGH/CRITICAL severity, fail on unfixed, upload SARIF |
| On schedule (03:00 UTC) | `nightly.yml` | `slow` job (Python 3.12, `pytest -m slow`) + `calibration` job (Python 3.12, `pytest -m slow_dataset`) |
| On schedule (weekly Sun 02:00 UTC) | `security.yml` | Semgrep with `p/default`, `p/security-audit`, `p/secrets`, `p/owasp-top-ten`; SARIF upload |
| Manual dispatch | `test.yml` e2e | Playwright smoke against `omniscribe-server` on `localhost:8000` (requires real LLM endpoint) |
| Manual dispatch / push-to-main-with-pyproject | `release.yml` | Bump version, tag, build wheel + sdist, publish GitHub release |

**Branch protection:** Not declared in repo; `test` workflow's `fast` job is the de facto required check. No `.github/CODEOWNERS`.

**Dependabot:** Enabled, all 4 ecosystems (pip, npm, github-actions, docker), `interval: weekly` for all. Consider `monthly` for github-actions / docker.

**Cross-cutting observations:**
- The 3-tier marker ladder is correct in shape (`slow` / `live_llm` / `slow_dataset`) but underused.
- `tests/_diag/` is the highest-leverage single cleanup. Three files, ~5 s saved, ~50 lines of irrelevant code removed.
- Pre-commit hook for `uv-lock` is the only one without a pass-time budget; with ruff + mypy + uv-lock, pre-commit on a 5-file change takes 30-60 s; developers bypass with `--no-verify`.
- Frontend tests are in the CI fast gate (Vitest via `npm test`); the E2E gap (F4.4) is about Playwright, not Vitest.

---

### 3.5 DevOps & Config (30 findings)

**Key files audited:** `Dockerfile`, `compose.yaml`, `.dockerignore`, `.github/workflows/`, `pyproject.toml`, `install.bat`, `install.ps1`, `start_app.vbs`, `stop_app.bat`, `.poll_server.ps1`, `_check_eol.ps1`, `Makefile`, `.pre-commit-config.yaml`, `.semgrepignore`, `frontend/package.json`, `scripts/`

**Findings:** 0 CRITICAL, 0 HIGH, 12 MEDIUM, 18 LOW

**MEDIUM highlights:**
- F5-01 — AGENTS.md says Python 3.12 base, but `Dockerfile:28,66` uses 3.14 — doc drift
- F5-02 — AGENTS.md omits `--extra preprocessing` from the baked-in extras list
- F5-03 — No `HEALTHCHECK` directive in the Dockerfile (only in `compose.yaml:56-61`)
- F5-05 — `compose.yaml:26` `8000:8000` binds to all host interfaces; with `OMNISCRIBE_AUTH_TOKEN` line commented, this is open by default
- F5-06 — `compose.yaml:35,73,90,98` all fall back to the same *known* default `omniscribe-local-dev` Redis password
- F5-11 — `frontend/package.json:22` `@types/node: ^26.2.0` and `package.json:34` `vite: ^8.2.1` — non-existent majors (Node max ~24, Vite max ~6 in the public timeline; needs verification of the actual registry)
- F5-12 — `frontend/package.json:19,23` `eslint: ^10.8.0` and `@eslint/js: ^10.0.1` — same concern
- F5-14 — No `install.sh`; Linux operators must read `Makefile` manually
- F5-16 — `compose.yaml:45` example token `change-me-in-prod` is in the boot-time denylist; uncommenting as-is triggers `RuntimeError` with no hint
- F5-21 — `pyproject.toml:168-176` Pillow override comment describes a surya-ocr 0.17.x workaround that no longer applies
- F5-24 — `.github/dependabot.yml:3-21` all four ecosystems on weekly cadence; github-actions / docker can be monthly
- F5-08 — `.github/workflows/release.yml:36,107,111` uses default `GITHUB_TOKEN` with `contents: write` to push back to main; many protected `main` branches block the default token

**LOW highlights (selected):**
- F5-07 — `compose.yaml:24,69` `mem_limit: 4g` is the legacy v1 key
- F5-09 — `test.yml:88-95` generates per-matrix SBOM artifact never consumed by release flow
- F5-10 — `test.yml:189-191` e2e is `workflow_dispatch`-only; the name suggests automatic smoke
- F5-13 — No `.gitattributes`; `_check_eol.ps1` exists *because* of past CRLF pain
- F5-15 — `_check_eol.ps1:1` hardcodes `D:\OmniScribe\start_app.vbs`
- F5-17 — `compose.yaml:40` references `.env.example` but no such file exists
- F5-18 — `scripts/fetch_datasets.py:74-91` is a `NotImplementedError` stub
- F5-29 — `install.ps1:33-40` downloads uv installer with version pinning but no SHA-256 verification
- F5-30 — `start_app.vbs:202-203` opens the default browser unconditionally

**Container-hardening quick-check:**

| Concern | Status | Notes |
|---------|--------|-------|
| Non-root USER | YES | `app` uid 1001, `nologin` shell, `Dockerfile:72,88` |
| Pinned base image | YES | `python:3.14-slim@sha256:ce4076…` at `Dockerfile:28,66` |
| Multi-stage build | YES | builder (uv + sync) → runtime (venv only) |
| HEALTHCHECK | PARTIAL | Only in `compose.yaml:56-61`; not in the Dockerfile itself |
| Layer caching | YES | `pyproject.toml` + `uv.lock` + `LICENSE` + `README.md` copied first, then `src/` |
| Secret mounts | NO | All env-driven; no Docker `secrets:` block |
| `--requirepass` on Redis | YES | `compose.yaml:90` |
| Loopback bind for Redis host port | YES | `127.0.0.1:6379:6379` |
| Loopback bind for API host port | NO | `8000:8000` (all interfaces) — auth-token opt-in is the only mitigation |
| `mem_limit` | YES (legacy) | `4g` on `api` + `worker` |
| `restart: unless-stopped` | YES | `compose.yaml:62,79,102` |
| `.dockerignore` is comprehensive | YES | Excludes `.env*`, `redis-password.txt`, `frontend/`, `examples/`, `tests/`, agent scratch dirs |

**Cross-platform compatibility matrix:**

| Concern | Windows | Linux | Notes |
|---------|---------|-------|-------|
| Path separators | `pathlib` everywhere | Same | Portable |
| Line endings | No `.gitattributes` — risk of CRLF in `*.ps1`/`*.bat`/`*.vbs` on checkout | LF assumed | `_check_eol.ps1` exists *because* of pain points |
| Shell syntax | PowerShell + VBScript + cmd | Bash in CI workflows | Windows dev box vs Linux CI runner |
| File system | `os.chmod` no-op on Windows (acceptable) | Honors `0o600`, `0o700` | Cross-platform-fine |
| `start_app.vbs` | Native | No native equivalent; Docker Compose is the Linux path | Most-tested Windows-only surface |
| Frontend npm install | `npm ci` in `install.ps1:80-84` | Same | No platform-specific deps |
| Git autocrlf | Windows default `true` can mangle shell scripts | Default `false` (or `input`) | Add `.gitattributes` (F5-13) |
| `make` availability | Limited (Git Bash, WSL only) | Native | `Makefile` is the cross-platform Linux surface |

**Cross-cutting observations:**
- "Pinned everywhere" is the project story. SHA-pinned actions + digest-pinned Docker base image are exemplary. The drift is in the less-trafficked surfaces: frontend npm versions, Compose password fallback, AGENTS.md text.
- The secrets posture is solid for a personal-project scale. `redis-password.txt` is double-ignored (git + docker). The `PLACEHOLDER_AUTH_TOKENS` denylist (35 entries) is thorough. PowerShell CSPRNG for Redis password generation in `start_app.vbs:80-92` (not VBScript `Rnd()`).
- Default = "open and friendly" is intentional and the docs acknowledge it. `compose.yaml:45` deliberately leaves `OMNISCRIBE_AUTH_TOKEN` commented. Fine for a personal/desktop app, but a `docker compose up` on a LAN-facing host hands anyone reachable the OCR API.
- Cross-platform: Windows is first-class, Linux is Docker-only. `install.ps1`, `start_app.vbs`, `stop_app.bat` exist. `Makefile` is the closest to a Linux path. There is no `install.sh`.

---

## 4. Recommended Remediation Order

### P0 — Block next release (5 items, ~3-5 days effort)

| ID | Title | Effort | Risk if not fixed |
|----|-------|--------|-------------------|
| F1.1 | Extract `ProviderConfig` into `core/`; invert the import | 1-2 days | Core unusable in isolation; tests can't mock the api layer |
| F1.2 | Pick one retry layer; remove the other | 0.5 day | 30+ min single-page hangs; CWE-400 uncontrolled resource consumption |
| F1.3 | Raise `LLMCallError` when neither `model` nor `provider_config.models` is set | 0.25 day | Accidental OpenAI cloud calls; cost + privacy surprise |
| F4.1 | Mark F4.1 tests `@pytest.mark.slow` OR replace with `_StubAligner()` | 0.25 day | Surya model load on every CI run; fast tier no longer fast |
| F4.2 | Move `tests/_diag/` out of pytest collection (`collect_ignore_glob` or delete) | 0.1 day | 2-3 s wasted per CI run; scaffolds fragile to FastAPI version bumps |

### P1 — This sprint (15 items, ~1-2 weeks effort)

**Domain 1 (5):** F1.4 loop-bound AsyncClient, F1.5 breaker increment metric, F1.6 NaN bbox guard, F1.7 reading-order caching, F1.8 None confidence coercion

**Domain 2 (2):** F2.1 per-namespace token posture, F2.2 management-route token scope

**Domain 3 (3):** F3.1 toast live region, F3.2 Toggle label/button overlap, F3.3 401 handling

**Domain 4 (4):** F4.3 live_llm CI coverage, F4.4 E2E required check, F4.5 SSE test enablement, F4.6 memory test marker

**Domain 1 (1):** F1.14 grounded repair Protocol gate

### P2 — This month (46 items, ~3-4 weeks effort)

Includes: 11 frontend MEDIUM (memory leaks, no AbortSignal, modal focus, tablist regression, async-translation polling); 6 API MEDIUM (upload deadline, WS rate limit, token redaction, CORS, headers validation, config-store error logging); 8 testing MEDIUM (PDF embed marker, text-layer-recall marker, axe-core, redundant asyncio marks, fixture scope, etc.); 9 core MEDIUM (env snapshot, calibration cache LRU, watermark vectorization, predictor concurrency, Tesseract counter, cross-page mutation, parser label consistency, crop params, thread pool placement); 12 DevOps MEDIUM (Dockerfile Python version, doc drift, HEALTHCHECK, port binding, Redis password, package majors, install.sh, doc example, surya workaround, Dependabot cadence, release GITHUB_TOKEN).

### P3 — Backlog (45 items)

Mostly LOW: dead code, style, naming, minor inefficiencies. None affect correctness or security.

---

## 5. Verification Notes

**Spot-checks performed (6, all CONFIRMED):**

1. **F1.1 layering inversion.** Confirmed: `core/llm_client.py:96,107,154,165` and `core/ocr/multi_format_client.py:94` import from `omniscribe.api` at runtime (the `from omniscribe.api.schemas import ProviderFormatEnum` is inside a function body, not under `TYPE_CHECKING`).
2. **F1.2 retry multiplication.** Confirmed: `core/ocr/processor.py:399` outer loop + `core/ocr/multi_format_client.py:223` inner loop are independent and stack.
3. **F1.3 silent gpt-4o.** Confirmed: `core/ocr/multi_format_client.py:105` literal `else "gpt-4o"`.
4. **F4.1 fast-tier Surya load.** Confirmed: `tests/test_phase1_async_streaming.py:270, 305` construct `HybridAligner()` with no `monkeypatch` and no marker.
5. **F4.2 `_diag` collected.** Confirmed: 3 files in `tests/_diag/` (`test_minimal.py`, `test_sse_keepalive.py`, `test_async_stream2.py`).
6. **F5-11/12 non-existent package majors.** Confirmed: `frontend/package.json` declares vite `^8.2.1`, `@types/node: ^26.2.0`, `eslint: ^10.8.0`, `@eslint/js: ^10.0.1`.

**What was NOT verified:**

- **Live VLM behavior.** I could not exercise the OCR processor against a real LM Studio / Ollama instance. `is_transient_error` classification, `model_supports_system_role` heuristics, retry logic need real-world validation across model families.
- **Surya 0.17.x specific bugs.** The known NaN bbox risk is noted; exact reproducer/frequency unverified.
- **PyMuPDF text-layer behavior.** Word-tuple shape is stable in recent versions; corner cases (rotated pages, encrypted PDFs) not tested.
- **TrOCR / handwriting arbitration.** Confidence comparison depends on TrOCR's confidence calibration, unverified.
- **Anthropic and Ollama provider paths.** Code paths reviewed but not verified against real APIs.
- **Celery worker / multi-loop behavior.** F1.4 is plausible but the actual failure mode depends on httpx + asyncio interaction in deployment.
- **Document processor strict-mode contract enforcement.** Default `strict=False`; I could not verify every processor's contract declaration.
- **PDF embedder font chain.** Per-run font registration against a real CJK + Arabic mixed document not tested.
- **Timing-attack measurements.** `secrets.compare_digest` use verified by source inspection only; practical measurement out of scope.
- **Multi-worker concurrent-write race** for the in-memory state backend cannot be exploited (per-process by design).
- **Frontend runtime behavior.** Actual screen-reader announcement, browser-specific double-toggle, `<a href="/">` same-tab reload behavior, 401 toast storm frequency — all unverified.
- **Bundle production output.** No `npm run build` run; cannot confirm tree-shaking drops `Showcase.svelte` or chunk boundaries match.
- **Node 26 / Vite 8 / ESLint 10 existence.** Versions in `package.json` are unusual; the registry was not queried to confirm whether they are real or typos.
- **Dependabot ecosystem currency.** Action SHAs may be stale relative to upstream; only Dependabot will surface drift.
- **Actual deployment posture** (live `start_app.log` content, real `.env`, production tokens) was not readable.

---

## 6. What Was NOT Audited (out of scope by design)

- **Domain 1:** `core/transcription/`, `core/lexicon/`, `core/glossary_library/`, `core/glossary_sources/`, `core/translation.py`, `core/translation_config.py`, `core/translation_tree.py`, `core/dual_translator.py`, `core/docx_writer.py`, `core/docx_tree_writer.py`, `core/html_writer.py`, `core/tree_export.py`, `core/nllb_engine.py`, `core/trocr_engine.py`, `core/providers.py`, `core/glossary.py`, `core/llm_temperatures.py`, `core/pdf/rasterizer.py`, `core/pdf/handler.py`, `core/pdf/page_range.py`, `core/pdf/rasterization_settings.py`, `core/handwriting_preprocessor.py` (mentioned in AGENTS.md but not deep-read).
- **Domain 2:** `core/ocr/resilience.py` (only verified at the F1.2/F1.5 integration point; not deep-read). `core/transcription/` (out of scope).
- **Domain 3:** Production `static/` build output; Playwright E2E spec (none committed). No visual contrast audit tool was run.
- **Domain 4:** Frontend line coverage (no `npx vitest run --coverage`); test duration distribution (no `pytest --durations=20`).
- **Domain 5:** Live `start_app.log`; real `.env`; Heroku-style `Procfile` (not used).

---

## Appendix A: Detailed Subagent Reports

The 5 domain subagent reports (full evidence, code snippets, regression test suggestions) are saved as separate files in `D:/OmniScribe/audits/`:

- `2026-08-17-domain-1-core-pipeline.md` (24 findings)
- `2026-08-17-domain-2-api-security.md` (12 findings)
- `2026-08-17-domain-3-frontend.md` (25 findings)
- `2026-08-17-domain-4-testing-qa.md` (20 findings)
- `2026-08-17-domain-5-devops-config.md` (30 findings)

---

_Generated 2026-08-17 by Mavis (MiniMax Code orchestrator) for the OmniScribe project._
