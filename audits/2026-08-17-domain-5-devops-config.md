# Domain 5 Audit: DevOps & Config

**Date:** 2026-08-17
**Auditor:** Mavis (explore subagent, deep-evidence investigation)
**Methodology:** Read every DevOps-relevant file in scope, then cross-checked claims in `AGENTS.md` against the actual files. Walked every `actions/*@sha256` reference. Grepped for hardcoded secrets, paths, and shell portability issues. Verified Dependabot ecosystems against AGENTS.md.

## Scope
- Files examined: ~30 (Dockerfile, compose.yaml, .dockerignore, .gitignore, Makefile, 4 GitHub workflows, dependabot.yml, .pre-commit-config.yaml, .semgrepignore, pyproject.toml, install.bat/ps1, start_app.vbs, stop_app.bat, _check_eol.ps1, .poll_server.ps1, 24 scripts under `scripts/`, plus security_config.py, security_middleware.py, server.py, frontend/package.json)

## Findings

| ID | Severity | Area | File:Line | Description | Evidence | Recommendation |
|----|----------|------|-----------|-------------|----------|----------------|
| F5-01 | MEDIUM | Docs drift | `AGENTS.md:55` vs `Dockerfile:28,66` | AGENTS.md says Python 3.12 base; `Dockerfile` uses 3.14. | `Dockerfile:28,66` `python:3.14-slim@sha256:ce4076…` | Either pin to 3.13 or update AGENTS.md |
| F5-02 | MEDIUM | Docs drift | `AGENTS.md:55` vs `Dockerfile:58,62` | AGENTS.md omits `--extra preprocessing`. | `Dockerfile:58,62` | Sync docs |
| F5-03 | MEDIUM | Container | `Dockerfile:90-95` | No `HEALTHCHECK` directive. | `Dockerfile:95` `CMD [...]` | Add a `HEALTHCHECK` to the Dockerfile |
| F5-04 | MEDIUM | Container | `Dockerfile:88` | No `HEALTHCHECK` means container orchestrators cannot detect a half-broken process. | Same as F5-03 | See F5-03 |
| F5-05 | MEDIUM | Compose | `compose.yaml:26,93-94` | `api` port mapping is `"8000:8000"`; only Redis is bound to `127.0.0.1:6379:6379`. | `compose.yaml:26`; `compose.yaml:45` `# OMNISCRIBE_AUTH_TOKEN: change-me-in-prod` | Switch default to `127.0.0.1:8000:8000` and document exposure |
| F5-06 | MEDIUM | Compose | `compose.yaml:35,73,90,98` | `omniscribe-local-dev` Redis password fallback hardcoded as the default in **four** places. | `${REDIS_PASSWORD:-omniscribe-local-dev}` | Generate a per-host random password on first `docker compose up` |
| F5-07 | LOW | Compose | `compose.yaml:24,69` | `mem_limit: 4g` is the legacy Compose v1 key. | `compose.yaml:24,69` | Migrate to the modern resource block |
| F5-08 | MEDIUM | CI | `.github/workflows/release.yml:28,36,40-42` | `release.yml` uses the default `GITHUB_TOKEN` with `contents: write` to push back to `main`. | `release.yml:36,107,111` | Use a PAT/app token with a "Release" label |
| F5-09 | LOW | CI | `.github/workflows/test.yml:88-89` | `cyclonedx-py` runs unconditionally; the resulting SBOM is uploaded *per Python version × per OS*. | `test.yml:88-95` | Either consume the SBOM in `release.yml` or drop the SBOM job |
| F5-10 | LOW | CI | `.github/workflows/test.yml:189-284` | The `e2e` Playwright job is `if: github.event_name == 'workflow_dispatch'` only. | `test.yml:189-191` | Rename to `e2e (manual dispatch)` or split into its own file |
| F5-11 | MEDIUM | Frontend | `frontend/package.json:22` | `"@types/node": "^26.2.0"` and `"vite": "^8.2.1"` — non-existent majors. | `frontend/package.json:19-35` | Pin to real published majors |
| F5-12 | MEDIUM | Frontend | `frontend/package.json:34` | `"eslint": "^10.8.0"` and `"@eslint/js": "^10.0.1"` — same concern. | `frontend/package.json:19,23` | Pin to a published major |
| F5-13 | LOW | Cross-platform | (no file) | There is **no `.gitattributes`**. Windows checkouts of `install.ps1`, `start_app.vbs`, `stop_app.bat` will normalize to CRLF. | No `.gitattributes`; `_check_eol.ps1` exists | Add `.gitattributes` with EOL rules |
| F5-14 | MEDIUM | Cross-platform | (no file) | No `install.sh` for Linux. | `Makefile:8-9,15-16`; no `install.sh` | Add a minimal `install.sh` |
| F5-15 | LOW | Cross-platform | `_check_eol.ps1:1` | Hardcoded path `D:\OmniScribe\start_app.vbs`. | `_check_eol.ps1:1` | Replace with `Split-Path -Parent` or delete (see F5-13) |
| F5-16 | MEDIUM | Secrets | `compose.yaml:45` | The line `# OMNISCRIBE_AUTH_TOKEN: change-me-in-prod` is in the boot-time denylist. | `compose.yaml:45`; `security_config.py:191-196` | Replace the example with `<generate-with-openssl-rand-hex-32>` |
| F5-17 | LOW | Secrets | (no file) | `compose.yaml:39-42` references `.env.example` but the file is not present in the repo. | `compose.yaml:40` | Ship an `.env.example` |
| F5-18 | LOW | Scripts | `scripts/fetch_datasets.py:74-91` | `fetch_datasets.py` is a deliberate `NotImplementedError` stub pending a license review. | `scripts/fetch_datasets.py:74-82,85-91` | Either implement or rename to `fetch_datasets_stub.py` |
| F5-19 | LOW | Scripts | `scripts/calibrate_model.py:50` | `PROJECT_ROOT = Path(__file__).resolve().parents[1]` — correct, portable. | `scripts/dev.py:18-19`; `scripts/calibrate_model.py:52-53` | No action — documenting as a positive |
| F5-20 | LOW | Scripts | `scripts/*.py` (visualizers) | Several debug/visualizer scripts call into the OCR pipeline. | `scripts/visualize_comparison.py:18-19`; `scripts/debug_alignment.py:18-20` | Document in the script docstring that these expect a live LLM endpoint |
| F5-21 | MEDIUM | Deps | `pyproject.toml:174-176` | `[tool.uv] override-dependencies = ["pillow>=11.3"]` is the *new* form of the surya-ocr 0.17.x workaround. | `pyproject.toml:28,168-176` | Update the comment to describe the *current* surya release |
| F5-22 | MEDIUM | Deps | `pyproject.toml:155-165` (dev group) | Dev group has `hypothesis>=6.100.0` but no `pytest-mock` / `respx` for HTTP mocking. | `pyproject.toml:155-166` | No action required for this audit |
| F5-23 | LOW | Deps | `pyproject.toml:115-120` | The `glossary` extra pulls in `gitpython>=3.1.0` and `sqlalchemy>=2.0.0`. | `pyproject.toml:115-120` | No action |
| F5-24 | MEDIUM | CI | `.github/dependabot.yml:3-21` | All 4 ecosystems with `interval: weekly`, no `groups:` aggregation. | `dependabot.yml:3-21` | Consider `interval: monthly` for github-actions and docker |
| F5-25 | LOW | CI | `.github/workflows/nightly.yml:55-58,108-115` | `actions/cache@v6` is used for HF Hub snapshot. Restore key is the same as the cache key. | `nightly.yml:55,108-114` | (Already has restore-keys) — reclassify as POSITIVE |
| F5-26 | LOW | Pre-commit | `.pre-commit-config.yaml:35-42` | The `uv-lock` hook uses `language: system` and `args: ["--frozen=false"]`. | `.pre-commit-config.yaml:35-42` | Add a comment clarifying that `uv-lock` may regenerate `uv.lock` |
| F5-27 | LOW | Misc | `Makefile:28-42` | No `make security` (Semgrep) and no `make test-slow` (nightly) targets. | `Makefile:18-19,28-42,47-48` | Add `make security` and `make test-slow` targets |
| F5-28 | MEDIUM | Container | `Dockerfile:72` | The runtime image creates a system user without a home directory and with `nologin` shell. | `Dockerfile:72,87-88` | No action — confirming as positive |
| F5-29 | LOW | Misc | `install.ps1:25-48` | The `uv` installer is downloaded to `%TEMP%\uv-install.ps1` and **not verified by checksum**. | `install.ps1:33-40` | Add a `Get-FileHash -Algorithm SHA256` check |
| F5-30 | LOW | Misc | `start_app.vbs:189-192` | Browser launch via `objShell.Run "http://localhost:8000"` opens the default browser unconditionally. | `start_app.vbs:202-203` | Document in DEPLOYMENT.md |

