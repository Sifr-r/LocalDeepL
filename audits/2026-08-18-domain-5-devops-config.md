# Domain 5 Audit Report: DevOps, Packaging & Environment Hardening

**Date:** 2026-08-18  
**Auditor:** Lead DevOps & Infrastructure Security Auditor  
**Domain:** Domain 5 — DevOps, Packaging & Environment Hardening  
**Target Repository:** OmniScribe (`https://github.com/Sifr-r/OmniScribe`)  
**Scope:** `Dockerfile`, `compose.yaml`, `.dockerignore`, `.env`, `.env.example`, `install.bat`, `install.ps1`, `install.sh`, `start_app.vbs`, `stop_app.bat`, `Makefile`, `pyproject.toml`, `frontend/package.json`, `.github/workflows/*`, `.github/dependabot.yml`, `.gitattributes`, `.gitignore`, `.pre-commit-config.yaml`, `scripts/dev.py`, `SECURITY.md`, `DEPLOYMENT.md`, `README.md`.

---

## Executive Summary

An exhaustive audit of OmniScribe's DevOps, packaging, and environment hardening surface was conducted across 30+ configuration files, deployment scripts, CI/CD pipelines, container specifications, and documentation manifests.

OmniScribe demonstrates exceptional infrastructure hygiene: immutable SHA pinning across all GitHub Actions, Trivy/Semgrep/pip-audit/SBOM automation, unprivileged non-root container users, and hardened secret denylists.

However, several critical and high-priority infrastructure and container hardening issues were uncovered:

### Findings Matrix

| ID | Severity | Area | File & Line | Summary |
|---|---|---|---|---|
| **D5-01** | **HIGH** | Container / Healthcheck | `compose.yaml:101-124`, `Dockerfile:103-104` | Worker service inherits HTTP `HEALTHCHECK`, causing healthcheck failures and restart loops. |
| **D5-02** | **MEDIUM** | Container / Optimization | `Dockerfile:81-88` | `RUN chown -R` duplicates `.venv` layer, inflating runtime image size by 1–2 GB. |
| **D5-03** | **MEDIUM** | Secrets Management | `compose.yaml:146`, `start_app.vbs:152,160,170` | Passwords passed via CLI flags expose credentials in process lists and container inspect. |
| **D5-04** | **MEDIUM** | CI / Release Automation | `.github/workflows/release.yml:101` | Release sed script uses obsolete repo name `local-deepl.git`, silently breaking README tag updates. |
| **D5-05** | **MEDIUM** | Supply Chain / Shell Parity | `install.sh:48` vs `install.ps1:50-63` | `install.sh` pipes unverified curl output to `sh` without SHA-256 checksum verification. |
| **D5-06** | **MEDIUM** | Packaging / Extras | `Dockerfile:58,62`, `install.ps1:95`, `install.sh:65` | LanceDB `lexicon` extra is missing from default syncs, silently disabling glossary RAG. |
| **D5-07** | **LOW** | Reproducibility | `Makefile:10` | `make setup` uses `npm install` instead of `npm ci`, risking `package-lock.json` mutation. |
| **D5-08** | **LOW** | Secrets & Storage Hygiene | `start_app.vbs:81,101-103` | Modulo bias in CSPRNG password generation; `redis-password.txt` lacks restricted DACLs. |
| **D5-09** | **LOW** | Container Hardening | `compose.yaml:18-151` | Missing `read_only`, `cap_drop: [ALL]`, and `no-new-privileges` security options. |
| **D5-10** | **LOW** | Persistence / Volumes | `compose.yaml:152-155`, `.dockerignore`, `.gitignore` | Missing persistent volume and gitignore/dockerignore rules for SQLite and LanceDB files. |
| **D5-11** | **LOW** | Configuration Drift | `.env.example:189-193`, `pyproject.toml:51` | Stale ChromaDB references and obsolete numpy comment in dependency manifests. |
| **D5-12** | **INFO** | Cross-Platform Portability | `.gitattributes:21-34` | Missing explicit `*.sh` and `Makefile` EOL pinning in `.gitattributes`. |

---

## Detailed Findings & Fixes

### D5-01: Celery Worker Inherits Incompatible HTTP Healthcheck (Container Crash Loop)
- **Location:** [`compose.yaml:101-124`](file:///D:/OmniScribe/compose.yaml#L101-L124), [`Dockerfile:103-104`](file:///D:/OmniScribe/Dockerfile#L103-L104)
- **Impact**: Dockerfile defines HTTP `/health` probe on port 8000; Celery worker does not listen on 8000 and is marked unhealthy, triggering restart loops under container orchestrators.
- **Fix**: Override healthcheck in `compose.yaml` with `celery -A omniscribe.api.tasks inspect ping`.

### D5-02: Layer Duplication in Dockerfile
- **Location:** [`Dockerfile:81-88`](file:///D:/OmniScribe/Dockerfile#L81-L88)
- **Impact**: `RUN chown -R app:app /app` after `COPY --from=builder /app/.venv /app/.venv` creates duplicate 1.5–2.0 GB layer in OverlayFS.
- **Fix**: Use `COPY --chown=app:app` directly.

### D5-03: Process Table & CLI Secret Exposure
- **Location:** [`start_app.vbs:152`](file:///D:/OmniScribe/start_app.vbs#L152), [`compose.yaml:146`](file:///D:/OmniScribe/compose.yaml#L146)
- **Impact**: Passwords exposed in `docker inspect` and `tasklist /v` / `Win32_Process`.
- **Fix**: Use environment variables and file mounts (`--requirepass` via `redis.conf`).

### D5-04: Release Regex Typo
- **Location:** [`.github/workflows/release.yml:101`](file:///D:/OmniScribe/.github/workflows/release.yml#L101)
- **Impact**: Sed expression matches `local-deepl.git` instead of `OmniScribe.git`, failing README tag updates on release.
- **Fix**: Update regex to `OmniScribe.git`.

### D5-06: Lexicon Extra Missing from Default Sync
- **Location:** [`Dockerfile:58`](file:///D:/OmniScribe/Dockerfile#L58), [`install.ps1:95`](file:///D:/OmniScribe/install.ps1#L95), [`install.sh:65`](file:///D:/OmniScribe/install.sh#L65)
- **Impact**: `uv sync` without `--extra lexicon` leaves LanceDB uninstalled; translation RAG falls back to empty context.
- **Fix**: Include `--extra lexicon` in default sync commands.
