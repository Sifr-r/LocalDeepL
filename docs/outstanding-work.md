# OmniScribe — Outstanding Work

**Consolidated:** 2026-08-31
**Sources:** `docs/audits/2026-08-30-pedantic-review.md` (rev. 2026-08-31),
`docs/superpowers/specs/2026-08-31-ocr-upload-content-type-bypass-fix-design.md`,
the deferred Medium/Low backlog of the 2026-08-29 five-domain audit, and
Phase C follow-ups.

All completed plans and specs (API rebuild, token-efficiency restructure,
Flutter client consolidation + takeover Phases A/B, audit-remediation
sprints 1–6, Phase C plugin slices 1–3) were deleted on 2026-08-31. They
remain recoverable in git history (last present at `0dd79aa`).

---

## 1. Immediate: commit the in-progress Wave 1 remediation

The working tree (uncommitted as of consolidation) contains fixes closing
six pedantic findings, plus their tests and doc reconciliation:

| Closes | Change | Files |
|---|---|---|
| **1.1** | `ALLOW_SSRF_LOCAL` doc reconciliation — code default stays `False` (secure default); `.env.example` sets `true` for local dev | `.env.example`, `SECURITY.md`, `AGENTS.md` |
| **1.3** | `"cancelled"` maps to `"cancelled"` in `_QUEUE_STATUS_TO_HTTP`; `_HttpJobStatus` literal gains `"cancelled"` | `plugins/ocr/service.py`, `plugins/ocr/schemas.py` |
| **1.4** | `run_job` runs `cancel_check` after `_execute()` returns and raises `OCRCancelled` before artifact persistence; queue catches it as cancellation | `plugins/ocr/service.py`, `plugins/jobs.py` |
| **1.7** | AVIF validated via ISOBMFF `ftyp` box layout (`ftyp` at offset 4, brand at offset 8, variable box sizes) | `plugins/ocr/plugin.py` |
| **1.8** | `_sniff_format` sniffs `application/octet-stream` uploads before writing to disk; non-matching uploads 415 | `plugins/ocr/plugin.py` |
| **9.1** | `JobQueue.list_jobs` Protocol gains `offset: int = 0`, matching `StateBackend.list_jobs` | `plugins/jobs.py` |

Tests: `tests/plugins/test_ocr_plugin.py` (+164 lines incl. the bypass
regression test), `test_ocr_schemas.py`, `test_jobs_plugin.py`,
`tests/routers/test_jobs_endpoints.py`, `test_process_status.py`, and the
`tests/openapi.json` snapshot.

### Design note for the 1.8 fix (from the bypass-fix spec)

**Problem.** The `application/octet-stream` branch of `_parse_upload`
skipped the magic-byte check entirely (a "Flutter file picker fallback"),
so any client labelling arbitrary bytes as `octet-stream` got through the
route unchallenged — untrusted bytes reached the tempdir (up to the 10 GB
cap) before downstream format detection rejected them. The H-5 audit-fix
"two layers" narrative was false for that branch.

**Decision (Option B — two-phase).** Typed uploads keep the existing
declarative magic-byte check; the `octet-stream` branch routes through a
separate `_sniff_format(head)` detector (PDF `%PDF-`, PNG 8-byte
signature, JPEG `\xff\xd8\xff`, WebP `RIFF…WEBP`, AVIF `ftyp` + brand)
returning a normalized type or `None` → 415 *before* the tempdir write.
Option A (always sniff, gate on the sniff) was rejected because it carried
the then-broken AVIF check into the only branch that would work; Option C
(pre-parse with `fitz.open(stream=…)` / `Image.open`) was rejected for
layering inversion and full-document memory materialization.

**Key acceptance criteria.** octet-stream + supported format reaches the
pipeline bridge; octet-stream garbage 415s before the tempdir; oversize
uploads still 413 (size check first); typed uploads unchanged; fast gate
green.

**Roll-back.** Single-commit revert of `_sniff_format` and the branch
change; pure route-layer revert.

**Next step:** run the fast gate and commit this batch.

---

## 2. Pedantic code review — open findings (rev. 2026-08-31)

Line-level review of `src/omniscribe/` plus `AGENTS.md` / `.env.example`.
Finding IDs below match the original review. File:line references are
as of 2026-08-31 and may drift — re-verify before fixing.

### 2.1 Real bugs still open

**1.5** `plugins/state_backend_sqlite.py:131-145` — `put_artifact` does
`INSERT OR REPLACE` + `path.write_bytes(blob)` without unlinking the
previous `.bin`. If the same `id` already exists (operator cleanup, backup
restore, ad-hoc SQL), the old blob file leaks. `delete_artifact` unlinks
properly; the asymmetry is purely a bug in `put`.
→ **Closed (Wave 2).** `put_artifact` now reads the existing row's
`blob_path` before INSERT OR REPLACE and unlinks the previous file if it
differs from the canonical path. Regression test
`test_put_artifact_replaces_unlinks_previous_blob_file`
(`tests/plugins/test_state_backend_sqlite.py`).

**1.11** `core/ocr/processor.py:153` — `self.page_max_tokens: int =
self.PAGE_MAX_TOKENS` re-binds the class constant at instance time. An
env-var change after import doesn't reach the instance via
`OMNISCRIBE_VLM_PAGE_MAX_TOKENS` (it never went through `load_settings()`
at all). Silently inconsistent with the F1.9 fix documented nearby.
→ **Closed (Wave 2).** `__init__` now reads the env at instance
construction time via `env_int("OMNISCRIBE_VLM_PAGE_MAX_TOKENS", ...)` /
`env_int("OMNISCRIBE_VLM_CROP_MAX_TOKENS", ...)`. A fresh
`OCRProcessor()` after an env-var change picks up the new value without
a module reload. Test
`test_env_change_after_import_picks_up_on_fresh_instance`
(`tests/core/ocr/test_vlm_timeout_env.py`).