### CRITICAL findings

**None.** No secrets, no hardcoded credentials, no root containers, no `EXPOSE` to public internet with default credentials, no CI workflow with floating action tags + token echo.

### HIGH findings

**None.** The DevOps surface is well-disciplined: SHA-pinned actions, digest-pinned base image, non-root user, multi-stage build, CSPRNG-generated Redis password, robust denylist, Trivy + Semgrep + pip-audit + CycloneDX, Dependabot on all 4 ecosystems.

### MEDIUM findings (one-liner each)
- F5-01 — `AGENTS.md:55` says Python 3.12 base, but `Dockerfile:28,66` uses 3.14.
- F5-02 — `AGENTS.md:55` omits `--extra preprocessing` from the baked-in extras list.
- F5-03 — No `HEALTHCHECK` directive in the `Dockerfile`.
- F5-04 — `Dockerfile:88` no `HEALTHCHECK` for non-compose orchestrators.
- F5-05 — `compose.yaml:26` `8000:8000` binds to all host interfaces.
- F5-06 — `compose.yaml:35,73,90,98` all fall back to the same *known* default Redis password.
- F5-11 — `frontend/package.json:22` `@types/node: ^26.2.0` and `package.json:34` `vite: ^8.2.1` — non-existent majors.
- F5-12 — `frontend/package.json:19,23` `eslint: ^10.8.0` and `@eslint/js: ^10.0.1` — non-existent majors.
- F5-14 — No `install.sh`; Linux operators must read `Makefile` manually.
- F5-16 — `compose.yaml:45` example token `change-me-in-prod` is in the boot-time denylist.
- F5-21 — `pyproject.toml:168-176` Pillow override comment describes a surya-ocr 0.17.x workaround that no longer applies.
- F5-24 — `.github/dependabot.yml:3-21` all four ecosystems on weekly cadence; github-actions / docker can be monthly.
- F5-08 — `.github/workflows/release.yml:36,107,111` requires a branch-protection bypass rule.
- F5-28 — `Dockerfile:72,87-88` runtime user is well-isolated (positive).

