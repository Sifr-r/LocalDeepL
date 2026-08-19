# Domain 2 Security & Architectural Audit Report
**Scope:** API, Security & Distributed State  
**Audited Subsystems:** `server.py`, `api/routers/*`, `api/services/*`, `api/tasks.py`, `api/schemas/*`, `utils/security.py`, `core/glossary_sources/*`  
**Date:** August 18, 2026  
**Auditor:** Lead API & Security Auditor (OmniScribe Architecture Group)

---

## Executive Summary

An exhaustive security, architectural parity, and vulnerability audit was conducted across Domain 2 of OmniScribe. The audit identified **13 findings** across Authentication & Authorization, SSRF Defense, State Backend Parity, WebSocket/SSE Resilience, and Denial-of-Service / Memory Management.

### Finding Severity Matrix

| Severity | Count | IDs | Key Impact |
| :--- | :---: | :--- | :--- |
| **CRITICAL** | 2 | D2-01, D2-02 | Management route auth bypass; Total OCR pipeline failure under SQLite/Redis backends |
| **HIGH** | 5 | D2-03, D2-04, D2-05, D2-06, D2-07 | Secret leakage, algorithmic DoS, internal network scanning/SSRF, HTTP stream corruption, broken Celery async jobs |
| **MEDIUM** | 4 | D2-08, D2-09, D2-10, D2-11 | CLI flag injection, API key corruption, Redis key collisions, cloud metadata bypass |
| **LOW** | 2 | D2-12, D2-13 | Event loop error spam, disk clutter on custom artifact directories |

---

## Detailed Audit Findings

