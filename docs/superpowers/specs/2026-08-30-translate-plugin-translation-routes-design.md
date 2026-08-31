# Translate Plugin — Phase C Slice 2: Translation Routes Rebuild

> **For agentic workers:** This spec rebuilds the deferred translation HTTP
> surface as a new `translate` boot plugin. The Flutter client already ships
> the translation UI and repository calls; the backend must serve the
> existing client contract with zero client changes. Slice 1 (extraction +
> export, `documents` plugin) is complete.

**Date:** 2026-08-30
**Status:** Approved — ready for implementation plan
**Owner:** rahin2uddin
**Parent scope:** Phase C of the Flutter takeover. Remaining after this
slice: transcription route, glossary-import routes.

## Context

The Cordis harness rebuild deleted the legacy `src/omniscribe/api/`
namespace without rebuilding its translation routes. The Flutter client
still calls four of them (constants frozen in
`client/lib/core/constants/api_constants.dart:59-64`):

| Client constant | Route | Consumer |
|---|---|---|
| `translate` | `POST /api/translate` | `feature_repository.dart:68-107`, sync wait |
| `translateAsync` | `POST /api/translate/async` | submit, then poll |
| `translationStatus(id)` | `GET /api/translate/status/{job_id}` | `features_notifier.dart` — `Timer.periodic(2s)` loop |
| `translateNllb` | `POST /api/translate/nllb` | sync wait |

The client's `TranslationJobStatusResponse` reads `job_id`, `state`
(falls back to `status`, else `'PENDING'`), `status`, `result` (dynamic),
`error`, `detail` and stops polling on `SUCCESS`/`COMPLETED` or
`FAILURE`/`FAILED`/`error != null` — state vocabulary must match.

The pre-rebuild server behavior was recovered from `44ef123^`
(`api/routers/translation.py`, `api/schemas/requests.py`,
`api/services/ai.py`, `api/celery_app.py`, `api/tasks.py`) and the old
contract tests from `e6b7b89^`.

**Async dispatch decision (user-approved):** the old path was Celery +
Redis — the exact stack broken in `compose.yaml` since the harness rebuild
(audit finding #2: `celery -A omniscribe.api.tasks` targets a deleted
namespace). This slice serves `/api/translate/async` through the existing
harness `JobQueue` (the same pattern as `POST /api/process/async`) and
retires the dead Celery surfaces.

## Goals

1. New `translate` boot plugin (`src/omniscribe/plugins/translate/`)
   serving the four client-frozen routes, contract-compatible with the
   current Flutter client — no client changes.
2. Async translation via the harness `JobQueue` with a
   `TranslationJobRunner` resolved at claim time (OCR pattern).
3. Verbatim re-home of the sync translation service from the deleted
   `api/services/ai.py` (`translate_text` + `build_translation_prompt` +
   `TRANSLATION_SYSTEM_MESSAGE` — the latter already lives in
   `core/translate/workflow.py`).
4. Tree-aware async translation through `core/translate/tree.translate_tree`
   with `EntityMemory`, parsed `Glossary`, and optional dual translator;
   translated text stored as a token-bound artifact (no sidecar writes).
5. Retire the broken Celery compose service and `start_app.vbs` window.
6. Router/service/schema tests + docs updates.

## Non-Goals

- `POST /api/translate/tree` and `POST /api/glossary` — the client has no
  constants for them (the Tree-Aware UI switch is unwired local state);
  glossary routes belong to the glossary slice.
- WebSocket chunk frames / `channel_id` progress — the client polls HTTP
  and never sets `channel_id`. JobQueue lifecycle events fire as usual.
- Removing Celery from the `async-translation` extra (recorded as tech
  debt; the extra also carries other deps).
- Redis state backend, auth middlewares (separate waves).
- Glossary injection into the **sync** route — the old `translate_text`
  accepted `glossary`/`glossary_text` fields but never used them; that
  legacy behavior is preserved verbatim (documented tech debt). Glossary
  is used on the async/tree path only, as before.

## Verified environment facts

Pinned so the implementation plan does not re-derive them:

- **JobQueue** (`plugins/jobs.py`): `await queue.submit(payload,
  request_meta={...}) -> JobHandle(job_id, status_url)`. `JobRunner`
  Protocol: `async def __call__(self, request: Any) -> JobOutcome`;
  resolved at claim time via `ctx.inject(JobRunner)`; the plugin
  registers it with `ctx.service(JobRunner, service.run_translate_job)`.
  `JobStatus = Literal["queued", "running", "complete", "error",
  "cancelled"]`; `JobOutcome(blob: bytes, content_type: str)`.