### LOW findings (one-liner each)
- F5-07 — `compose.yaml:24,69` `mem_limit: 4g` is the legacy v1 key.
- F5-09 — `test.yml:88-95` generates per-matrix SBOM artifact never consumed by release flow.
- F5-10 — `test.yml:189-191` e2e is `workflow_dispatch`-only.
- F5-13 — No `.gitattributes`.
- F5-15 — `_check_eol.ps1:1` hardcodes `D:\OmniScribe\start_app.vbs`.
- F5-17 — `compose.yaml:40` references `.env.example` but no such file exists.
- F5-18 — `scripts/fetch_datasets.py:74-91` is a `NotImplementedError` stub.
- F5-20 — `scripts/visualize_comparison.py:18-19` and `scripts/debug_alignment.py:18-20` call into the OCR pipeline with no safety rails.
- F5-23 — `pyproject.toml:115-120` `glossary` extra is heavy.
- F5-25 — `nightly.yml:55,108-114` HF Hub cache is fine (already has restore-keys) — POSITIVE.
- F5-26 — `.pre-commit-config.yaml:35-42` `uv-lock` with `--frozen=false` will rewrite `uv.lock` mid-pre-commit.
- F5-27 — `Makefile:1-48` has no `make security` or `make test-slow` targets.
- F5-29 — `install.ps1:33-40` downloads uv installer with version pinning but no SHA-256 verification.
- F5-30 — `start_app.vbs:202-203` opens the default browser unconditionally.

