# OmniScribe — Remediation Plan

**Date:** 2026-09-04
**Author:** Synthesized from the [Five-Lens Codebase Audit](./2026-09-04-five-lens-audit.md) of the same date.
**Mode:** Specification only — no code is being written yet. Each phase is a work order that can be picked up independently.
**Goal:** Bring OmniScribe from "beta-true, shippable only to power users" to "beta-stable, shippable to a general technical audience" without regressing on the existing Wave 14 cleanup momentum.

---

## 0. Roll-up

**Six phases, four-week horizon, three owners.** Each phase has a single owner-sized acceptance bar so a reviewer can sign off without reading the whole plan.

| Phase | Theme | Effort | Owner | Hard dependency |
|---|---|---|---|---|
| **0. Stop the bleeding** | One directly exploitable finding + three trivial docs fixes | ~1 hour | Security | — |
| **1. Truth in documentation** | Reconcile docs with shipped code; fix the "deferred" framing | 1–1.5 days | Docs | — |
| **2. First-run affordances** | Make the install journey findable; kill the silent state-loss default | 2 days | DX / Backend | Phase 1 (some README edits) |
| **3. Quick-win code cleanups** | Cheap high-leverage code changes | 1 week | Backend | — |
| **4. End-user install path** | Ship a working install for a non-developer | 2–6 weeks | Desktop / DevX | Phase 2 |
| **5. Test hardening** | Property-based, mutation, flake detection, fixture re-homing | 1 week | QA | — |
| **6. Long-tail** | Style nits, low-severity hardening, back-burner refactors | ongoing | any | — |

**Total committed work: 4–8 weeks for phases 0–3 and 5 (the "convergent-signal" path).** Phase 4 (desktop binary) is a separate workstream that needs scoping before committing to a date.

**Sequencing rationale.** Phases 0, 1, 2, 3, 5 are independent and can run in parallel. Phase 4 depends on Phase 2's install docs being final. Phase 6 is a parking lot.

---

## 1. Phase 0 — Stop the bleeding (≈ 1 hour, owner: Security)

**Goal.** Close the only directly exploitable finding in the audit and fix two trivial foot-guns that take seconds each.

**Source.** Audit findings S1, S3, A1, A12.

### 1.1 `.env.example` ships an active dev `REDIS_PASSWORD`

- **Problem.** `.env.example:194` = `REDIS_PASSWORD=omniscribe-secure-dev-password`. The `${REDIS_PASSWORD:?…}` substitutions in `compose.yaml:65,129,140` only fire when the variable is *missing*, so the documented `cp .env.example .env && docker compose up` path boots Redis on `127.0.0.1:6379` with a publicly documented password. Any other container on the host's default bridge (or a local process scraping the README) can issue `FLUSHALL`.
- **Scope.** One file: `.env.example`.
- **Concrete steps.**
  1. Change `.env.example:194` to `REDIS_PASSWORD=` (empty value, no space).
  2. Add a comment one line above: `# REQUIRED when running `docker compose up`. Generate with:  tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32`.
  3. Verify with: `grep -n REDIS_PASSWORD .env.example` — must show empty value.
- **Acceptance criteria.**
  - `cp .env.example .env && docker compose config` (after the change, with empty password) prints a clear error pointing at `REDIS_PASSWORD`.
  - No other place in `.env.example` references the dev password string.
- **Risks.** Trivial. If a contributor has a local `.env` that copies the old example, nothing changes for them — but no new copies of the dev password are produced.
- **Effort.** 5 minutes.

### 1.2 `ALLOW_SSRF_LOCAL` defaults to `true` in `.env.example` (footgun)

- **Problem.** `.env.example:66` sets `ALLOW_SSRF_LOCAL: "true"` but the code default at `src/omniscribe/config.py:206` is `false`. Operators copying the example get SSRF-local enabled even though the safer default is off.
- **Scope.** Two files: `.env.example`, `compose.yaml`.
- **Concrete steps.**
  1. Change `.env.example:66` to `ALLOW_SSRF_LOCAL: "false"`.
  2. Add the same override in `compose.yaml` under `services.api.environment` so `docker compose up` doesn't depend on `.env` for the safe default.
  3. Add a one-line comment above the variable: `# Only enable for local VLM endpoints (e.g. LM Studio at 127.0.0.1:1234). Keep false in production.`
- **Acceptance criteria.** `docker compose config | grep -i allow_ssrf` shows `false` even with an empty `.env`.
- **Risks.** None. Existing local-only installs with the var explicitly set to `true` are unaffected.
- **Effort.** 10 minutes.

### 1.3 Empty `REDIS_PASSWORD` will not break `docker compose up` because the env-default doc path is `cp .env.example .env`

- **Problem.** Phase 0.1 makes the password empty; an operator who runs `docker compose up` without setting a password gets a hard error. This is the desired behavior, but the failure should be friendly.
- **Scope.** `compose.yaml` only.
- **Concrete steps.**
  1. After the `:?` substitutions at `compose.yaml:65,129,140`, the error message is already a shell-style "variable empty or unset" message. Replace with a static fallback that names the variable and tells the operator to set it: this is harder than it looks because compose `:?` does not support custom messages. Workaround: leave the `:?` substitution; add a one-liner to `docker-compose-up` instructions in `DEPLOYMENT.md` (Phase 1 work) explaining the message.
  2. **Decision for the spec author:** leave as-is, document in Phase 1. Don't try to customize the compose error.
- **Acceptance criteria.** A fresh `cp .env.example .env && docker compose up` fails fast with a shell error that mentions `REDIS_PASSWORD`. The error is explained in `DEPLOYMENT.md`.
- **Effort.** 0 minutes here; covered in Phase 1.

### 1.4 Phase 0 sign-off

- Owner: Security lead.
- PR title: `[security] rotate dev REDIS_PASSWORD placeholder, force real choice`.
- Reviewer: same person who last reviewed `SECURITY.md`.
- Time to merge: ≤ 2 hours from PR open.

---

## 2. Phase 1 — Truth in documentation (1–1.5 days, owner: Docs)

**Goal.** Reconcile `SECURITY.md`, `outstanding-work.md`, `DEPLOYMENT.md`, and the READMEs with the code that actually shipped in Waves 11–14. This is the single largest source of risk identified by the audit (convergent finding C1).

**Source.** Audit findings S2, P1, P2, P7, P10, P12, U1, U5, U9, A2, A3, A4, A5, A6, A7, B1 (docs half), C1 (docs half).

### 2.1 Reconcile `SECURITY.md` against the wired middleware triad