- **OCR async pattern to mirror** (`plugins/ocr/service.py:169-203`):
  service keeps a bounded `submission_id → job_id` dict; `run_job`
  validates the payload type and returns `JobOutcome`. Translate mirrors
  this and additionally records a client-facing result summary dict in
  its own bounded `job_id → result` map at completion (the status route
  reads job state from the queue records and the result from this map —
  no artifact round-trip needed for status).
- **`run_translation(text, target_language="English", settings=None) -> str`**
  (`core/translate/workflow.py:170`) — sync, chunked LangGraph workflow,
  `TranslationSettings.from_env()`, raises `AsyncTranslationUnavailable`
  (workflow.py:77) when LangGraph is missing.
- **`translate_tree(tree, *, target_language, translator, settings=None,
  glossary=None, memory=None, sliding_window_words=80, dual_translate=False,
  second_translator=None, on_translate_chunk=None) -> DocumentTree`**
  (`core/translate/tree.py:68`) — async; `translator(prompt,
  target_language) -> str` is the only LLM hook (sync or async).
- **`EntityMemory`** (`core/translate/entity_memory.py:101`) — dataclass
  with `add_text(text)` / `to_prompt_block()`.
- **`Glossary`** (`core/translate/glossary.py:35`) — classmethods
  `Glossary.from_dict(data)` (takes `{"entries": [...]}` — the old route
  wrapped `req.glossary` exactly like that), `Glossary.from_paired_lines(text)`,
  instance `to_dict()`. Old-route precedence verified: `entries` wins,
  else `glossary_text`, else no glossary.
- **`resolve_nllb_code(language)`** (`core/translate/nllb.py:35`) never
  raises: known languages map via `LANGUAGE_CODE_MAP`, code-like strings
  pass through, anything else falls back to `"eng_Latn"` (verbatim).
- **`NLLBEngine`** (`core/translate/nllb.py:53`) — `is_available() -> bool`;
  `async translate(text, target_language) -> NLLBResult(text, source_lang,
  target_lang)`; `resolve_nllb_code(language)`; `nllb` extra exists in
  `pyproject.toml` (line 103). The plugin holds the engine in a lazy
  module-level singleton (the old server re-instantiated per request —
  same contract, no model reload per call).
- **`TEMPERATURE_TRANSLATION`** in `core/llm/temperatures.py`;
  **`TRANSLATION_SYSTEM_MESSAGE`** defined at
  `core/translate/nodes.py:42`.
- **Artifact helpers for the stored text shape** — `load_pages` /
  `build_tree` in `plugins/documents/service.py` parse the stored
  `{"<page>": "<lines joined by \n>"}` blob and build a `DocumentTree`.
  The translate plugin imports these two helpers from
  `plugins.documents.service` (single source of truth for the artifact
  shape; cross-plugin module import, documented).
- **LLM coordinate resolution** mirrors `pipeline_bridge.py:56-66`:
  SSRF-check the request override only, then
  `request.api_base or settings.llm_api_base` (same trio for key/model).
- **`call_llm`** is keyword-only (`model, api_base, api_key, prompt/
  messages, temperature, system_prompt, ...`) — the same seam documents
  extraction stubs in tests.
- **FastAPI >=0.141**: union return annotations need
  `response_model=None`; mounted plugin routes are invisible to
  `app.routes` introspection (assert via `/openapi.json`).

## Architecture

```
src/omniscribe/plugins/translate/
├── __init__.py      # re-exports plugin
├── schemas.py       # TranslationRequest / AsyncTranslationRequest / NllbRequest (extra="forbid")
├── service.py       # translate_text re-home; _TranslatePayload; run_translate_job; status mapping
└── routes.py        # one APIRouter (tags=["translate"]) + plugin.py mounts it
```

`cordis.yml` gains one row after `documents`; `ocr` shifts to row 11:

```yaml
  - id: translate
    use: omniscribe.plugins.translate:plugin
```

Registers `TranslationService` (not consumed elsewhere today, but the
runner registration requires a service object mirroring OCR) and
`TranslationJobRunner` via `ctx.service`. Injects `JobQueue`,
`ArtifactStore`, `RuntimeService`. `conftest.py` `_TEST_CORDIS_YML` gains
the row (eleven-row tree; comments updated).

## Route contracts (pinned)

Error envelope everywhere: `{"error": <code>, "detail": <string>}`.

### POST /api/translate (sync)

Request `TranslationRequest` (old schema verbatim, `extra="forbid"`):