## Cross-cutting observations

- **"Pinned everywhere" is the project story.** The drift is in the *less-trafficked* surfaces: frontend npm versions, Compose password fallback, and the AGENTS.md text.
- **The secrets posture is solid for a personal-project scale.** `redis-password.txt` is double-ignored. The `PLACEHOLDER_AUTH_TOKENS` denylist (`security_config.py:57-98`) is the most thorough I have seen. The VBS Redis password generator *already uses PowerShell CSPRNG* (`start_app.vbs:80-92`).
- **Default = "open and friendly" is intentional and the docs acknowledge it.** This is fine for a personal/desktop app, but a `docker compose up` on a LAN-facing host will hand anyone reachable the OCR API.
- **The placeholder-token denylist is the security lynchpin.**
- **Cross-platform: Windows is first-class, Linux is Docker-first.**

## Positive findings

- **Action SHA pinning with human-readable tag comments** is consistent across all four workflows.
- **Dockerfile base image is pinned by SHA-256 digest**.
- **Multi-stage build** with builder/runtime split.
- **Non-root runtime user** with stable uid 1001 and `nologin` shell.
- **`uv sync --locked`** in both builder and runtime install lines.
- **Healthcheck on both `api` and `redis` services** in `compose.yaml:56-61,97-101`.
- **Redis password generated via PowerShell CSPRNG**, not VBScript `Rnd()`.
- **Secret-handling denylist** (`security_config.py:57-98`) — 35 placeholder values rejected at boot.
- **Dependabot covers all 4 ecosystems**: pip, npm, github-actions, docker.
- **Trivy container scan + SARIF upload**.
- **CycloneDX SBOM** generated and uploaded per matrix cell.
- **`pip-audit --ignore-vuln PYSEC-2026-311`** with a detailed risk-acceptance rationale.
- **Concurrency groups** cancel in-progress PR runs.
- **Least-privilege permissions** in all workflows.
- **`--requirepass` on the Redis service**.
- **`omniscribe-server` console script** registered correctly.
- **`scripts/dev.py`** is the only script that touches the system.

## Coverage gaps

- **Cannot read** `start_app.log` (live, may contain real tokens).
- **Cannot read** `.env` if one exists.
- **Cannot verify** the `start_app.vbs` CSPRNG output matches a real password file in production.
- **No `install.sh`** means I cannot comment on the Linux install path beyond what the `Makefile` says.
- **No `Procfile`** — Heroku-style dyno manifest is not used.
- **Cannot test** whether the SHA-pinned actions are *current*; SHA-pinning is a pin against a tag.
- **The frontend `package.json` versions** are non-existent majors — cannot tell whether they are typos, future-dated, or from a private registry mirror.

## Secret-inventory check

