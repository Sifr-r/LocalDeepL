# OmniScribe — Five-Lens Codebase Audit

**Date:** 2026-09-04
**Scope:** Full repository at `D:\OmniScribe` (Python backend + Flutter client, `tests/`, `docs/`, `scripts/`, CI workflows).
**Mode:** Read-only. No files modified, no code executed. Every claim is anchored to `path:line` evidence.
**Method:** Five independent `explore` agents, each given one perspective and a self-contained briefing. Findings cross-referenced below.

---

## 1. Executive summary

OmniScribe is a **mature, well-engineered beta** that is significantly closer to shippable than its own documentation claims. The Python backend has a clean Cordis-style plugin harness, ~165 test files, defence-in-depth security (CORS + bearer + rate-limit + upload-cap + SSRF guard + DNS pin + token denylist + non-root container), and a fully wired ASGI middleware triad. The Flutter client exists for desktop and web. The code is in much better shape than `SECURITY.md` admits — most of what the docs call "deferred" was actually closed in the recent Wave 11–14 remediation.

The real audit signal lives in three places, all of which show up across multiple lenses:

1. **Documentation drift.** `SECURITY.md:62-78`, `DEPLOYMENT.md:113-131`, and several READMEs describe features as "deferred" or "scaffolding" that are in fact shipped. This is the single largest source of risk in the report — operators who believe the docs will misconfigure the system.
2. **First-impression surface.** No root `README.md` (the GitHub landing page renders `docs/README.md` via `pyproject.toml:5`, but the project-root is bare), `client/README.md` is the unmodified Flutter starter, no `CONTRIBUTING.md` / issue templates, no screenshots, no FAQ, no end-user install path. Five of five lenses flag something in this cluster.
3. **State-loss default and crash-on-switch hazards.** The in-memory `JobQueue` is the default state backend, losing async translation results and in-flight OCR jobs on every restart (`DEPLOYMENT.md:181-184`); `OMNISCRIBE_STATE_BACKEND=redis` crashes at plugin apply (`outstanding-work.md:111`). PM and Dev lenses both flag it; the fix is small.

There is **one concrete exploitable issue** found by the security lens: `.env.example:194` ships `REDIS_PASSWORD=omniscribe-secure-dev-password` as an active value, and the `:?` substitution in `compose.yaml:65,129,140` only fires when the variable is missing — so the documented `cp .env.example .env && docker compose up` quickstart leaves Redis listening on loopback with a publicly documented password.

Beyond that, no Criticals. The High/Medium findings are well-distributed across documentation, dev hygiene (god files, `load_dotenv()` at import time, HybridEngine re-injection), QA (10+ magic-number sleeps, almost no property-based tests, no flake detection), and end-user friction (16-step install journey for a tool whose value prop is "drop a PDF in").

**Overall verdict:** keep the Wave 14 cleanup momentum going, but stop the "audit → close items" treadmill for two sprints and instead spend that energy on **(a) correcting the documentation drift** and **(b) building the end-user entry point**. The code is ready; the words around it are not.

---

## 2. Methodology

Five `explore` agents were dispatched in parallel under a fixed briefing template, each with a self-contained scope and acceptance criteria:

| Lens | What it was asked to look for | Output budget |
|---|---|---|
| **Dev / Software engineering** | Code organization, API design, type safety, async correctness, patterns, technical debt, build/DX, dependency hygiene | ~2,500 words |
| **Security** | Secrets, auth/authz, input validation, file handling, network exposure, dependency CVEs, plugin trust boundary, crypto, logging hygiene, container hardening, web hardening, error leakage | ~2,500 words |
| **QA / Test engineering** | Test coverage shape, test quality, test-type balance, reproducibility, edge cases, CI, manual test affordances, bug hotspots, client-side QA, fixtures | ~2,000 words |
| **Product manager** | Product clarity, user journey, distribution, documentation, licensing posture, roadmap visibility, feature surface, cost story, support, telemetry, operational readiness | ~2,000 words |
| **End user** | First 60 seconds, install story, "just run it", error experience, documentation accessibility, output/feedback, format support, performance perception, help/escape hatches, trust signals, privacy story, platform support | ~2,000 words |

Each agent was required to: (1) be read-only, (2) cite `path:line` for every claim, (3) not print values of `.env` or any secret, (4) mark anything unverified as such, (5) skip nitpicks and focus on substantive findings.

The synthesis below de-duplicates findings that appear under multiple lenses, marks **convergent** items explicitly (these carry the highest signal), and preserves the per-lens detail as the audit's body.

---

## 3. Convergent findings (highest signal)

These are the items that showed up under **two or more of the five lenses**. They are the audit's strongest recommendations and the place to spend engineering attention first.

### C1. Documentation is materially out of date vs. shipped code — flagged by **Security, PM, End user, Dev**

- `docs/SECURITY.md:62-78` describes bearer auth, rate limiting, and `MaxUploadSizeMiddleware` as "currently deferred capabilities … scaffolding for the forthcoming middleware plugins." In fact all three are wired unconditionally in `src/omniscribe/server.py:184-202` and shipped since Wave 14.
- `docs/DEPLOYMENT.md:113-131` documents `OMNISCRIBE_OCR_AUTH_TOKEN`, `OMNISCRIBE_TRANSLATION_AUTH_TOKEN`, etc., as if enforced. With the middleware triad live, these are now enforced, but the doc also says the server may be exposed without them — a misconfiguration path.
- `outstanding-work.md:110-111` ("Deferred Architectural Capabilities: ASGI Middleware Suite") still lists auth/rate-limit/upload-size as deferred. The closing line says they're not built; they are.
- `docs/README.md:7` first paragraph reads as an internal changelog ("the previous in-browser workstation has been deprecated," "no `omniscribe` script entry is shipped") — flagged by end-user and PM lenses.

**Why it matters.** Operators reading the docs will believe auth is opt-in. Internal contributors will keep closing items that are already closed, and "what's left to ship" is miscommunicated.

**Fix.** Schedule a single documentation sprint to reconcile `SECURITY.md`, `DEPLOYMENT.md`, `outstanding-work.md`, and `README.md` with the current code. Where the docs lag a Wave, say so explicitly. Diff `outstanding-work.md` against `CHANGELOG.md` and the actual code paths in `server.py` line-by-line.

### C2. The end-user install path is 12–16 steps, with no working out-of-the-box flow — flagged by **End user, PM**

The end-user persona's reconstructed install:

1. `git clone` the repo (assumes `git`).
2. Install Python 3.11+ (assumes version awareness).
3. Install `uv` (a non-default Python tool, never heard of by the persona).
4. `uv sync --extra web --extra preprocessing` (assumes knowledge of extras).
5. Download LM Studio from `lmstudio.ai` (no link in docs).
6. Download a vision model (~5–50 GB; no recommendation).
7. Start LM Studio's local server on port 1234.
8. `uv run omniscribe-server --port 8000` in terminal A.
9. Install Flutter SDK (~1.5 GB).
10. `cd client && flutter pub get && flutter run` in terminal B.
11. Pick a target device (`windows` / `macos` / `linux` / `web`).
12. Configure the client to point at the server.
13. Drop a PDF into the Workstation tab.
14. Get a searchable PDF back.