**1.12** `core/ocr/processor.py:111-126` — class-level constants call
`load_settings()` at import (`PAGE_TIMEOUT_S = load_settings().vlm_page_timeout`,
etc.). Importing the module parses the full env and instantiates
`BaseSettings`, making the module un-importable in subprocesses without
env setup. The `__getattr__` workaround papers over it but every import
pays the cost.
→ **Closed (Wave 2).** The class-level constants
(`PAGE_TIMEOUT_S`, `PAGE_MAX_TOKENS`, `CROP_TIMEOUT_S`,
`CROP_MAX_TOKENS`, `MAX_RETRIES`, `RETRY_BASE_DELAY_S`,
`RETRY_MAX_DELAY_S`) are now hardcoded defaults matching
`load_settings()`'s values. The module is importable in subprocesses
without the full env set; `__init__` resolves the live values. Tests
`test_vlm_timeout_env.py` and `test_phase5_env_and_spellcheck.py` were
rewritten to test the new contract (instance-time resolution).

**1.15** `core/recall/whitespace.py:181-188` — on a page where Surya
returned only zero-height boxes, the recall filter `min_height` floor
drops to 0.27% of page height (~3 px at 1024 px), accepting basically any
horizontal ink stripe. Precision breach of the booster's documented
stance. Either skip the page or use a non-tiny floor.
→ **Closed (Wave 2).** When *every* surya box has zero height, the
min/max-height band now falls back to the absolute fallback
(`_FALLBACK_MIN_HEIGHT = 0.006`, `_FALLBACK_MAX_HEIGHT = 0.06`) instead
of `0.45 * 0.006` / `2.5 * 0.006`. A 16-px text line that the buggy
max of 15 px rejected is now accepted (regression test
`test_all_zero_height_surya_keeps_text_line_above_fallback_band` in
`tests/core/recall/test_text_recall.py`).
A hairline-rejection sanity test (`..._rejects_hairline_below_fallback_band`)
pins the absolute `_MIN_COMPONENT_HEIGHT_PX = 10` gate.

**1.18** `utils/security.py:269-270` — `check_ssrf_target` (sync wrapper)
spawns a new `ThreadPoolExecutor(max_workers=1)` + new event loop per
call, on the request hot path (`plugins/ocr/pipeline_bridge.py:57`,
`plugins/ocr/service.py:368`). Use a module-level singleton executor or
`loop.run_in_executor`.
→ **Closed (Wave 2).** `check_ssrf_target_sync` now reuses a
module-level `ThreadPoolExecutor` (`_SSRF_EXECUTOR`,
`max_workers=2`, `thread_name_prefix="omniscribe-ssrf-check"`)
created once at import time. Regression test
`test_check_ssrf_target_sync_uses_module_level_executor`
(`tests/utils/test_ssrf.py`) counts `ThreadPoolExecutor.__init__`
calls during 5 `check_ssrf_target_sync` invocations and asserts it
stays at 0.

**7.12** — `OMNISCRIBE_QUALITY_LOOP` / `OMNISCRIBE_QUALITY_TARGET` /
`OMNISCRIBE_QUALITY_MAX_RETRIES` are documented in `.env.example` and
AGENTS.md but **not declared in `config.py`** and not read by the OCR
plugin's `OCRSchema` (hard-coded `quality_loop_enabled=True`,
`quality_target=0.85`, `quality_max_retries=2`). The env seeds are
ignored. Real bug.
→ **Closed (Wave 2).** The three env vars are now first-class fields
on `RuntimeSettings` (`ocr_quality_loop_enabled`,
`ocr_quality_target`, `ocr_quality_max_retries`) so `load_settings()`
exposes the same contract as the cordis.yml boot-time expansion.
Out-of-range values are rejected at settings-load time instead of
crashing the OCR plugin at apply time. Four regression tests added to
`tests/test_cordis_settings.py`.

### 2.2 Medium priority (correctness / security / hygiene / drift)

**1.13** `harness/context.py:78-79` — duplicate service registration
raises `ValueError`; a test doing `ctx.dispose()` then fresh
`Loader(ctx).load(...)` could crash on re-entering the same plugin. If
intentional, prefer `RuntimeError` so it doesn't read as an `is`/`==`
confusion in logs.

**1.14** `harness/context.py:166-184` — if a plugin `dispose` raises
during failed-`apply()` rollback, the original `apply` exception is
replaced and the loader never learns the real reason; `from exc` is lost.
Rollback is silently best-effort.

**1.16** `core/recall/text_layer.py:111` — a renamed `.pdf` whose first
bytes are not `%PDF-` returns `False` silently (no log, no warning).
Both recall boosters silently no-op for every non-PDF input. Worth a
debug log.

**1.17** `utils/security.py:216-253` — `is_blocked_host` is sync and can
block an event loop for seconds (`socket.getaddrinfo`). The docstring
never warns against async-context use. Rename to
`_is_blocked_host_blocking_unsafe` or add a prominent warning.

**1.19** `utils/security.py:74-87` — `_is_blocked_ip` conflates "reserved"
with "private" (`ipaddress.is_reserved` includes 240.0.0.0/4, CGNAT).
Operators with LLM endpoints in IANA-reserved ranges are only covered by
`ALLOW_SSRF_LOCAL` for documented local ranges. Worth a comment that this
is deliberate.

**2.1** `plugins/documents/routes.py:128-131` — `GET /api/export/docx`
puts the document text in the query string → uvicorn access logs, proxy
logs, browser history, Referer headers. Fix: `POST /api/export/docx` only,
delete the GET (needs a paired Flutter client change).
→ **Closed (Wave 4).** The GET handler is gone. With the GET
removed, `GET /api/export/docx` falls through to the parametrized
`/api/export/{artifact_id}` route and is rejected there (403 without a
Bearer token) — the query string is never rendered into a document.
Paired Flutter change in
`feature_repository.dart::exportDocx` (GET → POST with body, same
shape as `exportHtml`). `tests/openapi.json` regenerated to drop
the GET operation. New test
`test_export_docx_get_no_longer_returns_docx` pins the no-DOCX
property. Commit `129ddae`.