| Field | Type / constraint |
|---|---|
| `text` | `str = ""` |
| `text_artifact_id` / `text_artifact_token` | `str \| None` (no length pin on the old sync schema — keep verbatim) |
| `target_language` | `str = "Spanish"`, 1–80 chars |
| `api_base` / `api_key` / `model` | `str \| None` |
| `glossary` | `list[dict] \| None`, max 1000 (accepted, unused on sync — legacy) |
| `glossary_text` | `str \| None` (accepted, unused on sync — legacy) |
| `sliding_window_words` | `int = 80`, 0–2000 (accepted, unused on sync — legacy) |
| `dual_translate` + `second_api_base` / `second_api_key` / `second_model` | accepted, unused on sync — legacy |

Client note: the Dart `TranslationRequest.toJson` can also emit
`prompt_template` and `channel_id`, but `features_notifier` never sets
them, so real traffic never carries them; the schema keeps the old strict
shape. (If a future client starts sending them, that is a deliberate
client change.)

Behavior:

- Both `text` (trimmed) and artifact pair absent → 400
  `{"error": "bad_request", "detail": "'text' or 'text_artifact_id'/'text_artifact_token' is required"}`.
- SSRF check on `api_base` override → 403 `ssrf_blocked`.
- If text blank but artifact pair present: load artifact via
  `ArtifactStore.get` (None → 404 `not_found` "text artifact not
  found"), parse with `load_pages`, join pages with `"\n\n"`.
- `build_translation_prompt(source_text, target_language)` → `call_llm(
  temperature=TEMPERATURE_TRANSLATION, system_prompt=TRANSLATION_SYSTEM_MESSAGE,
  messages=[user])` — verbatim old `_complete_text` semantics; provider
  failure → 502 `ai_error` (static detail, exception logged not leaked).
- Success → **200 `{"translated_text": str}`**.

### POST /api/translate/async

Request `AsyncTranslationRequest` = sync fields **plus** the artifact pair
required (old `TreeTranslationRequest` semantics, adapted): `text`
accepted but ignored; artifact pair absent → 400 with the same message as
sync. `target_language` default `"English"` (old async default), 1–80.
`glossary`, `glossary_text`, `sliding_window_words`, `dual_translate`,
`second_*` trio are live on this path. `channel_id` accepted-ignored
(`str | None`) — keeps the tolerant superset honest.

Behavior:

- Validate artifact pair loads (404 at enqueue time if not; wrong token →
  404 — does not leak existence).
- Wrap in `_TranslatePayload` (submission id + request + artifact ids) →
  `queue.submit(payload, request_meta={"submission_id", "target_language"})`.
- Success → **200 `{"job_id": <id>, "status": "Processing"}`**
  (client reads `job_id`/`status`).
- LangGraph missing → 503
  `{"error": "backend_unavailable", "detail": <the workflow's own
  message>}`: the submit path invokes `get_translation_app()`
  (`@lru_cache(1)`, `workflow.py:70-78`) which raises
  `AsyncTranslationUnavailable` with a stable install-hint message when
  langgraph is absent — checked at submit time, before enqueueing.

### Runner (`run_translate_job`)

1. Load + parse the artifact (`load_pages`), build tree (`build_tree`).
2. `EntityMemory` fed with every page's lines (`add_text` per line).
3. `Glossary` from `entries` (`from_dict`) or `glossary_text`
   (`from_paired_lines`); neither → None.
4. Translator hook: `async def translator(prompt, target_language):
   return await call_llm(model=..., api_base=..., api_key=...,
   temperature=TEMPERATURE_TRANSLATION, system_prompt=TRANSLATION_SYSTEM_MESSAGE,
   prompt=prompt)`; second translator built from the `second_*` trio when
   `dual_translate` (same hook, second coordinates; SSRF-check the
   override as well).
5. `translated_tree = await translate_tree(tree, target_language=...,
   translator=..., glossary=..., memory=..., sliding_window_words=...,
   dual_translate=..., second_translator=...)`.
6. Store the translated pages' text (`"\n".join` per page, same shape as
   OCR text artifacts) via `ArtifactStore.put(owner_job_id=job_id)` →
   translated artifact handle.
7. Return `JobOutcome(blob=json.dumps(summary).encode(), content_type=
   "application/json")` where `summary = {"artifact_id",
   "translated_artifact_id", "page_count", "blocks_translated"}`;
   record `summary` in the service's bounded `job_id → result` map.

### GET /api/translate/status/{job_id}

Always HTTP 200 for known jobs (old contract), 404 envelope for unknown
job ids. Mapping from `JobStatus`:

| JobStatus | Response |
|---|---|
| `queued` | `{"job_id", "state": "PENDING", "status": "Pending..."}` |
| `running` | `{"job_id", "state": "PROGRESS", "status": "Processing..."}` |
| `complete` | `{"job_id", "state": "SUCCESS", "status": "Completed", "result": <summary dict>}` |
| `error` | `{"job_id", "state": "FAILURE", "status": "Failed", "error": "internal_error", "detail": <stable message>}` |
| `cancelled` | `{"job_id", "state": "FAILURE", "status": "Cancelled", "error": "cancelled", "detail": "Translation was cancelled."}` |

(client stops polling on `FAILURE`; `cancelled` must not map to a state
the poller ignores, or the loop never stops.)

### POST /api/translate/nllb

Request plain model `NllbRequest`: `text: str` (blank/whitespace → 422
`{"error": "bad_request", "detail": ...}` — old code used 422 here; keep
it), `target_language: str = "English"`. `NLLBEngine.is_available()` False
→ 503 `{"error": "backend_unavailable", "detail": "NLLBEngine is not
available. Install the 'nllb' extra: uv sync --extra nllb"}`. Success →
**200 `{"translated_text", "source_lang", "target_lang"}`** (NLLB codes,
e.g. `eng_Latn`/`fra_Latn`).

## Error handling summary

| Condition | Response |
|---|---|
| Missing text AND artifact pair (sync) / pair (async) | 400 `bad_request` |
| `api_base`/`second_api_base` override fails SSRF | 403 `ssrf_blocked` |
| Artifact id unknown / expired / wrong token | 404 `not_found` |
| LLM call raises (sync or runner) | 502 `ai_error` (static detail) |
| LangGraph / NLLB missing | 503 `backend_unavailable` (stable install-hint detail) |
| Unknown job id on status | 404 `not_found` |
| Malformed request body | 422 (FastAPI native; pre-existing surface-wide behavior) |

## Pedantic-review ride-alongs