### D2-01 [CRITICAL]: Management Route Authentication Bypass when Global Token is Unset
- **Severity:** `CRITICAL`
- **Location:** [`src/omniscribe/api/services/security_middleware.py:364-388`](file:///d:/OmniScribe/src/omniscribe/api/services/security_middleware.py#L364-L388)
- **CWE:** CWE-306, CWE-285
- **Impact**: When only subsystem tokens (`OMNISCRIBE_OCR_AUTH_TOKEN`, etc.) are configured, `/api/config`, `/api/providers`, and `/api/jobs` bypass authentication entirely.
- **Fix**: Require active subsystem tokens for management routes if global token is unset.

---

### D2-02 [CRITICAL]: `JobHistory.record()` Signature Mismatch Crashing OCR Pipeline with Persistent Backends
- **Severity:** `CRITICAL`
- **Location:** [`src/omniscribe/api/services/state_backend_sqlite.py:343`](file:///d:/OmniScribe/src/omniscribe/api/services/state_backend_sqlite.py#L343), [`src/omniscribe/api/services/state_backend_redis.py:204`](file:///d:/OmniScribe/src/omniscribe/api/services/state_backend_redis.py#L204), [`src/omniscribe/api/routers/ocr.py:167`](file:///d:/OmniScribe/src/omniscribe/api/routers/ocr.py#L167)
- **CWE:** CWE-440
- **Impact**: `TypeError: unexpected keyword argument 'text_artifact_id'` crashes OCR completion on SQLite or Redis backend.
- **Fix**: Add `text_artifact_id: str | None = None` to `record()` signatures in SQLite and Redis backends.

---

### D2-03 [HIGH]: Token Leakage via URL Query Parameters in Artifact and Job Result Routes
- **Severity:** `HIGH`
- **Location:** [`src/omniscribe/api/routers/common.py:30-35`](file:///d:/OmniScribe/src/omniscribe/api/routers/common.py#L30-L35), [`src/omniscribe/api/routers/artifacts.py:33`](file:///d:/OmniScribe/src/omniscribe/api/routers/artifacts.py#L33), [`src/omniscribe/api/routers/jobs.py:85`](file:///d:/OmniScribe/src/omniscribe/api/routers/jobs.py#L85)
- **CWE:** CWE-598
- **Impact**: Secret artifact tokens logged in plaintext in reverse proxy and browser logs.
- **Fix**: Deprecate query string token extraction in favor of `Authorization: Bearer` and `X-Artifact-Token` headers.

---

### D2-04 [HIGH]: Unbounded Memory Leak and $O(N)$ Algorithmic DoS in `RateLimitMiddleware`
- **Severity:** `HIGH`
- **Location:** [`src/omniscribe/api/services/security_middleware.py:737-750`](file:///d:/OmniScribe/src/omniscribe/api/services/security_middleware.py#L737-L750)
- **CWE:** CWE-400, CWE-770
- **Impact**: Inactive client IP entries are never pruned; full dictionary iteration blocks asyncio event loop on every request.
- **Fix**: Cap tracking table to 10,000 entries with LRU/bounded eviction.

---

### D2-05 [HIGH]: Missing SSRF Validation on `sql_dsn` in SQL Glossary Importer
- **Severity:** `HIGH`
- **Location:** [`src/omniscribe/api/routers/glossary_imports.py:162-190`](file:///d:/OmniScribe/src/omniscribe/api/routers/glossary_imports.py#L162-L190), [`src/omniscribe/core/glossary_sources/sql_table.py:21-56`](file:///d:/OmniScribe/src/omniscribe/core/glossary_sources/sql_table.py#L21-L56)
- **CWE:** CWE-918
- **Impact**: Port scanning of internal infrastructure and local arbitrary file read via SQLite DSN.
- **Fix**: Validate host against `is_ssrf_target(host)` and constrain SQLite file paths.

---

### D2-06 [HIGH]: Flawed HTTP Parser in `_PinnedIPTransport` Corrupting Chunked/Gzip Responses
- **Severity:** `HIGH`
- **Location:** [`src/omniscribe/api/services/http_fetch.py:49-185`](file:///d:/OmniScribe/src/omniscribe/api/services/http_fetch.py#L49-L185)
- **Impact**: Corrupts text when importing glossaries from CDN/chunked endpoints.
- **Fix**: Use `httpx`/`httpcore` streaming transport with custom socket resolver.

---

### D2-07 [HIGH]: Out-of-Process State Isolation Failure in Celery Translation and Glossary Tasks
- **Severity:** `HIGH`
- **Location:** [`src/omniscribe/api/tasks.py:68-82,140-144,203-209`](file:///d:/OmniScribe/src/omniscribe/api/tasks.py#L68-L82)
- **Impact**: In-memory backend throws `ArtifactNotFoundError` on Celery workers; WebSocket frames silently dropped across processes.
- **Fix**: Require shared state backend for Celery and route WebSocket frames through Redis Pub/Sub.

---

### D2-08 [MEDIUM]: CLI Option Injection Vulnerability in Git Glossary Importer
- **Severity:** `MEDIUM`
- **Location:** [`src/omniscribe/core/glossary_sources/git_repo.py:44-58`](file:///d:/OmniScribe/src/omniscribe/core/glossary_sources/git_repo.py#L44-L58)
- **Impact**: Flag injection in `git archive`.
- **Fix**: Disallow leading hyphens in `ref` and add `--` delimiter.

---

### D2-09 [MEDIUM]: Masked API Key Placeholders Corrupting Stored Provider Credentials
- **Severity:** `MEDIUM`
- **Location:** [`src/omniscribe/api/services/provider_manager.py:507-526`](file:///d:/OmniScribe/src/omniscribe/api/services/provider_manager.py#L507-L526)
- **Impact**: Masked placeholder `"sk-1...abcd"` overwrites real API keys on provider updates.
- **Fix**: Preserve existing key when masked placeholder pattern is detected.

---

### D2-10 [MEDIUM]: Cross-Store Expiration Collision in `RedisTextArtifactStore`
- **Severity:** `MEDIUM`
- **Location:** [`src/omniscribe/api/services/state_backend_redis.py:43,67-99`](file:///d:/OmniScribe/src/omniscribe/api/services/state_backend_redis.py#L43)
- **Impact**: Shared `EXPIRATIONS_KEY` causes cross-store eviction collisions; `len()` returns 0.
- **Fix**: Namespace expiration keys per store and implement `zcard` checking.

---

### D2-11 [MEDIUM]: IMDS and CGNAT IP Range Exposure under `ALLOW_SSRF_LOCAL=true`
- **Severity:** `MEDIUM`
- **Location:** [`src/omniscribe/utils/security.py:32-46,120-134`](file:///d:/OmniScribe/src/omniscribe/utils/security.py#L32-L46)
- **Impact**: Cloud metadata `169.254.169.254` reachable under local development settings.
- **Fix**: Unconditionally block `169.254.0.0/16`, `100.64.0.0/10`, and `0.0.0.0/8`.

---

### D2-12 [LOW]: Unhandled `asyncio.QueueFull` Exception in SSE Event Stream Broker
- **Severity:** `LOW`
- **Location:** [`src/omniscribe/api/routers/events.py:71-79`](file:///d:/OmniScribe/src/omniscribe/api/routers/events.py#L71-L79)
- **Fix**: Drop oldest frame on queue full.

---

### D2-13 [LOW]: `cleanup_files` Fails on Custom `OMNISCRIBE_ARTIFACT_DIR`
- **Severity:** `LOW`
- **Location:** [`src/omniscribe/api/services/security.py:190-203`](file:///d:/OmniScribe/src/omniscribe/api/services/security.py#L190-L203)
- **Fix**: Allow cleaning files in `load_settings().artifact_base_dir`.