- **Problem.** `docs/SECURITY.md:62-78` describes bearer auth, rate limiting, and `MaxUploadSizeMiddleware` as "currently deferred capabilities … scaffolding for the forthcoming middleware plugins." In fact all three are wired unconditionally at `src/omniscribe/server.py:184-202`, and the loopback/placeholder deny at `server.py:375-395` is live.
- **Scope.** `docs/SECURITY.md`.
- **Concrete steps.**
  1. Re-read `docs/SECURITY.md` end-to-end. For each paragraph that references a deferred or "future" middleware, cross-check against `src/omniscribe/server.py:184-202` and `src/omniscribe/middleware/{auth,rate_limit,upload_limit}.py`.
  2. Rewrite the "Deferred capabilities" section (lines 62-78) to describe the **live** middleware triad, with: what each one does, where it's wired, what env-var activates it, and what happens when it's mis-configured (e.g. placeholder token on non-loopback bind = `SystemExit`).
  3. Add a "Profiles" table that cross-references `DEPLOYMENT.md:34-58`'s three deployment profiles with the actual middleware state (e.g. Profile 1 / loopback: no token required, all middlewares active, no enforcement effect; Profile 2 / LAN: token required, rate limit applied, upload cap applied; Profile 3 / public: same as Profile 2 plus reverse-proxy TLS).
  4. Update the "Hardening checklist" (lines 184-199) to remove items that are now done (placeholder-token denylist, upload size cap).
- **Acceptance criteria.**
  - No occurrence in `SECURITY.md` of "deferred", "scaffolding", "forthcoming", or "future" applied to bearer auth, rate limit, or upload cap.
  - The Profiles table matches what `DEPLOYMENT.md` says (cross-referenced).
  - The Hardening checklist has a "Done — automatic" column or marker for items that are now default.
- **Risks.** Low. Doc-only.
- **Effort.** Half a day.

### 2.2 Reconcile `outstanding-work.md` against Wave 14's actual closure

- **Problem.** `docs/outstanding-work.md:110-111` lists the ASGI Middleware Suite as a "Deferred Architectural Capability" even though the suite shipped in Wave 14 (`outstanding-work.md:63`). Every other section already says "All items in this section have been resolved," but §6 does not.
- **Scope.** `docs/outstanding-work.md`.
- **Concrete steps.**
  1. Move the ASGI Middleware Suite entry from §6 to §1 with a `Closed in Waves 11, 13, 14` note and a pointer to the audit section for evidence.
  2. Same treatment for the Redis state backend (still deferred) and Model pre-flight route (still deferred) — keep those in §6 but verify the wording matches `state_backend.py`'s current state.
  3. Add a `## Current focus` header at the top with a 3-bullet list of what's actively in flight (Phase 4 desktop binary, Phase 5 test hardening, etc.). This addresses P12 from the PM lens.
- **Acceptance criteria.** No "All items in this section have been resolved" sentence in §6. Every line in §6 has a clear "what is needed to unblock" sentence.
- **Effort.** 30 minutes.

### 2.3 Move `docs/README.md` to `README.md`

- **Problem.** The repo root has no `README.md`. `pyproject.toml:5` sets `readme = "docs/README.md"`, so GitHub does render `docs/README.md` on the landing page — but the repo root is bare, the `docs/` folder is hidden by default, and `git clone` users see no top-level entry. This is convergent finding C4.
- **Scope.** File system + cross-references.
- **Concrete steps.**
  1. `git mv docs/README.md README.md`.
  2. Update all internal `docs/README.md` links to `README.md` (search the tree with `rg 'docs/README\.md' .`).
  3. Update `pyproject.toml:5` to `readme = "README.md"`.
  4. Verify GitHub renders the file on the landing page after merge (a one-line `gh repo view --json readme` or visual check).
- **Acceptance criteria.**
  - `D:\OmniScribe\README.md` exists.
  - `rg 'docs/README\.md' .` returns no hits in `*.md` or `*.pyproject.toml`.
  - `pyproject.toml:5` says `readme = "README.md"`.
  - GitHub landing page shows the README contents.
- **Risks.** If any release artifact references `docs/README.md` by path, it will need to be updated too. Check `release.yml`, `Dockerfile` (no — copies file), and any docs tooling.
- **Effort.** 1 hour (including link-updates).

### 2.4 Rewrite `client/README.md`

- **Problem.** `client/README.md:1-3` is the unmodified Flutter starter. Any Flutter user lands here and learns nothing about OmniScribe. (Convergent C4.)
- **Scope.** `client/README.md` only.
- **Concrete steps.**
  1. Replace the file with a 1-page end-user guide covering: (1) how to install Flutter SDK, (2) how to run the OmniScribe backend (`uv run omniscribe-server --port 8000` per the main README), (3) `cd client && flutter pub get && flutter run -d <device>`, (4) how to point the client at the backend, (5) link back to the main README.
  2. Add a "Troubleshooting" section cross-linking to the new `TROUBLESHOOTING.md` (Phase 2.1).
  3. Add a single screenshot of the Workstation screen (Phase 4.2 will provide it; for now, a placeholder image is fine).
- **Acceptance criteria.** A Flutter-first-time user can install and run the client without opening a single other file in the repo.
- **Risks.** None. Doc-only.
- **Effort.** 2 hours.

### 2.5 Rewrite the README lede

- **Problem.** `README.md:7` (formerly `docs/README.md:7`) opens with three pieces of internal jargon in one sentence: "the supported product workflow is the Flutter Client + FastAPI API," "advanced document intelligence is delivered through the Flutter client," "the `OCRPipeline` class is still importable for in-process programmatic use." This is the audit's first-impression killer (U9).
- **Scope.** First paragraph of `README.md`.
- **Concrete steps.**
  1. Replace lines 7 of the new `README.md` with: *"OmniScribe turns scanned PDFs and photos into searchable, selectable PDFs. Everything runs on your machine — no cloud OCR, no signup, no API keys. The local VLM is yours to choose (LM Studio, Ollama, or any OpenAI-compatible server)."*
  2. Move the original paragraph (deprecation notes, `OCRPipeline` importability) to a "For developers" section at the bottom.
- **Acceptance criteria.** A non-developer can read the first paragraph and understand (a) what the product does, (b) what they need to bring (a local VLM), (c) what they don't need to bring (no signup, no internet).
- **Effort.** 10 minutes.

### 2.6 Add a "Before you start" section

- **Problem.** The audit (U2) found that the README has no link to LM Studio, no model recommendation, no RAM/VRAM table, and no acknowledgment that the operator must download and start a VLM before OmniScribe does anything. The persona lands at the README, runs the install, sees a working web UI, and discovers the OCR returns nothing because the VLM is missing.
- **Scope.** New top-level section in `README.md`.
- **Concrete steps.**
  1. Add a `## Before you start` section immediately after the lede.
  2. Contents:
     - "OmniScribe needs a local OpenAI-compatible vision model server. The default is **LM Studio** ([lmstudio.ai](https://lmstudio.ai))."
     - Recommended models table:

       | Hardware | Recommended model | Approx VRAM |
       |---|---|---|
       | 8 GB GPU, no CPU fallback | Qwen2.5-VL-7B-Instruct (Q4) | 6 GB |
       | 16 GB GPU | Qwen2.5-VL-7B-Instruct (Q8) | 9 GB |
       | 32 GB GPU | Qwen2.5-VL-72B-Instruct (Q4) | 24 GB |
       | CPU only (slow) | Qwen2.5-VL-3B-Instruct | 4 GB RAM |

     - One-line startup: "Start LM Studio's local server on port 1234 (Developer tab → Start Server)."
  3. Cross-link from the install section.
