# OmniScribe — Pedantic Code Review

A line-level, petty, pedantic audit of the codebase as of 2026-08-30. Every
finding cites a `file:line` reference. Findings are grouped by category, not
by severity — the summary at the end ranks them.

Scope: `src/omniscribe/` and the operator-facing `AGENTS.md` /
`.env.example` docs. The Flutter client (`client/`), test fixtures
(`tests/`), and one-off scripts (`scripts/`) are out of scope unless cited
in passing.

## 1. Real bugs (correctness)

### 1.1 `ALLOW_SSRF_LOCAL` default contradicts the documented intent
`src/omniscribe/config.py:123` declares `allow_ssrf_local: bool = Field(default=False, validation_alias="ALLOW_SSRF_LOCAL")`. But `AGENTS.md:177` and `.env.example:63` both document **`true` as the local-development default**. A user who copies `.env.example` to `.env` and never touches that line gets `true`; a user who sets the variable through any other means (system env, Helm, systemd unit) gets `False` and the server refuses to talk to a local LM Studio. This is the kind of footgun the audit-fix comments say you're closing. The fix is one line: `default=True`.

### 1.2 `harness/loader.py:135` env-override lookup is case-sensitive against `row.id`
```python
overrides.setdefault(plugin_part.lower(), {})[field_part.lower()] = raw
...
if row.id in overrides
```
`overrides` is keyed by the **lowercased** plugin id from the env var, but `row.id` keeps the YAML's original casing. A `cordis.yml` row that capitalises its id (`id: Runtime`) silently drops every `OMNISCRIBE_PLUGIN_Runtime__*` override. The lookup should be `overrides.get(row.id.lower(), {})`.