**2.2** `core/ocr/processor.py:252-256` — `client.close()` runs in
`try/finally` on every pre-flight. The `AsyncOpenAI` client is created in
`__init__`; closing it per pre-flight means either a leak (never reopens)
or a perf cliff (reopen every request). Intent unclear.

**2.3** `server.py:75-83` — `_load_optional_module` returns the module;
every consumer then does 5 separate attribute lookups. A
`_load_attr("fastapi:FastAPI")` helper would centralize the
optional-dep-missing message.

**2.4** `server.py:150, 256, 371` — `load_settings()` called three times
per startup; three equal-but-not-identical `RuntimeSettings` objects.
Call once and pass the object.

**2.5** `server.py:195` — `import logging as _logging` inside the
exception handler instead of using module-level `_log` (line 32).

**2.6** `plugins/ocr/service.py:189-194` — `_submission_to_job` eviction
(insertion-order trim on every submit) duplicates the `prune` eviction
policy with different timing. Duplicate eviction policy that will be
re-discovered later.

**2.7** `plugins/ocr/service.py:327-347` — `fetch_result` reveals job
existence via differential status codes (unknown → 404, bad token → 403,
in-progress → 409), enabling job-id enumeration. Collapse to a single
404 for "unknown or invalid".
→ **Closed (Wave 4).** Every non-200 path in `fetch_result` now
returns ``404`` with the same ``"result not available"`` detail.
The constant-time token compare still runs against a real
record's stored token so a wrong-token attempt has the same
timing shape as a record-missing attempt at the order of
magnitude of the queue-status round trip. New test
`test_result_failures_are_indistinguishable` exercises all four
failure modes and asserts the uniform ``(404, "result not
available")`` shape. Four pre-existing tests that pinned the
old 403/409 codes are updated to 404 with a comment pointing
at 2.7. Commit `6006c89`.

**2.8** `plugins/ocr/service.py` / `_OcrPayload` — the full upload bytes
are held in `_submission_to_job` until `run_job` consumes them; the memory
backend holds result PDF **plus** original upload in heap for the whole
job lifetime. No streaming pipeline.

**2.9** `utils/env.py:171-176` — `env_bool` returns True for anything not
in `{"0","false","no","off"}` (`"banana"` → True), while
`plugins/ocr/schemas.py:_parse_bool` uses the closed set
`{"true","1","yes","on"}`. Two boolean vocabularies; pick one canonical
helper.

**3.1** `config.py:127-152` accepts `ocr_auth_token`,
`translation_auth_token`, `transcription_auth_token` — none consumed by
any route. Misleading while auth is deferred; delete or document a
deprecation plan.
→ **Closed (Wave 3).** `ocr_auth_token` and `translation_auth_token`
deleted; `transcription_auth_token` kept (it flows into
`TranscriptionConfigStore`, which masks it for the
`/api/config/transcription` response). The `SECURITY.md` per-service
auth row was updated to list only the surviving field with a
config-mask / future-enforce note. Commit `9df1a81`.

**3.2** `config.py:128-145` — six legacy `LOCAL_DEEPL_*` aliases survive
the rename to OmniScribe. If the rename was intentional, the aliases can
go.
→ **Closed (Wave 3).** All six dropped from the `AliasChoices` entries
in `config.py` (the four auth-token ones via 3.1, the three
cors / max_upload_mb / rate_limit_per_min ones in the same commit).
Commit `9df1a81`.

**3.3** `.env.example:50-58` documents `OMNISCRIBE_MAX_PAGES` and
`OMNISCRIBE_TRUSTED_PROXIES`, which are not declared anywhere in `src/`.
Either document the missing features or remove the lines.
→ **Closed (Wave 3).** `OMNISCRIBE_MAX_PAGES` is now a first-class
field on `RuntimeSettings` (default 500, `ge=0`) so `load_settings()`
exposes the same contract the rasterizer is using. The runtime
read stays as `os.getenv` in `core/pdf/rasterizer.py:115` so the
per-call cap is hot-reloadable; both paths default to 500 and
agree on the `0` / unparseable = cap-disabled sentinel. Four
regression tests in `tests/test_cordis_settings.py` cover
default / override / zero-sentinel / negative-rejection.
`OMNISCRIBE_TRUSTED_PROXIES` was never implemented in code;
removed from `.env.example`, the `SECURITY.md` security-features
table, and the deployment checklist. Commit `6b53b89`.

**3.4** `.env.example:15-23` shows only the `LLM_*` form; `config.py`
also accepts `OMNISCRIBE_LLM_*` aliases. Users searching for the
canonical form come up empty.

**3.5** The `/api/config` seed list (22 keys) in
`plugins/ocr/service.py:88-113` has no canonical "what is exposed" doc.

**3.6** `JobStatusResponse` security note says clients get the token via
SSE, while AGENTS.md says the result URL is a polled endpoint. Two
different stories; reconcile.

**3.7** `core/ocr/processor.py:282` comment references
`tests/core/ocr/test_ocr.py::TestPromptConstants::*`. If the tests exist,
list them in AGENTS.md's inventory; if not, the comment is broken.

**3.8** `core/recall/whitespace.py:42-43` references
`docs/superpowers/plans/2026-08-14-whitespace-recall.md`, which never
existed in `docs/`. Stale path — remove or write the doc.

**3.9** `core/recall/text_layer.py:1-17` and `core/recall/whitespace.py:1-18`
have near-duplicate module docstrings and duplicated constants
(`MAX_*_BOXES_PER_PAGE = 10`). Promote shared knobs to one module.

**7.2** AGENTS.md says the historic `GET /v1/models` pre-flight "is not
yet re-implemented", but `core/ocr/processor.py:232-256`
(`ensure_model_loaded`) does exactly that. Doc is stale.

**7.3** AGENTS.md's rebuild note claims pre-flight is missing; same
contradiction as 7.2.

**7.7** AGENTS.md's tunables table omits `OMNISCRIBE_VLM_PAGE_MAX_TOKENS`
/ `OMNISCRIBE_VLM_CROP_MAX_TOKENS`, which
`core/ocr/processor.py:112,120` reads via `env_int`.

### 2.3 New findings on harness/plugin code (post-Phase-C)

**9.2** `harness/effects.py:17` — module-level
`_effect_counter = itertools.count(1)` is process-global and never
resets. Tie it to the `Context` instance or owning scope.

**9.3** `harness/effects.py:47-56` — `EffectScope.aclose` abandons
remaining cleanups if the first raises. Pick a policy: best-effort
(log + continue) or strict (fail fast).
→ **Closed (Wave 5).** Each cleanup call (sync and async paths)
is wrapped in try/except; a failure is logged at ERROR with
the traceback and the loop continues so every registered
effect gets a chance to run. New tests
``test_scope_aclose_continues_after_failing_cleanup`` and
``test_scope_aclose_continues_after_failing_async_cleanup``
pin the contract. Commit `0e8bee7`.

**9.4** `harness/effects.py:41-45` — `EffectScope.add` mutates
`self._cleanups` without a lock; concurrent registration from plugin
threads can lose entries.
→ **Closed (Wave 5).** A ``threading.Lock`` now guards the
``_cleanups`` list mutation in ``add()`` and the
``aclose()`` pop loop. New test
``test_scope_add_is_thread_safe`` fires 8 threads × 50 adds
through a barrier and asserts the final list length is
exactly 400. Commit `0e8bee7`.

**9.5** `harness/service.py:21-41` — `service_protocol(name, methods)`
dynamically fabricates Protocol classes via `types.new_class`; **no
caller uses it**. Breaks mypy/IDE navigation. Delete or document a user.
→ **Closed (Wave 3).** `service_protocol()` deleted along with its
re-export from `omniscribe.harness.__init__` and the self-test
`test_service_protocol_builds_named_protocol` (the two marker-Protocol
tests stay). Commit `a4de270`.

**9.6** `plugins/glossary/store.py:33-46` — `LexiconProvider.get()` is a
one-shot lazy load: after an `ImportError` (missing `lexicon` extra),
`_tried` stays True forever. Installing the extra later requires a process
restart. Document or invalidate `_tried` on `ImportError` only.
→ **Closed (Wave 5).** ``_tried`` is now set to ``True`` only
on a successful import. ``ImportError`` leaves it ``False``
so the next call retries the import. A successful import is
still cached — the same store object is returned on every
subsequent call without re-invoking the constructor. Three
regression tests in
``tests/plugins/test_glossary_store.py`` (new file). Commit
`3281764`.

**9.7** `plugins/glossary/store.py:49-52` — `null_provider()` has zero
call sites. Dead helper; delete or wire.
→ **Closed (Wave 3).** `null_provider()` deleted (and the now-unused
`Callable` import). Commit `e05be41`.

**9.8** `plugins/glossary/plugin.py:31-34` — `LexiconProvider` is created
per boot; the service captures the bound `provider.get`. Right shape, but
the one-shot laziness of 9.6 is inherited.

**9.9** `plugins/translate/service.py:100-120` — sync translation
tolerates `request.text=""` by falling back to the artifact, while
`extract` (`plugins/documents/service.py:71`) returns 400 for empty text.
Pick one semantic.

**9.10** `plugins/translate/service.py:36-41` — the plugin imports
`TRANSLATION_SYSTEM_MESSAGE` from `core.translate.nodes`, sharing a
constant across the plugin/core boundary. Copy it into the plugin with a
sync comment, or expose it through a stable `core.translate` re-export.

**9.11** `plugins/transcribe/service.py:60-77` —
`str(request.api_key or config.get(...)) or None` is a 4-step
value-or-config-or-default-or-None funnel. Flatten with a helper or
accept the noise.

**9.12** `plugins/transcribe/service.py:80-100` — the route unpacks five
kwargs to match the service signature; the unpack helper should live next
to the schema to stay in sync.

**9.13** `plugins/transcribe/service.py:27-33` — the 7-line import block
is `noqa: F401` wholesale; dropping a symbol the service doesn't use
would silently break route-layer imports. Narrow the noqa or move unused
names to `TYPE_CHECKING`.

**9.14** `plugins/translate/plugin.py:34` — multi-producer dispatch relies
on an implicit `runner_protocol` class-attribute convention on payload
classes; no Protocol declares it. A fourth producer's author must read
`plugins/jobs.py:250-259` to discover it. Document or formalize.

**9.15** `plugins/jobs.py:91-102` — `JobRunner`, `TranslationJobRunner`,
`GlossaryJobRunner` are three near-identical Protocols differing only in
name/docstring. Deduplicate via a base + aliases.
→ **Closed (Wave 5).** The structural contract is extracted
into a private ``_JobRunnerContract`` Protocol that each
runner extends with only a distinguishing docstring. The
three runner Protocols remain distinct type identities (DI
keys) so the multi-producer dispatch in
``InMemoryJobQueue._resolve_runner`` still routes payloads
to the right runner via the ``runner_protocol`` class
attribute. The duplicate ``async def __call__`` body now
lives in only one place. New test
``test_runner_protocols_share_contract`` pins both the
distinct-identity property and the shared-MRO property.
Commit `ed8ed3a`.

**9.16** `plugins/jobs.py:28` `_TERMINAL_STATUSES`,
`plugins/state_backend.py:36` `JobStatus` literal, and
`plugins/ocr/service.py:60` `_TERMINAL_QUEUE_STATUSES` — three copies of
the same terminal set. Promote one public constant or derive it from the
literal's `__args__`.
→ **Closed (Wave 5).** ``TERMINAL_JOB_STATUSES: frozenset[str]``
added to ``state_backend.py``, derived from
``get_args(JobStatus)`` minus the non-terminal set
(``{queued, running}``). ``plugins/jobs.py::_TERMINAL_STATUSES``
and
``plugins/ocr/service.py::_TERMINAL_QUEUE_STATUSES``
are now aliases of the canonical constant — kept as
source-level readability for the call sites but pointing
at the same object. A new terminal status (e.g.
``"superseded"``) needs one edit. New test
``test_terminal_job_statuses_derived_from_literal``
pins the single-source-of-truth contract. Commit
`ed8ed3a`.

**9.17** `plugins/translate/routes.py`, `plugins/transcribe/routes.py`,
`plugins/glossary/routes.py` — the three new route modules never got the
same audit pass as the existing routes: confirm the `{"error","detail"}`
envelope, `response_model=None` union pattern, and SSRF guard on
caller-supplied `api_base`.

### 2.4 Test gaps

**5.1** No test for the `_OcrPayload` round-trip when the `submission_id`
lookup misses (evicted by the 500-deep map) — service silently uses
`job_id=""`.

**5.2** No test for the SQLite `INSERT OR REPLACE` blob leak (1.5).
→ **Closed (Wave 2).** `test_put_artifact_replaces_unlinks_previous_blob_file`
simulates the operator-cleanup / backup-restore scenario by repointing the
row's `blob_path` to a sibling file, then asserts the sibling is unlinked
after the second `put_artifact`.

**5.3** A `-O` regression test around `core/recall/text_layer.py` would
still be valuable after the 1.9 fix.

**5.4** No test exercises the SSE event-flap in
`plugins/ocr/plugin.py:199` (see 4.18).

**5.5** No test covers `plugins/jobs.py` shutdown with >1000 queued jobs
(1.6 fix's pagination loop).

**5.6** No test for the `load → unload → reload` cycle in `Context`
(1.13).

**5.7** No frontend test distinguishes cancelled from error status (1.3
is now fixed server-side; the Flutter side still needs the distinction).

### 2.5 Low-priority index (naming/API smells §4 and style §6)

One-line index; full text lives in git history at the committed
pedantic-review revision (`3b8b011`) plus the rev. 2026-08-31 delta.
Duplicates of findings above are omitted.

**§4 naming/API smells**
- **4.1** `cors_origins_raw: str | None` + property — prefer typed list field
- **4.2** `_disable_negative_rate_limit` name is misleading; rename/document
- **4.3** `_inherit_llm_model_for_grounded` compares a magic model string; use a sentinel
- **4.4** retry loop's `last_exc` invariant is implicit, not asserted
- **4.5** `TrOCREngine` TYPE_CHECKING-only but wired in production; document the requirement
- **4.6** `_DISABLE_VALUES` duplicated in whitespace + text_layer; promote to `utils.env`
- **4.7** `WhitespaceRecallOptions.from_env` vs `TextLayerRecallOptions.from_env`; shared base
- **4.8** `_RepairEngineHost` Protocol documents a contract the file then breaks
- **4.9** `input_path: str = ""` default is dead code
- **4.10** `state_backend.py:200-206` circular-import workaround is fragile; split types module
- **4.11** four names for two concepts across `jobs.py`/`state_backend.py` (`artifact_id` vs `result_artifact_id`)
- **4.12** `_PYTHON_BUG_EXCEPTION_TYPES` treats `ValueError` as non-retryable; conflates bug vs garbage
- **4.13** `CircuitOpenError.retry_after` never surfaced as a `Retry-After` header
- **4.14** `load_dotenv()` at module level in processor.py and server.py; move to entry point
- **4.15** `cli/migrate_lexicon.py` ships despite the CLI deprecation note; check `[project.scripts]`
- **4.16** `_MODELS_WITHOUT_SYSTEM_ROLE` substring matching catches fine-tunes; document intent
- **4.17** inner `import base64` in TrOCR arbitration belongs at top
- **4.18** SSE loop's clear-on-wake `asyncio.Event` flaps — dropped/interleaved frames; use a deque
- **4.19** `max_buffered_jobs` caps three structures with two eviction functions; fold
- **4.20** `update_config` mutates shared `RuntimeSettings` mid-flight; document "applies to subsequent requests"
- **4.21** `_DENSE_MODE_ALIASES` on/off→always/never mapping is hidden; document in contract
- **4.22** `_parse_bool` vs `env_bool` vocabularies (see 2.9)
- **4.23** `_QUEUE_STATUS_TO_HTTP` should live next to the schema
- **4.24** state-backend allowlist in three places, `redis` passes settings validation then crashes at plugin apply; unify
- **4.25** `PRAGMA journal_mode=WAL` set but never verified
- **4.26** embedder docstrings reference a 470-LOC file that no longer exists; trim
- **4.27** `env_int` logs a warning on bad input; other helpers don't; align
- **4.28** `env_list_csv` vs `env_str` empty-value semantics differ
- **4.29** `extract_json` walks every `{`/`[` — O(n²) on big responses; single `raw_decode`
- **4.30** whitespace.py constants block carries 15 lines of audit history; move to docs (this file now absorbs it)
- **4.31** loader `row = replace(row, ...)` rebind shadows traceback context
- **4.32** env-override typos surface as opaque Pydantic ValidationErrors; coerce via schema earlier
- **4.33** "harness mounted plugins" log lacks a count
- **4.34** text_layer `close()` not re-entrant (smelly, fitz is idempotent so safe)
- **4.36** `_overlaps_existing` is O(n²) per page on pathological box counts
- **4.37** HybridEngine re-injects deps into long-lived stages every `execute()`; constructor args decorative
- **4.38** `_reset_run_state` resets only two of the stage states; document or full-reset
- **4.39** `_decoded_cache` integer keys could collide across runs; use `(run_id, page)` keys
- **4.40** `trust_images_dict` aliases `images_dict`; a future mutation leaks across
- **4.41** `_DEFAULTS` dict rebuilt per attribute access; hoist
- **4.42** exponential backoff cumulative sleep budget undocumented
- **4.43** context-length error message is LM Studio-specific; generalize or branch
- **4.44** `_instantiate` error omits the plugin class name
- **4.45** `Context.__init__` pre-allocates nine collections (negligible cost, signal only)

**§6 style nits** (deduplicated)
- **6.1** dead `_LOGGER` in server.py:31 (duplicate of `_log`)
- **6.2** inconsistent divider comment styles in server.py
- **6.3** `artifact_cleanup_interval_s` vs `cleanup_interval_seconds` naming/units drift
- **6.4** HybridEngine's 9-kwarg `__init__` is a permanent API surface
- **6.5** `_STRADDLE_MIN_OVERLAP` duplicated in both recall modules
- **6.6** `_KERNEL_W_RANGE` tuples; named MIN/MAX constants would read better
- **6.7** whitespace candidates carry an unused score element; misleading annotation
- **6.8** triple-`or` candidate filter; three named predicates would scan better
- **6.9** `_resolve_unicode_chain` is 70 lines; split
- **6.10** `_UNICODE_GLYPH_MISS_LOGGED` one-shot flag; use a log-once helper
- **6.11** font-probe log uses `exc_info=True` for operational noise
- **6.12** add a Persian `peh` probe codepoint
- **6.13** `hybrid_repair.py` `concurrency` param is a documented no-op
- **6.14** default-arg closure binding; prefer `functools.partial`
- **6.15** sqlite path-traversal check rejects deliberate sibling-dir layouts
- **6.16** `range(self.max_retries + 1)` cryptic; make 1-based
- **6.17** post-loop error translation duplicates `is_transient_error` logic
- **6.18** `_parse_env_line` is 50 lines of bespoke parsing; document or use stdlib
- **6.19** `update_dotenv` round-trip normalizes CRLF to LF
- **6.20** `update_dotenv` unconditionally sets every key into `os.environ`
- **6.25** `_MAX_RECALL_BOXES_PER_PAGE = 10` duplicated; promote
- **6.26** memory backend caps blobs at 256 MB; sqlite has no cap; clarify intent
- **6.27** missing `OMNISCRIBE_CORDIS_PATCH` file is silently ignored; log a warning
- **6.28** loader's `except PluginLoadError: raise` clause is a no-op
- **6.29** duplicate of 4.33
- **6.30** `new_doc.save` exposes no `garbage`/compression kwargs
- **6.31** embedder `page_nums` branching has a dead conditional; unify
- **6.32** duplicate of 4.26
- **6.33** `_OcrPayload` IR lives in the HTTP layer; pipeline can't enqueue without it
- **6.34** grounded engine duplicates hybrid's execution path; lockstep-change risk
- **6.35** `AsyncSubmitResponse.status` is `str`, should use the job-status Literal
- **6.36** `JobStatusResponse.text_artifact_id` exposure is safe (positive note)
- **6.37** `_parse_bool` lacks `"enabled"` while recall accepts it; align vocabularies
- **6.38** `_split_processors` only handles comma-joined form fields; repeated keys drop
- **6.39** `preprocessing_enabled` property couples HTTP naming to behavior; move to bridge
- **6.40** sqlite `_job_from_row` uses positional access; use `sqlite3.Row`
- **6.42** `cursor.rowcount if cursor.rowcount >= 0 else 0` repeated 4×; extract
- **6.43** `candidates_dropped` counts per candidate, log reads per page; document
- **6.45** `trust_images_dict` param on `_finalize` is dead; delete
- **6.46** `select_dense_pages` union `str | DenseMode` is historical; narrow
- **6.47** `_apply_adaptive_threshold` via `to_thread` — function not in file; locate/document
- **6.48** Tesseract dual-engine contract undocumented
- **6.49** `self_correction` second VLM call path review notes
- **6.50** F1.9 comment block is 23 lines; trim to a one-liner + pointer
- **6.51** `import statistics` mid-module
- **6.52** every whitespace constant carries a multi-line audit comment; move history to docs
- **6.53** substring matching over a frozenset; list + early exit
- **6.55** two `PROMPT_VERSION` constants share a value by coincidence; hazard
- **6.56** chat client re-encodes JPEG to PNG (+30% payload); use `multi_format_client`
- **6.57** backoff formula note (informational)
- **6.63/6.64/6.65/6.66** hybrid engine re-injection wrappers do nothing; call stages directly
- **6.68** `_build_document_result` helper visibility note
- **6.69** `completed_box` mutable-list pattern; `nonlocal` would be cleaner
- **6.70** repair loop vs OCR loop not coordinated; possible double re-OCR
- **6.71** frozen dataclasses containing unhashable fields break the hashable promise
- **6.72** `cast("JobRunner", ...)` string syntax unneeded with future annotations
- **6.73** duplicate of 9.16
- **6.74** `start`/`shutdown` idempotency (verified OK; informational)
- **6.75** queue worker swallows runner exceptions; document the trade-off
- **6.76** `_mark_cancelled` discard semantics (OK; informational)
- **6.77** cancelling an already-terminal job suppresses `JobCancelled`; UI may spin
- **6.78** progress `frame_cap` is soft when done-callbacks never fire
- **6.79** `broadcast` returns submissions, not successes; document
- **6.80** `_on_foreign_send_done` catch is over-broad; catch `KeyError` only
- **6.81** extensionless upload filenames fall back to `.pdf`; misleading
- **6.82** defensive `assert self._progress is not None` after outer check
- **6.83** sync path gets no cancel check (`job_id=""` short-circuit)
- **6.84/6.85** `started_at` always None; populate or document
- **6.86** masked `api_key == "******"` skip contract is subtle; document
- **6.87** `update_config` writes even unchanged values; `model_copy(update=...)`
- **6.88** `OCRRequest` is 18 fields / 4 validators; consider nested config
- **6.89** `_coerce_bool` field list duplicates declarations
- **6.90** duplicate of 4.21
- **6.91** recall `from_env` enable-default semantics (OK; informational)
- **6.93** text_layer `close` is sync, forcing `to_thread`; document
- **6.94** text-layer line grouping order note (final re-sort makes it OK)
- **6.95–6.101** loader parse/merge/validate behaviors (verified OK; informational)

### 2.6 Closed since the first pass (record)

Committed: **1.2** (loader env-override case folding), **1.6** (shutdown
pagination), **1.9** (text_layer assert → explicit None check), **1.10**
(chat_client assert → explicit RuntimeError).

In the uncommitted Wave 1 batch (§1): **1.1, 1.3, 1.4, 1.7, 1.8, 9.1**.

**Wave 2 (this commit):** **1.5** (real bug, blob leak on INSERT OR
REPLACE) + **5.2** (its regression test).

**Wave 2 (continued):** **1.11** + **1.12** — `OCRProcessor` class-level
settings no longer call `load_settings()` at import. The class-level
constants are hardcoded defaults; `__init__` resolves the live values
via `load_settings()` and `env_int()` at instance time. Two existing
test files (`test_vlm_timeout_env.py`,
`test_phase5_env_and_spellcheck.py`) were rewritten to test the new
per-instance env contract.

**Wave 2 (continued):** **1.15** — `WhitespaceRecallBooster.supplement`
now falls through to the absolute `_FALLBACK_MIN_HEIGHT` /
`_FALLBACK_MAX_HEIGHT` band when *every* surya box has zero height,
instead of multiplying the fallback by `_MIN_HEIGHT_FRACTION` /
`_MAX_HEIGHT_FRACTION` and collapsing the height window to
~[3 px, 15 px]. Two regression tests added to
`tests/core/recall/test_text_recall.py`.

**Wave 2 (continued):** **1.18** — `check_ssrf_target_sync` reuses a
module-level `ThreadPoolExecutor` (`_SSRF_EXECUTOR`,
`max_workers=2`) instead of allocating a fresh pool per call on the
OCR hot path. Regression test
`test_check_ssrf_target_sync_uses_module_level_executor` in
`tests/utils/test_ssrf.py` counts `ThreadPoolExecutor.__init__`
calls during repeated sync checks and asserts it stays at 0.

**Wave 2 (continued):** **7.12** — `OMNISCRIBE_QUALITY_LOOP` /
`OMNISCRIBE_QUALITY_TARGET` / `OMNISCRIBE_QUALITY_MAX_RETRIES` are
now first-class fields on `RuntimeSettings`
(`ocr_quality_loop_enabled`, `ocr_quality_target`,
`ocr_quality_max_retries`). Out-of-range values are rejected at
settings-load time instead of crashing the OCR plugin during
`apply()`. Four regression tests in `tests/test_cordis_settings.py`.

**Wave 3 (this batch):** **9.5** + **9.7** (dead helpers deleted:
`service_protocol()` and `null_provider()`), **3.1** + **3.2**
(truly-dead per-service auth tokens + legacy `LOCAL_DEEPL_*` aliases
removed from `RuntimeSettings`; `transcription_auth_token` kept
because it flows into the config-mask path), **3.3**
(`OMNISCRIBE_MAX_PAGES` declared on `RuntimeSettings`;
`OMNISCRIBE_TRUSTED_PROXIES` removed from `.env.example` and
`SECURITY.md` because it was never implemented).

**Wave 4 (this batch):** **2.1** + **2.7** (security sweep on
public surfaces: ``GET /api/export/docx`` deleted because the
text-in-query-string variant leaked the document body to
uvicorn / proxy / browser-history / Referer; the Flutter
client was updated in lockstep to POST the text in the
request body. ``fetch_result`` failures now collapse to a
single uniform 404 + ``"result not available"`` detail so
job-id enumeration via differential status codes is no
longer possible.)

**Wave 5 (this batch):** **9.2** / **9.3** / **9.4** (per-Context
effect-id counter + ``EffectScope.aclose`` failure isolation
+ thread-safe ``add``); **9.6** (retry
``LexiconProvider.get`` on ``ImportError`` so a later
``uv sync --extra lexicon`` doesn't need a restart);
**9.15** / **9.16** (dedupe the three runner Protocols
behind a shared ``_JobRunnerContract`` base + canonicalise
the terminal status set in ``state_backend``).

---

## 3. Five-domain audit — deferred Medium/Low backlog (2026-08-29)

All **Critical and High** findings across the five domains are closed
(sprints 1–6 + follow-up batches; see CHANGELOG "cumulative audit status"
entries). Sprint 6 additionally cleared the flagged residuals (dead code,
`os.getenv` bypasses, `asyncio.get_event_loop`, god-function splits). The
Medium/Low items below were **never individually verified closed** — treat
as a candidate backlog and re-verify file:line before working (code has
moved since 2026-08-29).

**Domain 1 — Core Pipeline (Medium):** refine stage decodes all target
pages at once (reuse `_decoded_cache`) · fresh unclosed `AsyncOpenAI` per
OCR request (cache per `api_base` or `aclose()`) · throwaway unclosed
client per grounded run (`ensure_model_loaded`) · first-use HF model loads
on the event loop in local_engine/trocr/nllb (use `asyncio.to_thread`) ·
process-wide breaker registry shares one `asyncio.Lock` across loops
(use `threading.Lock`) · embedder pre-rasterizes all pages before serial
construction (interleave in bounded batches) · cancelled grounded tasks
never awaited in finally (gather with `return_exceptions=True`).

**Domain 1 — Core Pipeline (Low):** one PIL page shared across concurrent
crop threads (document or lock) · triple image decode per page in layout
stage · O(repaired × blocks) identity scan in grounded.py · lexicon
fallback/listing loads entire tables (partially addressed by Sprint 6
LanceDB pushdown) · nllb deprecated `get_event_loop()` + no concurrency
guard.

**Domain 2 — API & Security (Medium):** `_parse_upload` buffers the whole
upload before the size check (byte-budget streaming; TTL-expire
bookkeeping) · default cordis patch path lives in the shared temp dir and
patch `use:` executes arbitrary `module:attr` (mode-0700 default; log
pickup) · non-loopback/placeholder-token guards live only in CLI `main()`,
bypassed by `uvicorn omniscribe.server:app` (move into `create_app()`).

**Domain 2 — API & Security (Low):** `/api/progress/cancel/{channel_id}`
requires no session token · `DELETE /api/jobs` unauthenticated wipe · no
Origin check on WS handshake + stale `?token=` comment · provider
`api_key` as query param (leaks to logs) · artifact token compared with
`!=` not `compare_digest` · `ValueError` text echoed to clients · SQLite
DB/artifacts default into world-readable temp dir · env overrides are
trust-equivalent to editing cordis.yml (document).

**Domain 3 — Frontend (Medium):** workstation relies solely on WS frames
after async submit (poll status on WS close; fetch result) · result token
duplicated into query param + header (header only) · server health badge
is a simulation (wire `/api/health`) · a11y coverage is 2 files vs ~30
screens; client-tests job missing from the AGENTS.md gate table.

**Domain 3 — Frontend (Low):** job "Download" discards fetched bytes ·
per-call `wsUrl` ignored on reconnect · dead `/health` + `/api/ready`
constants · benign job status-schema drift (add round-trip contract test
against `tests/openapi.json`).

**Domain 4 — Testing & QA (Medium):** coverage gate only in CI flags, not
local addopts · marker drift (`slow_dataset`) between CI/Makefile/nightly
· wall-clock budget meta-test is a flake candidate · `importlib.reload`
leaks state mid-suite · untested modules (`page_preprocess.py`,
`local_engine.py`, `ocr_quality/routing.py`) · fixed-sleep negative
assertion in `test_jobs_plugin.py`.

**Domain 4 — Testing & QA (Low):** nightly stale `force_run` comment ·
Semgrep image pinned by mutable tag · CI runs `mypy src tests` but local
gate runs `mypy src`.

**Domain 5 — DevOps & Config (Medium):** compose aborts without
`REDIS_PASSWORD` though `.env.example` claims to ship a generator
one-liner · image Python 3.14 is tested nowhere (CI tests 3.11–3.13) ·
DEPLOYMENT.md profile 3 pulls a GHCR image no workflow publishes · no
`HF_HOME` for surya's model download in the runtime stage · `start_app.vbs`
`f.Close` on an FSO File aborts boot when the log exceeds 10 MiB.

**Domain 5 — DevOps & Config (Low):** Redis password visible in process
argv · plaintext `redis-password.txt` (acceptable for single-user
desktop) · uv tarball SHA-256 verified only in install.ps1 · pre-commit
uv hook rev vs pinned uv drift · no dependency-review gate.

**Flutter-client deferred backlog** (from the Sprint 3 close): full
axe/a11y regression coverage, complete 48 dp touch-target sweep, all
keyboard shortcut bindings.

---

## 4. Phase C follow-ups

1. **Sanitize `JobRecord.error` echoes** — the generic
   `/api/jobs/{job_id}/status` route echoes `str(exc)` verbatim for failed
   jobs (pre-existing OCR surface). Job ids are uuid4 so risk is low.
2. **Fourth-producer registry** — three runner producers now exist
   (`JobRunner`, `TranslationJobRunner`, `GlossaryJobRunner`, dispatched
   via payload-class `runner_protocol` in
   `InMemoryJobQueue._resolve_runner`). If a fourth appears, generalize to
   a registry (see also 9.14/9.15).
3. **Docs polish** — ARCHITECTURE.md tables dated 2026-06-03 still
   reference deleted `api/celery_app.py` (add "(since deleted)");
   DEPLOYMENT.md's auth section still describes per-route tokens although
   the surface is unauthenticated today.
4. **Transcribe spec-wording drift (informational)** — text artifacts are
   stored as page-dict JSON (`application/json`), not the spec's literal
   `text/plain`; the response `job_id` is a synthetic `job-<hex>` used as
   artifact owner for pruning. Both are plan-pinned; no transcription
   status route exists to poll them.
5. **Pedantic findings 2.1/2.2** need paired Flutter client changes when
   scheduled (see §2.2).

---

## 5. Deferred capabilities (documented in AGENTS.md)

Product-level deferrals, not bugs — listed for completeness:

- **Auth / rate-limit / upload-size ASGI middlewares** — the rebuilt route
  surface is unauthenticated; do not expose the server to untrusted users
  until the auth middleware plugin lands. Related pedantic items: 3.1,
  3.2, 7.5.
- **Redis state backend** — deferred in the harness rebuild; the
  `OMNISCRIBE_STATE_BACKEND=redis` value passes settings validation but
  crashes at plugin apply (pedantic 4.24 — unify the allowlists).
- **Model pre-flight route** — the historic `GET /v1/models` check is
  actually implemented in-core as `ensure_model_loaded`
  (`core/ocr/processor.py`); AGENTS.md's "not yet re-implemented" claim is
  stale (pedantic 7.2/7.3). The OCR plugin only seeds the `verify_model`
  config key.
- **slow_dataset fixtures** — `scripts/fetch_datasets.py` is a no-op skip
  until the upstream license review clears (OCR-Quality / KIE-HVQA
  regression data).