The PM lens finds a parallel install story: "the local single-user profile works, but the README admits auth is 'scaffolding'" (`SECURITY.md:71`).

**Why it matters.** The product is positioned for hobbyists and power users (per its own classification), but neither the front door nor the docs acknowledge that. A non-developer who reaches the GitHub page will leave.

**Fix.** Three concrete steps:

1. Add a `Before you start` section to the README with the LM Studio link, a recommended first model, and a RAM/VRAM table.
2. Add a "GUI users" section that pre-decides `--extras`, documents one `uv sync` line, and one `uv run` command. Remove the "no CLI script" hedge from the first paragraph.
3. **Ship a desktop binary.** Either a PyInstaller bundle of the FastAPI server, or a Flutter build that embeds the server. Without this, the "16 steps" path is the only path.

### C3. In-memory state backend is the default and silently loses history on restart — flagged by **PM, Dev**

- `DEPLOYMENT.md:181-184`: *"A restart loses in-memory history."* (Footnote, not a warning.)
- `outstanding-work.md:111`: the Redis backend is deferred and "currently crashes at plugin apply."
- `AGENTS.md:170` (per Dev lens) confirms `memory` (in-memory) is the default.

**Why it matters.** A user running async translation or batch OCR will lose results on every restart with no warning. The PM lens rates this High.

**Fix.** Make SQLite the default state backend. `OMNISCRIBE_STATE_BACKEND=sqlite` is documented and ready; one line in `compose.yaml` and the `omniscribe-server` CLI default. Or, at minimum, log a loud warning at startup when state is in-memory and bound to non-loopback.

### C4. No top-level `README.md`; Flutter client README is the unmodified starter — flagged by **End user, PM**

- No `D:\OmniScribe\README.md`. `pyproject.toml:5` sets `readme = "docs/README.md"`, so GitHub does render `docs/README.md` on the landing page — the end-user lens claim that "GitHub will show a blank project page" is *technically* wrong, but the user experience of a `docs/`-only README is still bad (GitHub hides it inside the "docs" folder on the file browser).
- `D:\OmniScribe\client\README.md:1-3` is the unmodified Flutter starter: *"A new Flutter project."* No mention of OmniScribe, no install instructions, no link back to the main README.

**Why it matters.** Two of the three places a first-time visitor lands (root, client) are useless. The landing page *is* rendered (it shows `docs/README.md`), but the absence of a root README signals "not packaged" to anyone scanning the repo from a search engine or a `git clone`.

**Fix.** `git mv docs/README.md README.md` and update internal links; rewrite `client/README.md` to point at the server, list the tabs, and link to the main README.

### C5. `.env.example` ships a working dev default for `REDIS_PASSWORD` — flagged by **Security, Dev** (as dependency risk)

- `.env.example:194`: `REDIS_PASSWORD=omniscribe-secure-dev-password` is shipped as an active, uncommented value.
- `compose.yaml:65,129,140` uses `${REDIS_PASSWORD:?…}` which only fires when the variable is *missing* — since the example supplies it, the documented `cp .env.example .env && docker compose up` boots with a publicly known password.
- Redis is published on `127.0.0.1:6379` by default; on a multi-user host or a bridged container, anyone on the host's default bridge can issue `FLUSHALL`.

**Why it matters.** This is the only directly exploitable issue in the audit. The remediation is one line.

**Fix.** Set `REDIS_PASSWORD=` (empty) in `.env.example` so the `:?` substitution forces a real choice. Or rename to `REDIS_PASSWORD_PLACEHOLDER_SET_ME` and document a `tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32` one-liner.

### C6. `make doctor` is a great affordance that no-one documents — flagged by **End user, Dev**

`Makefile:74-75` ships a `doctor` target that runs Python version, `uv`, Redis reachability, and VLM endpoint reachability checks. The Dev lens calls it "genuinely useful." The End user lens reconstructs an install story that doesn't mention it.

**Why it matters.** This is the single most useful tool for a stuck user, and it's invisible.

