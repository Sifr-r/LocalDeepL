# Documents Plugin — Phase C Slice 1: Extraction + Export Rebuild

> **For agentic workers:** This spec rebuilds the deferred extraction and
> export HTTP surface as a new `documents` boot plugin. The Flutter client
> already ships the UI and repository calls for these routes; the backend
> must serve the existing client contract with zero client changes.

**Date:** 2026-08-30
**Status:** Approved — ready for implementation plan
**Owner:** rahin2uddin
**Parent scope:** Phase C of the Flutter takeover (deferred backend feature
subsystems: translation, transcription, extraction, export, glossary).
Extraction + export is slice 1; translation, transcription, and glossary
are later slices with their own specs.

## Context

The Cordis harness rebuild (2026-08-23) deleted the legacy
`src/omniscribe/api/` namespace without rebuilding its extraction and
export routes. The Flutter client still calls them:

- `client/lib/data/repositories/feature_repository.dart:145–205` — every
  extraction/export call 404s today.
- `client/lib/core/constants/api_constants.dart:55–101` — the route
  constants that define the client-side contract.
- `client/lib/data/models/feature_models.dart` — request/response models
  (`ExtractionRequest/Response`, `DocumentExportRequest/Result`,
  `ExportHtmlRequest`, `ExportBlockTreeRequest`, `ExportDocxRequest`).

Additionally, `GET /api/text/{artifact_id}` and
`GET /api/metadata/{artifact_id}` were not rebuilt either, so the client's
`getTextArtifact` (sync OCR path reads `X-Text-Artifact-Id/Token` response
headers at `ocr_repository.dart:159–160`) 404s — text display in the
workstation is broken. The artifact fetch routes belong to the same family
and are in scope.

The pre-rebuild server behavior was recovered from git history:
routes from `44ef123^` (`api/routers/extraction.py`,
`api/routers/artifacts.py`, `api/services/document_exports.py`,
`api/services/ai.py`), contract tests from `e6b7b89^`
(`tests/api/routers/test_artifacts.py`,
`test_extraction_translation_routers.py`, `test_ai_router.py`).

## Goals

1. New `documents` boot plugin (`src/omniscribe/plugins/documents/`)
   mounting all routes below, contract-compatible with the current
   Flutter client — no client changes.
2. Restore `GET /api/text/{id}` and `GET /api/metadata/{id}`.
3. Re-home extraction prompts/templates and export format builders from
   the deleted api namespace into the plugin package.
4. Router contract tests under `tests/routers/` on the existing harness
   fixtures.
5. Docs: AGENTS.md boot table, ARCHITECTURE.md plugin list, CHANGELOG.

## Non-Goals

- Translation / transcription / glossary routes (Phase C later slices).
- Auth / rate-limit / upload-size middlewares (separate hardening wave).
- Old route aliases (`/api/artifacts/export/{id}`, `/api/artifacts/text/{id}`,
  `/api/artifacts/metadata/{id}`) — only the client's constants are served.
- Persistent tree sidecars (`.tree.json`) — trees are built on demand.
- JobQueue integration — all routes are synchronous (extraction is one LLM
  call; export is deterministic and fast, matching old behavior).
- Client-side changes of any kind.

## Verified environment facts

Pinned so the implementation plan does not re-derive them:

- `ArtifactStore.put(blob: bytes, *, content_type: str, owner_job_id: str,
  ttl_seconds: int | None = None) -> ArtifactHandle` where
  `ArtifactHandle.id = uuid.uuid4().hex` (32 chars — matches the client's
  32-char id validation) and `token = secrets.token_urlsafe(32)` (~43
  chars — fits the client's 32–256 token validation).
  `ArtifactStore.get(artifact_id, token) -> ArtifactBlob | None`.
- **Text artifact blob shape is `{"<page_index>": "<lines joined by \n>"}`
  (`plugins/ocr/service.py:153–158`, `owner_job_id=""`)** — NOT the legacy
  `{page: [lines]}` shape the old routes parsed. Every loader in this
  plugin must split values on `\n` to recover lines.
- `block_tree.from_pages_data(pages_data: dict[int, Sequence[tuple[Sequence[float], str]]], *, source_path=None) -> DocumentTree`
  — needs `(bbox, text)` tuples; stored text artifacts have no bboxes, so
  tree construction fabricates zero bboxes per line (this is exactly the
  old code's "legacy fallback" path; block types come from
  `_classify_simple` text heuristics).
- Writers: `convert_markdown_to_docx(markdown_text: str) -> io.BytesIO`,
  `convert_tree_to_docx(tree) -> io.BytesIO`,
  `render_html(tree) -> str`, `export_json(tree, *, indent=2) -> str`.
- `call_llm(*, model=None, api_base=None, api_key=None, prompt=...,
  temperature=0.1, max_tokens=None, timeout=None, system_prompt=None,
  ...) -> str`; `TEMPERATURE_EXTRACTION = 0.1`
  (`core/llm/temperatures.py`).
- `utils.json_parse.extract_json(text) -> Any`;
  `utils.security.check_ssrf_target_sync(url) -> SSRFCheckResult`
  (`.allowed`, `.reason`).
- LLM coordinate resolution pattern to mirror:
  `plugins/ocr/pipeline_bridge.py:56–66` — SSRF-check the request
  override only, then
  `api_base = request.api_base or settings.llm_api_base` (same trio for
  key/model).
- Plugin pattern: `Plugin` base with `Schema` ClassVar; `ctx.inject(...)`
  for `ArtifactStore`/`RuntimeService` (settings via
  `runtime.settings`); `ctx.mount_router(router)`; module-level
  `plugin` instance (`__init__.py` re-exports it).

## Architecture

```
src/omniscribe/plugins/documents/
├── __init__.py      # re-exports `plugin`
├── plugin.py        # DocumentsPlugin(Plugin); DocumentsSchema; builds service, mounts router
├── schemas.py       # Pydantic request models + StrEnums (constraints below)
├── prompts.py       # EXTRACTION_SYSTEM_MESSAGE + template schemas (PROMPT_VERSION "2026-08-15.v1")
├── service.py       # artifact loading/token checks, tree building, format builders, extraction runner
└── routes.py        # one APIRouter (tags=["documents"]) with all routes
```

`cordis.yml` gains one row after `health` (depends only on `artifacts`
and runtime settings; no `ocr` dependency):

```yaml
  - id: documents
    use: omniscribe.plugins.documents:plugin
```

No Context service registration — routes are the whole surface and
nothing else consumes them. No config fields; `DocumentsSchema` is an
empty `BaseModel`.

## Route contracts (pinned)

Error envelope everywhere: `{"error": <code>, "detail": <string>}`
(the client's `api_client.dart` `_translateDioError` parses this shape).

| Route | Method | Request | Success response |
|---|---|---|---|
| `/api/extract` | POST | JSON `ExtractionRequest` | 200 `{"extracted_data": <dict>}` |
| `/api/export/document` | POST | JSON `DocumentExportRequest` | 200 `{"artifact_id", "token", "format"}` |
| `/api/export/{artifact_id}` | GET | `Authorization: Bearer <token>` | bytes, content type stored at put time |
| `/api/export/docx` | GET **and** POST | GET: `?text=` query param; POST: JSON `{text}` | inline `.docx`, `Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `Content-Disposition: attachment; filename="document.docx"` |
| `/api/export/html` | POST | JSON `ExportHtmlRequest` | inline `text/html; charset=utf-8`, attachment `document.html` |
| `/api/export/docx-tree` | POST | JSON `ExportBlockTreeRequest` | inline `.docx`, attachment `document.docx` |
| `/api/export/blocktree` | POST | JSON `ExportBlockTreeRequest` | JSON block tree |
| `/api/text/{artifact_id}` | GET | Bearer token | `application/json` text artifact |
| `/api/metadata/{artifact_id}` | GET | Bearer token | `application/json` metadata artifact |

`GET /api/export/docx` must exist because the Flutter ExportModal calls
`repo.exportDocx` via `apiClient.getBytes(..., queryParameters: ...)` —
the old server only had POST, a pre-existing mismatch this rebuild fixes
server-side.

### Request model constraints (old contract, `extra="forbid"`)

- Artifact ids: `min_length=32, max_length=32`; artifact tokens:
  `min_length=32, max_length=256`. String fields trimmed by validator.
- `ExtractionRequest`: `text: str = ""`;
  `template: ExtractionTemplate` (server default `invoice`; the client
  always sends it); `custom_prompt: str = ""` with `max_length=4000`;
  `api_base / api_key / model: str | None`.
- `DocumentExportRequest`: `text_artifact_id`, `text_artifact_token`,
  `export_format: DocumentExportFormat` (server default `json`), optional
  `metadata_artifact_id` / `metadata_artifact_token`.
- `ExportHtmlRequest`: `text_artifact_id`, `text_artifact_token`.
- `ExportBlockTreeRequest`: `ExportHtmlRequest` fields + optional
  metadata pair.
- `ExportDocxRequest`: `text: str = ""`.
- StrEnums — `ExtractionTemplate`: `invoice, resume, academic, table,
  table_extraction, custom`. `DocumentExportFormat`: `json, markdown,
  text, docling, mineru`.

## Extraction prompts (pinned)

`PROMPT_VERSION = "2026-08-15.v1"` (re-homed verbatim from
`api/services/ai.py`):

- System message: extract only fields explicitly present; `null` for
  absent; single valid JSON object; no markdown fences.
- User prompt wrapper:
  `"You are a structured data extraction AI. Analyze…\n\nEXTRACTION SCHEMA:\n{instructions}\n\nCRITICAL INSTRUCTION: Output the results STRICTLY as a single valid JSON object…\n\nDOCUMENT TEXT:\n{sanitized text}"`
  (text via `sanitize_prompt_input`, `utils/prompt_safety.py:57`). Full
  verbatim prompt text is recovered from commit `44ef123^`
  (`api/services/ai.py`) during implementation — the ellipses above are
  illustrative, not authoritative.
- Template key schemas (exact keys, in order):
  - **invoice**: `vendor_name`, `invoice_number`, `date`, `due_date`,
    `line_items` (array of `{description, quantity, price, total}`),
    `tax`, `total_amount`, `currency`.
  - **resume**: `candidate_name`, `email`, `phone`, `links` (string
    array), `education` (array of `{degree, institution, year}`),
    `work_experience` (array of `{title, company, dates, highlights}`),
    `skills` (string array).
  - **academic**: `title`, `authors` (string array),
    `publication_year`, `abstract`, `key_conclusions` (string array),
    `methodology`, `limitations` (string array).
  - **table** / **table_extraction**: `{"tables": [{title, headers,
    rows}]}`.
  - **custom**: sanitized `custom_prompt` fenced between
    `--- CUSTOM INSTRUCTION START/END ---`; output a logical key-value
    JSON object.

## Data flow

- **Text artifact loader** (`service.py`): parse stored JSON as
  `dict[str, str]`; sort keys by `int()` value (non-numeric keys
  ignored — artifacts are machine-generated); `lines = value.split("\n")`
  → `pages: dict[int, list[str]]`.
- **Tree builder**: `pages` → `{page: [((0.0, 0.0, 0.0, 0.0), line) for
  line]}` → `block_tree.from_pages_data`. Documented limitation: no real
  bboxes (stored artifacts carry none); structure comes from text
  classification, matching the old legacy-fallback behavior.
- **`build_document_export`** format builders (re-homed from
  `api/services/document_exports.py`), over `pages` + optional metadata:
  - `text`: pages joined by blank lines.
  - `markdown`: `## Page N` sections.
  - `json`: `{"pages": [{"page_index", "lines", "text"}], "metadata"?}`.
  - `docling`: `{"schema": "docling_compatible", "document": pages,
    "metadata"?}`.
  - `mineru`: `{"schema": "mineru_compatible", "pages": pages,
    "metadata"?}`.
  - Media types: json → `application/json`, markdown →
    `text/markdown; charset=utf-8`, text → `text/plain; charset=utf-8`,
    docling/mineru → `application/json`.
  - `POST /api/export/document` stores the built payload via
    `ArtifactStore.put` (`owner_job_id=""`) and returns the handle.
- **Extraction runner**: resolve coordinates (request override →
  `RuntimeSettings`, `pipeline_bridge` pattern) → `check_ssrf_target_sync`
  on the override → `call_llm(prompt=..., system_prompt=EXTRACTION_SYSTEM_MESSAGE,
  temperature=TEMPERATURE_EXTRACTION)` → `extract_json` → nest under
  `extracted_data`.
- **Metadata artifacts**: optional on tree routes;
  `metadata_artifact_id/token` loaded like text artifacts and attached
  under the response's metadata field (blocktree: `tree.metadata["processor_report"]`).

## Error handling

| Condition | Response |
|---|---|
| `/api/extract` with empty (trimmed) text | 400 `{"error": "bad_request", "detail": "'text' is required"}` |
| `api_base` override fails SSRF check | 403 `{"error": "ssrf_blocked", "detail": ...}` |
| LLM call raises | 502 `{"error": "ai_error", "detail": <public message>}` |
| LLM returns unparseable JSON | 200 `{"extracted_data": {}}` (old contract — client renders empty state, not an error) |
| Artifact id unknown / expired / wrong token on `document`, `blocktree`, `html`, `docx-tree` | 404 (old semantics — does not leak existence) |
| Fetch routes (`/api/export/{id}`, `/api/text/{id}`, `/api/metadata/{id}`) missing or wrong Bearer | 403 |

All artifact access stays token-bound (`ArtifactStore.get` compares the
token). Routes remain unauthenticated like the rest of the surface until
the auth middleware wave lands.

## Testing

New `tests/routers/test_documents_export.py` and
`tests/routers/test_documents_extract.py` on the existing conftest
fixtures (`cordis_env`, `harness_ctx`, `api_client`); artifacts are
seeded in tests via `ctx.inject(ArtifactStore).put(...)`. Ported contract
cases:

1. `/api/export/document` markdown round-trip: seed text artifact →
   export → 200 `{artifact_id, token, format}` → fetch with Bearer →
   body starts `## Page 1`; wrong Bearer → 403.
2. `POST /api/export/docx` → 200, docx media type, `content-disposition`
   contains `document.docx`, body starts `PK`; **plus the GET variant**
   (`GET /api/export/docx?text=...`) which the old tests never covered.
3. `/api/export/blocktree` — tree built from a seeded text artifact,
   metadata `processor_report` attach, 404 unknown id, 404
   well-formed-but-wrong token.
4. `/api/export/html` → `text/html`, renders block text, 404 unknown.
5. `/api/export/docx-tree` → docx `PK` magic.
6. `/api/extract` with stubbed `call_llm`: valid JSON → nested
   `extracted_data`; invalid JSON → 200 `{}`; SSRF-blocked `api_base` →
   403 `ssrf_blocked`; empty text → 400.
7. `GET /api/text/{id}` — 200 with correct Bearer, 403 without/wrong.

Fast tier only; no slow markers, no live LLM.

## Docs updates

- `AGENTS.md`: boot-order table gains row 10 (`documents`); the
  deferred-capabilities paragraph drops extraction/export from its list.
- `ARCHITECTURE.md`: plugin list / API surface mentions the documents
  plugin.
- `README.md`: its existing route claims become true again (verify
  wording; no structural edit expected).
- `CHANGELOG.md`: entry under the current unreleased section.

## Acceptance criteria

1. All ten routes serve the current client contract with zero client
   changes (field names, wrappers, media types, token semantics).
2. `uv run ruff check src tests`, `ruff format --check`, `mypy src`,
   `uv run pytest -m "not slow"` all green; new router tests pass.
3. Boot smoke: `cordis.yml` loads ten plugin rows; `/api/health` still
   200 after boot.
4. Contract quirks honored: GET `/api/export/docx`, `extracted_data`
   wrapper, 404-vs-403 split, 200-with-`{}` on invalid extraction JSON.

## Edge cases

- `GET /api/export/docx` with empty/missing `text` → empty docx (old
  model allowed `text: str = ""`; keep lenient).
- Non-numeric page keys in a seeded artifact are ignored by the loader.
- Metadata artifact provided but unknown/expired → 404 (same as text
  artifact).
- Expired artifacts (`ArtifactStore.get` → `None`) → 404.
- `/api/export/document` on a text artifact whose pages are all empty
  still succeeds (empty export payload is valid).
- Extraction with `template != custom` ignores `custom_prompt`; with
  `template == custom` and an empty `custom_prompt`, the old server was
  lenient (fenced empty instructions) — keep that behavior, no 400.

## See also

- [2026-08-27 Flutter takeover Phase A](2026-08-27-flutter-takeover-phase-a-design.md)
- [2026-08-28 Flutter takeover Phase B](2026-08-28-flutter-takeover-phase-b-design.md)
- [2026-08-29 five-domain audit](../../audits/2026-08-29-five-domain-audit.md) — findings #11 (dead client routes) and the deferred-routes context
- Recovered pre-rebuild sources: commit `44ef123^` (routes/services), `e6b7b89^` (contract tests)

_Last updated: 2026-08-30_
