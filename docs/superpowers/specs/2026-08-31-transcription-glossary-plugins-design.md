# Transcription + Glossary Plugins — Design (Phase C slice 3)

**Date:** 2026-08-31
**Status:** Approved design — pending implementation plan
**Predecessors:** `2026-08-30-documents-plugin-extraction-export-design.md` (slice 1), `2026-08-30-translate-plugin-translation-routes-design.md` (slice 2)

## 1. Goal

Rebuild the two remaining deferred HTTP surfaces as harness plugins, finishing Phase C:

- **`transcribe` plugin** — `POST /api/transcribe` + `GET/POST /api/config/transcription` + back-compat `GET /api/models/transcription`.
- **`glossary` plugin** — the 9 glossary-import/library routes, with large imports dispatched on the harness JobQueue.

Plus one ride-along: a token-redeeming translate result route (closes the slice-2 follow-up "async translate results are write-only").

## 2. Decisions (user-approved 2026-08-31)

1. Both surfaces in one slice (~13 tasks).
2. **Contract drifts → backend accepts both shapes**: the rebuilt glossary import accepts the old JSON source envelope *and* the Flutter client's multipart/JSON-body variants. No client changes.
3. **Glossary async → JobQueue parity**: the 5,000-entry sync threshold is kept verbatim; large imports dispatch on the harness JobQueue via a third runner producer.
4. **Lexicon seam → lazy store, 503 routes**: the glossary plugin always boots; `LexiconStore` construction is guarded, and lexicon-backed routes 503 with the old install hint when the `lexicon` extra is missing.
5. **Transcription config → plugin-owned store**: the transcription plugin owns its config routes with an in-memory store (mirroring the OCR plugin's `/api/config` pattern). OCR's config surface is untouched.
6. **Packaging → two plugins** (`plugins/transcribe/`, `plugins/glossary/`), boot rows 11 and 12 (`ocr` → 13).

## 3. Verified environment facts

All facts verified in source on 2026-08-31 (old-contract facts via `git show 44ef123^:...`; client facts are current `client/lib` code):

- **Old transcription router** (`44ef123^:src/omniscribe/api/routers/transcription.py`, 194 lines): 3 routes, all synchronous, no job dispatch, no status polling. Progress was WS frames via the old manager — **not rebuilt** (see §8 deviations).
- **`TranscriptionJobResponse`** (`44ef123^:api/schemas/responses.py:209-220`): `text: str`, `language: str|None`, `duration: float|None`, `text_artifact_id/token: str|None`, `metadata_artifact_id/token: str|None`, `job_id: str|None`, `segments: list[dict] = []`.
- **`TranscriptionConfigResponse`** (responses.py:195-206): `transcription_api_base: str`, `transcription_api_key: str` (masked), `transcription_model: str`, `transcription_engine: str`, `transcription_auth_token: str|None`, `language: str|None`, `prompt: str|None`, `temperature: float = 0.0`.
- **Transcribe form fields** (`44ef123^` transcription.py:41+): multipart `file: UploadFile` (required) + optional form fields `model, engine, api_base, api_key, language, prompt` (str|None), `temperature: float = Form(0.0)`, `channel_id: str|None`. Config fallback chain per field: form → config store → defaults (`transcription_api_base="https://api.openai.com/v1"`, `transcription_engine="api"`, `transcription_model="whisper-1"`).
- **Core transcription is import-safe without the extra**: `core/transcription/__init__.py` eagerly imports all modules but `local_engine.py` imports `faster_whisper` lazily inside the method (raises `TranscriptionError(status_code=503)`). `core/transcription/factory.py::get_transcription_engine(engine_type="api", model="whisper-1", api_base=..., api_key=...)` — engine map: `api|whisper_api → GenericAudioAPIEngine`, `local|whisper_local → WhisperLocalEngine`, `auto → local if faster-whisper importable else api`. Client `TranscriptionEngineType` enum values: `api, whisper_api, local, whisper_local, auto` (default `auto`) — all handled by the factory.
- **`core/transcription/types.py::TranscriptionResult`** carries `text, language, duration, segments`; has `to_document_result()` (pinned block metadata `start_time`/`end_time`).
- **`validate_audio_input(filename, content_type, file_size)`** → `AudioValidationError` (bad extension → 415 semantics, oversize → 413 semantics; both surfaced as 400 `bad_request` envelopes in the rebuild — see §7).
- **Old glossary schemas** (`44ef123^:api/schemas/requests.py:438-500`): `GlossaryFormat` StrEnum (`csv, tsv, xliff, tbx, tmx, git_glossary, sql_table, json_pairs`); `GlossaryImportSource` (extra="forbid", fields: `format` + `text, inline_bytes_b64, url, git_url, git_ref="HEAD", git_path="GLOSSARY.md", git_credentials, sql_dsn, sql_source_table, sql_target_table, sql_source_col="source", sql_target_col="target", sql_where, encoding, max_entries(1..1_000_000), name(≤200)` with strip validators); `GlossaryImportRequest` (extra="forbid": `source`, `channel_id`, `session_token`); `GlossaryListItem` (`id, name, format, source_uri, encoding, entry_count≥0, enabled=True, priority=0, group="default"`).
- **`GlossaryImportJobResponse`**: `job_id, format, name, entry_count, warnings: list, queued: bool` — sync path returns the real counts with `queued: false`; async returns `entry_count: 0, warnings: [], queued: true`.
- **`SYNC_THRESHOLD = 5_000`** (verbatim, `44ef123^:glossary_imports.py`); estimate via `_entry_count_estimate(kwargs)` (recover verbatim).
- **`/api/glossary/import/url`** (old): query params `url (required, ≥1), name (≤200), encoding, format` (alias `format_param`); SSRF-check the URL; extension→format map `csv, tsv, xlf|xliff, tbx, tmx, json` (inference failure → 422 with "Could not infer format from URL. Pass ?format=csv|tsv|xliff|tbx|tmx|json_pairs."); fetches bytes then delegates to the import path as an `inline_bytes_b64` source.
- **Old library routes** (9 total, `44ef123^:glossary_imports.py:314-464`): `POST /api/glossary/import`, `POST /api/glossary/import/url`, `GET /api/glossary/library`, `POST /api/glossary/library/{id}/enable`, `POST /api/glossary/library/reorder`, `DELETE /api/glossary/library/{id}`, `GET /api/glossary/library/preview`, `GET /api/glossary/library/{id}/entries`, `GET /api/glossary/library/merged`.
- **Core lexicon**: `LexiconStore` Protocol (`core/lexicon/store.py:119-145`: `save_glossary/list_glossaries/toggle_glossary/reorder_glossaries/delete_glossary/get_glossary/list_entries`); helpers `merged_enabled_glossary(store)`, `preview(store)`, `GlossaryNotFoundError` (`core/lexicon/helpers.py`). **`LanceDBLexiconStore` hard-imports `pyarrow` at module top (`lancedb_store.py:33`) — importing the module fails without the `lexicon` extra.** No harness plugin registers a lexicon service today.
- **Core glossary parsers**: `core/glossary_sources/` — `parse(format=..., **kwargs) -> GlossaryImportSummary(entries, warnings, source_uri, encoding)`, `PARSERS` registry, `FormatNotAvailableError` (→ 503 with install hint), `GlossaryImportLimitError` (→ 400 "Too many entries (max N)").
- **Flutter client** (`client/lib/data/repositories/feature_repository.dart`): `transcribe()` multipart → `ApiConstants.transcribe` with `TranscriptionRequest.toJson()` `{model, engine, api_base, language, prompt, temperature}` (engine default `auto`); parses `TranscriptionResponse` incl. `segments` + all four artifact fields. Glossary: `GET library`, `GET {id}/entries` (accepts raw list **or** `{entries:[...]}`), `GET merged`, `GET preview`, `POST {id}/enable {enabled}`, `DELETE {id}`, `POST reorder {ordered_ids}`; `importGlossaryFile` posts **multipart** (`file` + optional `channel_id`) to `/api/glossary/import`; `importGlossaryUrl` posts **JSON body** `{url, format, name, channel_id}` to `/api/glossary/import/url`. `GlossaryImportJobResponse.fromJson` parses the import response; the client never polls a glossary status route.
- **Client transcription settings** (`client/lib/data/repositories/config_repository.dart:65-70`): returns `[]` for the `transcription` namespace today — the settings screen expects the config routes to come back.
- **Harness seams available**: `ArtifactStore` (token-bound, `put`→`ArtifactHandle(id, token)`), `JobQueue` + claim-time runner dispatch via payload-class `runner_protocol` marker (`plugins/jobs.py::_resolve_runner` — `TranslationJobRunner` precedent), `ProgressService` (unused by these surfaces), error envelope `{"error", "detail"}` via `JSONResponse`, `check_ssrf_target_sync` (`utils/security.py`), plugin pattern per `plugins/translate/` and `plugins/documents/`.
- **Old config-store write gating**: the old `POST /api/config/transcription` returned 503 on the memory backend (`_ConfigBackendIncompatible`). **Not carried over** — the rebuilt plugin-owned store is in-memory and always writable (matches the current OCR `/api/config` semantics). Documented deviation, §8.

## 4. Transcribe plugin (`src/omniscribe/plugins/transcribe/`)

Package: `schemas.py`, `service.py`, `config_store.py`, `routes.py`, `plugin.py`, `__init__.py`.

### 4.1 Routes

| Route | Contract |
|---|---|
| `POST /api/transcribe` | multipart, verbatim field list (§3). Sync. Returns `TranscriptionJobResponse` shape exactly. |
| `GET /api/config/transcription` | `TranscriptionConfigResponse` shape; `api_key` masked (old `_mask_api_key` behavior — never clear text; old surface returned `"..."`). |
| `POST /api/config/transcription` | Body: optional `api_base, api_key (or transcription_api_key alias), model, engine, language, prompt, temperature (0.0–2.0)`; extra="forbid". Writes through, returns the masked read shape. Always writable (in-memory store). |
| `GET /api/models/transcription` | Back-compat discovery route, re-homed from `44ef123^:api/routers/models.py:271-320`: read `transcription_api_base`/`transcription_api_key` from the plugin config store → SSRF-check (`is_ssrf_target`; blocked → `ModelsResponse(fallback)`), probe `{base}/models`, `{base}/v1/models`, `{base}/api/tags` (5s httpx timeout, bearer header unless key == "lm-studio"), extract ids via the provider-manager helper; any failure/empty → the pinned 6-model whisper fallback list (`whisper-1, whisper-large-v3, whisper-medium, whisper-base, whisper-small, whisper-tiny`). Response `{"models": [...]}`. |

### 4.2 Service flow (`POST /api/transcribe`)

1. Read/validate the upload bytes (`await file.read()`); resolve engine settings: per-field chain **form → plugin config store → default** (§3).
2. `check_ssrf_target_sync(api_base)` — **override only** (translate precedent): the SSRF check runs when the caller supplied `api_base`; the config-store/default values are trusted operator config.
3. `validate_audio_input(filename, content_type, len(bytes))` → failure: 400 `bad_request` envelope carrying the old 415/413 reason in `detail` (see §7 status mapping).
4. `get_transcription_engine(engine, model, api_base, api_key)` → `await engine.transcribe(bytes, filename, language, prompt, temperature)` → `TranscriptionResult`.
5. Store two artifacts via `ArtifactStore`: text (`result.text`, `content_type="text/plain"`) and metadata (JSON: language/duration/segments/etc.). **Tokens ARE returned in this response** — it is the direct response to the uploader (same trust posture as the documents plugin's extract response).
6. Response: `TranscriptionJobResponse` shape with `job_id=None` (sync path; the old surface set it from the async record when one existed — none here), `segments` verbatim from the result.

Errors: `TranscriptionError` from core → 503 `backend_unavailable` (message verbatim from core, e.g. the faster-whisper install hint); unexpected engine exception → 502 `ai_error` ("The AI service request failed."); validation → 400; ssrf → 403 `ssrf_blocked`.

### 4.3 Config store

`config_store.py`: in-memory dict seeded at apply() from `RuntimeSettings`/env where a `transcription_auth_token` setting exists (the only core transcription setting, `config.py:146`), else defaults (§3). GET returns the masked read shape; POST validates temperature bounds (422 outside 0.0–2.0 via Pydantic), writes through. Masking helper recovered verbatim from `44ef123^` (`_mask_api_key`).

## 5. Glossary plugin (`src/omniscribe/plugins/glossary/`)

Package: `schemas.py`, `service.py`, `runner.py` (or in service.py — planner's call, keep files focused), `routes.py`, `plugin.py`, `__init__.py`.

### 5.1 Lexicon seam

- `_get_store() -> LexiconStore | None`: lazily constructs ONE `LanceDBLexiconStore` (module-level singleton) inside `try/ ImportError`; returns `None` when the `lexicon` extra is missing.
- Every lexicon-backed route: `store is None` → 503 `backend_unavailable`, detail `"Lexicon store is not available. Install with: uv sync --extra lexicon"` (old string verbatim).
- `GlossaryNotFoundError` → 404 `not_found`.

### 5.2 Import routes (dual-shape)

One route function branches on `Content-Type` (via the raw `Request`):

- `POST /api/glossary/import`
  - `application/json` → parse `GlossaryImportRequest` (old envelope, extra="forbid"); `channel_id`/`session_token` accepted-and-ignored.
  - `multipart/form-data` → fields `file` (UploadFile, required), optional `format` (StrEnum), `name` (≤200), `channel_id`. Bytes → `inline_bytes_b64`; format inferred from the filename extension via the §3 extension map (no extension + no `format` → 422 with the old inference-failure wording, adapted to name the filename).
- `POST /api/glossary/import/url`
  - Query params (old): `url, name, encoding, format`.
  - JSON body (client): `{url, format, name, channel_id}` — `channel_id` ignored.
  - Both converge on the same flow: SSRF-check `url` (403 `ssrf_blocked`), infer format if absent (§3 map; failure → 422 old wording), fetch bytes (fetch helper recovered from the old `api/services/http_fetch.py`, adapted to `utils/` conventions; fetch failure → 502 `ai_error` with "Failed to fetch URL: …" detail — old used 503 `BackendUnavailable`, the rebuild maps network fetch failures to `ai_error`; §8), delegate to the import path as `inline_bytes_b64`.

### 5.3 Dispatch

- `_entry_count_estimate(kwargs)` recovered verbatim; `≤ SYNC_THRESHOLD (5000)` → sync: `parse(format=..., **kwargs)` → `store.save_glossary(...)` → `GlossaryImportJobResponse{..., queued: false}` with real counts.
- Estimate > threshold → `_GlossaryImportPayload` (frozen dataclass: `submission_id`, `source: GlossaryImportSource`-equivalent kwargs, `name`) submitted to the injected `JobQueue` with `request_meta={"submission_id", "name"}` → response `{job_id, format, name, entry_count: 0, warnings: [], queued: true}`.
- **`GlossaryJobRunner`** Protocol (same `__call__` shape as `JobRunner`/`TranslationJobRunner`) added to `plugins/jobs.py`; `_GlossaryImportPayload` carries `runner_protocol = GlossaryJobRunner` (marker mechanism, third producer). Runner body: build kwargs → `parse` → `save_glossary` → `JobOutcome(blob=json.dumps({format, name, entry_count, warnings}), content_type="application/json")`. Errors inside the runner fail the JobRecord (queue standard).

### 5.4 Library routes

1:1 over the injected store (§3 Protocol methods): list → `list_glossaries` (`list[GlossaryListItem]`); enable → `toggle_glossary(id, enabled)` with body `{"enabled": bool}`; reorder → `reorder_glossaries(ordered_ids)` with body `{"ordered_ids": [...]}`; delete → `delete_glossary(id)` returning 200 with the old success shape (exact response pinned from `44ef123^` during planning; old tests assert success + subsequent list exclusion); preview → `preview(store)` (conflicts shape verbatim); entries → `{"entries": [...]}` (old shape — the client accepts both it and a raw list; ship the old shape); merged → `merged_enabled_glossary(store)`.

## 6. Ride-along: translate result redeem route

`GET /api/translate/result/{job_id}?token=<artifact_token>` in the translate plugin's router:

- Resolve the JobRecord via the queue; unknown job → 404 `not_found`.
- Job not `complete`, or record lacks `result_artifact_id` → 404 `not_found`.
- `token` query param must equal the record's `result_artifact_token`; mismatch/missing → 404 `not_found` (same wrong-token→404 semantics as the documents fetch route; no existence leak).
- Success: stream/return the translated text artifact (`GET /api/text/{id}`-equivalent payload, `text/plain`) — keeps C-3/H-3 (token required) while making async results usable. +3 tests (unknown job, wrong token, happy path).

## 7. Error semantics

| Condition | Status | Envelope |
|---|---|---|
| Malformed body / unknown field / temperature out of range | 422 | FastAPI native (surface-wide) |
| Missing source text/bytes/file; audio validation failure (bad ext / oversize); max entries exceeded | 400 `bad_request` | `{"error","detail"}` (detail carries the old wording, e.g. "Too many entries (max N)") |
| SSRF-blocked url / git_url / api_base override | 403 `ssrf_blocked` | envelope |
| Unknown glossary id / lexicon record | 404 `not_found` | envelope |
| Translate result: unknown job / wrong token / not complete | 404 `not_found` | envelope |
| Optional dep missing (faster-whisper, lexicon extra) / TranscriptionError | 503 `backend_unavailable` | envelope, old install-hint details verbatim |
| Engine/LLM/network failure | 502 `ai_error` | envelope, static or old wording |
| URL-format inference failure | 422 | envelope (old wording) |

## 8. Deliberate deviations from the old server

1. **No WS progress frames** for transcription or glossary imports (old: coarse state transitions over the channel). `channel_id` accepted-and-ignored everywhere (translate precedent). Job visibility rides the existing `/api/jobs` surface.
2. **Config writes always allowed** (old 503'd on the memory backend) — matches current OCR config semantics.
3. **URL-fetch failures → 502 `ai_error`** (old: 503 `BackendUnavailable`) — network failures are not "feature unavailable" in the rebuilt taxonomy.
4. **Audio-validation failures → 400** (old mapped extension/size errors to 415/413) — the rebuild keeps the two-digit error taxonomy consistent; details carry the old reason strings.
5. **`GET /api/models/transcription`** may delegate differently than the old monolith depending on what the old route actually returned — pinned during planning from `44ef123^`, not guessed here.

## 9. Testing

- **Transcription** (`tests/plugins/test_transcribe_service.py`, `tests/routers/test_transcribe_routes.py`): engine factory map (5 enum values incl. `auto` fallback), service flow with stubbed engine (artifacts stored, response shape, `job_id=None`), 415/413 validation → 400, ssrf override → 403, TranscriptionError → 503, unexpected → 502; router: 200 contract with all fields, config GET masked / POST roundtrip + temperature 422, models route shape.
- **Glossary** (`tests/plugins/test_glossary_service.py`, `tests/routers/test_glossary_routes.py`): ported old pins — empty library `[]`, json_pairs sync import (`entry_count==1, format=="json_pairs"`), csv `inline_bytes_b64`, multipart file import (client shape), JSON-body URL import (client shape) + query-param URL import (old shape), 422 no text/bytes, 400 max_entries, git SSRF 403, toggle persists / unknown 404, delete, preview conflicts, entries list, merged; async-threshold test (estimate > 5000 → `queued: true` + job lands on the queue; runner test with stubbed parse/store); lexicon-missing 503 (store seam stubbed to None).
- **Boot** (`tests/plugins/test_boot_config.py`, `tests/harness/`): thirteen rows (transcribe 11, glossary 12, ocr 13), router count 8, per-plugin boot tests; conftest test tree updated to match.
- **Ride-along**: 3 result-route tests (unknown job 404, wrong token 404, happy path via seeded record + artifact).
- **Snapshot**: `tests/openapi.json` regenerated, additions-only (13 new paths: `/api/transcribe`, `/api/config/transcription`, `/api/models/transcription`, the 9 `/api/glossary*` paths, `/api/translate/result/{job_id}` + request schemas).
- **Gate**: full fast tier + ruff/format/mypy; real-server smoke of the new surfaces.

## 10. Docs updates

- AGENTS.md: boot table rows 11/12 (ocr → 13), plugins enumeration thirteen, deferred-capabilities list — transcription and glossary-import removed (**Phase C complete**: deferred list shrinks to auth/rate-limit/upload-size middlewares, Redis state backend, model pre-flight), Key Files rows for both packages, "Last updated" stamps.
- ARCHITECTURE.md: plugin entries + route-surface rows; deferred-routes paragraph updated.
- CHANGELOG.md: Unreleased entry for both plugins + the translate result route.
- README/DEPLOYMENT: verify translation/transcription/glossary claims against code; `.env.example` verified only.
- Web Notes: the "translation core intact but routes deferred" note and the transcription/glossary deferred notes become "shipped".

## 11. Out of scope

- WebSocket progress frames for any of these surfaces (tracked deviation §8.1).
- Persisted (file/SQLite-backed) transcription config store.
- LexiconStore backend alternatives (Redis state backend remains deferred separately).
- Any Flutter client changes (frozen contract; drifts handled backend-side).