**Fix.** Reference `make doctor` in the install section. Add a "Stuck? Run `make doctor`" line at the top of `TROUBLESHOOTING.md` (which doesn't exist yet — see C7).

### C7. No `TROUBLESHOOTING.md` / `USER_GUIDE.md` / `CONTRIBUTING.md` — flagged by **End user, PM**

- No `TROUBLESHOOTING.md`. The only troubleshooting copy is three bullets in `DEPLOYMENT.md:170-176`.
- No `CONTRIBUTING.md`. `AGENTS.md` doubles as a contributor guide but is not user-facing.
- No `docs/USER_GUIDE.md` for the Windows Defender false positive on `arrow_substrait.dll` (well documented in `SECURITY.md:147-182`), the placeholder-auth-token rejection, or the LM Studio 1234-port check.

**Why it matters.** When something breaks, the user has no entry point. They will file a low-quality GitHub issue or leave.

**Fix.** Add a `TROUBLESHOOTING.md` (or `USER_GUIDE.md`) with the top 10 first-run errors and fixes. Cross-link from the README and from `make doctor`'s output. Add `CONTRIBUTING.md` pointing at `AGENTS.md`. Add `.github/ISSUE_TEMPLATE/bug_report.md` and `feature_request.md`.

---

## 4. Per-lens findings

### 4.1 Dev / Software engineering

**Verdict.** Mature codebase with intentional architecture, clean DI, correct fail-open semantics on the recall boosters, and unusually disciplined lifecycle handling in the harness. The remaining debt is concentrated in two god files (`plugins/ocr/service.py` ~890 LOC, `core/workflows/hybrid.py` 800+ LOC), some `load_dotenv()` double-loading, and 60+ tracked style nits in `outstanding-work.md` §7.

**Strengths.**

- **Harness rollback.** `src/omniscribe/harness/context.py:204-221` rolls back partial registrations on `apply()` failure.
- **Fail-open on per-page exceptions.** Every recall booster and `core/workflows/base.py:201-214` swallows per-page exceptions and degrades. Tested.
- **`CircuitBreakerRegistry` keyed by `(api_base, model)`** (`core/ocr/resilience.py:325-341`) — clean cross-request sharing.
- **Constant-time token comparison** with `hmac.compare_digest` at every check site (`middleware/auth.py:111`, `plugins/ocr/service.py:570`).
- **Upload streaming + per-job tempdir** (`plugins/ocr/service.py:338-381`) — memory bounded by concurrent on-disk count, not queue depth × upload size.
- **Startup guard** at `server.py:375-395` refuses non-loopback binds without a real auth token and blocks placeholder tokens on LAN binds.
- **OpenAPI snapshot drift test** at `tests/routers/test_openapi_schema.py` (verified by QA lens) catches accidental route-shape changes.

**Findings.**

| # | Severity | Title | Evidence |
|---|---|---|---|
| D1 | Critical | `JobStatusResponse.started_at` is always `None` | `plugins/ocr/service.py:519-530`; tracked `outstanding-work.md` §6.84/6.85 |
| D2 | Critical | `InMemoryJobQueue._run` swallows runner exceptions with only a log; subsequent `JobFailed` path is hidden | `plugins/jobs.py:281-291, 343-355` |
| D3 | High | `HybridEngine` re-injects stage dependencies on every `execute()` call (decorative) | `core/workflows/hybrid.py:325-326, 353-355, 434-437, 491, 518`; tracked §4.37, §6.63-66 |
| D4 | High | `HybridEngine._reset_run_state` resets only two stage states | `core/workflows/hybrid.py:165-178`; tracked §4.38 |
| D5 | High | `load_dotenv()` is called at module import *and* at `main()`; importing `omniscribe.server` reads `.env` | `server.py:26,125,459`; tracked §4.14 |
| D6 | High | `plugins/ocr/service.py` is 890 LOC and mixes four concerns | service file itself (header comment acknowledges split history) |
| D7 | High | Routes reach into private service state via ~8 cross-boundary touches | `plugins/ocr/plugin.py:170,182,246,310,326` |
| D8 | High | Global exception handler envelope differs from per-route envelope | `server.py:220-243` vs `plugins/ocr/plugin.py:99` and `plugins/glossary/routes.py:48` |
| D9 | Medium | `mypy.disallow_untyped_defs` is enabled only for `omniscribe.core.*`; plugins/harness are looser | `pyproject.toml:337-339` |
| D10 | Medium | `cors_origins` accepts three aliases (legacy + env); widens config attack surface for typos | `config.py:224-229`; tracked §4.1 |
| D11 | Medium | `extract_json` walks every `{` / `[` (O(n²) on large responses) | `utils/json_parse.py`; tracked §4.29 |
| D12 | Medium | `OCRProcessor.__getattr__` rebuilds a `_DEFAULTS` dict on every miss | `core/ocr/processor.py:228-236`; tracked §4.41 |
| D13 | Medium | `is_transient_error` lumps `ValueError` with bugs; conflated in retry path | `core/ocr/resilience.py:55-63`; tracked §4.12 |
| D14 | Medium | `_DENSE_MODE_ALIASES` mapping is hidden in a property; should live in one place | `plugins/ocr/schemas.py:20-26,92-95` |
| D15 | Medium | `trust_images_dict` plumbed into `_finalize` then immediately discarded | `core/workflows/hybrid.py:263,310,438`; tracked §6.45 |
| D16 | Low | `Dockerfile` pins `python:3.14-slim` (line 28) but `pyproject.toml` classifiers only list 3.11/3.12/3.13 | `Dockerfile:28` vs `pyproject.toml:15-19` |
| D17 | Low | `transformers>=5.15.1` pin in `[trocr]` / `[nllb]` is unusual (stable is 4.x) | `pyproject.toml:97,104` |
| D18 | Low | `make lint` runs `ruff --no-fix` while pre-commit runs `ruff --fix` | `Makefile` vs `.pre-commit-config.yaml:22` |
| D19 | Low | `is_transient_error` default treats `RuntimeError` as permanent; `httpx.ConnectError` is a `RuntimeError` subclass, transiently | `core/ocr/resilience.py:160` |
| D20 | Low | `tests/conftest.py:30` mutates `sys.path` at import time | `tests/conftest.py:30` |

**DX quick wins (Dev lens).**

1. Add `make fix` mirroring the pre-commit flow.
2. Run `uv run ruff check --fix src tests` once to clean the per-file-ignores list at `pyproject.toml:258-289`.
3. Add `make check` (lint + mypy + fast tests) and `make diag` (`make doctor` + slow-test `--collect-only`).
4. Make `make test` accept a path argument.

### 4.2 Security

**Verdict.** Defence-in-depth is real, not theatre. CORS + bearer + rate-limit + upload-cap are wired; SSRF guard with DNS pin and IP-blocklist; placeholder-token denylist on LAN binds; constant-time token comparison; non-root container with `tini` PID 1; pinned base image digests. The audit's one concrete exploitable finding is the `.env.example` default for `REDIS_PASSWORD`. The other findings are hardening, documentation drift, or footgun territory.

**Strengths.**

- **Bearer auth + placeholder-token denylist** — `_PLACEHOLDER_AUTH_TOKENS` at `src/omniscribe/server.py:39-46`; non-loopback bind without `OMNISCRIBE_AUTH_TOKEN` exits at `server.py:375-381`; placeholder token on non-loopback exits at `server.py:383-395`.
- **Middleware triad wired unconditionally** — `server.py:184-202`.
- **SSRF guard with DNS-pin** — `src/omniscribe/utils/security.py:142-217`; `_PinnedIPTransport` at `src/omniscribe/plugins/glossary/http_fetch.py:53-64` defeats DNS-rebinding.
- **Magic-byte sniffing before tempdir write** — `src/omniscribe/plugins/ocr/plugin.py:186-240` returns 415 before disk.
- **Constant-time artifact-token comparison** — `src/omniscribe/plugins/state_backend_sqlite.py:217,401`; `secrets.token_urlsafe(32)` generation at `plugins/progress.py:139` and `plugins/artifacts.py:78`; `min_length=32` on schemas at `plugins/documents/schemas.py:53-54`.
- **Container hardening** — `Dockerfile:83` creates `app` uid 1001 no-shell; `Dockerfile:131` runs under `tini`; `Dockerfile:28,77` pin `python:3.14-slim` to digest; `compose.yaml:44-49` adds `no-new-privileges:true` and `cap_drop: ALL`; `compose.yaml:48` binds loopback-only.
- **`subprocess.run([...])` with list args, no `shell=True`** (`core/glossary_sources/git_repo.py:49-57`); ref regex + `_validate_path` defeat argument injection.
- **No `eval`/`exec`/`yaml.load`/`pickle`/`marshal`** anywhere in `src/`.
- **`defusedxml` as a base dep** for XLIFF/TBX/TMX parsing (`pyproject.toml:44`).
- **Error sanitization at the edge** — `_sanitize_value_error` at `server.py:292-312`, `_sanitize_job_error` at `plugins/ocr/service.py:114-144`.
- **Plugin loader is module-string only** — no `eval`/`exec` in `harness/loader.py:100-118`.

**Findings.**

| # | Severity | Title | Evidence |
|---|---|---|---|
| S1 | High | `.env.example` ships active `REDIS_PASSWORD=omniscribe-secure-dev-password`; `compose.yaml` `:?` substitution only fires when missing | `.env.example:194`; `compose.yaml:65,129,140` |
| S2 | High | `SECURITY.md` describes bearer/rate-limit/upload middlewares as "deferred"; they are wired in `server.py:184-202` | `docs/SECURITY.md:62-78` vs `server.py:184-202` |
| S3 | Medium | `ALLOW_SSRF_LOCAL` defaults to `true` in `.env.example` but `false` in code; footgun | `.env.example:66` vs `config.py:206` |
| S4 | Medium | `MAX_UPLOAD_MB` default is 10 GB; LAN caller can pin 10 GB of memory+disk per request | `config.py:230`; `compose.yaml:74` |
| S5 | Medium | `?token=` query-param bearer accepted on broad path prefix (`/api/process/`, `/api/jobs/`); URL-borne tokens leak | `middleware/auth.py:49-52,163` |
| S6 | Medium | `/api/progress/cancel/{channel_id}` allows unauthenticated cancel on loopback dev profile | `plugins/progress.py:294-307` |
| S7 | Medium | Rate limiter is per-process; `--workers 4` ⇒ 4× effective ceiling | `middleware/rate_limit.py:151-152`; `server.py:441-455` |
| S8 | Medium | `transcription_auth_token` mask leaks 8 chars (first4…last4) for short operator-chosen tokens | `plugins/transcribe/config_store.py:34-40` |
| S9 | Medium | `StaticFiles` mount is exempt from auth; risky if a future feature lets operators drop files into `static/` | `server.py:204-209`; `middleware/auth.py:30` |
| S10 | Low | JSON-logger sensitive-field redaction is substring-based; both false positives and false negatives | `utils/structured_logging.py:134-167` |
| S11 | Low | `Dockerfile` CMD binds `0.0.0.0`; compose masks with `127.0.0.1:8000:8000` but `docker run -p 8000:8000 image` exposes wildcard | `Dockerfile:132` |
| S12 | Low | `git_repo._with_credentials` embeds the secret into the URL passed to `git archive --remote` (argv leak) | `core/glossary_sources/git_repo.py:123-142` |
| S13 | Low | `cors_origins=*` interaction with `allow_credentials=True` (Starlette fallback) — unverified without runtime test | `server.py:166-167` |
| S14 | Low | WebSocket origin check disabled when CORS contains `*` (intentional; token still gates) | `plugins/progress.py:310-318` |
| S15 | Low | `GET /api/jobs` lists all jobs to any bearer-auth caller; on dev bind (no auth) any process can enumerate | `plugins/ocr/plugin.py:308-311` |
| S16 | Low | `extract_json` walks every `{` / `[` — O(n²) DoS-shape concern | `utils/json_parse.py:26-33` |
| S17 | Info | PyMuPDF is AGPL-3.0 (dual-licence) — not a vuln, called out per audit lens | `pyproject.toml:25`; `THIRD_PARTY_LICENSES.md` |
| S18 | Info | `requests>=2.34.2` is dev-only; runtime tree pulls via `surya-ocr`; `pip-audit` needs dev group | `pyproject.toml:165-179` |
| S19 | Info | Uvicorn access log format does not log Authorization headers — unverified | (worth a quick test) |

**Secrets inventory (high-level only — values not reproduced).**

| Secret | Where read | Storage | Logged? | Token comparator |
|---|---|---|---|---|
| `OMNISCRIBE_AUTH_TOKEN` | env | env-only | `auth_enabled` boolean only | `hmac.compare_digest` |
| `OMNISCRIBE_TRANSCRIPTION_AUTH_TOKEN` | env + `/api/config/transcription` (masked first4…last4) | env | masked | `hmac.compare_digest` |
| `LLM_API_KEY` / `OMNISCRIBE_LLM_API_KEY` | env; default `"lm-studio"` | env | never | n/a |
| `REDIS_PASSWORD` | env; required by compose `:?` | env; `.env` gitignored, `.dockerignore`d | no | n/a |
| Artifact blob tokens | generated per upload | SQLite (`state_backend_sqlite.py:39-42`) | no | `secrets.compare_digest` |
| WebSocket session tokens | same generator | same store | no | `secrets.compare_digest`, `consumed=1` on first use |

**Dependency risk callouts.**

- **PyMuPDF AGPL-3.0** — not a vuln, but any operator distributing a network service must comply or buy a commercial licence. Already disclosed in `pyproject.toml:25`, `README.md:148-164`, `THIRD_PARTY_LICENSES.md`.
- **Unbounded majors** — all majors in `pyproject.toml` are bounded.
- **Windows Defender false positive on `arrow_substrait.dll`** — documented in `SECURITY.md:147-182`. Not a code defect.

### 4.3 QA / Test engineering

**Verdict.** Mature, layered test suite. Roughly 165 Python test files + 35 Flutter files. The Cordis-style boot fixture chain (`cordis_env` → `harness_ctx` / `api_client` in `tests/conftest.py:204-238`) is exemplary. The pipeline-orchestration tests and the bug-hunting e2e WS test are well-targeted. The weaknesses are: (1) almost no property-based testing (5 `@given` in 1 file), (2) 10+ magic-number sleeps that are textbook flaky patterns, (3) two doc/code drifts in CI, and (4) one Makefile/contract drift.

**Strengths.**

- **Layered boot fixture chain** — `tests/conftest.py:204-238` boots the full 13-plugin tree in memory with isolated artifact dir + small TTLs.
- **OpenAPI snapshot test** — `tests/routers/test_openapi_schema.py:18-32`; 3.2k-line `tests/openapi.json` checked in.
- **Hypothesis invariants on the trust-scorer** — `tests/core/ocr_quality/test_ocr_quality_trust_scorer_props.py:29-86`; three core invariants fuzzed across thousands of inputs.
- **Real PDFs as fixtures** — `examples/` re-used via `EXAMPLE_PDF_NAMES` (`tests/conftest.py:35-41`).
- **SSRF fail-closed test** — `tests/utils/test_ssrf.py:26` stubs `socket.getaddrinfo` and asserts negative DNS is rejected.
- **Negative-path parametrize** — `tests/core/ocr/test_ocr_resilience.py:30-72` covers both transient and non-transient HTTP errors.
- **Bug-hunting e2e WS test** — `tests/routers/test_progress_ws_e2e.py:35-89` was added specifically to catch the audit-flagged `channel`-arg loss regression.
- **E2E PDF round-trip** — `tests/core/test_document_roundtrip.py` + DOCX/HTML writers tests.
- **CI is well-structured** — `test.yml` (lint + format + mypy + pytest fast tier with 80% gate + pip-audit + Trivy container scan + CycloneDX SBOM), separate `client-tests` job, `nightly.yml` (slow tier with HF cache + calibration regression), `security.yml`, `release.yml`, `dependabot.yml`. SHA-pinned action refs.

**Findings.**

| # | Severity | Title | Evidence |
|---|---|---|---|
| Q1 | High | Makefile comment references non-existent test path | `Makefile:78` vs `tests/routers/test_openapi_schema.py` |
| Q2 | High | Stale `live_llm` references in CI comments; marker was removed per `CHANGELOG.md:193-199` | `test.yml:8`; `nightly.yml:12` |
| Q3 | High | 10+ "drain the worker" magic-number sleeps (`time.sleep(0.01)`, `asyncio.sleep(0.01..0.05)`) | `tests/routers/conftest.py:80`; `test_translate_routes.py:70`; `test_glossary_routes.py:348`; `test_context.py:121,125`; `test_jobs_plugin.py:50,129`; `test_auth.py:310`; `test_aligner.py:710`; `test_dictionary_postprocess.py:339` |
| Q4 | Medium | Property-based testing is token: 5 `@given` in 1 file; many fuzzable surfaces uncovered | `tests/core/ocr_quality/test_ocr_quality_trust_scorer_props.py` |
| Q5 | Medium | `core/translate/workflow.py` has no direct test; LangGraph driver exercised only indirectly | `src/omniscribe/core/translate/workflow.py` |
| Q6 | Medium | `tests/fixtures/` has no PDFs; all real PDFs live under `examples/` | `tests/fixtures/` (empty) |
| Q7 | Medium | No mutation testing (`mutmut` / `cosmic-ray` / `mutatest`) | `pyproject.toml`; workflows |
| Q8 | Medium | Coverage gate honestly admits 80% is the floor; 15 named under-tested modules | `pyproject.toml:307-317` |
| Q9 | Low | Calibration tests use hard-coded `seed=42` without a parallel test that the seed actually controls the result | `tests/scripts/test_ocr_quality_calibration_regression.py:82,91,102`; `test_calibrate_model_script.py:53` |
| Q10 | Low | Single `live` smoke test for `arrow_substrait`; either expand or merge into `tests/scripts/` | `tests/ops/test_arrow_substrait_present.py` |
| Q11 | Low | No chaos / fault-injection tests combining failures | (no test file) |
| Q12 | Low | Flutter `client/test/` has 35 files but no `integration_test/` directory; e2e Flutter test against a real server missing | `client/test/` |
| Q13 | Low | Flutter widget test smoke count is uneven; rich widget surface but inconsistent coverage | `client/test/widget_test.dart` (1 test) |
| Q14 | Info | Scripts excluded from lint/typecheck; `_StubOCR` from `tests/conftest.py:24` is referenced in 8+ test files | `pyproject.toml:234-237, 287-289` |
| Q15 | Info | No explicit `[tool.hypothesis]` block; default 100-example runs fine, no deadline for CI | `pyproject.toml:195-203` |
| Q16 | Info | `slow_dataset` marker is referenced by `nightly.yml` but only mini-fixture JSONs exist; full upstream datasets gated by `scripts/fetch_datasets.py` | `outstanding-work.md:113` |

**Coverage shape (rough estimates).**

| Area | Test files | Risk if untested | Est. coverage |
|---|---|---|---|
| `core/ocr/` | 10 | LLM call resilience, retry/breaker, VLM timeout | High (~85%) |
| `core/ocr_quality/` | 14 | Trust scoring, watermark, hallucination | Very High (~90%) |
| `core/workflows/` | 9 | Hybrid/grounded orchestration | High (~80%) |
| `core/translate/` | 9 | Translation pipeline + lexicon integration | Medium (~65%) — `workflow.py` not directly tested |
| `core/pdf/` | 6 | Rasterizer, embedder, AGPL-lock | High (~85%) |
| `core/lexicon/` | 3 | LanceDB store, migration, atomic toggle | Medium (~60%) |
| `plugins/` (15 plugins) | 24 | Plugin lifecycle, schemas, services | High (~85%) |
| `routers/` (HTTP routes) | 14 | End-to-end contract via `api_client` | High |
| `harness/` | 10 | Loader, context, effects, plugin base | High |
| `middleware/` | 3 | Auth / rate limit / upload limit | High (Wave 14) |
| Property-based (`@given`) | 1 file, 5 tests | `trust_scorer.score` invariants | Very Low (3%) |

**CI gap analysis.**

1. No test-result persistence — `pytest-slow-results` upload (`nightly.yml:63-70`) is only `.pytest_cache/v/cache/lastfailed`; no JUnit XML.
2. No flake detection (`pytest-flakefinder`, `pytest-rerunfailures`).
3. No Codecov / coverage trend — coverage XML is generated (`test.yml:85`) but never uploaded.
4. No `dependency-review-action` on PRs.
5. Windows matrix is single Python (3.11) — regressions on 3.12/3.13 go undetected between nightly runs.
6. No nightly that runs Flutter.

### 4.4 Product manager

**Verdict.** **Beta-true** v0.1.0. Feature surface is real, the local single-user profile works, but auth/rate-limit middleware is *not* deferred (despite what docs say) and the README admits auth is "scaffolding." It is shippable as a local single-user research/preview tool for someone willing to run LM Studio/Ollama on the side; it is **not** shippable as a v1.0 to non-technical users.

**Strengths.**

- **Strong AGPL posture for a permissive project** — PyMuPDF + Surya flagged in `README.md:148-164`, `pyproject.toml:25`, `THIRD_PARTY_LICENSES.md:11-38`; README points at clean default `pypdfium2` for closed-source forks.
- **Threat model is written down** — `SECURITY.md:36-57` defines three profiles (local/LAN/public) and what breaks at each.
- **Extras are honestly scoped** — `pyproject.toml:53-131` makes clear `lexicon` replaced `memory`, `async-translation` is intentionally light, `trocr`/`nllb`/`quality` are opt-in.
- **CI is real and tiered** — fast gate on PRs across Python 3.11/3.13/Windows + Flutter, nightly slow tests, Trivy scan, Dependabot.
- **Examples ship in the repo** as CC0 — no first-run download.
- **`outstanding-work.md` is unusually disciplined** — every closed item has a "closed in Wave N" outcome; deferred items individually tracked.

**Findings.**

| # | Severity | Title | Evidence |
|---|---|---|---|
| P1 | Critical | Auth/rate-limit/upload-size middleware described as "deferred scaffolding" in docs but actually shipped in `server.py:184-202` | `SECURITY.md:62-67`; `outstanding-work.md:110-111`; `AGENTS.md:247-248` |
| P2 | Critical | `client/README.md` is the unmodified Flutter starter | `client/README.md:1-3` |
| P3 | High | Install footprint large; "stays light" footnote concedes it's not actually light once you want translation + glossary | `README.md:25-41, 37`; `pyproject.toml:22-131` |
| P4 | High | "Local" claim conditional on a non-shipped VLM endpoint; out-of-the-box `omniscribe-server` runs but OCR's nothing | `README.md:59`; `compose.yaml:55` |
| P5 | High | In-memory state default loses history on restart; mentioned as a footnote | `DEPLOYMENT.md:181-184`; `AGENTS.md:170` |
| P6 | High | No `CONTRIBUTING.md`, no `CODE_OF_CONDUCT.md`, no `.github/ISSUE_TEMPLATE/`, no PR template | repo root (absent) |
| P7 | Medium | AGPL PyMuPDF warning is mid-README, not header; first-time reader sees MIT badge and may stop reading | `README.md:5, 146-164` |
| P8 | Medium | CHANGELOG is implementation-audit heavy, not user-facing | `CHANGELOG.md:7-356` |
| P9 | Medium | No `v0.1.0` GitHub release tag yet; auto-release workflow exists but hasn't fired | `pyproject.toml:3`; `client/pubspec.yaml:4`; `release.yml:5-19` |
| P10 | Medium | Per-service tokens documented but not enforced; configuration theatre | `DEPLOYMENT.md:113-131` |
| P11 | Low | `omniscribe-migrate-lexicon` script ships despite CLI deprecation note (consistent but confusing) | `pyproject.toml:134-136`; `AGENTS.md:108` |
| P12 | Low | `outstanding-work.md` is a closing log, not a roadmap; forward-looking items buried at §5–6 | `outstanding-work.md:13, 22, 35, 46, 106-113` |
| P13 | Low | No published PGP key for security contact | `SECURITY.md:18` |
| P14 | Low | `compose.yaml` configures `OMNISCRIBE_MAX_UPLOAD_MB=10240` while middleware enforcement is partly true / partly deferred | `compose.yaml:74`; `SECURITY.md:73` |
| P15 | Info | No telemetry, no analytics, no phone-home — genuine privacy posture | `SECURITY.md:142-143` |
| P16 | Info | Author contact is single point of contact — bus-factor risk | `pyproject.toml:9`; `SECURITY.md:11` |

**Feature surface map.**

| Feature | In code? | Documented? | Working? | Notes |
|---|---|---|---|---|
| PDF → searchable sandwich PDF | Yes | `README.md:12`; `ARCHITECTURE.md:12-17` | Yes | Hybrid + grounded engines |
| Image inputs (JPEG/PNG/BMP/WebP/TIFF/AVIF) | Yes | `README.md:11` | Yes | Pillow ≥11.3 for native AVIF |
| Hybrid OCR (Surya + VLM + DP) | Yes | `README.md:13`; `ARCHITECTURE.md:13` | Yes | Default engine |
| Grounded (bbox-native VLM) | Yes | `README.md:14` | Yes | `core/grounded/` |
| Async translation (LangGraph, harness JobQueue) | Yes | `README.md:119-126`; `ARCHITECTURE.md:64-71` | Yes | Single in-process worker (Celery retired) |
| NLLB-200 offline translation | Yes | `pyproject.toml:103-106` | Unverified (extra) | `nllb` extra not in main `uv sync` |
| Glossary import (TBX/CSV/JSON/URL/SQL/git/TMX/XLIFF) | Yes | `ARCHITECTURE.md:78-86, 154-156` | Yes | 9 routes; >5000 entries async |
| Lexicon RAG (LanceDB) | Yes | `README.md:34-41` | Yes with `lexicon` extra; otherwise 503 | Windows AV false positive |
| Speech-to-text (`/api/transcribe`) | Yes | `README.md:17`; `ARCHITECTURE.md:72-77` | Yes (sync only) | `transcription` extra for `faster-whisper` |
| Document intelligence processors (6) | Yes | `README.md:79-89` | Yes | Reading order, quality, structure, section, layout, table |
| Structured extraction (invoice/resume/academic/table) | Yes | `README.md:113` | Yes | Templates re-homed from pre-harness API |
| Export (JSON/MD/text/DOCX/HTML/Docling/MinerU) | Yes | `README.md:113` | Yes | Token-bound artifacts |
| OCR Quality Trust Layer | Yes | `README.md:90-111` | Off by default, opt-in | All 4 sub-modules fail open |
| In-browser workstation | No | `README.md:7` ("deprecated") | N/A | Replaced by Flutter client |
| `omniscribe` CLI script | No | `README.md:7`; `AGENTS.md:108` | N/A | Intentionally removed |
| ASGI bearer auth / rate-limit / upload-size | Code wired | `SECURITY.md:62-67` (says deferred) | **Yes** | Wave 14 closed — see P1 |
| Redis state backend | Code scaffold | `outstanding-work.md:111` | No (crashes at apply) | Deferred |
| Model pre-flight API route | Internal only | `outstanding-work.md:112` | Partial | `ensure_model_loaded()` exists, no public route |

**Onboarding friction (ranked).**

1. VLM endpoint not bundled (P4) — biggest blocker; the user must install LM Studio, download a model, start a separate service, *then* OmniScribe works.
2. Install footprint surprises (P3) — `surya-ocr` + `torch` + `opencv` on a fresh venv, plus possible Windows AV false positive on `arrow_substrait.dll`.
3. Flutter client README is the default stub (P2) — no install, no "how to connect to the server."
4. No `CONTRIBUTING.md` / issue templates (P6) — anyone who hits a wall has no guided way to report it.
5. In-memory state default loses history on restart (P5) — silently.
6. Auth documentation vs. reality mismatch (P1) — operators waste time configuring tokens they think aren't checked.

### 4.5 End user

**Verdict.** **3 / 10** first-impression rating. The product is real and working but the front door reads like an internal engineering changelog. A non-developer won't get past the first paragraph of `docs/README.md`.

**Strengths.**

- **Real, local-first product** — privacy stated in `SECURITY.md:131-143`: "We do not collect telemetry. We do not embed analytics. We do not phone home."
- **MIT license + clear author + open issues** — `pyproject.toml:8-10, 138-141`.
- **Format support is broad and honest** — `docs/README.md:11` lists PDFs + JPEG/PNG/BMP/WebP/TIFF/AVIF.
- **Sensible defaults on the protocol level** — Flutter client hard-codes `http://127.0.0.1:8000` (`client/lib/data/providers/repository_providers.dart:18`).
- **`make doctor` is genuinely useful** — `Makefile:74-75` runs real health checks.

**Findings.**

| # | Severity | Title | Evidence |
|---|---|---|---|
| U1 | Critical | No top-level `README.md` (only `docs/README.md`, referenced by `pyproject.toml:5`); GitHub renders `docs/README.md` but the repo root is bare | `pyproject.toml:5`; (no root `README.md`) |
| U2 | Critical | User must install a separate VLM server; README has no link to LM Studio, no model recommendation, no RAM/VRAM guidance | `docs/README.md:59` |
| U3 | Critical | No end-user install path at all; "no `omniscribe` script entry is shipped" (`README.md:7`) and "the user-facing CLI script has been deprecated" (`README.md:77`); only path is 12+ steps | `docs/README.md:7, 77` |
| U4 | Critical | The "web UI" referenced in `DEPLOYMENT.md` is a 5-line placeholder page; user following docs gets a dead end in the browser | `DEPLOYMENT.md:11-12` vs `src/omniscribe/static/index.html:24-29` |
| U5 | High | `client/README.md` is unmodified Flutter starter | `client/README.md:1-15` |
| U6 | High | No screenshots, GIFs, or demo anywhere (glob for `screenshots*`, `*.gif`, `*.mp4` returned zero matches in tree) | (verified by glob) |
| U7 | High | No FAQ, no `TROUBLESHOOTING.md`; only three bullets in `DEPLOYMENT.md:170-176` | `DEPLOYMENT.md:170-176` |
| U8 | High | No performance expectations set anywhere (200-page scanned PDF, no GPU, no time estimate) | (no benchmark section) |
| U9 | Medium | First paragraph uses three pieces of internal jargon in one sentence | `docs/README.md:7` |
| U10 | Medium | `docker compose up` requires `${REDIS_PASSWORD:?…}` to be set in `.env`; `REDIS_PASSWORD` is in `.env.example` (verified) so this works, but the persona's "nothing works" experience still applies (see U2) | `compose.yaml:65, 58-61`; `.env.example:194` |
| U11 | Medium | No "supported platforms" list | (no tested-platforms section) |
| U12 | Medium | `examples/` framed as developer fixtures, not user samples; no in-UI "try with sample" affordance | `examples/README.md:1-2` |
| U13 | Low | Trust signals (MIT, author, security policy) are good but buried because no top-level README | `LICENSE`; `pyproject.toml:8-10`; `docs/SECURITY.md` |
| U14 | Low | CHANGELOG is dev-focused; 1300+ lines of code-architecture decisions | `docs/CHANGELOG.md:1-200+` |

**"I got an error" recovery test — No.** A user who hits any common failure (Defender quarantining `arrow_substrait.dll`, LM Studio not on port 1234, `uv` not installed, Flutter not on PATH, placeholder auth token rejection, Compose refused to start because `.env` is missing) has no entry point in the user-facing docs. The information is scattered: Defender info in `SECURITY.md:147-182`, auth tokens in `DEPLOYMENT.md:103-112`, Compose env in `compose.yaml:58-61`.

**Note on the agent's claim that `.env.example` doesn't exist.** Verification: the file exists at `D:\OmniScribe\.env.example` (9,108 bytes, line 194 = `REDIS_PASSWORD=omniscribe-secure-dev-password`). The agent's finding U10 is therefore accurate in spirit (the persona experience is still "nothing works") but inaccurate in the specific claim that the file is missing. U2 / U3 / U4 are unaffected.

---

## 5. Consolidated action plan

Prioritized for impact-to-effort, with the convergent findings up top. Estimates are conservative.

### 5.1 Do first (≤ 1 day each; convergent signal)

| # | Action | Source | Effort |
|---|---|---|---|
| A1 | Empty the active `REDIS_PASSWORD` in `.env.example` (or rename to `_PLACEHOLDER_SET_ME`) | S1 / C5 | 5 min |
| A2 | Reconcile `SECURITY.md` and `outstanding-work.md` against `server.py:184-202` — remove "deferred" / "scaffolding" framing; note loopback/placeholder deny in features | S2 / C1 | half a day |
| A3 | Move `docs/README.md` to `README.md` (or symlink) and rewrite `client/README.md` with install + connect flow | U1, U5 / C4 | 1 day |
| A4 | Add a `Before you start` section to the README: LM Studio link, recommended first model, RAM/VRAM table | U2 / C2 | half a day |
| A5 | Replace the first paragraph of `docs/README.md:7` with a one-line hook ("turns scans into searchable PDFs, on your machine, no internet") | U9 / C2 | 10 min |
| A6 | Reference `make doctor` in the install section | U2 / C6 | 5 min |
| A7 | Fix `Makefile:78` comment (real path is `tests/routers/test_openapi_schema.py`) and rewrite the `live_llm` references in `test.yml:8` and `nightly.yml:12` | Q1, Q2 | 30 min |
| A8 | Make SQLite the default state backend (one-line change to `omniscribe-server` default + `compose.yaml`); or log a loud warning when in-memory + non-loopback | P5 / C3 | 1 day |

### 5.2 Do next (1–3 days each; high-impact, but not as urgent)

| # | Action | Source | Effort |
|---|---|---|---|
| B1 | Add a `TROUBLESHOOTING.md` (or `USER_GUIDE.md`) with the top 10 first-run errors and fixes; cross-link from `make doctor` | U7, U10 / C7 | 1–2 days |
| B2 | Add `CONTRIBUTING.md`, `.github/ISSUE_TEMPLATE/bug_report.md`, `feature_request.md` | P6 / C7 | 1 day |
| B3 | Add the "Web UI" choice: either remove the browser instruction from `DEPLOYMENT.md` or make the browser a real UI | U4 | 1–3 days (depends on direction) |
| B4 | Reduce `MAX_UPLOAD_MB` default from 10 GB to 1024 MB; require operators to raise it | S4 | 30 min |
| B5 | Narrow `QUERY_TOKEN_PATHS` to exact SSE/event-stream routes; document the SSE-only rationale | S5 | 1 day |
| B6 | Replace the 10+ magic-number sleeps in tests with explicit synchronization (`asyncio.wait_for` + condition) | Q3 | 1–2 days |
| B7 | Refactor `plugins/ocr/service.py` (890 LOC) into `services/{error_sanitization,content_sniff,config_seeding}.py` | D6 | 2 days |
| B8 | Drop `HybridEngine` re-injection (decorative); move to constructor-arg pattern | D3 | 1 day |
| B9 | Single-call `load_dotenv()` at `main()`; remove the `from dotenv import load_dotenv` from `core/ocr/processor.py` | D5 | 1 day |
| B10 | Fix `JobStatusResponse.started_at` (always None) — either persist or delete the field | D1 | half a day |
| B11 | Fix `InMemoryJobQueue._run` worker-level `except Exception` swallowing | D2 | 1 day |
| B12 | Override `ALLOW_SSRF_LOCAL=false` in `compose.yaml`; add a one-line note above the variable in `.env.example` | S3 | 10 min |

### 5.3 Do when planning allows (≥ 1 week each; long-tail)

| # | Action | Source | Effort |
|---|---|---|---|
| C1 | Ship a desktop binary (PyInstaller bundle of the FastAPI server, or a Flutter build that embeds the server) | U3 / C2 | 2–6 weeks |
| C2 | Add screenshots and a 10-second GIF of "drop PDF → searchable PDF" | U6 | 1 day |
| C3 | Add property-based tests for `utils/json_parse`, `utils/prompt_safety`, `core/pdf/page_range`, `core/recall/whitespace`, `core/ocr/filters` | Q4 | 1 week |
| C4 | Add direct test for `core/translate/workflow.py` (LangGraph driver) | Q5 | 3 days |
| C5 | Add mutation testing (`mutmut` for pure utilities) | Q7 | 1 week |
| C6 | Add JUnit XML upload + `pytest-rerunfailures` for flake detection | Q-Note 1–2 | 1 day |
| C7 | Re-home `examples/` into `tests/fixtures/pdfs/` and provide an in-UI "try with sample" affordance | Q6, U12 | 1 day |
| C8 | Adopt "User-visible changes" subsection in `CHANGELOG.md`; move refactor noise under `## Maintenance` | P8 | 1 day |
| C9 | Add a "Performance" section to the README with ballpark numbers and model recommendations per hardware tier | U8 | 1 day |
| C10 | Move `SECURITY.md` install and Flutter run instructions to a top-level `USER_GUIDE.md` (or first-time-run section of `README.md`) | C1 (C1's doc half) | 1 day |

### 5.4 Backlog (small, can be done any time)

- D7 (promote private OCR service state to public properties), D8 (single error envelope), D9 (mypy strictness for plugins), D10 (drop legacy CORS aliases), D11 (`extract_json` single-pass), D12 (hoist `_DEFAULTS`), D13 (split `is_transient_error` ValueError branch), D14 (single `DenseMode` parse), D15 (delete dead `trust_images_dict` param), D16 (Dockerfile vs classifiers consistency), D17 (verify `transformers>=5.15.1` resolves), D18 (drop `--no-fix` from `make lint`), D19 (fix `is_transient_error` default), D20 (`sys.path` scoping in conftest).
- S6 (`/api/progress/cancel` loopback gating), S7 (rate limiter per-worker documentation), S8 (constant-length token mask), S9 (StaticFiles comment), S10 (exact-key JSON redaction), S11 (Dockerfile `127.0.0.1` bind), S12 (git credential netrc), S13 (CORS `*` + credentials unit test), S14 (WS origin note), S15 (job-list dev-bind note).
- Q8 (named under-tested modules wave), Q9 (calibration seed control test), Q10 (merge `tests/ops/`), Q11 (chaos tests), Q12 (Flutter `integration_test/`), Q13 (Flutter widget test balance).
- P7 (AGPL badge near top), P9 (cut v0.1.0 tag), P10 (cross-link per-service tokens to deferred-middleware note), P11 (CLI script narrative consistency), P12 (roadmap header in `outstanding-work.md`), P13 (PGP key for security contact), P14 (compose upload size alignment).
- U11 (supported platforms list), U13 (trust signals cross-link), U14 (CHANGELOG user-facing summary).

---

## 6. Notable strengths (across all lenses)

These were consistently called out as good practice. Worth preserving during refactor.

- **Cordis-style plugin harness with Protocol-keyed services and LIFO effect disposal** — `src/omniscribe/harness/` is the standout design choice; the rollback-on-failure in `context.py:204-221` is correct.
- **Fail-open contract is consistent** across recall boosters and the trust orchestrator — per-page exceptions don't break the pipeline.
- **`CircuitBreakerRegistry` keyed by `(api_base, model)`** — clean cross-request sharing of breaker state without a heavyweight abstraction.
- **Constant-time token comparison** at every check site (`hmac.compare_digest` / `secrets.compare_digest`).
- **Upload streaming + per-job tempdir** — memory bounded by concurrent on-disk count, not queue depth × upload size.
- **Startup guard** refuses non-loopback binds without a real auth token and blocks placeholder tokens on LAN binds.
- **SSRF guard with DNS-pin and IP-blocklist** — `_PinnedIPTransport` defeats DNS-rebinding in the glossary `http_fetch` path.
- **Magic-byte sniffing before tempdir write** — 415 returned before disk.
- **Subprocess calls with list args, no `shell=True`**; `git_repo._validate_path` rejects `..` and leading `/`; ref regex bounds argument injection.
- **No `eval` / `exec` / `yaml.load` / `pickle` / `marshal`** anywhere in `src/`.
- **`defusedxml` as a base dep** for XLIFF/TBX/TMX.
- **Container hardening** — non-root `app` uid 1001 no-shell, `tini` PID 1, pinned base digests, `no-new-privileges`, `cap_drop: ALL`, loopback-only publish.
- **AGPL disclosure for PyMuPDF** — called out in three places (README, `pyproject.toml`, `THIRD_PARTY_LICENSES.md`), with a clean default (`pypdfium2`) for closed-source forks. Unusually honest.
- **Three-profile threat model** documented in `SECURITY.md`.
- **Extras are honestly scoped** — `lexicon` replaced `memory`; `async-translation` is intentionally light; `trocr`/`nllb`/`quality` are opt-in.
- **CC0-licensed example PDFs** in the repo — no first-run download.
- **Layered boot fixture chain** in `tests/conftest.py:204-238` — `cordis_env` → `harness_ctx` / `api_client` yields deterministic offline integration tests.
- **OpenAPI snapshot drift test** catches accidental route-shape changes.
- **Hypothesis invariants on the trust-scorer** as a starting point for property-based testing.
- **CI is well-structured** — Python 3.11/3.13 matrix on ubuntu + 3.11 on Windows + Flutter; lint + format + mypy + pytest fast tier with 80% gate + pip-audit + Trivy container scan + CycloneDX SBOM; separate nightly slow tier; SHA-pinned action refs.
- **`outstanding-work.md` is unusually disciplined** — every closed item has a "closed in Wave N" outcome; deferred items individually tracked.
- **No telemetry, no analytics, no phone-home** — genuine privacy posture.

---

## 7. Out of scope / caveats

- **Flutter client security** (`client/lib/`) — Dart code spot-checked, not audited. Riverpod 2.x state, smart-preset selector, `ServerHealthNotifier` mentioned in `ARCHITECTURE.md`. Recommend a dedicated Dart audit.
- **Reverse-proxy configs (Caddy/nginx)** — deployment responsibility per `SECURITY.md:125-127`.
- **CVE database scan against `uv.lock`** — not run (read-only audit). `pip-audit` and `trivy` already wired in CI.
- **TLS cipher/profile strength** of operator-chosen proxy.
- **Runtime behaviour of the in-process single-worker `JobQueue` under load** (DoS via job floods).
- **`python -m` and `cli/migrate_lexicon.py` entry points** — referenced, not opened.
- **Live LLM end-to-end validation** — out by design; no CI endpoint.
- **Non-English / RTL / CJK PDF ground truth** — only English examples on disk.
- **Cross-platform PDF edge cases** — corrupt PDFs, password-protected, 1000+ page documents.
- **Browser-automation testing of the Flutter web build** — no `integration_test/`.
- **Single-agent claims** that I could not independently verify are marked "unverified" inline; the most material correction was the End-user lens's claim that `.env.example` doesn't exist — it does (9,108 bytes, line 194 = `REDIS_PASSWORD=omniscribe-secure-dev-password`). That finding's spirit (out-of-the-box does nothing useful) is unaffected; the specific assertion is corrected.

---

## 8. Appendix — agent dispatch summary

For reproducibility, the five parallel agent dispatches used the following fixed briefing template per lens (paraphrased; full prompts in the task system):

- **Common ground rules:** read-only; do not modify files; do not run code; every claim must have a `path:line` reference; mark anything unverified; do not print values of `.env` or any secret; focus on substantive findings; keep under the per-lens word budget.
- **Lens-specific audit axis:**
  - **Dev:** code organization & modularity; API design; type safety & error handling; concurrency & async; patterns & idioms; tech debt; build & DX; cross-platform packaging; dependency hygiene.
  - **Security:** secrets; auth & authz; input validation & injection; file handling; external network exposure; dependency CVEs & supply chain; plugin/dynamic load; cryptography; logging hygiene; container & deploy; headers & web hardening; error responses.
  - **QA:** coverage shape; test quality; test types balance; reproducibility; edge cases; CI; manual test affordances; bug-likely hotspots; client-side QA; test data & fixtures.
  - **PM:** product clarity; user journey; distribution & packaging; documentation completeness; licensing posture; roadmap visibility; feature surface; cost story; support & community; telemetry; operational readiness.
  - **End user:** first 60 seconds; install story; "just run it"; error experience; documentation accessibility; output & feedback; file format support; performance perception; help & escape hatches; trust signals; privacy story; platform support.
- **Deliverable format:** markdown report with summary, strengths, severity-sorted findings (each with title, what, where, impact/why-it-matters, suggested fix), and an explicit "out of scope" section.
- **Where to look (in priority order):** docs first (stated intent), then `pyproject.toml` / `compose.yaml` / `Dockerfile` / `Makefile` / `.pre-commit-config.yaml`, then the relevant `src/omniscribe/` subpackage, then `tests/`, then `examples/` and `scripts/`.

---

*End of report. Total length: ~6,000 words. Five perspective agents, fully read-only, zero file modifications.*