`docs/audits/2026-08-30-pedantic-review.md` (landed 2026-08-30, with
corrections) is folded into this slice as a bounded ride-along set —
findings that are small, re-verified in source, and live in or adjacent to
code this slice touches. Everything else is deferred to a dedicated
remediation wave (mirroring the five-domain audit's remediation order).

In scope (one task in the plan, full fast gate — harness and core paths):

1. **1.2 — env-override lookup case sensitivity** (`harness/loader.py:135-141`):
   `overrides` is keyed by lowercased plugin id but `row.id` is matched
   with original casing, so `OMNISCRIBE_PLUGIN_Runtime__*` silently drops.
   Fix: match on `row.id.lower()`. Unit test with a mixed-case row id.
2. **1.6 — jobs shutdown cancels only the newest 1000 queued jobs**
   (`plugins/jobs.py:208`): `list_jobs(limit=1000)` orders by
   `created_at DESC`, so flooded queues leak "queued" rows forever on the
   SQLite backend. Fix: paginate until exhausted (drop the magic number).
   Unit test seeding more jobs than one page.
3. **1.9 — `assert self._doc is not None`** (`core/recall/text_layer.py:165`):
   stripped under `python -O`, turning fail-open into an AttributeError.
   Fix: explicit `if self._doc is None: return []`.
4. **1.10 — `assert last_exc is not None`** (`core/ocr/chat_client.py:161`):
   same `-O` hazard in the retry loop. Fix: explicit guard.
5. **1.1 — `ALLOW_SSRF_LOCAL` docs reconciliation** (docs-only): the code
   default stays `False` (secure; per the review-file correction), and
   `AGENTS.md:234` is reworded to state that the *code* default is False
   while the shipped `.env.example` enables it for local development.

Refuted during re-verification (no action): **7.12** — the quality-loop
env seeds are consumed via `cordis.yml:61-63` `${...}` expansion.

Deferred to the future remediation wave (recorded, not in this slice):
1.3, 1.4, 1.5, 1.7, 1.8, 2.1 (needs a paired Flutter change — the client
switches `exportDocx` to POST before the GET route can be dropped), 2.2,
2.7, and the remaining section 3–6 findings.

## Celery retirement

- `compose.yaml`: remove the `worker` (Celery) service block and any
  async-profile references that only existed to serve it; keep `redis` if
  other docs reference it — check and prune honestly.
- `start_app.vbs`: drop the Celery window launcher.
  `start_app.vbs` no longer exists in the repo; retirement is
  compose-only.
- `DEPLOYMENT.md` / `AGENTS.md`: async-profile wording now describes the
  JobQueue path; note the Celery removal.
- `AGENTS.md` Known Tech Debt: the "Celery task once translation routes
  are rebuilt" bullet is updated — translation async now rides the
  harness queue; Celery remains only as a future multi-worker option.

## Testing

- `tests/plugins/test_translate_schemas.py` — field constraints, defaults,
  extra-forbid, target_language bounds.
- `tests/plugins/test_translate_service.py` — sync `translate_text`
  verbatim behavior with stubbed `call_llm` (artifact join, 404 on bad
  artifact, ai_error wrap, ssrf_blocked); runner pipeline with stubbed
  translator (glossary/entity-memory wiring, dual second translator, tree
  walk on a seeded artifact, outcome + summary map); status mapping for
  all five JobStates + unknown job.
- `tests/routers/test_translate_routes.py` — the four client-frozen
  contracts: sync 200 `{"translated_text"}` / 400 / 403 / 404; async 200
  `{"job_id", "status": "Processing"}` + 400 + 503; status PENDING →
  SUCCESS (in-test drain) → result shape; nllb 200 / 422 / 503 (stubbed
  engine). Seeding via `StateBackend.put_artifact`; `call_llm` stubbed at
  `plugins.translate.service`.
- `tests/plugins/test_boot_config.py` — eleven rows, router count 6.
- `tests/openapi.json` — regenerate (additions-only expected; verify).
- Port the old pins where they map: sync provider-error no-leak, async
  unavailable 503, status shapes, nllb shapes.

## Docs updates

- `AGENTS.md`: boot table (translate row 10, ocr → 11), deferred list
  drops translation, Web Notes async-translation + tech-debt bullets
  updated, "Last updated" stamps.
- `ARCHITECTURE.md`: plugin tree/rows/API-surface additions; deferred
  paragraph trim.
- `CHANGELOG.md`: unreleased Added entry (four routes, JobQueue async,
  Celery retirement).
- `README.md`: translation feature claims become true (verify wording).

## Acceptance criteria

1. The four routes serve the current client contract with zero client
   changes (field names, wrappers, status vocabulary, 2s-polling
   stop conditions).
2. `/api/translate/async` completes end-to-end in-test: submit → queued →
   drained by the single worker → SUCCESS status with the summary result;
   translated text fetchable via `GET /api/text/{translated_artifact_id}`.
3. Fast gate green (`ruff check/format`, `mypy src`,
   `pytest -m "not slow"`); openapi snapshot additions-only.
4. Shipped `cordis.yml` boots eleven plugins; `compose.yaml` +
   `start_app.vbs` contain no Celery references; audit finding #2 closed.
5. Docs match code (boot table, deferred list, changelog).

## Edge cases

- Sync request with artifact pair whose artifact is empty (`{}`) →
  translate empty string? Old code: source_text = "" → returns ""? (old
  `translate_text` returned "" for empty source — client renders empty
  output; keep verbatim: `{"translated_text": ""}`).
- Async submit while the queue worker is busy → job queues (single
  worker); status stays PENDING — client keeps polling (matches OCR async
  semantics).
- `target_language` whitespace-only → 422 (min_length=1 after the trim
  validator).
- Glossary `entries` present AND `glossary_text` present → `entries`
  wins (old route verified: `if req.entries: from_dict(...)` else
  `from_paired_lines`).
- `dual_translate` true but any `second_*` coordinate missing → resolve
  against settings like the primary trio (old behavior resolved the
  second translator from config; keep: request override → settings).
- NLLB `target_language` not resolvable to an NLLB code → `resolve_nllb_code`
  falls back to `"eng_Latn"` (never raises — verbatim).
- Artifact with non-numeric page keys → `load_pages` ignores them
  (documents-plugin semantics, shared helper).

## See also

- [2026-08-30 documents plugin spec](2026-08-30-documents-plugin-extraction-export-design.md) — slice 1; artifact helpers + envelope conventions
- [2026-08-23 API rebuild design](2026-08-23-omniscribe-api-rebuild-design.md) — deferred-capabilities source
- [2026-08-29 five-domain audit](../../audits/2026-08-29-five-domain-audit.md) — finding #2 (Celery) closed by this slice
- [2026-08-30 pedantic review](../../audits/2026-08-30-pedantic-review.md) — bounded ride-along set (see "Pedantic-review ride-alongs")
- Recovered pre-rebuild sources: commit `44ef123^` (`api/routers/translation.py`, `api/services/ai.py`, `api/celery_app.py`, `api/tasks.py`), contract tests `e6b7b89^`

_Last updated: 2026-08-30_