| Location | Has secret? | Notes |
|----------|-------------|-------|
| `.env.example` | NOT PRESENT | Referenced in `compose.yaml:40`; missing from repo |
| `compose.yaml:35,73,90,98` | DEFAULT PASSWORD FALLBACK | `omniscribe-local-dev` — *known* string |
| `compose.yaml:45` | PLACEHOLDER (commented) | `# OMNISCRIBE_AUTH_TOKEN: change-me-in-prod` — in the denylist |
| `install.ps1:33` | PINNED URL | `https://astral.sh/uv/0.11.16/install.ps1` — version-pinned, not hash-pinned |
| `start_app.vbs:64-105` | GENERATED AT RUNTIME | PowerShell CSPRNG → `redis-password.txt` |
| `start_app.log` | NOT READ | Live log |
| `redis-password.txt` | GENERATED, GITIGNORED, DOCKERIGNORED | `.gitignore:233`, `.dockerignore:33` |
| `Dockerfile` | NONE | Only `ARG UV_VERSION=0.11.16` (build-time) |
| `.github/workflows/*.yml` | `${{ secrets.GITHUB_TOKEN }}` (auto-injected) | Used in `test.yml:161` |
| `pyproject.toml` | NONE | No tokens, no API keys |
| `scripts/*.py` | NONE | Only reads `LLM_API_KEY` / `OPENAI_API_KEY` from env |
| `_check_eol.ps1:1` | NONE | Hardcoded path, not a secret |

## Container-hardening quick-check

| Concern | Status | Notes |
|---------|--------|-------|
| Non-root USER | YES | `app` uid 1001, `nologin` shell |
| Pinned base image | YES | `python:3.14-slim@sha256:ce4076…` |
| Multi-stage build | YES | builder (uv + sync) → runtime (venv only) |
| HEALTHCHECK | PARTIAL | Only in `compose.yaml:56-61`; not in the Dockerfile itself |
| Layer caching | YES | `pyproject.toml` + `uv.lock` + `LICENSE` + `README.md` copied first, then `src/` |
| Secret mounts | NO | All env-driven |
| `--requirepass` on Redis | YES | `compose.yaml:90` |
| Loopback bind for Redis host port | YES | `127.0.0.1:6379:6379` |
| Loopback bind for API host port | NO | `8000:8000` (all interfaces) — auth-token opt-in is the only mitigation |
| `mem_limit` | YES (legacy) | `4g` on `api` + `worker` |
| `restart: unless-stopped` | YES | `compose.yaml:62,79,102` |
| `EXPOSE 8000` | YES | `Dockerfile:90` |
| `.dockerignore` is comprehensive | YES | Excludes `.env*`, `redis-password.txt`, `frontend/`, `examples/`, `tests/`, agent scratch dirs |
| Build cache (GHA) | YES | `cache-from: type=gha` + `cache-to: type=gha,mode=max` |

## Cross-platform compatibility matrix

| Concern | Windows | Linux | Notes |
|---------|---------|-------|-------|
| Path separators | `pathlib` everywhere | Same | Portable |
| Line endings | No `.gitattributes` — risk of CRLF in `*.ps1`/`*.bat`/`*.vbs` on checkout | LF assumed | `_check_eol.ps1` exists *because* of pain points |
| Shell syntax | PowerShell + VBScript + cmd | Bash in CI workflows | Windows dev box vs Linux CI runner |
| File system | `os.chmod` no-op on Windows | Honors `0o600`, `0o700` | Cross-platform-fine |
| `start_app.vbs` | Native | No native equivalent; Docker Compose is the Linux path | Most-tested Windows-only surface |
| Frontend npm install | `npm ci` in `install.ps1:80-84` | Same | No platform-specific deps |
| HF Hub cache path | `~/.cache/huggingface` | Same | `nightly.yml:53-54,109-111` |
| Git autocrlf | Windows default `true` can mangle shell scripts | Default `false` (or `input`) | See F5-13 |
| Windows-specific assumptions | `start_app.vbs:30-44` `WScript.Shell.Exec` polling, `WinHttpRequest.5.1` (line 182) | N/A | These are intentional |
| `make` availability | Limited (Git Bash, WSL only) | Native | The `Makefile` is the cross-platform developer surface |
