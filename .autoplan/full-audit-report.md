# OmniScribe Comprehensive Codebase Audit

**Date:** 2026-08-16 · **Scope:** security, frontend, QA, core pipeline, DevOps/CI · **Method:** Semgrep SAST + manual code review + parallel sub-agent audits + live browser testing + full test suite + coverage run

---

## Executive Summary

No exploitable critical vulnerabilities were found. The codebase shows strong security engineering (centralized SSRF guard, constant-time auth, opaque artifact IDs with path containment, XXE pre-screening). The test suite is healthy: **1429 passed, 0 failed, 82% line coverage**.

The most consequential issues are:

1. **A silent-failure mode in the OCR pipeline** — a tripped circuit breaker on the dense path is swallowed by a generic `except Exception`, producing jobs that "succeed" with empty text.
2. **The searchable PDF layer cannot encode non-Latin scripts** (`helv` font only) — undermining a core product promise for Arabic-first users.
3. **Docker Compose as documented starts nothing** (`profiles: ["default"]` bug).
4. **CI security workflow is partially broken** (unpinned `semgrep:latest` container, missing `security-events: write`) and **npm gets zero Dependabot coverage**.
5. **A live frontend/backend contract break** — `/api/glossary/merged` 404s on every page load.

---

## Live Testing Summary (browser-use against running instance on :8000)

| Check | Result |
|---|---|
| App load + SPA render | ✅ Clean render, all 7 tabs reachable |
| API endpoints (config, models, jobs, glossary, health) | ✅ All 200 except one (below) |
| `GET /api/glossary/merged` | ❌ **404** — frontend calls a route that doesn't exist → console error on every load |
| File upload (examples/dense.pdf) | ✅ Accepted, viewer chip populated |
| Sync `/api/process` start | ✅ Progress frames flow (CONVERT 5% → DETECT → OCR with real box counts) |
| OCR throughput | ⚠️ 3-page dense PDF: **0/3 pages after ~7 min** on 7B model with quality target 0.98 |
| Cancel run | ⚠️ "Cancelling…" stuck >25s — cancel honored only between blocks; in-flight VLM call blocks it |
| Metadata panel during run | ⚠️ "Overall confidence 100%" placeholder never updates; Total pages / Active page / Blocks streamed stayed "—" throughout |
| Accessibility | ⚠️ 3 comboboxes (language, model, model-select in Settings) have **no accessible name** |
| Branding | ⚠️ Page title "DocuVerse — …" vs "OmniScribe" header |
| Upload copy | ⚠️ UI says "up to 50 MB"; configured cap is 10,240 MB |

Screenshots: `.autoplan/audit-ui-workstation.png`, `.autoplan/audit-ui-post-cancel.png`

---

## 1. Security Findings