### 1.3 `plugins/ocr/service.py:55-59` — `cancelled` is squashed to `error`
```python
"cancelled": "error",
```
A user-cancelled job surfaces in the UI with `status: "error"` and `error: "Job cancelled."`. The Flutter client (per AGENTS.md's "Frontend types" promises) can no longer distinguish "I hit cancel" from "the model OOM'd." This is observable in `JobStatusResponse.status` and the SSE replay.

### 1.4 `plugins/ocr/service.py:264-276` — `cancel_check` doesn't observe the `JobCompleted` race
The `check()` closure returns `True` if either the queue's `is_cancelled` or the progress channel's `is_cancelled` is set. But the runner is wrapped in `asyncio.to_thread` (per AGENTS.md note), so the cancel gate is the only signal the worker thread sees. The `OCRServiceImpl.run_job` does **not** call `check()` after the runner returns, so a cancel that arrives between the last `check()` and `_artifacts.put(...)` will still persist the result PDF. Then `JobCompleted` is emitted with the token, and the next `cancel_job` returns `False` (terminal), but the file is already on disk. Net effect: cancel a job, get a downloadable PDF.

### 1.5 `plugins/state_backend_sqlite.py:131-145` — `INSERT OR REPLACE` leaks the previous blob file
```python
def _put() -> None:
    conn = self._require_conn()
    path = self._blob_path(id)
    path.write_bytes(blob)         # writes new blob
    conn.execute("INSERT OR REPLACE INTO artifacts ...", ...)
    conn.commit()
```
If the same `id` already exists (operator-initiated cleanup, restore from backup, ad-hoc SQL), the new blob overwrites the row, the new `.bin` file is written, **but the old `.bin` is never `unlink()`ed**. Long-lived SQLite installs will silently leak the bytes of every overwritten artifact. The `delete_artifact` path (line 187) does the unlink properly, so the asymmetry is purely a bug in `put`.

### 1.6 `plugins/jobs.py:208-213` — `shutdown` cancels only the newest 1000 queued jobs
```python
for record in await self._backend.list_jobs(limit=1000):
    if record.status == "queued":
        ...
```
`list_jobs` orders by `created_at DESC`. With a queue flood (>1000 pending), the *oldest* jobs never get their status flipped to `cancelled` and never get a `JobCancelled` event. They sit as "queued" forever in the SQLite backend (where they survive restart). 1000 is also a magic number with no constant or env override.

### 1.7 `plugins/ocr/plugin.py:135` — AVIF magic-byte check is too narrow
```python
or head.startswith(b"\x00\x00\x00\x1c")  # AVIF ftyp
```
The AVIF/HEIF `ftyp` box size is variable (anything from 20 to several hundred bytes). Only files whose first 4 bytes are `0x0000001C` (exactly 28) pass. A real `ftyp` size of 32 (e.g. with `mif1` brand + minor version padding) fails this check and gets a 415, even though PyMuPDF/Pillow would happily decode it. A correct check looks for `b"ftyp"` at offset 4–7 and one of `b"avif"`, `b"avis"`, `b"mif1"` at offset 8–11.

### 1.8 `plugins/ocr/plugin.py:107-128` — `application/octet-stream` bypasses magic-byte check
The `content_type != "application/octet-stream"` clause short-circuits the magic-byte verification. The comment justifies this as a "Flutter file picker fallback", but the same bypass applies to any HTTP client that lies about the content type. An attacker who can submit a form with `Content-Type: application/octet-stream` and arbitrary bytes gets past `_parse_upload`. The downstream pipeline will of course fail on non-PDF/non-image content, but you lose one of the two layers you advertised in the H-5 audit fix.

### 1.9 `core/recall/text_layer.py:165` — `assert` as defensive check
```python
def _supplement_inner(...):
    assert self._doc is not None
```
Asserts are stripped under `python -O`. The wrapper's "fail-open" guarantee silently becomes "crash with `AttributeError` and the bare `self._doc` access on the next line." Use an explicit `if self._doc is None: return []`.

### 1.10 `core/ocr/chat_client.py:161` — same `assert last_exc is not None` problem
`assert` after a loop that always assigns on first iteration is defensive, but again it's an assertion. A retry loop where the first `try` raises will leave `last_exc` set; the only way to reach line 161 with `last_exc is None` is an `asyncio.CancelledError` raised before line 140 — which is its own bug class (CancelledError is not a regular Exception, but the `except Exception` is below). Run with `-O` and you can get an `AttributeError` on `str(last_exc)`.

### 1.11 `core/ocr/processor.py:153` — instance `page_max_tokens` re-binds the class constant
```python
self.page_max_tokens: int = self.PAGE_MAX_TOKENS
```
The F1.9 audit fix moved the runtime-tunable settings into `__init__`; `page_max_tokens`/`crop_max_tokens` re-bind the class constant at instance time. A `load_settings()` env-var change after import doesn't reach the instance via the `OMNISCRIBE_VLM_PAGE_MAX_TOKENS` env (it never went through `load_settings()` at all). The behaviour is silently inconsistent with the F1.9 fix you're documenting 30 lines above.

### 1.12 `core/ocr/processor.py:111-126` — class-level constants call `load_settings()` at import
`PAGE_TIMEOUT_S = load_settings().vlm_page_timeout`, `MAX_RETRIES = load_settings().llm_max_retries`, etc. The "fallback for `__new__` in tests" justification is fine, but the side effect is that **importing `omniscribe.core.ocr.processor` parses the full env and instantiates a `BaseSettings`**. That makes the module un-importable in subprocesses that haven't set up env (e.g. some CI tests, some static-analysis runs). The `__getattr__` workaround papers over it, but every import of the module still pays the cost.

### 1.13 `harness/context.py:78-79` — service re-registration overwrites silently in one path
The `service()` method (line 73) raises `ValueError` for a duplicate key, but `dispose()` then `plugin.apply()` could re-register the same protocol in tests. The harness's `unload` path correctly removes services (`_reverse` for `kind="service"`, line 211), so in normal flow this is fine. The smell: a test that does `ctx.dispose()` then a fresh `Loader(ctx).load(...)` would crash if the dispose→reload sequence re-enters the same plugin. There's a test helper around this; if it's intentional, the `ValueError` could be `RuntimeError` so it doesn't look like an `is`/`==` confusion in logs.

### 1.14 `harness/context.py:166-184` — failed `apply()` cleanup can leak the exception
```python
self._plugin_order.remove(plugin_id)
self._plugin_instances.pop(plugin_id, None)
refs = self._plugin_effects.pop(plugin_id, [])
for ref in reversed(refs):
    await self._reverse(ref)
raise
```
If `_reverse` raises (a plugin's own `dispose` does cleanup that fails), the original `apply` exception is replaced and the loader never knows the real reason. The `from exc` is also lost. The `try/except` in `Context.plugin` is doing two jobs — rollback and re-raise — and the rollback is silently best-effort.

### 1.15 `core/recall/whitespace.py:181-188` — `min_height` falls through to a tiny floor on empty Surya
```python
heights = [b[3] - b[1] for b in surya_boxes if b[3] - b[1] > 0]
median_h = statistics.median(heights) if heights else _FALLBACK_MIN_HEIGHT  # 0.006
min_height = _MIN_HEIGHT_FRACTION * median_h  # = 0.0027
```
On a page where Surya returned **only zero-height boxes** (you have a separate `if ... > 0` filter that drops them, so this is reachable when all are degenerate), the recall filter floor drops to 0.27% of page height. The "candidate_height" check on line 199 then accepts anything ≥ that floor. With a 1024-px-tall image, that's ~3 pixels — basically any horizontal ink stripe. The booster is documented to err on the side of precision; this is the precision breach. Either skip the page or use a non-tiny floor.

### 1.16 `core/recall/text_layer.py:111` — extension check rejects uppercase PDFs
```python
if not input_path.lower().endswith(".pdf"):
    return False
```
Fine on POSIX (case-sensitive), but on Windows the same `.lower()` makes this a no-op, so this is actually OK. The real issue is the converse: an `.html` file with a `%PDF-` magic in its first 4 bytes is correctly *not* opened (pass returns False), but a renamed `.pdf` whose first bytes are not `%PDF-` returns `False` silently — no log, no warning. The booster and text-layer both silently no-op for every non-PDF input, including inputs that the rest of the pipeline would happily accept as image. Worth a debug log.

### 1.17 `utils/security.py:216-253` — `is_blocked_host` is sync and can block an event loop
The docstring never says "do not call from an async context." Anyone who reaches for it inside an async route handler (or, more likely, a future plugin) gets a multi-second `socket.getaddrinfo` call on the main loop. There's already a `check_ssrf_target_sync` helper specifically for sync use, but the *unsafe* sync helper ships side-by-side. Either rename to `_is_blocked_host_blocking_unsafe` or add a giant "do not call from an event loop" warning at the top.

### 1.18 `utils/security.py:269-270` — `ThreadPoolExecutor` per SSRF check
```python
with ThreadPoolExecutor(max_workers=1) as executor:
    future = executor.submit(asyncio.run, is_ssrf_target(url))
    return future.result()
```
A new thread + a new event loop per call. This is called on the request hot path (`plugins/ocr/pipeline_bridge.py:57` and `plugins/ocr/service.py:368`). The thread-pool + new-loop churn is hundreds of microseconds per call. A module-level singleton executor (or a pre-spun `asyncio.run` style helper that uses `loop.run_in_executor`) would be dramatically cheaper.

### 1.19 `utils/security.py:74-87` — `_is_blocked_ip` conflates "reserved" with "private"
`is_reserved` in Python's `ipaddress` is broader than RFC 1918 — it includes 240.0.0.0/4 and the like. Some operators run LM Studio or Ollama on addresses inside IANA-reserved ranges (e.g. carrier-grade NAT). The `ALLOW_SSRF_LOCAL=true` escape hatch covers this only for documented "local" ranges; a 100.64.0.0/10 LLM endpoint (allowed in CGNAT) is "private" per Python but might be intended. Worth a one-liner comment that this is a deliberate choice.

---

## 2. Security / data hygiene

### 2.1 `plugins/documents/routes.py:128-131` — `GET /api/export/docx` puts text in the query string
```python
@router.get("/api/export/docx")
async def export_docx_get(text: str = "") -> Response:
    return _docx_response(text)
```
A GET with `?text=...` lands in:
- uvicorn's access log
- any reverse-proxy access log
- browser history
- the Referer header to anything the browser then loads

The Flutter client uses this per AGENTS.md; the clean fix is `POST /api/export/docx` only and delete the GET. The `_docx_response` function is then only called by the POST handler and the file size is no longer URL-bounded.

### 2.2 `core/ocr/processor.py:252-256` — `client.close()` is called inside a `try/finally` on every pre-flight
```python
try:
    loaded = await _list_loaded_model_ids(self.client, self.api_base)
    if not _model_in_loaded(self.model, loaded):
        raise ModelNotLoadedError(...)
finally:
    close_method = getattr(self.client, "close", None)
    if callable(close_method):
        res = close_method()
        if asyncio.iscoroutine(res):
            await res
```
The client is an `AsyncOpenAI` instance created in `__init__`. Closing it on every pre-flight means the next pre-flight (next request) needs a fresh client. If the engine reuses one `OCRProcessor` across many requests, the client is being closed each time. This is either a leak (client never reopens) or a perf cliff (re-open every time). The intent is unclear from the code.

### 2.3 `server.py:75-83` — `_load_optional_module` returns the module, not just the symbol
The function signature returns the whole module on `ModuleNotFoundError`. Every consumer (lines 116-118, 151, 415) does `_load_optional_module("fastapi")` and then `fastapi.FastAPI(...)` — five separate module-attribute lookups. A small helper `_load_attr("fastapi:FastAPI")` would be a tighter API and would let you centralize the "optional dep missing" message.

### 2.4 `server.py:150` and `server.py:371` — `load_settings()` is called twice per startup
Each call re-instantiates `RuntimeSettings(**overrides)`. The objects are equal but not identical. The lifespan's `_validate_runtime_settings` runs first (line 124), then the CORS guard at line 371 calls `load_settings()` again. If anything between them mutates env (it shouldn't, but the `RuntimeSettings` model is mutable), the two objects diverge. Use one call and pass the object.

### 2.5 `server.py:195` — `import logging as _logging` inside the exception handler
Re-importing the stdlib `logging` module for a single `getLogger` call is harmless but stylistically weird. Just use the module-level `_log` you already declared (line 32). The fact that this handler uses `_logging` while the rest of the file uses `_log` is inconsistent.

### 2.6 `plugins/ocr/service.py:189-194` — submission_id map is bounded by insertion order, not by job_id
```python
while len(self._submission_to_job) > self._max_buffered_jobs:
    self._submission_to_job.pop(next(iter(self._submission_to_job)), None)
```
`next(iter(dict))` is insertion order. If the in-flight job rate is steady, this trims the *oldest* unconsumed submission id. But `submission_id` → `job_id` is only needed for the `run_job` round trip. The submission_id is also stored on the `JobRecord.request_meta`. The map is duplicated state and is bounded at 500, but the bound and the `prune` cleanup (line 429-430) drift apart: the implicit cap here is `max_buffered_jobs`, the explicit `prune` is also `max_buffered_jobs`. They share the constant, but the eviction policy and timing are different. The `prune` happens on demand; this one happens on every `submit`. Fine, but it's a duplicate eviction policy that will be re-discovered in 6 months.

### 2.7 `plugins/ocr/service.py:327-347` — `fetch_result` reveals job existence via differential status code
Unknown job → 404, completed with bad token → 403, in-progress → 409. The Flutter client (and any attacker) can use this to enumerate which `job_id` values exist before attempting a token guess. Collapse to a single 404 for "unknown or invalid" and skip the 403.

### 2.8 `core/document.py` and `core/ocr/processor.py` — `_OcrPayload` and `JobRecord.request_meta` leak the upload bytes summary into a stringly-typed dict
`payload.file_bytes` (the whole upload!) is held in `_submission_to_job` via `_OcrPayload` until `run_job` consumes it. The default `MemoryStateBackend` holds the result PDF in memory **plus** the original upload in memory for the entire job lifetime. On a 10-GB upload (the default `MAX_UPLOAD_MB`!) and a slow job, that's two full blobs in the heap. There's no streaming pipeline.

### 2.9 `utils/env.py:171-176` — `env_bool` is too loose
```python
return value.strip().lower() not in {"0", "false", "no", "off"}
```
A value of `"banana"` returns `True`. Compare to `_parse_bool` in `plugins/ocr/schemas.py:36-41` which uses the closed set `{"true", "1", "yes", "on"}`. Two different boolean vocabularies in the same project. Document a canonical list (or import a single helper).

---

## 3. Documentation / code drift

### 3.1 `AGENTS.md:123` says the route surface is "currently unauthenticated", but `config.py:127-152` accepts `ocr_auth_token`, `translation_auth_token`, `transcription_auth_token`
Three auth tokens are configured, none are consumed by any route. They show up in the `_validate_runtime_settings` log only as a single boolean `auth_enabled`. The fields are still useful as scaffolding for the deferred auth middleware, but their presence is misleading. Either delete the fields or surface a deprecation plan.

### 3.2 `config.py:128-145` — every auth-token field has a `LOCAL_DEEPL_*` alias
The product was renamed from `localdeepl` to `omniscribe`; the alias `AliasChoices("OMNISCRIBE_AUTH_TOKEN", "LOCAL_DEEPL_AUTH_TOKEN")` is dead. Same for OCR, translation, transcription, CORS origins, max upload, rate limit. Six legacy aliases carry forward the old name. If the rename was intentional, the legacy aliases can go.

### 3.3 `.env.example:50-58` — `OMNISCRIBE_MAX_PAGES`, `OMNISCRIBE_TRUSTED_PROXIES`, `OMNISCRIBE_RATE_LIMIT_PER_MIN` are documented but not declared
`grep "OMNISCRIBE_MAX_PAGES" src/` returns zero hits. `OMNISCRIBE_TRUSTED_PROXIES` is not in `config.py` either. `OMNISCRIBE_RATE_LIMIT_PER_MIN` *is* declared (`config.py:165`) but the trusted-proxy and max-pages settings have no declaration. Either the env example documents a feature that doesn't exist, or the configuration is loaded somewhere outside `config.py`.

### 3.4 `.env.example:15-23` and `config.py:34-46` use different env names
`.env.example` documents `LLM_API_BASE`, `LLM_MODEL`, etc. `config.py` accepts both `LLM_*` and `OMNISCRIBE_LLM_*` aliases. Fine, but `.env.example` doesn't show the `OMNISCRIBE_LLM_*` form, so users who search for it come up empty.

### 3.5 `AGENTS.md:128` says the LLM coordinate defaults are exposed in `/api/config`, but the sync `seed` in `plugins/ocr/service.py:88-113` has 22 keys and the GET returns 22 keys with `api_key` masked — yet the docstring on `OCRServiceImpl.__init__` (line 116) doesn't list the seeded keys. Anyone editing the seed list has no canonical "what is exposed" doc.

### 3.6 `AGENTS.md:11` advertises a `/api/jobs/{job_id}/result` endpoint; the route is at `/api/jobs/{job_id}/result` (`plugins/ocr/plugin.py:218`). Match — but the security note in `JobStatusResponse` (`schemas.py:124-135`) says clients get the token via SSE, while `AGENTS.md:122` says the result URL is a polled endpoint. Two different stories.

### 3.7 `core/ocr/processor.py:282` comment references `tests/core/ocr/test_ocr.py::TestPromptConstants::test_olmocr_prompt_is_canonical` and `test_prompt_version_is_present`. Verified the prompts file at `core/ocr/prompts.py:12-14` references the same tests, but the AGENTS.md doesn't list them. If they exist, they should be in the test inventory; if not, the comment is broken.

### 3.8 `core/recall/whitespace.py:42-43` mentions `docs/superpowers/plans/2026-08-14-whitespace-recall.md`. No such file exists under `docs/`. Either the doc is missing or the path is stale.

### 3.9 `core/recall/text_layer.py:1-17` and `core/recall/whitespace.py:1-18` are near-duplicate module docstrings. Both reference the same "second box source", the same merge order, the same fail-open guarantees. The constants and the `MAX_*_BOXES_PER_PAGE = 10` cap are duplicated. Promote the shared knobs to a single module.

---

## 4. Naming / API smells

### 4.1 `config.py:153-157` `cors_origins_raw: str | None` with a `.cors_origins` property
The `*_raw` naming convention is unusual for Pydantic. A `list[str]` field with a `field_validator` would be cleaner and would let the typed value be used in nested models (the property pattern is opaque to anyone reading a model dump).

### 4.2 `config.py:280-283` `_disable_negative_rate_limit`
```python
return None if value is not None and value <= 0 else value
```
The name reads as "disable the function when value is negative" but it actually means "treat 0 and negatives as None (disabled)." Rename to `_coerce_rate_limit_off` or document.

### 4.3 `config.py:243-264` `_inherit_llm_model_for_grounded` checks a magic string
```python
if self.grounded_model == "qwen/qwen3-vl-8b" and os.environ.get("LLM_MODEL"):
```
If the default `grounded_model` ever changes, this logic silently stops inheriting. Use a sentinel (`_UNSET = object()`) and compare against `self.model_fields_set` or a dedicated `grounded_model_explicit` flag.

### 4.4 `core/ocr/chat_client.py:104` — the `M3 audit fix` comment is good, but the surrounding `last_exc` pattern is fragile
A retry loop that conditionally retries and then unconditionally references `last_exc` after the loop has an implicit invariant: at least one iteration ran AND that iteration raised. The invariant is documented implicitly but not asserted. The `assert last_exc is not None` (line 161) — see also bug 1.10.

### 4.5 `core/ocr/processor.py:69` `TrOCREngine` is `TYPE_CHECKING` only but the engine wires it in production
The `__init__` parameter `trocr_engine: TrOCREngine | None` is type-hinted via `TYPE_CHECKING`. The actual runtime code at line 358 (`self.trocr_engine.recognize(...)`) imports nothing at runtime; if `TrOCREngine` is None, the code is dead. If a user passes a non-`None` instance, the class is dynamically resolved via the import. The type-hint-as-string pattern here is fine, but the "lazy import" isn't lazy — the user has to have installed whatever package provides the engine. Document the requirement.

### 4.6 `core/recall/whitespace.py:107` & `text_layer.py:71-75` — identical disable-value sets
```python
_DISABLE_VALUES = {"0", "false", "no", "off", "n", "disabled"}
```
Two copies. Promote to `omniscribe.utils.env` as `env_bool_with_disable_set`.

### 4.7 `core/recall/text_layer.py:33-56` and `core/recall/whitespace.py:33-92` — different `__init__` signatures for similar objects
`WhitespaceRecallOptions.from_env()` vs `TextLayerRecallOptions.from_env()`. Same shape, different names. Promote to a shared base.

### 4.8 `core/workflow/hybrid_repair.py:53-65` `_RepairEngineHost` Protocol
Defined as a Protocol but only used for `ocr_processor` and `block_callbacks`. The rest of `HybridEngine` (e.g. `_decoded_get`) is accessed via direct attribute access (`engine.ocr_processor`, not via the protocol). The Protocol documents a contract that the rest of the file then breaks.

### 4.9 `core/workflow/hybrid.py:300-303` — `input_path: str = ""` default
The kwarg default of `""` is meant to be "no text-layer recall" (since `text_layer.open("")` returns False on a non-PDF path), but it's also reachable from the `_detect_layout` call where `input_path` is always provided. The default of `""` is dead code that papers over an unused parameter on `_detect_layout`.

### 4.10 `plugins/state_backend.py:200-206` — circular import workaround
The comment is honest ("after the dataclasses + plugin class are defined") but the pattern (re-export after-the-fact with `# noqa: E402`) is fragile. Anyone reordering the file at line 198 will hit a circular import that's only obvious from the comment. Use a `_state_backend.py: types` split.

### 4.11 `plugins/jobs.py:36-70` and `plugins/state_backend.py:36-70` define overlapping concepts
`JobStatus` literal lives in `state_backend.py`. `_TERMINAL_STATUSES` lives in `jobs.py`. The `JobCompleted` event has `artifact_id` and `artifact_token` fields, the `JobRecord` has `result_artifact_id` and `result_artifact_token`. Four names for two concepts.

### 4.12 `core/ocr/resilience.py:55-63` `_PYTHON_BUG_EXCEPTION_TYPES`
Treats `ValueError` as a "programming bug" and never retries it. But many transient parse errors (JSON decode, base64 decode, etc.) raise `ValueError`. The list conflates "the OCR processor has a bug" with "the LLM returned garbage we should retry." Either narrow the list or document the policy.

### 4.13 `core/ocr/resilience.py:163-177` `CircuitOpenError(failures, retry_after)` and `retry_after: float`
The `retry_after` is computed at check-time (line 252) and is a number. The HTTP layer could surface this as a `Retry-After` header for clients. There's no such wiring anywhere.

### 4.14 `core/ocr/processor.py:71` — `load_dotenv()` at module level
`server.py:25` also calls `load_dotenv()`. Two `load_dotenv()` calls, idempotent but noisy. Move to the entry point only.

### 4.15 `cli/migrate_lexicon.py:1-15` is the only entry in `src/omniscribe/cli/`. `AGENTS.md:78` says the user-facing CLI has been deprecated. But the CLI package still ships. A grep for `omniscribe-` script entries (in `pyproject.toml [project.scripts]`) is needed — if `omniscribe-migrate-lexicon` is registered, it's a contradiction with the AGENTS.md statement.

### 4.16 `core/ocr/prompts.py:62-65` `_MODELS_WITHOUT_SYSTEM_ROLE` — `"olmocr"` is a substring of `"allenai/olmocr-7b-0225-preview"`
```python
return not any(needle in name for needle in _MODELS_WITHOUT_SYSTEM_ROLE)
```
`name = "allenai/olmocr-7b-0225-preview".lower() = "allenai/olmocr-7b-0225-preview"`. The check `"olmocr" in name` is True (it's a substring of the model name). But `"allenai/olmocr-2-7b"` also matches `"olmocr-2-7b"` (no, actually it doesn't match `"olmocr"` alone because... wait, `"allenai/olmocr-2-7b"` lowercased is `"allenai/olmocr-2-7b"`, which contains `"olmocr"`. OK, all three are matched. Substring matching is the intent, but the comment on line 65 says `"olmocr"` is a separate model. The matching would also trigger on `"my-fine-tuned-olmocr-2-7b-clone"` — which may or may not be desired.

### 4.17 `core/ocr/processor.py:381-391` `TrOCR` arbitration exception handler
```python
except Exception as e:
    logger.warning("TrOCR arbitration failed: %s", e)
    return vlm_result
```
`except Exception` is fine here, but the inner `import base64` (line 353) belongs at the top of the file. Same for the `_heuristic_confidence` import.

### 4.18 `plugins/ocr/plugin.py:166-206` `process_events` SSE loop
The `asyncio.wait_for(service.wait_for_events(job_id), timeout=SSE_KEEPALIVE_SECONDS)` (line 199-202) is wrapped around a coroutine that **clears its own event on wake** (`service.py:447` `notify.clear()`). If a second frame lands during the `yield` of the previous frame, the event is set again, but the cleared event has already been observed and the wake doesn't fire. This is a classic asyncio event-flap bug; SSE clients would see interleaved or dropped frames. The fix is to use a `collections.deque` of frames rather than a clear-on-wait event, or to check backlog size after wake.

### 4.19 `plugins/ocr/service.py:189-194` `max_buffered_jobs` is the cap on submissions, events, and done jobs
Three different data structures (`submission_to_job`, `event_buffers`, `done_jobs`) all share the same cap, but `_prune_events_if_needed` (line 400) keeps them loosely in sync. The `prune` method (line 415) is also a separate eviction pass with the same logic. Two functions, same logic, two names. Fold.

### 4.20 `plugins/ocr/service.py:382-385` `update_config` mutates `self._settings.llm_api_base`
Pydantic v2 models are mutable; this works. But the same `RuntimeSettings` instance is held by `RuntimeServiceImpl` (`runtime.py:57`), by `ProviderManagerImpl` (`providers.py:114`), and by the OCR service. The mutation write-through is documented (line 380-381) but the timing is racy: a request mid-flight that captured `settings.llm_model` at request start sees the old value; a request that started after the mutation sees the new value. The Flutter client gets a 200 OK back, but the in-flight batch is on the old model. Worth a one-liner in the response: "model change applies to subsequent requests."

### 4.21 `plugins/ocr/schemas.py:18-24` `_DENSE_MODE_ALIASES` — `"on"` → `"always"`, `"off"` → `"never"`
A toggle literal that pretends to be a tri-state. The semantics of "always dense" vs "always sparse" is a meaningful difference from "on"/"off", but the alias map is hidden inside a private dict. Document this in the route docstring or the Flutter client contract.

### 4.22 `plugins/ocr/schemas.py:36-41` `_parse_bool` accepts `{"true", "1", "yes", "on"}` — different from `env_bool`
See 2.9.

### 4.23 `plugins/ocr/service.py:84-86` `_QUEUE_STATUS_TO_HTTP` lives next to the only consumer
Move next to the schema so the wire vocabulary is co-located with the wire shape.

### 4.24 `plugins/state_backend.py:144-197` `StateBackendPlugin` is 53 lines and duplicates logic from the loader
The backend selector pattern (memory vs sqlite vs redis) is repeated across:
- `config.py:99-109` (env-var schema)
- `config.py:210-221` (validator with the same allowlist)
- `state_backend.py:136-156` (plugin-time allowlist, with `redis` documented as deferred)

Three sources of truth for the backend allowlist. The `state_backend.py` allowlist is `{"memory", "sqlite"}`; the `config.py` allowlist is `{"memory", "redis", "sqlite"}`. The user can set `OMNISCRIBE_STATE_BACKEND=redis` and pass settings validation, then crash at plugin apply. Unify.

### 4.25 `plugins/state_backend_sqlite.py:97-103` `PRAGMA journal_mode=WAL` is set but not verified
If the pragma silently fails (e.g. a network filesystem), the `WAL` setup is broken. Capture the return value and assert it equals `"wal"` in dev/test.

### 4.26 `core/pdf/embedder_helpers.py:1-15` and `core/pdf/embedder.py:1-7` have docstrings referring to a 470-LOC file that no longer matches
The docstring says "the file at `omniscribe/core/pdf/embedder.py` (578 LOC) had 470 LOC". The current `embedder.py` is 110 lines. The historical reference is now stale and confuses new readers.

### 4.27 `utils/env.py:159-168` `env_int` returns `default` on `ValueError` but logs a warning
The warning is at WARN level. The other `env_*` helpers don't log on the happy path but this one logs on the bad path. Inconsistent. Either always log or never log.

### 4.28 `utils/env.py:179-184` `env_list_csv` drops empty items but `env_str` doesn't drop the empty string from a `os.environ` lookup
Two helpers, two slightly different "empty" semantics. Pick one.

### 4.29 `utils/json_parse.py:8-34` `extract_json` walks every `{` and `[` position
```python
for start in (i for i, ch in enumerate(stripped) if ch in "{["):
    try:
        parsed, _end = decoder.raw_decode(stripped[start:])
        ...
```
For a 200 KB OCR response with one JSON object at the end, this decodes 200 KB worth of `{` attempts. On the extraction path, this is fine. On a hot path, it's wasteful. A `re.search` for the first `[{]` followed by a single `raw_decode` from that position would be O(n).

### 4.30 `core/recall/whitespace.py:33-92` — `_MIN_COMPONENT_HEIGHT_PX = 10`
Constant defined in pixels; applied to a per-image pixel-height calculation. The comment is fine. But the surrounding "T7 retune attempt" comment block is 15 lines of historical context inside a constants block. Move the commentary to a `docs/` file and leave the constant clean.

### 4.31 `harness/loader.py:174` — `row = replace(row, config=expand_env(row.config, row_id=row.id))` rebinds `row`
The local `row` is shadowed by the rebinding. The original `row` (after the `for row in rows:`) is no longer accessible. If `expand_env` raises, the previous `row.id` reference in the except handler is the rebound one — confusing when reading the traceback.

### 4.32 `harness/loader.py:121-143` — env override fields land as raw strings
Comment says "Values land as raw strings; the plugin's pydantic `Schema` coerces them." Good. But `_validate` (line 207) calls `schema(**row.config)`, and a missing required field (because the env override was a typo) raises a Pydantic `ValidationError` with a long, unfamiliar message. The error path is "harness mounted plugins failed", which doesn't help an operator find the typo. A `_resolve_env_value` helper that uses the schema for type coercion would catch typos earlier.

### 4.33 `harness/loader.py:185-186` — `mounted` log line omits the count
```python
_LOGGER.info("harness mounted plugins: %s", ", ".join(mounted))
```
Three plugins is `"ocr, jobs, progress"`. If a patch file adds 7 plugins, the log line is unreadable. Use `len(mounted)` and consider a structured log.

### 4.34 `core/recall/text_layer.py:121-131` — `close` is async-safe but not re-entrant
```python
def close(self) -> None:
    doc = self._doc
    self._doc = None
    if doc is not None:
        doc.close()
```
Two concurrent `close()` calls (e.g. from a cancelled `try/finally` race) each grab `self._doc`, both set it to None, and only the first finds a non-None value. The second calls `doc.close()` on the already-closed doc. `fitz.Document.close()` is idempotent so no crash, but the pattern is smelly.

### 4.35 `core/recall/text_layer.py:165` — `assert self._doc is not None`
See 1.9.

### 4.36 `core/recall/text_layer.py:198-200` — `_overlaps_existing` helper (not read but referenced)
`kept = [box for box in candidates if not _overlaps_existing(box, existing_boxes)]`. If `_overlaps_existing` is O(n²) and the page has 500 candidate boxes (pathological), this is 250k comparisons. The whitespace booster has the same shape.

### 4.37 `core/workflow/hybrid.py:88-90` — every `__init__` arg re-bound to every `Stage.__init__` on every `execute()`
The `HybridEngine.__init__` constructs four stage classes with bound references, then `_reset_run_state` and every `execute()` call re-assigns `self.converter.pdf_handler = self.pdf_handler` etc. on the stage objects. The stage objects are long-lived; the engine re-injects dependencies on every call. The pattern works, but the `Stage.__init__` parameters are essentially decorative — the actual values come from runtime injection. Either pass via constructor (and rebuild stages per run) or document that stages are mutable holders.

### 4.38 `core/workflow/hybrid.py:142-146` — `_reset_run_state` resets `_decoded_cache` and `last_failed_pages` but not the stage internal state
If a stage caches anything (e.g. `decoded_image` in the layout detector — doesn't currently, but easy to add), the next run inherits it. The reset is partial; document what's expected to be reset or do a full reset of all stages.

### 4.39 `core/workflow/hybrid.py:107` `_decoded_cache: OrderedDict[int, Image.Image]`
The OrderedDict is unbounded by size until `_decoded_put` (line 139). The comment says `must stay >= DETECT_CHUNK_SIZE`. If a malicious or buggy caller calls `_decoded_put` with the same key, the cache is fine (idempotent put). If they call with a different key while `DETECT_CHUNK_SIZE` is 8, the cache grows to 16 before any eviction. That's fine. But: an integer key with 200+ pages could be confused with a page number. A `tuple[run_id, page_num]` would prevent cross-run contamination.

### 4.40 `core/workflow/hybrid.py:265` — `trust_images_dict=images_dict` is passed as both the per-page image and the trust-orchestrator's per-page image
The same dict of base64 strings is used twice. A future change that mutates one (e.g. decoding to PIL for the trust layer) would silently mutate the other. Make a copy or split the signature.

### 4.41 `core/ocr/processor.py:111-112` — `_DEFAULTS` dict in `__getattr__` rebuilt on every attribute access
Minor perf nit. Hoist to module level.

### 4.42 `core/ocr/chat_client.py:147-149` exponential backoff uses `2**attempt`
`2**0 = 1`, `2**1 = 2`, `2**2 = 4`, ... so for `retry_base_delay_s=1.0` and `max_retries=2`, delays are `1s, 2s`. Capped at `retry_max_delay_s=8.0`. Reasonable. But the `min(..., retry_max_delay_s)` cap is applied per-attempt, so the cumulative sleep is `1+2 = 3s` for two retries. If a user sets `max_retries=10`, the cap kicks in at attempt 3. Document the cumulative sleep budget or expose it as a separate setting.

### 4.43 `core/ocr/chat_client.py:171-176` — context-length error message is LM Studio specific
The translated error message names LM Studio's "Context Length" right-side panel. Other providers (Ollama, vLLM) use different terminology. The translation works for the default config but misleads operators on other backends. Either make the message generic ("increase the model's context length") or branch on provider.

### 4.44 `harness/loader.py:188-201` — `_instantiate` catches all exceptions from `__init__`
```python
try:
    target = target()
except Exception as exc:
    raise PluginLoadError(row_id=row.id, reason=f"cannot instantiate plugin: {exc}")
```
A typo in a plugin's `__init__` becomes "cannot instantiate plugin: name 'foo' is not defined" wrapped in a `PluginLoadError`. The original traceback is preserved via `from exc`, but the operator-facing message is bare. Include the plugin class name.

### 4.45 `harness/context.py:39-44` — nine pre-allocated collections
The `__init__` allocates 9 attributes. None are lazily initialized. For an empty context (no plugins, no services), this is wasteful. The 9 collections total <1KB so the cost is negligible, but the pre-allocation signals "this class is always used" — if it's ever used as a "maybe context" the pattern doesn't scale.

---

## 5. Test gaps (specifics, not vibes)

### 5.1 The `_OcrPayload` round-trip in `run_job` has no test that exercises the `submission_id` lookup failing
If `payload.submission_id` is not in `self._submission_to_job` (because the 500-deep LRU evicted it), the service silently uses `job_id=""` and proceeds. The `JobCompleted` event has the right `job_id` (from the queue's record), but the operator log shows an empty job id. No test pins this.

### 5.2 `plugins/state_backend_sqlite.py` has no test for `INSERT OR REPLACE` leaking the old blob
See 1.5.

### 5.3 `core/recall/text_layer.py:165` has no test that runs with `-O`
A test that imports the module and calls `supplement` under `python -O` would catch 1.9.

### 5.4 No test exercises the SSE event-flap in `plugins/ocr/plugin.py:199`
See 4.18.

### 5.5 No test covers `plugins/jobs.py:208-213` with >1000 queued jobs
See 1.6.

### 5.6 The `LOAD → unload → reload` cycle in `Context` has no test
See 1.13.

### 5.7 The `cancelled` → `error` status squashing has no frontend test
See 1.3. The Flutter side probably parses `status: "error"` and shows a generic failure; a user-initiated cancel looks identical to a model OOM.

---

## 6. Style nits

### 6.1 `server.py:31-32` — duplicate logger declarations
```python
_LOGGER = logging.getLogger(__name__)        # line 31 — never used
_log = logging.getLogger("omniscribe.server")  # line 32 — used everywhere
```
Both resolve to the same logger (`omniscribe.server` module). The leading-underscore `_LOGGER` is dead. `ruff` is not flagging it because it's a module-level name with the leading underscore convention, not because it's used.

### 6.2 `server.py:55` — `_STATIC_DIR` is a module-level constant
Documented in a divider comment that has 5 trailing `---` characters. The divider conventions in this file are inconsistent (some use `===`, some `---`, some `# ---`).

### 6.3 `config.py:80-83` — `artifact_cleanup_interval_s` default is `60.0`, the runtime schema's `cleanup_interval_seconds` default is `60`. Two different units, two different names, same intent.

### 6.4 `core/workflow/hybrid.py:82-94` — `__init__` has 9 kwargs but the engine is always constructed via the pipeline factory. The public kwargs are an API surface that may need support forever.

### 6.5 `core/recall/text_layer.py:48` `_STRADDLE_MIN_OVERLAP = 0.15` — same constant as whitespace
Two copies.

### 6.6 `core/recall/whitespace.py:43-44` `_KERNEL_W_RANGE = (7, 35)` and `_KERNEL_H_RANGE = (3, 11)`
A `tuple` for the clamp range. `_clamp` (referenced at line 167) probably does `min(max(x, lo), hi)`. If so, named constants `KERNEL_W_MIN, KERNEL_W_MAX = 7, 35` would read more clearly.

### 6.7 `core/recall/whitespace.py:189-201` — `candidates: list[tuple[BBox, float]]` built then discarded
The list is iterated to build a list of validated candidates, but the score (the second tuple element) is never used. The `tuple` type annotation is misleading.

### 6.8 `core/recall/whitespace.py:198-201` — the `if nh < min_height or nh > max_height or nw * nh > _MAX_AREA_FRACTION` chain
Three independent conditions; `or` is fine, but reading "is this candidate worth keeping?" three times in three different ways is harder to scan than three named predicates.

### 6.9 `core/pdf/embedder_helpers.py:142-220` — `_resolve_unicode_chain` is a 70-line function (per the docstring)
The function does file probing, font loading, probe testing, and a chain assembly. Split.

### 6.10 `core/pdf/embedder_helpers.py:65` `_UNICODE_GLYPH_MISS_LOGGED: bool = False` is a module-level flag for "I already logged a warning"
A `logging_once` helper would be cleaner; this is a one-shot log pattern copy-pasted.

### 6.11 `core/pdf/embedder_helpers.py:127-140` — `exc_info=True` in the probe-failed log
A failed font probe is operational noise, not a bug. `exc_info=True` dumps a full traceback. Should be `logger.warning("Embedder font probe failed: %s", exc)`.

### 6.12 `core/pdf/embedder_helpers.py:99` `_PROBE_CODEPOINTS = (0x0645, 0x05D0)` — Arabic meem and Hebrew alef
Two codepoints. Comment says "Arabic meem and Hebrew alef — the scripts OS fonts most often remap to presentation-form codepoints." A third probe (Persian/Farsi `peh`, U+067E) would catch more remapping variants. Not a bug, just incomplete.

### 6.13 `core/workflow/hybrid_repair.py:88-91` — `concurrency` is a documented no-op
The function signature takes `concurrency` but never uses it. The docstring explains. Either remove the parameter or wire it. Documenting a no-op is a code smell.

### 6.14 `core/workflow/hybrid_repair.py:178-204` — `re_ocr` inner function has `_img` and `_page` as default args
The default-arg trick to bind `page_image` and `p_num` is a common Python workaround for late binding in closures. It works. A `functools.partial` would be more idiomatic.

### 6.15 `plugins/state_backend.py:172-194` — the path-traversal check rejects operators who want a separate state db
```python
try:
    candidate.relative_to(base)
except ValueError as exc:
    raise RuntimeError(...)
```
An operator who wants `<artifact_base_dir>/../shared/omniscribe.db` (a sibling directory by design) is rejected. A symlink-resolved check would be more permissive.

### 6.16 `core/ocr/chat_client.py:106` — `for attempt in range(self.max_retries + 1)`
The `+1` is correct but cryptic. A `for attempt in range(1, self.max_retries + 2)` with `attempt=1` for the first call would be self-documenting.

### 6.17 `core/ocr/chat_client.py:160-180` — the post-loop error-translation block
The same `_PERMANENT_TERMS` substring check that `is_transient_error` already does is duplicated here for the context-length case. A single error-translation function would be cleaner.

### 6.18 `utils/env.py:55-105` `_parse_env_line` — 50 lines of state-machine parsing
Stdlib `shlex` and `configparser` cover this. The custom parser handles some edge cases (`export ` prefix, inline comments) that `shlex` would not, but the cost of 50 lines of bespoke parsing is high. Document the divergence from POSIX dotenv or use `dotenv` (you already depend on it elsewhere).

### 6.19 `utils/env.py:265` `target_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")`
On Windows, this writes a file with a trailing `\n`. The `splitlines()` + `"\n".join` produces POSIX line endings. If the original file was CRLF (as Windows `.env` files often are), the round-trip changes line endings. Not a bug, just data drift.

### 6.20 `utils/env.py:271-272` — "Sync to live os.environ"
```python
for k, v in formatted_entries.items():
    os.environ[k] = v
```
This unconditionally sets every key in `formatted_entries`, even if the key didn't exist in the file. The `update_dotenv` function is for adding or modifying; it doesn't remove. If the user passes `{"REMOVED_KEY": "..."}` (misuse), the key is added to env. Not a bug, just subtle.

### 6.21 `harness/loader.py:121-143` — `_apply_env_overrides` lowercases plugin IDs but the YAML may not be
Already covered in 1.2. Repeated for emphasis.

### 6.22 `harness/loader.py:174` — `row = replace(row, config=expand_env(row.config, row_id=row.id))` shadowing
Already covered in 4.31. Repeated.

### 6.23 `harness/context.py:166-184` — error path loses the original exception type
Already covered in 1.14.

### 6.24 `core/ocr/processor.py:111-127` — class-level constants re-loading settings
Already covered in 1.12.

### 6.25 `core/recall/whitespace.py:55-58` — `_MAX_RECALL_BOXES_PER_PAGE = 10`
The comment says "at most this many recall boxes per page". The number 10 is also in `text_layer.py:56`. Promote.

### 6.26 `plugins/state_backend_memory.py:27` `_MEMORY_BLOB_CAP_BYTES = 256 * 1024 * 1024`
256 MB. The SQLite backend has no equivalent cap. An operator who switches from memory to SQLite can have a single 4 GB artifact that the memory backend would have rejected. The intent is unclear — is the cap an arbitrary safety, or does it reflect an upstream consumer limit?

### 6.27 `harness/loader.py:165-168` — patch file path is silently dropped if it doesn't exist
```python
if not path.is_file():
    continue
```
If an operator misconfigures `OMNISCRIBE_CORDIS_PATCH=/etc/omniscribe/patch.yml` and the file is missing, the loader proceeds as if the patch were empty. No warning. An operator who thinks their patch is active will be confused. Log a warning.

### 6.28 `harness/loader.py:172-184` — the per-row try/except is bare
```python
try:
    await self._ctx.plugin(instance, config=config)
except PluginLoadError:
    raise
except Exception as exc:
    raise PluginLoadError(row_id=row.id, reason=str(exc)) from exc
```
The first clause (`except PluginLoadError: raise`) is a no-op — `raise` re-raises the current exception, which is exactly what not having the `except` would do. The clause is dead code, presumably for explicitness. Either delete it or add a comment that says "intentional re-raise to avoid losing the traceback."

### 6.29 `harness/loader.py:185` — `_LOGGER.info("harness mounted plugins: %s", ", ".join(mounted))`
The log is at INFO and unconditionally fires. On a debug session, the line is fine. On production with a 9-plugin tree and 50 patch-loaded plugins, the line is unreadable. The count is also not logged.

### 6.30 `core/pdf/embedder.py:107` `new_doc.save(output_pdf_path)`
No `garbage=` parameter, no compression options. PyMuPDF defaults to deflate + cleanup. For a 100-page output, the default may not be what the operator wants. Expose `garbage` and `deflate` as kwargs.

### 6.31 `core/pdf/embedder.py:71-78` — `doc = fitz.open(input_pdf_path)` is not closed in the `not page_nums` early return path
```python
doc = fitz.open(input_pdf_path)
new_doc = fitz.open()
try:
    if page_nums is not None:
        page_nums = [pn for pn in page_nums if 0 <= pn < len(doc)]
    else:
        page_nums = list(range(len(doc)))
    if not page_nums:
        new_doc.save(output_pdf_path)
        return  # <-- doc is not closed before return
```
The `try/finally` closes `new_doc` and `doc`, but the early `return` is inside the `try` and the `finally` does run. OK, the leak is plugged. But the conditional `page_nums = [pn for pn in page_nums if 0 <= pn < len(doc)]` is dead when `page_nums is None` — the else branch always overrides. Unify.

### 6.32 `core/pdf/embedder_helpers.py:1-15` — historical-context comment
The comment says "the file at `omniscribe/core/pdf/embedder.py` (578 LOC) had 470 LOC of underscored helper functions." The current `embedder.py` is 110 LOC. Stale historical reference. Trim to one sentence.

### 6.33 `core/document.py` (not read) — `_OcrPayload` is defined in `plugins/ocr/service.py:75-82`, not in `core/document.py`
The IR for "one OCR payload" lives in the HTTP layer; the OCR pipeline doesn't know about it. If `core/workflow` ever wants to enqueue jobs directly, it would need to import from the plugin layer. Smelly.

### 6.34 `core/workflow/grounded.py:1-30` (not read fully) — the grounded engine has its own execution path
If a refactor to `core/workflow/hybrid.py` touches shared helpers (`pages_structured` shape, `_build_document_result`, `_apply_trust`), the grounded engine must be updated in lockstep. The duplication risk is not visible from the API; only from reading both files.

### 6.35 `plugins/ocr/schemas.py:115-120` `AsyncSubmitResponse` — `status: str = "pending"`
A string literal, not a Literal type. The frontend contract is "pending | processing | complete | error" (per `JobStatusResponse` on line 139). The submit response should use the same Literal.

### 6.36 `plugins/ocr/schemas.py:144-146` `JobStatusResponse.text_artifact_id` is safe to expose
The `JobCompleted` event has `artifact_id` and `artifact_token`. The `JobStatusResponse` deliberately omits the token (per the security note on line 124-135). The text_artifact_id is the opaque handle. The docstring says "the unauthenticated status polling endpoint would otherwise bypass the constant-time gate at fetch_result." Good security narrative. The implementation matches.

### 6.37 `plugins/ocr/schemas.py:36-41` `_parse_bool` — accepts `"true"`, `"1"`, `"yes"`, `"on"` for True
The set includes `"on"` but not `"enabled"`. The recall booster accepts `"enabled"` via its own disable-value set. The two vocabularies diverge.

### 6.38 `plugins/ocr/schemas.py:69-76` `_split_processors` — the comma-split is hard-coded
A multi-value form field arrives as repeated `key=value` entries, not a comma-joined string. FastAPI's `form()` gives a `FormData` object. The current code only handles the comma-joined case. If the frontend sends `document_processors=reading_order&document_processors=layout_enrichment`, only the first one is captured (because `FormData.get("document_processors")` returns a list when the key is repeated, and the validator checks `isinstance(value, str)` and would fail). Worth testing.

### 6.39 `plugins/ocr/schemas.py:99-112` `preprocessing_enabled` is a computed property, not a field
The validator at line 78-92 is `mode="before"`, so `preprocess_pages` is a string at validation time. The `preprocessing_enabled` property reads `self.preprocess_pages` and the per-step booleans. Correct logic, but the property is on the schema (an HTTP boundary object), not on a domain model. It couples HTTP form naming to preprocessing behavior. Move the "any toggle means enabled" logic to the bridge.

### 6.40 `plugins/state_backend_sqlite.py:55-65` `_job_from_row` — positional access `row[0]`, `row[1]`, ...
The SELECT statements have a long column list. `sqlite3.Row` is more readable. Use `conn.row_factory = sqlite3.Row` and access by column name.

### 6.41 `plugins/state_backend_sqlite.py:131-145` — INSERT OR REPLACE
Already covered in 1.5. Repeated.

### 6.42 `plugins/state_backend_sqlite.py:373-384` `prune_expired_channels` — same `cursor.rowcount if cursor.rowcount >= 0 else 0` pattern
Repeated 4 times across the file (artifacts prune, jobs clear, channels prune). Extract.

### 6.43 `core/recall/whitespace.py:130-134` — `candidates_dropped` counter
The counter is incremented per dropped candidate, not per page. A page that drops 50 candidates increments the counter by 50. The summary log line in `layout.py:142-149` reads "X candidate(s) dropped" without context. Document the per-candidate vs per-page semantics.

### 6.44 `core/recall/text_layer.py:90-94` — same `candidates_dropped` pattern
Already covered in 6.43. Repeated for the text-layer analog.

### 6.45 `core/workflow/hybrid.py:170` `trust_images_dict: dict[int, str] | None = None`
Unused in the engine's `_finalize` (it re-passes `images_dict`). The parameter is dead. Delete.

### 6.46 `core/workflow/hybrid.py:357-359` — `select_dense_pages` signature takes `dense_mode: str | DenseMode`
The union accepts both the enum and the string. Callers always pass the enum. The union is historical from the pre-StrEnum days.

### 6.47 `core/ocr/processor.py:267-269` `_apply_adaptive_threshold` is called via `asyncio.to_thread`
The function presumably runs OpenCV. The `to_thread` is correct, but the name says "adaptive threshold" — is it cv2.adaptiveThreshold or a custom implementation? The function isn't in the file. Either it's defined elsewhere or it's a forward reference that needs implementation.

### 6.48 `core/ocr/processor.py:285-288` `if dual_engine: draft = await asyncio.to_thread(self._get_tesseract_draft, image_base64)`
The dual-engine path uses Tesseract via the thread pool. The tesseract install is optional (F1.13 audit fix adds a counter). The error handling is in the `_get_tesseract_draft` method (not read). Document the contract.

### 6.49 `core/ocr/processor.py:312-326` `self_correction` path
A second VLM call on the same page, with the first VLM's text as a draft. No retry guard. If the first call raises, `self_correction` is skipped (because `if not text: return []`). If the first call succeeds, the second call is unprotected by the retry loop — it goes through `_chat` which has retry. OK.

### 6.50 `core/ocr/processor.py:111-127` — the F1.9 fix comment block
The comment is 23 lines explaining the class-level vs instance-level decision. Long. The decision could be a one-liner with a pointer to the audit report.

### 6.51 `core/recall/whitespace.py:30-31` — `import statistics` is used once (line 182)
Standard library; no cost. But the import is mid-module, not at the top.

### 6.52 `core/recall/whitespace.py:36-92` — every constant has a multi-line block comment
The audit commentary is valuable but bloats the file. Move the audit history to a `docs/` note and keep the constants in code.

### 6.53 `core/ocr/prompts.py:60-66` `_MODELS_WITHOUT_SYSTEM_ROLE` — frozenset
The `frozenset` is correct (immutable), but the contents are lowercased model names and the matching is substring (`any(needle in name for ...)`). Substring matching with a frozenset is wasteful — convert to a list and early-exit, or use a trie. Not a perf concern at this size.

### 6.54 `core/ocr/prompts.py:69-86` `model_supports_system_role` — `name = model_name.lower()`
The function lowercases the input but the constant members are already lowercase. Consistent.

### 6.55 `core/ocr/prompts.py:12-14` — `PROMPT_VERSION` is the same as the documents plugin's `PROMPT_VERSION` (`plugins/documents/prompts.py:11`)
Two prompts versions, both `"2026-08-15.v1"`. Independent version spaces that happen to share a value. The coincidence is fine; the duplication is a maintenance hazard.

### 6.56 `core/ocr/chat_client.py:131-135` — the message format embeds a `data:image/png;...` URL
The image is PNG regardless of the input format. A JPEG image is re-encoded to PNG before being sent. Two consequences: 30%+ larger payloads for JPEG inputs, and a quality loss. The `multi_format_client.py` exists for a reason; this code path doesn't use it.

### 6.57 `core/ocr/chat_client.py:147-149` — backoff delay
`min(self.retry_base_delay_s * (2**attempt), self.retry_max_delay_s)`. For `attempt=0`, delay is `base * 1 = base`. So the first retry waits `base` seconds, not `0` (good). The formula is `base * 2^attempt` (not `base * 2^(attempt+1)`), so attempt 0 waits `base`, attempt 1 waits `2*base`, etc. Reasonable.

### 6.58 `harness/loader.py:174-184` — try/except wrapping
Already covered in 6.28.

### 6.59 `harness/loader.py:188-201` — `_instantiate` catches all
Already covered in 4.44.

### 6.60 `core/recall/whitespace.py:1-18` — the docstring references `docs/superpowers/plans/2026-08-14-whitespace-recall.md`
Already covered in 3.8.

### 6.61 `core/recall/text_layer.py:1-17` — the docstring is 17 lines
Repeated. Already covered.

### 6.62 `core/workflow/hybrid.py:88-90` — 9-arg `__init__`
Already covered in 6.4.

### 6.63 `core/workflow/hybrid.py:316-318` `_apply_recall` is a thin wrapper around `self.layout_detector.apply_recall`
The wrapper re-injects the recall booster on every call. The stage already has the reference. The wrapper does nothing except the re-injection. Delete the wrapper, call the stage directly.

### 6.64 `core/workflow/hybrid.py:339-344` `_apply_text_layer_recall` — same shape
Same nit.

### 6.65 `core/workflow/hybrid.py:396-415` `_ocr_per_box` — same re-injection pattern
The OCR runner already has `self.ocr_processor`. The re-injection is again a stage-bound reference.

### 6.66 `core/workflow/hybrid.py:445-468` `_refine_uncertain` — same
Same nit.

### 6.67 `core/workflow/hybrid.py:142-146` `_reset_run_state` resets `_decoded_cache` and one stage attribute
Already covered in 4.38. The docstring says "clear run-scoped state" but only clears two things.

### 6.68 `core/workflow/hybrid.py:497-505` `_build_document_result` — not visible (helper)
A separate method, not in the file I read.

### 6.69 `core/workflow/hybrid_repair.py:80-138` `run_repair_phase` — the `completed_box` mutable list
The comment explains the pattern. The pattern works. It's a code smell because Python 3 `nonlocal` would be cleaner. Performance is the same.

### 6.70 `core/workflow/repair.py:1-20` (not read) — `QualityRepairLoop`
The repair phase has its own loop, separate from the OCR loop. The decision to repair vs the decision to OCR are orthogonal but not coordinated. A page that was already low-confidence might be re-OCR'd, repaired, and then re-OCR'd again in a next phase.

### 6.71 `plugins/state_backend.py:39-83` — three dataclasses, all `frozen=True`
`ArtifactRecord`, `ArtifactBlob`, `JobRecord`, `ChannelRecord` are all frozen. `ArtifactBlob` contains a `record: ArtifactRecord` (frozen) and a `blob: bytes`. `bytes` is not hashable, so `ArtifactBlob` is not hashable by default. Same for `JobRecord` (contains `request_meta: dict[str, Any]`, also not hashable). `frozen=True` on a non-hashable dataclass is fine but the implicit "this is hashable" promise is broken.

### 6.72 `plugins/jobs.py:14-17` — `import cast, runtime_checkable` and then `cast("JobRunner", self._ctx.inject(JobRunner))`
The string-quoted type for `cast` is the older syntax. With `from __future__ import annotations` (which is imported on line 8), the cast could be plain `cast(JobRunner, ...)`.

### 6.73 `plugins/jobs.py:32` `_TERMINAL_STATUSES = {"complete", "error", "cancelled"}` — duplicated
`plugins/state_backend.py:36` defines `JobStatus = Literal["queued", "running", "complete", "error", "cancelled"]`. `plugins/ocr/service.py:60` defines `_TERMINAL_QUEUE_STATUSES = {"complete", "error", "cancelled"}`. Three copies of the same set.

### 6.74 `plugins/jobs.py:195-206` `start` and `shutdown` are not idempotent
`start` is guarded by `if self._worker is None`; `shutdown` sets `self._worker = None` after cancelling. If `start` is called twice, the second is a no-op. If `shutdown` is called twice, the second sees `self._worker is None` and is a no-op. But the loop in `_run` (line 215-225) catches `asyncio.CancelledError` and re-raises; `shutdown` awaits the worker with `contextlib.suppress(asyncio.CancelledError)`. OK, all paths covered.

### 6.75 `plugins/jobs.py:215-225` `_run` — except `Exception` swallows everything
If the runner raises a bug, the worker logs and continues. The next job is unaffected. The trade-off is "robust worker" vs "fail loud on the first bug." Document the choice.

### 6.76 `plugins/jobs.py:283` `_mark_cancelled` discards `cancelled` set
`self._cancelled.discard(job_id)` — fine, removes the marker. The set is then never re-populated unless `cancel` is called again. Good.

### 6.77 `plugins/jobs.py:286-291` — `transitioned` is local; `emit` is conditional on it
```python
if record is not None and record.status not in _TERMINAL_STATUSES:
    await self._backend.upsert_job(...)
    transitioned = True
if emit and transitioned:
    await self._ctx.emit(JobCancelled(job_id=job_id))
```
If the record was already terminal, no upsert, no emit. The caller can't tell whether the job was already cancelled. The `cancel_job` return is a bool, so the caller's UI gets `True` regardless. The `JobCancelled` event is suppressed. The frontend may keep showing "cancelling..." for an already-cancelled job. Edge case.

### 6.78 `plugins/progress.py:174-179` — `frame_cap` is a soft cap
The `sent_so_far` is incremented before the send. If a foreign-loop send's done callback never fires (e.g. the accept loop is dead but the cross-loop thread is alive), the cap is bypassed. The `if sent_so_far >= self._frame_cap` check is the only guard.

### 6.79 `plugins/progress.py:181-211` — `broadcast` returns `sent_so_far` (submissions, not successes)
Document.

### 6.80 `plugins/progress.py:213-234` `_on_foreign_send_done` — `try/except` around `detach`
The `detach` call (line 232) is wrapped in `try/except Exception`. The `detach` method (line 155-160) is simple and shouldn't raise. The defensive catch is over-broad. Catch `KeyError` only.

### 6.81 `plugins/ocr/service.py:215-216` — `f"input{Path(filename).suffix or '.pdf'}"`
A filename like `evil.tar.gz` gives `suffix=".gz"`, so the file is `input.gz`. PyMuPDF will fail. OK. But a filename like `evil` (no extension) gives `suffix=""` and falls back to `.pdf`. The file is then `input.pdf`. If the upload is a real image, the PDF pipeline will fail. The fallback is misleading.

### 6.82 `plugins/ocr/service.py:238-248` `_progress_adapter` and `_warning_adapter` — the inner functions capture `self._progress` after the outer `None`-check
The `assert self._progress is not None` is defensive (for mypy), but the outer check (line 236) already guarantees it. The assertion is fine; could be removed with `from __future__ import annotations` and a Protocol.

### 6.83 `plugins/ocr/service.py:264-276` `_cancel_check` — the `if not job_id and not channel: return None` short-circuit
A request with neither `job_id` nor `channel` (which happens for the sync path's empty `job_id=""`) gets no cancel check. The sync path runs to completion. The async path always has both. OK.

### 6.84 `plugins/ocr/service.py:295-311` `_status_response` — `started_at: None` always
The `JobRecord` doesn't track a separate `started_at`; only `created_at` and `updated_at`. The `started_at` field is reserved but never populated. Document or populate.

### 6.85 `plugins/ocr/service.py:319-321` `job_list_item` — same `started_at: None` issue
Same.

### 6.86 `plugins/ocr/service.py:376-385` `update_config` — the `api_key == "******"` skip
The masked value is exactly the magic string returned by `get_config` (line 361). The skip means "if the client sent the masked value, don't overwrite the real one." A subtle contract: the client must echo the masked value to "not change" the key. Document.

### 6.87 `plugins/ocr/service.py:381-384` — the unconditional write to `self._settings.llm_*`
The write happens even if the values are unchanged. Pydantic v2's `model_copy(update=...)` would be cleaner. The mutation pattern is fine for performance but obscures the intent.

### 6.88 `plugins/ocr/schemas.py:44-65` `OCRRequest` — 18 fields, 4 validators, 2 properties
The schema is large. A nested config object (e.g. `OCRPreprocessingConfig`) would group related fields.

### 6.89 `plugins/ocr/schemas.py:78-92` `_coerce_bool` — string → bool for 7 fields
The list of field names duplicates the field declarations. Add a class-level annotation pattern.

### 6.90 `plugins/ocr/schemas.py:18-24` `_DENSE_MODE_ALIASES` — `"on" → "always"`, `"off" → "never"`
A toggle literal pretending to be a tri-state. The frontend sends `"on"` or `"off"`, the API maps to the enum. Document this in `OCRPipeline` (which takes `DenseMode`).

### 6.91 `core/recall/whitespace.py:107-110` — `from_env` is a classmethod
The pattern is "set from env, allow override via __init__." Good. The default value of `True` (enabled) is documented. If the env var is unset, `raw = ""` and the condition `raw not in _DISABLE_VALUES` is True, so enabled. Good.

### 6.92 `core/recall/whitespace.py:178-187` — `min_height` falls through to 0.006
Already covered in 1.15. Repeated.

### 6.93 `core/recall/text_layer.py:120-131` — `close` is sync
The method is sync but called via `asyncio.to_thread(text_layer.close)` (`layout.py:135`). The sync API forces the thread-pool indirection. If the method were async, the call could be plain `await`. PyMuPDF's `Document.close()` is sync (releases the C-level handle), so the thread indirection is needed. Document.

### 6.94 `core/recall/text_layer.py:178-194` — line grouping
The grouping logic uses `(block_no, line_no)` as the key. The PDF's text-layer extraction groups words into lines. The grouping is correct but the order is lost: lines from different blocks are interleaved by their `(block_no, line_no)` order. The page's reading order is not preserved. For multi-column pages, the order may be wrong. The post-merge `sorted([*boxes, *extra], key=lambda b: (b[1], b[0]))` re-sorts by Y then X, so the final order is correct.

### 6.95 `harness/loader.py:55-63` `parse_rows` — `data["plugins"]` may be `None`
```python
data = yaml.safe_load(yaml_text) or {}
if not isinstance(data, dict) or not isinstance(data.get("plugins"), list):
```
If `data["plugins"]` is `None`, `isinstance(None, list)` is False, and the error is raised. The error message says "expected a top-level 'plugins' list" — accurate. OK.

### 6.96 `harness/loader.py:67-75` `_merge_config` — recursive dict merge, list replacement
Lists in the patch replace the base's lists. This is documented ("lists are replaced"). A "list merge" mode would be useful for `allowed_types` etc., but is out of scope.

### 6.97 `harness/loader.py:78-97` `deep_merge` — `order = [row.id for row in base]`
The order is preserved from the base. Patch-only rows are appended. The comment says "Base order is preserved; patch-only ids are appended." Correct.

### 6.98 `harness/loader.py:135-142` — env override is applied after deep_merge
The order is: base → patch → env override. The env override is the last word. Document.

### 6.99 `harness/loader.py:188-201` `_instantiate` — supports both a class and an instance
```python
if isinstance(target, type):
    try:
        target = target()
    except Exception as exc:
        ...
```
A factory function that returns a non-`Plugin` is rejected (line 197). A factory that returns a `Plugin` is accepted. The pattern is flexible but undocumented. A `Plugin` subclass is the normal case; the flexibility is for tests.

### 6.100 `harness/loader.py:203-212` `_validate` — the schema is `model_dump`'d back to a dict
```python
return schema(**row.config).model_dump()
```
The plugin's `apply(ctx, config=self.config)` receives the validated dict. Pydantic's `model_dump` returns Python primitives; nested models become dicts. The plugin's `apply` then accesses `self.config.get("key")` (e.g. `ocr/plugin.py:276`). The dict access is fine.

### 6.101 `harness/loader.py:203-212` — `Schema = None` is the "no schema" case
A plugin with no schema skips validation. The plugin's `apply` must handle untyped config. Good for simple plugins.

---

## 7. AGENTS.md / docs discrepancies

### 7.1 `AGENTS.md:127` says `OMNISCRIBE_LLM_*` env vars are tunable
The table in `AGENTS.md:122-130` lists `OMNISCRIBE_LLM_MAX_RETRIES`, `OMNISCRIBE_LLM_RETRY_BASE_DELAY`, `OMNISCRIBE_CB_FAILURE_THRESHOLD`, `OMNISCRIBE_CB_COOLDOWN`. The `config.py` defaults match. Good.

### 7.2 `AGENTS.md:122` says "The historic `GET /v1/models` check is not yet re-implemented"
But `core/ocr/processor.py:232-256` has `ensure_model_loaded` which does exactly that. The docstring says "Wrap any underlying transport / auth failure in LLMCallError." So the check is implemented, the doc says it's not. Discrepancy.

### 7.3 `AGENTS.md:179-180` mentions `settings_manifest.md` and `pre-flight` not being re-implemented
But `core/ocr/processor.py:232-256` is the pre-flight. The `AGENTS.md` description of the rebuild appears to be stale relative to the code.

### 7.4 `AGENTS.md:122-127` lists quality-loop options; the schema in `ocr/plugin.py:257-261` matches
Match.

### 7.5 `AGENTS.md:9` says the rebuilt route surface is "unauthenticated"
But `runtime.py:24` (not read in full) logs `auth_enabled: bool(settings.auth_token)` on startup. The `auth_token` is read but never enforced. The startup log line is correct as a "configured but not enforced" indicator; the doc is correct as "auth is deferred."

### 7.6 `AGENTS.md:122-127` lists `OMNISCRIBE_VLM_PAGE_TIMEOUT` and `OMNISCRIBE_VLM_CROP_TIMEOUT`
`config.py:55-60` declares them. Match.

### 7.7 `AGENTS.md:122-127` does not list `OMNISCRIBE_VLM_PAGE_MAX_TOKENS` / `OMNISCRIBE_VLM_CROP_MAX_TOKENS`
But `core/ocr/processor.py:112,120` reads them via `env_int`. The audit A-11 / Phase 5 mention exists in the comment but the table doesn't list them.

### 7.8 `AGENTS.md` references `scripts/confidence_eval.py` and `scripts/confidence_image.py` (line 130+)
Both exist. Match.

### 7.9 `AGENTS.md:140-141` says `pre-commit` runs `ruff (check + format)`, `mypy`, and `uv-lock`
`.pre-commit-config.yaml` exists. Not read in this review.

### 7.10 `AGENTS.md:96` describes the deferred translation routes
The `LexiconStore` import is preserved. Match.

### 7.11 `AGENTS.md:90-94` describes the plugin boot order
9 plugins listed. The `cordis.yml` (not read) presumably matches.

### 7.12 `AGENTS.md:122-128` lists `OMNISCRIBE_QUALITY_LOOP` etc.
The schema in `ocr/plugin.py:257-261` does not read these env vars. The schema is hardcoded to `quality_loop_enabled: bool = True`, `quality_target: float = 0.85`, `quality_max_retries: int = 2`. The env vars documented in `.env.example:135-142` and AGENTS.md are not declared in `config.py` and not read by the plugin. **Real bug** — the env seeds are ignored.

### 7.13 `AGENTS.md:122-128` lists `OMNISCRIBE_WHITESPACE_RECALL` and `OMNISCRIBE_TEXT_LAYER_RECALL`
The `WhitespaceRecallOptions.from_env()` and `TextLayerRecallOptions.from_env()` read them. The pipeline at `pipeline.py:111-114` constructs the options from `from_env()`. Match.

### 7.14 `AGENTS.md:140-141` says `ruff format` is run on commit
`pyproject.toml` has `[tool.ruff.format]` (not read). Likely matches.

### 7.15 `AGENTS.md:177` says `ALLOW_SSRF_LOCAL=true is the local-development default`
`config.py:123` defaults to `False`. Discrepancy. See 1.1.

---

## 8. Summary of real, non-cosmetic issues

Highest priority (real bugs):

- **1.1** `ALLOW_SSRF_LOCAL` default contradicts docs
- **1.2** env-override lookup case sensitivity in `harness/loader.py:135`
- **1.4** cancel after race window still persists result PDF
- **1.5** `INSERT OR REPLACE` in SQLite leaks old blob file
- **1.6** shutdown only cancels newest 1000 queued jobs
- **1.7** AVIF magic-byte check is too narrow
- **1.8** `application/octet-stream` bypasses magic-byte check
- **1.9** / **1.10** `assert` as defensive check (stripped under `-O`)
- **7.12** `OMNISCRIBE_QUALITY_LOOP` / `_TARGET` / `_MAX_RETRIES` env vars documented but never read

Medium priority (smells / inconsistencies):

- **1.3** cancelled → error status squashing
- **1.11** `page_max_tokens` re-binds class constant
- **1.12** `load_settings()` at module import
- **1.14** failed `apply()` cleanup can leak the exception
- **1.15** recall `min_height` falls through to 0.27% of page
- **1.18** new thread pool per SSRF check
- **2.1** `GET /api/export/docx` puts text in URL
- **2.2** `client.close()` on every pre-flight
- **2.4** `load_settings()` called twice per startup
- **2.5** redundant logger in `server.py:31`
- **2.6** / **2.7** two cancel-record cleanup paths
- **2.9** two boolean vocabularies in the codebase
- **3.3** env vars documented but not declared
- **3.4** / **3.5** / **3.7** / **3.8** stale references in docstrings

Low priority (style / dead code):

- everything in section 6

The 9 highest-leverage fixes are 1.1, 1.2, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 7.12 — the rest is consistency work.

---

## 9. Corrections (2026-08-30, post-publication re-verification)

- **7.12 is a false positive.** `OMNISCRIBE_QUALITY_LOOP` / `_TARGET` /
  `_MAX_RETRIES` **are** consumed: `src/omniscribe/resources/cordis.yml:61-63`
  seeds the ocr plugin's config via `${OMNISCRIBE_QUALITY_LOOP:-true}`-style
  env expansion, applied by the harness loader
  (`harness/loader.py:174`, `expand_env`). The finding's grep scope
  (`config.py` + plugin schema) missed the cordis.yml expansion layer.
- **1.1 resolution direction (2026-08-30):** the discrepancy is real, but
  the chosen fix is to keep the secure code default (`False`) and correct
  the AGENTS.md / `.env.example` wording — flipping the code default to
  `True` would weaken SSRF protection for every deployment that does not
  use the shipped `.env`.