- **Acceptance criteria.** A first-time reader knows, before running `uv sync`, that they need a VLM and what to install.
- **Effort.** 1 hour (mostly copy-paste from LM Studio's docs).

### 2.7 Reference `make doctor` from the install section

- **Problem.** `Makefile:74-75` ships a `make doctor` target that runs a real health check (Python version, `uv`, Redis reachability, VLM endpoint reachable). It is the single most useful tool for a stuck user, and the README doesn't mention it. (Convergent C6.)
- **Scope.** `README.md` install section.
- **Concrete steps.**
  1. Add a single line to the install section: *"If anything goes wrong, run `make doctor` to see what's missing."*
  2. Add a "Stuck?" section to `TROUBLESHOOTING.md` (Phase 2.1) that says the same thing in bold.
- **Acceptance criteria.** A reader who hits a first-run error thinks "I should run `make doctor`" within 10 seconds.
- **Effort.** 5 minutes.

### 2.8 Fix CI / Makefile doc drifts

- **Problem.** Two concrete doc drifts identified by the QA lens:
  - `Makefile:78` references a non-existent `tests/api/test_frontend_openapi_contract.py` (the real test is at `tests/routers/test_openapi_schema.py`).
  - `test.yml:8` and `nightly.yml:12` describe skipping `-m live_llm`, but the marker was removed per `CHANGELOG.md:193-199`.
- **Scope.** `Makefile`, `.github/workflows/test.yml`, `.github/workflows/nightly.yml`.
- **Concrete steps.**
  1. Edit `Makefile:78` to reference the real path: `tests/routers/test_openapi_schema.py`.
  2. Edit `.github/workflows/test.yml:8` to remove the "skip `-m live_llm`" instruction; replace with: "No live LLM is required for CI. Local LLM tests must run outside CI."
  3. Same edit for `.github/workflows/nightly.yml:12`.
- **Acceptance criteria.** A contributor who reads the CI workflow comments gets accurate information.
- **Effort.** 30 minutes.

### 2.9 Phase 1 sign-off

- Owner: Docs lead (or whoever last edited `SECURITY.md`).
- PR title: `[docs] reconcile SECURITY.md / outstanding-work.md / READMEs with Wave 11-14`.
- Reviewer: At least one engineer from each of: backend, security, frontend.
- Time to merge: ≤ 2 days from PR open.
- Roll-back: trivial. Doc-only.

---

## 3. Phase 2 — First-run affordances (2 days, owner: DX / Backend)

**Goal.** A user who hits any first-run error has a place to go. The in-memory state default stops being silent.

**Source.** Audit findings P5, P6, U7, U10, U11, U12, A8, B1, B2, B11 (state half).

### 3.1 Add `docs/TROUBLESHOOTING.md`

- **Problem.** The audit found no `TROUBLESHOOTING.md` and no `USER_GUIDE.md`. The only troubleshooting copy is three bullets in `DEPLOYMENT.md:170-176`. The most-searched-for problems — Windows Defender quarantining `arrow_substrait.dll`, LM Studio not on port 1234, `uv` not installed, Flutter not on PATH, placeholder auth token rejection, Compose refused to start — are scattered across the repo with no central entry. (Convergent C7.)
- **Scope.** New file: `docs/TROUBLESHOOTING.md`. Cross-references from `README.md` and `make doctor` output.
- **Concrete steps.**
  1. Create `docs/TROUBLESHOOTING.md` with the following sections (each a 5–10 line answer + a link to the source-of-truth doc):
     - **"OCR returns nothing"** — usually the VLM is not on `127.0.0.1:1234`; verify with `make doctor`; start LM Studio.
     - **"Server won't start: non-loopback bind requires a real auth token"** — set `OMNISCRIBE_AUTH_TOKEN` (32+ chars); placeholder values like `changeme` are rejected.
     - **"Defender quarantined `arrow_substrait.dll`"** — LanceDB false positive; see `SECURITY.md:147-182`; restore from quarantine or add an exclusion.
     - **"Compose refuses to start: `REDIS_PASSWORD` … variable empty or unset"** — set a real password in `.env` (see Phase 0.1).
     - **"`uv` is not recognized"** — install `uv` per its one-liner at `astral.sh/uv`.
     - **"Flutter not on PATH"** — install Flutter SDK; add `<flutter-sdk>/bin` to PATH.
     - **"Placeholder auth token rejected on LAN bind"** — placeholder denylist is in `src/omniscribe/server.py:39-46`; pick a real 32+ char token.
     - **"Server boots, but `uv run omniscribe-server` exits immediately"** — usually a config error; run `uv run omniscribe-server --log-level debug`.
     - **"Async translation result is gone after restart"** — by default the in-memory state backend loses history; switch to SQLite (`OMNISCRIBE_STATE_BACKEND=sqlite`).
     - **"Open the browser, see a '5-line placeholder page'"** — the in-browser workstation was deprecated; the supported client is the Flutter app (see `client/README.md`).
  2. Cross-link from `README.md` install section (one line).
  3. Cross-link from `make doctor` (if it can print a "see TROUBLESHOOTING.md for fix" hint on failure — Phase 2.6).
  4. Cross-link from the new `USER_GUIDE.md` first-run section (if it exists).
- **Acceptance criteria.** Each common first-run error has a 1-paragraph answer that points at a fix and a deeper doc.
- **Risks.** None. Doc-only.
- **Effort.** 1 day.

### 3.2 Add `CONTRIBUTING.md`, issue templates, PR template

- **Problem.** No `CONTRIBUTING.md`, no `CODE_OF_CONDUCT.md`, no `.github/ISSUE_TEMPLATE/`, no PR template. Bug reports will be low-quality. The user profile memo notes the project is personal, not commercial — so multi-team affordances aren't needed, but a single-purpose CONTRIBUTING that points at `AGENTS.md` is. (PM finding P6.)
- **Scope.** Repo root + `.github/`.
- **Concrete steps.**
  1. Create `CONTRIBUTING.md` (1 page): "Read `AGENTS.md` first. Run `make check` before opening a PR. Open an issue if you're planning a non-trivial change."
  2. Create `CODE_OF_CONDUCT.md` (use the Contributor Covenant, 1 page).
  3. Create `.github/ISSUE_TEMPLATE/bug_report.md` (fields: what you did, what happened, what you expected, server logs, screenshots, OS + Python + Flutter version, model + endpoint).
  4. Create `.github/ISSUE_TEMPLATE/feature_request.md` (fields: problem, proposed solution, alternatives considered, who benefits).
  5. Create `.github/PULL_REQUEST_TEMPLATE.md` (fields: what, why, testing done, screenshots if UI, related issue).
- **Acceptance criteria.** A new contributor's first action is a guided one.
- **Effort.** 1 day (mostly template boilerplate).

### 3.3 Make SQLite the default state backend

- **Problem.** The in-memory state backend is the default and silently loses history on restart (`DEPLOYMENT.md:181-184`). The Redis backend crashes at plugin apply (`outstanding-work.md:111`). SQLite is ready and one env-var away. (Convergent C3.)
- **Scope.** `src/omniscribe/server.py`, `compose.yaml`, `docs/DEPLOYMENT.md`, `docs/SECURITY.md`.
- **Concrete steps.**
  1. Change the default in `src/omniscribe/config.py` (or wherever `OMNISCRIBE_STATE_BACKEND` defaults) from `memory` to `sqlite`.
  2. Add a `OMNISCRIBE_STATE_BACKEND=sqlite` to `compose.yaml` `services.api.environment` so the Compose path uses SQLite out of the box.
  3. Add a startup banner at `src/omniscribe/server.py:create_app()` that logs the state backend on boot. (Use `structured_logging`.)
  4. Update `DEPLOYMENT.md:181-184` to remove the "A restart loses in-memory history" footnote; replace with: "SQLite is the default. Set `OMNISCRIBE_STATE_BACKEND=memory` to use the in-memory backend (results lost on restart)."
  5. Add an entry to `TROUBLESHOOTING.md`: "I want a fresh state" → "Delete the SQLite file at `<omniscribe-data-dir>/state.sqlite`" (or document the path).
- **Acceptance criteria.**
  - A fresh `omniscribe-server` boot creates `<omniscribe-data-dir>/state.sqlite` automatically.
  - A restart preserves in-flight job state.
  - An operator who explicitly opts into in-memory gets a loud warning at boot: `"STATE BACKEND IS IN-MEMORY — RESTART WILL LOSE HISTORY"`.
- **Risks.**
  - Medium. State backend change is a behavior change. Need a CHANGELOG entry and a minor-version bump (or call it a bugfix in CHANGELOG).
  - Existing in-memory users will see SQLite take over; they need a one-line `OMNISCRIBE_STATE_BACKEND=memory` to keep current behavior.
- **Effort.** 1 day (most of it is the CHANGELOG + back-compat messaging).

### 3.4 Optional: make `make doctor` print remediation hints

- **Problem.** The audit praised `make doctor` but found it doesn't tell users *where* to look when something fails. This is an opportunistic improvement; do it in Phase 2 if there's time.
- **Scope.** `Makefile` only.
- **Concrete steps.**
  1. After each failed check in the `doctor` target, append a `→ see docs/TROUBLESHOOTING.md#<anchor>` line.
  2. Examples:
     - "Python 3.11+ not found → see docs/TROUBLESHOOTING.md#python-version"
     - "uv not on PATH → see docs/TROUBLESHOOTING.md#uv-not-recognized"
     - "Redis unreachable → see docs/TROUBLESHOOTING.md#redis-unreachable"
     - "VLM endpoint not reachable at 127.0.0.1:1234 → see docs/TROUBLESHOOTING.md#vlm-not-running"
- **Acceptance criteria.** A user who runs `make doctor` after a failure has a clear "click here next" link.
- **Effort.** 2 hours.

### 3.5 Phase 2 sign-off

- Owner: DX lead + one backend engineer.
- PR titles: `[docs] add TROUBLESHOOTING.md`, `[dx] add CONTRIBUTING + issue/PR templates`, `[backend] default state backend to sqlite`.
- Reviewers: 1 docs, 1 backend per PR.
- Time to merge: ≤ 3 days from first PR open.

---

## 4. Phase 3 — Quick-win code cleanups (1 week, owner: Backend)

**Goal.** Clean up the high-leverage code debt that the dev lens surfaced. Each item is ≤ 1 day of work and removes a known footgun.

**Source.** Audit findings D1, D2, D3, D5, D6, D7, D10, D11, D12, D13, D14, D15, S4, S5, Q3.

### 4.1 Reduce `MAX_UPLOAD_MB` default to 1024 MB

- **Problem.** `src/omniscribe/config.py:230` defaults `MAX_UPLOAD_MB` to 10 GB. A LAN caller with bearer auth can pin 10 GB of memory + disk per request. The cap is enforced, but it's generous. (S4.)
- **Scope.** `src/omniscribe/config.py`, `compose.yaml`, `docs/DEPLOYMENT.md`.
- **Concrete steps.**
  1. Change default to 1024 (1 GB).
  2. Document in `DEPLOYMENT.md` how to raise it for batch hosts.
  3. Add a CHANGELOG entry under "Security" (or "Configuration") with a one-line note.
- **Acceptance criteria.** `OMNISCRIBE_MAX_UPLOAD_MB` defaults to 1024 in a fresh `.env`; operators must explicitly raise it.
- **Effort.** 30 minutes.

### 4.2 Narrow `QUERY_TOKEN_PATHS` to exact SSE/event-stream routes

- **Problem.** `src/omniscribe/middleware/auth.py:49-52,163` enables `?token=` query-param bearer auth on every path starting with `/api/process/` and `/api/jobs/`. URL-borne tokens leak into nginx access logs, browser history, and referer headers. (S5.)
- **Scope.** `src/omniscribe/middleware/auth.py`, `src/omniscribe/middleware/auth.py` tests.
- **Concrete steps.**
  1. Change `QUERY_TOKEN_PATHS` to exact SSE/event-stream routes: `/api/process/{job_id}/events` and `/api/jobs/{job_id}/events` (or whatever the current SSE routes are — verify with `rg 'EventSource' src` and `rg 'WebSocket' src`).
  2. Add a comment in the code explaining the SSE-only rationale (EventSource cannot send custom headers).
  3. Add a test that asserts `?token=` is rejected on `/api/jobs/{job_id}` (non-events) and accepted on `/api/jobs/{job_id}/events`.
  4. Add a `SECURITY.md` note documenting the choice.
- **Acceptance criteria.** A path that doesn't serve SSE rejects `?token=` and demands the `Authorization: Bearer` header.
- **Effort.** Half a day.

### 4.3 Replace magic-number `time.sleep(0.01)` / `asyncio.sleep(0.01)` patterns in tests

- **Problem.** 10+ sites in `tests/` use `time.sleep(0.01)` or `asyncio.sleep(0.01..0.05)` to "drain the worker." These are textbook flaky patterns under load. (Q3.)
- **Scope.** Test files only:
  - `tests/routers/conftest.py:80`
  - `tests/routers/test_translate_routes.py:70`
  - `tests/routers/test_glossary_routes.py:348`
  - `tests/harness/test_context.py:121,125`
  - `tests/plugins/test_jobs_plugin.py:50,129`
  - `tests/middleware/test_auth.py:310`
  - `tests/core/test_aligner.py:710`
  - `tests/core/test_dictionary_postprocess.py:339`
- **Concrete steps.**
  1. For each site, identify the real synchronization primitive:
     - If waiting for a worker to finish: use `await asyncio.wait_for(worker_task, timeout=2.0)` instead of sleep.
     - If waiting for an event to be processed: use a `asyncio.Event` that the worker sets.
     - If waiting for queue draining: poll with a budget (`for _ in range(100): if queue.empty(): break; await asyncio.sleep(0.01)` with a `pytest.fail` after the budget).
  2. Replace each sleep with the right primitive.
  3. Add a CI step that runs the test 10× in a row on the same runner to verify no flakes.
- **Acceptance criteria.** `pytest -p no:randomly tests/ --count=10` (or manual `for i in {1..10}; do pytest tests/X.py; done`) produces 0 flakes.
- **Effort.** 1–2 days.

### 4.4 Single `load_dotenv()` call at `main()`

- **Problem.** `load_dotenv()` is called at module import AND at `main()` in `server.py:26,125,459`; `core/ocr/processor.py:154` also reads env via `load_settings()` which doesn't call `load_dotenv` (probably). Two consequences: (1) `create_app()` and `main()` each call it; (2) importing `omniscribe.server` reads `.env` even when the caller just wanted `app.openapi()`. (D5.)
- **Scope.** `src/omniscribe/server.py`, `src/omniscribe/core/ocr/processor.py`.
- **Concrete steps.**
  1. Remove `load_dotenv()` call from `create_app()`.
  2. Keep the call in `main()` only.
  3. Remove the `from dotenv import load_dotenv` from `core/ocr/processor.py` (it doesn't call it directly).
  4. Add a test that `import omniscribe.server; assert os.environ.get('SOMETHING') is None` does not silently load `.env`.
- **Acceptance criteria.** `python -c "import omniscribe.server; print('OK')"` does not read `.env` from a non-`omniscribe-server` process.
- **Risks.** Low. Affects only import side effects.
- **Effort.** 1 day.

### 4.5 Drop `HybridEngine` re-injection

- **Problem.** `core/workflows/hybrid.py:325-326, 353-355, 434-437, 491, 518` writes `self.converter.pdf_handler = self.pdf_handler` and similar on every `execute()` call. The `__init__` already receives these via constructor args. The re-injection is decorative. (D3.)
- **Scope.** `src/omniscribe/core/workflows/hybrid.py`.
- **Concrete steps.**
  1. Remove the 5+ re-injection lines.
  2. Verify the tests still pass; add a test that asserts the converter's deps are stable across calls.
  3. Document the constructor-arg-only pattern in `ARCHITECTURE.md` §3.
- **Acceptance criteria.** No `self.<stage>.<dep> = self.<dep>` lines outside `__init__` in `hybrid.py`.
- **Effort.** Half a day.

### 4.6 Fix `JobStatusResponse.started_at` (always `None`)

- **Problem.** `plugins/ocr/service.py:519-530` sets `started_at=None` even after `JobStarted` has fired. The schema exposes the field, so clients see a "buggy clock." (D1.)
- **Scope.** `src/omniscribe/plugins/ocr/service.py`, `src/omniscribe/plugins/ocr/schemas.py`.
- **Concrete steps.**
  1. Decide: persist or delete. (Recommend persist — clients probably want it.)
  2. Add `started_at: datetime | None` to `JobRecord` (or whatever the internal job record type is).
  3. Set it in the `JobStarted` handler.
  4. Surface it in `_status_response`.
  5. Add a test that asserts `started_at` is non-None after `JobStarted` fires.
- **Acceptance criteria.** After a job starts, the status response includes the actual start time.
- **Effort.** Half a day.

### 4.7 Fix `InMemoryJobQueue._run` exception swallowing

- **Problem.** `plugins/jobs.py:281-291` catches all exceptions in the worker with only a log. A runner that consistently raises the same transient `httpx.ConnectError` will flood the log and never surface a `JobFailed` to the client. (D2.)
- **Scope.** `src/omniscribe/plugins/jobs.py`.
- **Concrete steps.**
  1. Replace the worker's `except Exception` with `except asyncio.CancelledError` only.
  2. Let exceptions propagate to the existing `_process_one` `except` block (`plugins/jobs.py:343-355`) which emits the `JobFailed` event.
  3. Add a test that simulates a runner that raises `httpx.ConnectError`; assert the queue emits `JobFailed` and the status response says "failed".
- **Acceptance criteria.** A failing runner produces one `JobFailed` event visible to the client and one log line; not a log flood.
- **Effort.** 1 day.

### 4.8 Extract `services/{error_sanitization, content_sniff, config_seeding}.py` from `plugins/ocr/service.py`

- **Problem.** `plugins/ocr/service.py` is 890 LOC and mixes four concerns: route-adjacent helpers, error-sanitization regexes, content-type sniffing, service implementation, SSE event formatting, config seeding. (D6.)
- **Scope.** `src/omniscribe/plugins/ocr/service.py`, plus three new files in `src/omniscribe/plugins/ocr/services/`.
- **Concrete steps.**
  1. Create `services/error_sanitization.py` with `_sanitize_job_error` and its private regex constants.
  2. Create `services/content_sniff.py` with `_guess_suffix` and the magic-byte constants.
  3. Create `services/config_seeding.py` with `_CONFIG_KEY_SET` and `_seed_config`.
  4. Update `plugins/ocr/service.py` to import from these.
  5. Update `plugins/ocr/plugin.py` to import from these (it already imports `SSE_KEEPALIVE_SECONDS` from service, so the seam is already drawn).
  6. Add tests for each extracted module.
- **Acceptance criteria.** `plugins/ocr/service.py` is under 500 LOC. The three new modules have ≥ 90% coverage.
- **Effort.** 2 days.

### 4.9 Phase 3 sign-off

- Owner: Backend lead.
- 8 PRs total (one per item 4.1–4.8). Each PR is self-contained; can land in any order.
- Reviewers: 1 backend per PR; security review for 4.1, 4.2, 4.7.
- Time to merge: ≤ 7 days from first PR open.
- Risk: low. Most items are refactors; only 4.3, 4.6, 4.7 are behavior changes (and small).

---

## 5. Phase 4 — End-user install path (2–6 weeks, owner: Desktop / DevX)

**Goal.** Reduce the 12–16 step install to a 3-step happy path for a non-developer.

**Source.** Audit findings U2, U3, U4, U6, C2.

> **Note on scope.** This is the largest workstream in the plan. Before committing to a date, scope a 1-page design doc that picks: (a) PyInstaller bundle of the FastAPI server, (b) Flutter desktop build that embeds the server, or (c) a `pip install omniscribe` + standalone CLI. The audit doesn't make a recommendation — that's a product decision, not an engineering one.

### 5.1 Decide: distribution shape

- **Decision needed.** Three options on the table:
  1. **PyInstaller bundle of the FastAPI server** (smaller scope, no Flutter). Ship a `omniscribe-server.exe` that runs without a Python install.
  2. **Flutter desktop build that embeds the server** (larger scope). Ship `OmniScribe.exe` (Windows) / `.app` (macOS) / `.AppImage` (Linux) that includes a Python runtime and starts the server on first launch.
  3. **Standalone CLI** (`pip install omniscribe`) that gives `omniscribe <file.pdf>` (smaller than a server, requires Python 3.11+).
- **Concrete steps for the decision.**
  1. Open a 1-page RFC under `docs/rfcs/`.
  2. List the tradeoffs (PyInstaller: easy, but doesn't include Flutter UI; Flutter: covers the UI but doubles the packaging surface; CLI: smallest, but loses the UI).
  3. Pick one and document the choice.
  4. The audit does not recommend a specific path.
- **Acceptance criteria.** An RFC exists with a decision; the rest of Phase 4 is buildable.
- **Effort.** 1 day (decision only).

### 5.2 Add screenshots + a 10-second GIF to the README

- **Problem.** The audit found zero screenshots, GIFs, or videos anywhere in the tree. (U6.)
- **Scope.** `docs/screenshots/` (new), `README.md`, `client/README.md`.
- **Concrete steps.**
  1. Take a screenshot of the Workstation screen (`client/lib/presentation/workstation/workstation_screen.dart:18-19`).
  2. Take a screenshot of the Settings / Advanced Configuration panel.
  3. Take a screenshot of the OCR result preview.
  4. Capture a 10-second GIF of "drop a PDF → OCR runs → result is selectable."
  5. Embed in `README.md` after the lede.
- **Acceptance criteria.** A non-developer can see what the product looks like in 3 seconds.
- **Effort.** 1 day (assuming the screenshots are quick to capture).

### 5.3 Resolve the "Web UI" confusion

- **Problem.** `DEPLOYMENT.md:11-12` says "You open the browser to `http://localhost:8000` and use it." But `src/omniscribe/static/index.html:24-29` says "OmniScribe API server is running. The interactive client ships as a Flutter desktop application under `client/`." (U4.)
- **Scope.** Either `DEPLOYMENT.md` or `static/index.html` (depending on the decision).
- **Concrete steps.**
  1. If Phase 5.1 picks Flutter desktop as the supported client: remove the browser line from `DEPLOYMENT.md:11-12`; rewrite `static/index.html` to be a clear "API server is running, here's the OpenAPI URL, here's how to run the client" page.
  2. If Phase 5.1 picks a browser-based UI as supported: build it (this is the bigger branch — out of scope for the spec).
- **Acceptance criteria.** The README, DEPLOYMENT.md, and the static index page all agree on what the user is supposed to do next.
- **Effort.** Half a day for the doc branch; 4+ weeks for the build branch.

### 5.4 Phase 4 sign-off

- Owner: Desktop / DevX lead.
- PR title: `[desktop] ship v0.2.0 install path`.
- Time to merge: 2–6 weeks depending on Phase 5.1 decision.

---

## 6. Phase 5 — Test hardening (1 week, owner: QA)

**Goal.** Test quality > test count. The audit's QA lens found that coverage is good but property-based testing is token, mutation testing is absent, and flake detection is manual.

**Source.** Audit findings Q3 (already covered in Phase 4.3), Q4, Q5, Q6, Q7, Q8, Q11, Q12, Q13.

### 6.1 Add property-based tests for the five fuzzable surfaces

- **Problem.** The project declares `hypothesis>=6.100.0` and has a `slow_dataset` marker — clear intent for property-based testing. But only 5 `@given` decorators in 1 file exist. (Q4.)
- **Scope.** New tests in:
  - `tests/utils/test_json_parse_props.py`
  - `tests/utils/test_prompt_safety_props.py`
  - `tests/core/pdf/test_page_range_props.py`
  - `tests/core/recall/test_whitespace_props.py`
  - `tests/core/ocr/test_filters_props.py`
- **Concrete steps.**
  1. For each module, identify the invariants:
     - `json_parse`: idempotent on `json.dumps(json.loads(x))` round-trip; tolerates leading/trailing whitespace; rejects malformed input.
     - `prompt_safety`: never returns more than 2× the input length; never returns the input verbatim; no PII-shaped substrings (e.g. email regex).
     - `page_range`: round-trips through `parse` and `serialize`; rejects negative, zero, out-of-bounds page numbers.
     - `whitespace`: candidate set is a subset of input tokens; non-empty candidates have non-empty text; confidence in `[0, 1]`.
     - `ocr filters`: input count ≥ output count; never loses a non-empty text block; preserves order.
  2. Write `@given` tests for each invariant with `@settings(max_examples=200, deadline=200)`.
  3. Run each in CI.
- **Acceptance criteria.** ≥ 30 new property-based tests across the five modules; CI is green.
- **Effort.** 3 days.

### 6.2 Add direct test for `core/translate/workflow.py`

- **Problem.** The LangGraph driver at `src/omniscribe/core/translate/workflow.py` is exercised only indirectly via 3 other test files. None imports `workflow.py` directly. Graph state machine, node sequencing, and error recovery are exactly the things that need direct tests. (Q5.)
- **Scope.** New file: `tests/core/translate/test_workflow.py`.
- **Concrete steps.**
  1. Read `src/omniscribe/core/translate/workflow.py` end-to-end.
  2. Identify the graph nodes and their transitions.
  3. For each node, write a test that stubs the LLM and asserts the node's output shape.
  4. For each transition, write a test that asserts the next node is called with the right context.
  5. Add a happy-path integration test.
  6. Add a failure-path test (LLM returns malformed JSON) and assert the graph recovers.
- **Acceptance criteria.** ≥ 10 direct tests of `workflow.py`; coverage of `workflow.py` is ≥ 70%.
- **Effort.** 2 days.

### 6.3 Re-home `examples/` PDFs into `tests/fixtures/pdfs/`

- **Problem.** `tests/fixtures/` has no PDFs; all real PDFs live under `examples/`. The conflation means `pytest --ignore=examples` (e.g. for a Docker image) would silently break. (Q6.)
- **Scope.** `examples/`, `tests/fixtures/pdfs/` (new), `tests/conftest.py`.
- **Concrete steps.**
  1. Copy (or symlink) the 5 PDFs from `examples/` into `tests/fixtures/pdfs/`.
  2. Update `tests/conftest.py:35-41` to load from `tests/fixtures/pdfs/`.
  3. Keep `examples/` for user-facing "try this PDF" purposes, with a `README.md` that says: "These PDFs are also used as test fixtures. Do not remove."
  4. Add a CI step that verifies `tests/fixtures/pdfs/` matches `examples/`.
- **Acceptance criteria.** `pytest --ignore=examples` passes.
- **Effort.** 1 day.

### 6.4 Add mutation testing for pure utilities

- **Problem.** With 80% line coverage, ~20% of "covered" lines may be mutation-survivors. (Q7.)
- **Scope.** `tests/utils/`, `tests/core/recall/`.
- **Concrete steps.**
  1. Add `mutmut` to `[dependency-groups] dev` in `pyproject.toml`.
  2. Add a `mutmut` config that runs against `src/omniscribe/utils/` and `src/omniscribe/core/recall/`.
  3. Add a CI step (nightly only) that runs `mutmut run` and reports the mutation score.
  4. Triage the top 10 surviving mutants per run and add tests to kill them.
- **Acceptance criteria.** Mutation score on the targeted modules is ≥ 70%.
- **Effort.** 2 days for setup + 1 day per round of triage.

### 6.5 Add JUnit XML upload + flake detection

- **Problem.** `pytest-slow-results` upload in `nightly.yml:63-70` is only `.pytest_cache/v/cache/lastfailed`. No JUnit XML, no flake detection. (QA gap analysis #1, #2.)
- **Scope.** `.github/workflows/test.yml`, `.github/workflows/nightly.yml`, `pyproject.toml`.
- **Concrete steps.**
  1. Add `--junitxml=reports/junit.xml` to the pytest invocation in `test.yml` and `nightly.yml`.
  2. Upload `reports/junit.xml` as an artifact.
  3. Add `pytest-rerunfailures` to dev deps with `--reruns=2 --reruns-delay=1`.
  4. Add a `pytest --flake-finder` to nightly (or use `pytest-flakefinder`).
  5. Surface a "flake dashboard" comment on the nightly summary.
- **Acceptance criteria.** A flaky test surfaces within 1 nightly run; JUnit XML is available for any run.
- **Effort.** 1 day.

### 6.6 Phase 5 sign-off

- Owner: QA lead.
- 5 PRs (one per item). Each can land independently.
- Reviewers: 1 backend per PR.
- Time to merge: ≤ 7 days from first PR open.

---

## 7. Phase 6 — Long-tail (ongoing)

**Goal.** Work down the audit's backlog items. None of these is urgent; they should be picked up opportunistically.

**Source.** Audit findings in the "Backlog" section of the action plan.

### 7.1 DX polish

- D7: promote private OCR service state to public properties.
- D8: single error envelope across routes and global handler.
- D9: enable `mypy.disallow_untyped_defs` for `omniscribe.plugins.*` and `omniscribe.harness.*`.
- D10: drop legacy CORS aliases (`cors_origins`, `cors_origins_raw`); keep only `OMNISCRIBE_CORS_ORIGINS`.
- D11: switch `extract_json` to single-pass `raw_decode`.
- D12: hoist `OCRProcessor._DEFAULTS` to module scope.
- D13: split `is_transient_error` ValueError branch (bugs vs. garbage).
- D14: parse `DenseMode` directly in the validator; drop the aliasing property.
- D15: delete dead `trust_images_dict` parameter.
- D16: align Dockerfile `python:3.14-slim` pin with `pyproject.toml` classifiers.
- D17: verify `transformers>=5.15.1` resolves in the lockfile.
- D18: drop `--no-fix` from `make lint` (or document the difference).
- D19: fix `is_transient_error` default (RuntimeError-as-permanent is wrong).
- D20: `sys.path` scoping in `tests/conftest.py`.

### 7.2 Security hardening

- S6: gate `/api/progress/cancel` behind session token on loopback dev profile.
- S7: document rate limiter per-worker multiplier; consider Redis-backed sliding window.
- S8: constant-length token mask (don't leak first4…last4 for short tokens).
- S9: comment requirement in `server.py:204` that `static/` must be a sealed dir.
- S10: switch JSON-logger redaction from substring to exact-key.
- S11: bind `Dockerfile` CMD to `127.0.0.1`; document override.
- S12: pass `git` credentials via `.netrc` / `GIT_ASKPASS` instead of argv.
- S13: add unit test for CORS `*` + credentials behavior.
- S14: add comment on WebSocket origin check fallback.
- S15: document job-list dev-bind enumeration behavior.

### 7.3 QA polish

- Q8: named under-tested modules wave (transcription, grounded, lexicon, glossary_sources, plugins/glossary).
- Q9: add a parallel test that verifies the `seed=42` actually controls Platt scaling.
- Q10: merge `tests/ops/` into `tests/scripts/` (or expand into a proper ops-smoke dir).
- Q11: chaos / fault-injection tests (timeout during mid-job, Redis drop during progress WS, VLM 503 after 30s).
- Q12: Flutter `integration_test/` against a real running server.
- Q13: balance Flutter widget test coverage.

### 7.4 PM polish

- P7: AGPL badge near top of README (or move notice above Features).
- P8: "User-visible changes" subsection in CHANGELOG; move refactor noise under `## Maintenance`.
- P9: cut `v0.1.0` GitHub tag; document the client release flow in `AGENTS.md` or `docs/CLIENT_RELEASE.md`.
- P10: cross-link per-service tokens section to deferred-middleware note (matters less after Phase 1).
- P11: clarify `omniscribe-migrate-lexicon` script's role in the CLI deprecation narrative.
- P12: add `## Current focus` header to `outstanding-work.md` (done in Phase 1.2).
- P13: publish PGP key for security contact.
- P14: align `compose.yaml` upload size with the live middleware (done as part of Phase 3.1).

### 7.5 End-user polish

- U11: add a "supported platforms" table to the README (Windows 11 / macOS 14 / Ubuntu 24.04).
- U12: add in-UI "try with sample PDF" affordance (after Phase 4 ships).
- U13: cross-link trust signals from the main README.
- U14: user-facing CHANGELOG summary (covered by P8).

---

## 8. Rollout sequence (top-down)

The plan is designed to be read and acted on top-down. Here's the explicit order with parallelization.

```
Week 0 (Day 0)
└── Phase 0 ─── security one-liner + 2 trivial foot-guns
   └── ~1 hour, single PR

Week 1 (Days 1-5)
├── Phase 1 ─── docs reconciliation
│   └── 1-1.5 days, single PR or 2 PRs (SECURITY/outstanding-work vs READMEs)
│
└── Phase 2 ─── first-run affordances (parallel with Phase 1)
    ├── 2.1 TROUBLESHOOTING.md ──────── 1 day
    ├── 2.2 CONTRIBUTING + templates ── 1 day
    └── 2.3 SQLite default state backend ─ 1 day
    └── 3 PRs, can land in any order

Week 2 (Days 6-10)
└── Phase 3 ─── quick-win code cleanups
    ├── 4.1 MAX_UPLOAD_MB default ───────── 0.5 day
    ├── 4.2 Narrow QUERY_TOKEN_PATHS ─────── 0.5 day
    ├── 4.3 Replace magic-number sleeps ── 1-2 days
    ├── 4.4 Single load_dotenv() ─────────── 0.5 day
    ├── 4.5 Drop HybridEngine re-injection  0.5 day
    ├── 4.6 Fix JobStatusResponse.started_at 0.5 day
    ├── 4.7 Fix InMemoryJobQueue exception ── 1 day
    └── 4.8 Refactor plugins/ocr/service.py ─ 2 days
    └── 8 PRs, parallel up to 3 at a time

Week 3 (Days 11-15)
└── Phase 5 ─── test hardening (parallel with Phase 4 RFC)
    ├── 6.1 Property-based tests ─── 3 days
    ├── 6.2 Translate workflow tests ─ 2 days
    ├── 6.3 Re-home fixtures ─────── 1 day
    ├── 6.4 Mutation testing ─────── 3 days
    └── 6.5 JUnit XML + flake detect  1 day
    └── 5 PRs, can land in any order

Weeks 4-8 (Days 16-40)
└── Phase 4 ─── end-user install path
    ├── 5.1 RFC + decision ──── 1 day
    ├── 5.2 Screenshots + GIF ── 1 day
    ├── 5.3 Web UI direction ── 0.5 day (doc branch) or 4+ weeks (build branch)
    └── Build the chosen path

Ongoing (post-Week 4)
└── Phase 6 ─── long-tail backlog
```

**Critical path.** Phases 0 → 1 → 4 (because Phase 4 needs Phase 1's README to be final for the install docs to be correct). Phases 2, 3, 5 are independent of 4 and can run in parallel.

**Parallelism budget.** Up to 3 PRs can be open at once without thrash. Recommended owner assignment:
- PR1 (Phase 0): Security lead
- PR2 (Phase 1.1-1.2): Docs lead
- PR3 (Phase 1.3-1.7): Docs lead or backend lead
- PR4-6 (Phase 2): DX lead + backend
- PR7-14 (Phase 3): 2-3 backend engineers
- PR15-19 (Phase 5): QA lead + 1 backend

---

## 9. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Phase 2.3 (SQLite default) breaks a user with a custom in-memory workflow | Low | Medium | CHANGELOG note, opt-in via env var, minor version bump |
| Phase 1.1 doc edits miss a place where the "deferred" language appears | Medium | Low | Phase 1 acceptance: `rg -i 'deferred\|scaffolding' docs/` returns no security-relevant hits |
| Phase 4 ships a desktop binary that the project can't actually maintain | Medium | High | Phase 5.1 RFC; if the answer is "too much", pick the smaller distribution shape |
| Phase 5.4 mutation testing generates too many false positives | High | Low | Nightly-only, manual triage, no gate |
| The Phase 3 code cleanups regress the Wave 14 cleanup | Low | Medium | Each Phase 3 PR is small + has a test; no big-bang refactor |
| 8 PRs in Phase 3 merge-conflict with each other | Medium | Low | Owners work on disjoint files; pair-review before merge |
| `.env.example` rotation breaks existing local installs that copied the file | Low | Low | Phase 0.1 only changes the example, not any committed `.env` |
| The Phase 5.1 RFC takes longer than a day because the decision is genuinely hard | Medium | Medium | Plan B: ship the smaller distribution (PyInstaller of just the server) and iterate |

---

## 10. Success metrics

How to know the plan worked.

- **30 days after Phase 0 lands:** GitHub issues mentioning "REDIS_PASSWORD" or "auth token" drop to ≤ 1 per week.
- **30 days after Phase 1 lands:** Search `rg -i 'deferred\|scaffolding' docs/` returns no security-relevant hits.
- **30 days after Phase 2 lands:** The `TROUBLESHOOTING.md` page is among the top 5 most-edited files. A `make doctor` run that fails prints a clickable hint to the right doc anchor.
- **30 days after Phase 3 lands:** `pytest -p no:randomly --count=10` on the affected test files produces 0 flakes. The OCR service module is < 500 LOC.
- **30 days after Phase 4 lands:** A non-developer can install OmniScribe in ≤ 3 steps. The "Web UI is a 5-line placeholder" finding is closed.
- **30 days after Phase 5 lands:** Mutation score on `src/omniscribe/utils/` is ≥ 70%. ≥ 30 new property-based tests are passing in CI. Flake detection surfaces any regression within 1 nightly run.
- **At all times:** A new issue filed against the project hits one of the `.github/ISSUE_TEMPLATE/` paths and includes a structured report.

---

## 11. Out of scope for this spec

These were called out in the audit but are not in the remediation plan because they need product/strategy decisions first, or they're out of the project scope:

- **Flutter client security audit** — a separate Dart-focused audit is warranted.
- **Reverse-proxy configs (Caddy/nginx)** — deployment responsibility, not project code.
- **TLS cipher/profile strength** of operator-chosen proxy.
- **Live LLM end-to-end validation** in CI — explicitly out of design.
- **Cross-platform PDF edge cases** (corrupt PDFs, password-protected, 1000+ page documents) — feature work, not remediation.
- **Non-English / RTL / CJK PDF ground truth** — feature work.
- **Performance benchmarks at scale** — feature work.

---

## 12. Appendix — Phase-to-finding cross-reference

| Phase | Audit finding IDs (from `2026-09-04-five-lens-audit.md`) |
|---|---|
| 0 | S1, S3, A1, A12 |
| 1 | S2, P1, P2, P7, P10, P12, U1, U5, U9, A2, A3, A4, A5, A6, A7 |
| 2 | P5, P6, U7, U10, A8, B1, B2 |
| 3 | D1, D2, D3, D5, D6, S4, S5, Q3 |
| 4 | U2, U3, U4, U6, C2 |
| 5 | Q4, Q5, Q6, Q7, Q11, Q12, Q13 |
| 6 | D7, D8, D9, D10, D11, D12, D13, D14, D15, D16, D17, D18, D19, D20, S6, S7, S8, S9, S10, S11, S12, S13, S14, S15, Q8, Q9, Q10, Q11, Q12, Q13, P7, P8, P9, P10, P11, P13, P14, U11, U12, U13, U14 |

Every audit finding (Critical, High, Medium, Low, Info) is in at least one phase. None is dropped.

---

*End of plan. Total length: ~5,500 words. Read top-down; sign off on Phase 0 first.*