### Verified strong points
- **SSRF**: [is_ssrf_target](file:///d:/OmniScribe/src/omniscribe/utils/security.py) fails closed (bad scheme/URL/DNS → blocked), blocks cloud metadata host, applied at every URL-taking route incl. glossary URL import (`_validate_ssrf` before `fetch_url_bytes`). `file://` can never reach the urllib fallback.
- **Auth**: `BearerAuthMiddleware` uses `secrets.compare_digest`, canonicalizes percent-encoded paths, rejects non-ASCII homoglyph paths before token compare, health exemption is an exact set.
- **Artifacts**: opaque 32-hex IDs + per-artifact tokens, `Path.resolve().relative_to()` containment check, constant-time token compare in the SQLite backend.
- **SQLite backend**: table names are code constants; all user values parameterized. No injection.
- **XXE**: user-supplied glossary XML funnels through `safe_xml_root` (rejects DOCTYPE/ENTITY/SYSTEM).
- Semgrep `p/security-audit`: 7 findings, all assessed mitigated or dev-only (see `.autoplan/semgrep-full-scan.json`).

### Findings

| Sev | Finding | Location |
|---|---|---|
| Medium | **WebSocket connect never verifies the issued token binding.** `ConnectionManager.connect()` only validates token *format*, then overwrites `_tokens[channel_id]` with whatever the connector sent. Anyone who obtains a `channel_id` (it travels in the WS URL) can attach with any well-formed token, receive the OCR text stream, and send `{"type":"cancel"}`. Mitigated only by 192-bit channel-id entropy. | [websocket.py L185-194](file:///d:/OmniScribe/src/omniscribe/api/routers/websocket.py#L185-L194) |
| Medium | Session token travels in the WebSocket **query string** → logged by proxies/access logs. | [frontend websocket.ts L53-59](file:///d:/OmniScribe/frontend/src/lib/api/websocket.ts#L53-L59) |
| Low | XML guard is a 1 MB byte-scan with coarse `SYSTEM` substring match; prefer `defusedxml` for defense-in-depth. | [_common.py safe_xml_root](file:///d:/OmniScribe/src/omniscribe/core/glossary_sources/_common.py#L144-L153) |
| Low | `ALLOW_SSRF_LOCAL=true` dev default permits loopback fetches — documented, keep `false` in any exposed deployment. | [utils/security.py](file:///d:/OmniScribe/src/omniscribe/utils/security.py) |
| Low | Rate limiter is per-process in-memory (`per_minute * workers` effective cap) — documented, fine for single-worker desktop use. | [security_middleware.py](file:///d:/OmniScribe/src/omniscribe/api/services/security_middleware.py#L443-L457) |
| **High** | `start_app.vbs` runs **unpinned `redis:latest` with no auth on 0.0.0.0:6379** on every consumer machine. | [start_app.vbs L64](file:///d:/OmniScribe/start_app.vbs#L64) |
| Medium | `compose.yaml` exposes Redis 6379 to host with no auth. | [compose.yaml](file:///d:/OmniScribe/compose.yaml) |

**Fix for WS binding:** store the issued `(channel_id, session_token)` pair from `/api/progress/session` in `ProgressService`/state, and reject `connect()` when the presented pair doesn't match; move the token out of the query string into the first post-accept frame or Sec-WebSocket-Protocol.

---

## 2. Frontend / UI / UX Findings

| Sev | Finding | Fix |
|---|---|---|
| **High** | **Contract break:** frontend `getMerged()` calls `/glossary/merged`; backend exposes `/api/glossary/library/merged` → 404 + "Failed to fetch merged glossary preview" console error on **every** page load. | Point [endpoints.ts L173](file:///d:/OmniScribe/frontend/src/lib/api/endpoints.ts#L173) at `/glossary/library/merged` |
| Medium | Metadata panel is not live: "Overall confidence 100%" shown before any result; Total pages / Active page / Blocks streamed never populated during a run. | Wire `block_complete` / `page_complete` frames into the stats; show "—" instead of 100% pre-run |
| Medium | Cancel responsiveness: cancel flag is checked between blocks; an in-flight VLM call (observed >25s) delays "Cancelling…" resolution. | Surface "waiting for current model call" state; consider request-level abort of the VLM HTTP call |
| Low | Page title "DocuVerse — Intelligent Document Processing & Translation" while header says OmniScribe. | Align branding (`index.html` title) |
| Low | Upload hint "up to 50 MB" hard-coded; server cap is 10,240 MB (`max_upload_mb` in `/api/config`). | Render the cap from config |
| Low | A11y: language / translation-model / OCR-model-select comboboxes lack accessible names; Settings tab pairs a textbox and combobox for model ID. | Add labels / `aria-label` |
| Low | Settings "Document processors" labels (Table Structure Extractor, LaTeX Math Formula Engine, …) don't match the canonical processor names used in the workstation tab and AGENTS.md. | Reconcile naming |

Accessibility positives: landmarks (`banner`, `navigation`, `main`) present, buttons/switches named, heading hierarchy sane, theme toggle has a description.

---

## 3. QA / Test Coverage

- **Suite:** `pytest -m "not slow"` → **1429 passed, 3 skipped, 0 failed** (77s).
- **Coverage: 82% overall.** Core pipeline modules are 85-100% (`workflows/base` 99%, `hybrid` 93%, `repair` 100%, `text_recall` 100%).

**Coverage gaps (risk-ordered):**

| Module | Cov | Risk |
|---|---|---|
| `core/glossary_sources/sql_table.py` | 15% | SQL identifier handling — security-adjacent |
| `core/glossary_sources/git_repo.py` | 20% | Remote fetch + credentials plumbing |
| `core/transcription/local_engine.py` | 28% | — |
| `api/routers/extraction.py` | 38% | User-facing route surface |
| `api/routers/translation.py` | 38% | User-facing route surface |
| `core/nllb_engine.py` | 40% | — |
| `api/services/state_backend_redis.py` | 43% | Opt-in backend, silently undertested |
| `api/tasks.py` (Celery) | 54% | Async translation path |
| `api/routers/glossary_imports.py` | 52% | — |

Other QA gaps: two regression tests skip for missing datasets (`scripts/fetch_datasets.py` never run in this checkout — same silent-skip pattern flagged in nightly CI); `wait_for`-style E2E browser coverage exists only as `test_ui.py` (Playwright, manual); no contract test would have caught the `/glossary/merged` break — an OpenAPI-vs-frontend snapshot test would.

---

## 4. Core OCR Pipeline Findings

### High
1. **Silent empty-output jobs.** `CircuitOpenError` re-raised inside `asyncio.TaskGroup` is wrapped in an `ExceptionGroup`; on the **dense** path `process_page`'s `except Exception` swallows it → job "succeeds" with empty text on every page. Sparse path dies as a generic 500. Fix: `except* CircuitOpenError` unwrapping (pattern already used for `OCRCancelled`) + `eg.subgroup()` split in `process_page`. ([hybrid.py](file:///d:/OmniScribe/src/omniscribe/core/workflows/hybrid.py#L708-L788))
2. **Non-Latin text dropped in searchable layer.** All `insert_text`/`insert_textbox` use `fontname="helv"` (WinAnsi) — Arabic/CJK glyphs can't be encoded, so the embedded text layer is empty for exactly the scripts this product targets. ([embedder.py](file:///d:/OmniScribe/src/omniscribe/core/pdf/embedder.py#L30-L42))
3. **Surya model reloaded per request.** `build_pipeline` constructs `HybridAligner()` → `DetectionPredictor()` on every `/process` call (seconds of load + VRAM churn; 2 resident copies under concurrency). Make it a process-level singleton like the circuit-breaker registry. ([ocr_pipeline_factory.py L213](file:///d:/OmniScribe/src/omniscribe/api/services/ocr_pipeline_factory.py#L209-L213))

### Medium
4. Wrong bbox area formula in hallucination density check (`x1*w * y1*h` instead of `(x1-x0)*w * (y1-y0)*h`). ([hallucination.py L98-101](file:///d:/OmniScribe/src/omniscribe/core/ocr_quality/hallucination.py#L89-L101))
5. `zip(sizes, predictions, strict=False)` — a short Surya batch raises `IndexError` outside per-page handlers, killing the whole job. Use `strict=True` + chunk-level degradation. ([aligner.py L58](file:///d:/OmniScribe/src/omniscribe/core/aligner.py#L56-L58))
6. `_apply_trust` runs CPU-heavy pixel work (pure-Python watermark scan) on the event loop, stalling all in-flight pages. Wrap in `asyncio.to_thread`. ([base.py L167-199](file:///d:/OmniScribe/src/omniscribe/core/workflows/base.py#L167-L199))
7. Embed pass re-rasterizes the *whole* document even for page subsets; grounded repair re-rasterizes the full PDF per repaired block. Add a page-image cache / thread images through. ([embedder.py](file:///d:/OmniScribe/src/omniscribe/core/pdf/embedder.py), [prompted.py L265](file:///d:/OmniScribe/src/omniscribe/core/grounded/prompted.py#L248-L281))
8. Blank-page retry rebuilds `DetectionPredictor` up to 3× for legitimately blank scans. ([aligner.py L81-85](file:///d:/OmniScribe/src/omniscribe/core/aligner.py#L77-L86))
9. No hard total page-count cap (chunk size capped at 500, document size unbounded).

### Live performance observation
3-page dense PDF, hybrid mode, olmocr-2-7b, quality target 0.98 / max_retries 2: **0/3 pages after ~7 minutes**, cancel blocked by in-flight calls. Dense per-box OCR + aggressive repair loop on a 7B model compounds badly. Consider lowering the default target, streaming per-box progress to the UI, and per-call timeouts that honor cancellation.

### Verified sound
Normalized-bbox contract end-to-end; cancellation design (`OCRCancelled(BaseException)`, cooperative checks, `except*` unwrapping); bounded LRU image cache; fail-open recall boosters with kill switches; repair loop stall-guard logic; prompt hygiene (`sanitize_prompt_input`, pinned OlmOCR prompt, `PROMPT_VERSION`).

---

## 5. DevOps / CI-CD Findings

### High
1. **`docker compose up` starts nothing** — `api`/`redis` carry `profiles: ["default"]`; Compose has no implicit default profile. Remove `profiles` from both. ([compose.yaml](file:///d:/OmniScribe/compose.yaml))
2. **security.yml:** SARIF upload lacks `security-events: write` (upload silently no-ops) **and** uses mutable `returntocorp/semgrep:latest` (stale image name + supply-chain vector). ([security.yml](file:///d:/OmniScribe/.github/workflows/security.yml))
3. **Dockerfile:** unpinned `curl | sh` uv install; `uv sync` without `--locked`; no `.dockerignore` (build context includes `.env`). ([Dockerfile](file:///d:/OmniScribe/Dockerfile))
4. **Dependabot missing the `npm` ecosystem** — `frontend/package-lock.json` gets zero automated security updates. ([dependabot.yml](file:///d:/OmniScribe/.github/dependabot.yml))
5. **CI/Makefile pip-audit divergence:** CI runs `pip-audit` bare while Makefile documents `PYSEC-2026-311` as risk-accepted — gates disagree.
6. `start_app.vbs`: unpinned redis, no auth, 0.0.0.0 bind (also listed under Security); Celery app module drift (`-A src.omniscribe.api.celery_app` vs compose's `-A omniscribe.api.tasks`) can register tasks in a different module copy. *(Redis half: P1-6. Drift half: fixed 2026-08-16 — `start_app.vbs` celery + uvicorn targets now use the installed-package `omniscribe.*` path, matching compose; pinned by `test_celery_and_uvicorn_targets_match_installed_package_path` in `test_repo_hygiene.py`.)*

### Medium
- nightly.yml: `if-no-original-found:` is not a valid upload-artifact input (should be `if-no-files-found`); dataset fetch `|| true` turns the slow regression gate into a silent no-op.
- All GitHub Actions pinned to mutable tags (`@v4`), no top-level `permissions:` block.
- pre-commit mypy runs in an isolated env (weaker than CI's `uv run mypy src`).
- `pyproject.toml`: `torch>=2.0.0` unbounded; duplicated dep declarations across extras.
- `install.bat` self-elevates to admin unnecessarily; `install.ps1` pipes a remote script to `iex` unverified and never checks npm exit codes; uses `npm install` instead of `npm ci`.
- `stop_app.bat` never stops the `redis-local-ocr` container.

### Good
Concurrency groups, fail-fast-off matrices, build-before-tag release ordering, HF/dataset caching, Python 3.11→3.13 matrix, frontend gate in CI, non-root Docker runtime user, layer-cache-friendly COPY order, uv-lock pre-commit hook, lockfile in sync.

---

## Prioritized Remediation Roadmap

**P0 — correctness/silent-data-loss (this week)** ✅ *shipped 2026-08-16*
1. ✅ Unwrap `CircuitOpenError` from `ExceptionGroup` (sparse + dense paths + refine) — 3 regression tests in `test_workflows_hybrid.py`.
2. ✅ Fix `/glossary/merged` endpoint path in the frontend (`/glossary/library/merged` + entries→map flattening in `glossaryStore.ts`).
3. ✅ Unicode-capable font for PDF text embedding — font chain (env override → bundled `resources/fonts/` → OS font → PyMuPDF `cjk`), codepoint-fidelity probe demotes remapping fonts (Tahoma Arabic → presentation forms), Latin stays on `helv` (zero size cost), uncovered chars dropped instead of U+0000; 4 tests in `test_pdf.py`. Verified: CJK + Cyrillic round-trip exactly; Arabic needs a bundled/pointed-at Arabic font (warning message guides the user).
4. ✅ `compose.yaml` profiles fix (`docker compose config` now lists api+redis) + security.yml `security-events: write` + pinned `semgrep/semgrep:1.173.0`. Repo-hygiene test updated to pin the correct invariant; pre-existing frontend test TDZ race (`WorkstationView.test.ts`) fixed along the way.

**P1 — security hardening** ✅ *shipped 2026-08-16*
5. ✅ WS token-binding at connect + token out of the query string — `/api/progress/session` registers the minted `(channel_id, session_token)` pair on the manager (LRU-capped); the WS handshake now requires `{"type":"auth","session_token":...}` as the first inbound frame, verified with `hmac.compare_digest` against the minted record (10s auth timeout, 1008 close, no channel takeover of an active socket). Frontend sends the auth frame on open; dev scripts + ARCHITECTURE.md updated. Regression tests: `test_ws_handshake_rejects_wrong_unminted_and_silent_tokens` + 2 frontend handshake tests.
6. ✅ Redis hardening — `start_app.vbs`: pinned `redis:7-alpine`, `127.0.0.1` bind, generated-once `requirepass` (persisted to gitignored `redis-password.txt`, never logged) with `REDIS_URL` threaded into Celery + uvicorn; pre-hardening containers are recreated. `compose.yaml`: `requirepass` via `${REDIS_PASSWORD:-omniscribe-local-dev}`, loopback-only publish, auth-aware healthcheck, matching `REDIS_URL` on api/worker. Verified with `docker compose config`.
7. ✅ Dependabot `npm` (`/frontend`) + `docker` ecosystems; Dockerfile uv installer pinned (`UV_VERSION=0.11.16`), `uv sync --locked` on both layers (lockfile verified in sync); new `.dockerignore` keeps `.env`, caches, and the frontend out of the build context.
8. ✅ `defusedxml` swap for glossary XML — `safe_xml_root` parses via `defusedxml.ElementTree.fromstring(forbid_dtd=True)` (XXE/DTD/entity rejection at the expat level; stable `ValueError` messages preserved); dep promoted from the optional `glossary` extra to base deps since the guard must not be optional. Old `SYSTEM` substring false-positive eliminated. 5 new tests in `TestSafeXmlRoot`.

**P2 — performance & reliability** ✅ *shipped 2026-08-16*
9. ✅ Surya predictor singleton (`get_shared_detection_predictor` / `get_shared_hybrid_aligner`, circuit-breaker-registry pattern, detection serialized on a shared lock; factory uses the shared aligner); blank-batch retry reuses the predictor instead of rebuilding up to 3×; hallucination density area fixed to `(x1-x0)·w × (y1-y0)·h` (off-origin regression test); `zip(..., strict=True)` with chunk-level degradation to empty boxes (LLM text still lands via full-page fallback); trust scoring off the event loop via per-page `asyncio.to_thread`; embed pass rasterizes only the processed pages (`page_nums=` threaded embedder → writer → `EngineBase._emit`, `None` = all pages) and grounded repair reuses a per-instance raster cache; hard page-count cap `OMNISCRIBE_MAX_PAGES` (default 500, applied after page-range selection, clean 4xx via `ValueError`). New tests: 3 aligner (singleton + degradation + no-rebuild retry), hallucination off-origin, 2 embed-subset, grounded raster cache, 6 page-cap.
10. ✅ Metadata panel live wiring — default `confidenceSummary` is now `null` so the panel renders "—" pre-run instead of "Overall confidence 100%"; confidence chain = streamed block average → `quality_summary` → response summary; "Active page" follows the last streamed `block_complete` page; cancel-state UX surfaces "waiting for the current model call" (PipelineProgress notice + honest optimistic status line). Frontend gate green (0 svelte-check errors, 40 vitest tests, build OK).

**P3 — quality & hygiene** ✅ *shipped 2026-08-16*
11. ✅ Coverage push — `sql_table` + `git_repo` glossary sources (`test_glossary_sources_sql_git.py`, 40 tests; surfaced a real bug: markdown table headers ingested as glossary entries — `_parse_text` now skips `#` headers, separator rows, and pipe rows directly above a separator); extraction + translation routers (`test_extraction_translation_routers.py`, 24 tests; surfaced two real bugs: `/api/translate/tree`'s precedence-broken config resolution made request overrides **and** the SSRF guard dead code — now resolves through `_config` like model discovery; duplicate shadowed `POST /api/export/docx` registration removed from `extraction.py`); redis state backend (`test_state_backend_redis.py`, 14 tests on a shared `FakeServer`; `setex` deprecation fixed); frontend↔OpenAPI contract test (`test_frontend_openapi_contract.py`, 38 tests — every endpoints.ts route asserted live, duplicate-operation-ID guard, route-set snapshot with env-gated regen; snapshot regenerated 31→62 paths; dead `configApi.getModels('general')` 404 path fixed).
12. ✅ Action SHA pinning (all 4 workflows: checkout/setup-node/setup-uv/cache/upload-artifact/upload-sarif/action-gh-release pinned to commit SHAs with `# vX` comments) + top-level `permissions:` blocks (test/nightly `contents: read`; security/release unchanged — already least-privilege); pip-audit CI↔Makefile aligned (`--ignore-vuln PYSEC-2026-311` + risk-acceptance comment in test.yml); nightly hardening (invalid `if-no-original-found` → `if-no-files-found`; dataset fetch `|| true` replaced with an exit-code contract — `fetch_datasets.py` exits `77` (EX_NOPERM) on license-gated skip, CI fails on any other non-zero, regression test pins the code); branding/copy (page title + meta description DocuVerse/LocalDeepL → OmniScribe; upload hint and Settings "Max upload cap" badge rendered from `/api/config` cap instead of hard-coded 50 MB / 10 GB; 4 unlabeled comboboxes got `aria-label` via a new `Select` `ariaLabel` prop; Settings processor chips replaced made-up 422-rejected ids with the canonical `DocumentProcessorName` six, matching the workstation tab). Gates: ruff + mypy clean, 1573 passed / 4 skipped (fast tier), frontend 0 svelte-check errors / 40 vitest / build OK.

---

## Artifacts
- Semgrep results: `.autoplan/semgrep-full-scan.json`
- UI screenshots: `.autoplan/audit-ui-workstation.png`, `.autoplan/audit-ui-post-cancel.png`
- Test run: 1429 passed / 82% coverage (fast tier, 2026-08-16); 1455 passed after P2; 1573 passed after P3 (fast tier, 2026-08-16)
