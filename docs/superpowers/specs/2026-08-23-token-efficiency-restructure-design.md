# Token-Efficiency Codebase Restructure — Design Spec

Date: 2026-08-23
Status: Approved (design); implementation plan pending.

## Objective

Restructure the OmniScribe repository so that crawling and discovery
processes (AI agents, indexers, tree scans) spend the fewest possible
tokens to (a) list the repository, (b) navigate to any source file, and
(c) decide which files matter.

## Locked constraints (user decisions)

- **Scope**: deep restructure including module renames. Every in-repo
  import site, doc, and config path is updated; no backward-compat
  shims except the compatibility floor below.
- **Priority**: tree-crawl cost is the tie-breaker. Depth/navigation and
  per-file read cost are addressed only where they do not conflict.
- **Disposition**: non-essential generated/one-off files are deleted,
  not archived. History remains in git.
- **Compatibility floor**: `omniscribe.pipeline.OCRPipeline` must stay
  importable at its current path. (`pipeline.py` never moves, so this
  requires zero shim code.) All AGENTS.md extension-point types
  (`DocumentProcessor`, `PagePreprocessor`, `DocumentResultWriter`,
  `OutputWriter`, progress/warning callbacks) keep their module paths
  because their defining modules do not move.
- **Test layout**: `tests/` mirrors the new `src/` layout.

## Success metrics (verified at the end)

| Metric | Before | Target | Verified |
|---|---|---|---|
| Repo-root file entries | ~26 | no removable junk (see note) | 22 — all mandatory anchors |
| Largest flat directory listing | `tests/` = 142 files | ≤ 25 entries in any directory; `tests/` root ≤ 10 | max 25 (`tests/api/routers`); `tests/` root = 8 |
| Tracked generated artifacts (reports, logs, caches, scratch) | dozens | 0, enforced by `.gitignore` | 0 |
| Max source depth under `src/omniscribe/` | 4 | ≤ 4 | 4 |
| Import breakage | — | none beyond internal updates; `OCRPipeline` path intact | verified intact |

**Root-metric note.** The original "≤ 15" target was internally
inconsistent with the spec's own keep-at-root list (12 config/tool
anchors + 6 markdown docs + 4 protected one-click entry points = 22).
Final policy: the root holds only mandatory project anchors; all junk
moved to untracked/gitignored locations. The remaining 24 entries are
all non-removable.

**Tests note (C5).** C4 met the `tests/`-root target but left
`tests/core` (68) and `tests/api` (61) flat. C5 (`28e4c1b`) sub-grouped
both into directories mirroring the src subpackages, bringing every
directory to ≤ 25 entries.

## Execution shape — Approach A (single branch, five gate-green commits)

One feature branch; commits land in dependency order so the branch is
bisectable even though it merges as one unit. All moves use `git mv`
to preserve history. Every commit passes the AGENTS.md fast gate.
(C5 was added during final verification to close the tests listing
counts — see below.)

## C1 — Prune & ignore (no imports touched)

**Delete tracked junk:** `pylint_report.json`, `.coverage`,
`_check_eol.ps1`, `.poll_server.ps1`, tracked `*.log` / report txt
files. Fold in the already-staged deletions (`audits/`,
`mypy_report.txt`, `ast_checks.txt`, `.fallowrc.json`).

**Keep at root:** `pyproject.toml`, `uv.lock`, `Makefile`,
`Dockerfile`, `compose.yaml`, `.env.example`, `.gitignore`,
`.gitattributes`, `.dockerignore`, `.semgrepignore`,
`.pre-commit-config.yaml`, `LICENSE`, the six markdown docs
(README/AGENTS/ARCHITECTURE/CHANGELOG/DEPLOYMENT/SECURITY), and the
four documented one-click entry points (`install.bat`, `install.ps1`,
`install.sh`, `start_app.vbs`) — user-facing launchers whose
discoverability is the point.

**Move:** `test_ui.py` → `e2e/test_ui.py` (update the CI workflow path
that runs it).

**`.gitignore` hardening** so junk cannot re-enter: `*.log`,
`*_report.txt`, `*_report.json`, `.coverage`, `pytest_co.log`,
`start_app.log`, `.mavis/scratch/`, `.hypothesis/`, `.fallow/`,
`audit_dump.txt`. Audit every root dot-directory: tracked-and-generated
content is untracked via `git rm --cached`; tool config is left tracked.

Gate: fast gate + `git ls-files` audit confirming zero tracked junk.

## C2 — `core/` regroup & rename

`core/` lists 29 loose files + 10 subpackages today. The loose files
cluster into five new subpackages (grouping grounded in module
docstrings); everything moves via `git mv`, all import sites updated in
the same commit.

| New home | Moves (old → new) |
|---|---|
| `core/translate/` | `translation.py`→`workflow.py`, `translation_config.py`→`config.py`, `translation_tree.py`→`tree.py`, `dual_translator.py`→`dual.py`, `nllb_engine.py`→`nllb.py`, `glossary.py`, `entity_memory.py` |
| `core/writers/` | `docx_writer.py`→`docx.py`, `docx_tree_writer.py`→`docx_tree.py`, `html_writer.py`→`html.py`, `tree_export.py`→`tree_json.py`, + absorb `document_exporters/` contents |
| `core/recall/` | `text_recall.py`→`whitespace.py`, `text_layer_recall.py`→`text_layer.py` |
| `core/llm/` | `llm_client.py`→`client.py`, `llm_temperatures.py`→`temperatures.py`, `provider_config.py`→`providers.py` |
| `core/imaging/` | `preprocessing.py`→`page_preprocess.py`, `handwriting_preprocessor.py`→`handwriting.py`, `image_utils.py`→`utils.py` |

**Re-home:** `trocr_engine.py` (handwriting OCR specialist, not
translation) → `core/ocr/trocr.py`. `routing.py` (quality-routing
recommendation metadata, part of the trust layer) →
`core/ocr_quality/routing.py`.

**Stays at `core/` root (8 files):** `document.py`, `block_tree.py`,
`aligner.py`, `callbacks.py`, `errors.py`, `evaluation.py`,
`postprocess.py` (spellcheck), `__init__.py`. Final `core/` listing:
8 files + 14 subpackage dirs = 22 entries, each dir self-describing.

**Untouched subpackages:** `grounded/`, `lexicon/`, `ocr/` (except the
`trocr.py` addition), `ocr_quality/`, `pdf/`, `processors/`,
`transcription/`, `workflows/`, `glossary_sources/`.

Gate: full fast gate + `pytest tests/test_aligner.py -v` (C2 touches
`core/ocr/`).

## C3 — `api/` regroup

`api/services/` goes from 28 files to 17:

| Move | Detail |
|---|---|
| New `api/services/ocr/` | `ocr_chunked_runner.py`→`chunked_runner.py`, `ocr_jobs.py`→`jobs.py`, `ocr_pipeline_factory.py`→`pipeline_factory.py`, `ocr_response.py`→`response.py`, `ocr_settings.py`→`settings.py`, + new `execution.py` receiving `_run_ocr_pipeline` / `_execute_ocr_pipeline` / `_record_job` internals extracted from `routers/ocr.py` |
| New `api/services/state/` | `state_backend.py`→`base.py` (Protocol + `build_state_backend` factory), `state_backend_redis.py`→`redis.py`, `state_backend_sqlite.py`→`sqlite.py` |
| Security consolidation | Delete `security_middleware.py` (compat facade; imports updated to `api.middleware`); `security_config.py`→`api/middleware/settings.py`; `security.py`→`uploads.py` |
| Small merge | `api_helpers.py` + `config_helpers.py` → `helpers.py` |

**`routers/ocr.py` (924 lines):** not a route split — it has only 3
routes (`/process`, `/process/async`, `/process/status/{job_id}`). The
~420 lines of pipeline-execution internals move to
`services/ocr/execution.py`, leaving a thin ~500-line route module.
Route paths and behavior unchanged.

**Untouched:** `middleware/` (+ incoming `settings.py`), `plugin/`
(12-file migration-window package), `schemas/` (2 files),
`celery_app.py`, `tasks.py`. `routers/` stays flat (15 entries, under
threshold; router-per-file is discovery-friendly).

Resulting listings: `api/` = 8 entries, `api/services/` = 17,
`api/routers/` = 15, package root unchanged (9).

Gate: full fast gate.

## C4 — Mirror `tests/` + docs/config sweep

```text
tests/
├── conftest.py              (stays — shared fixtures)
├── fixtures/                (stays)
├── openapi.json             (stays)
├── core/                    (~70 files; includes core/workflows/ mirror)
├── api/                     (existing dir absorbs ~55 top-level API tests)
├── scripts/                 (script smoke/CLI tests)
└── e2e/                     (test_ui.py, moved in C1)
```

Placement rule: each test file follows the package path of the module
it primarily imports; cross-cutting suites (`test_integration.py`,
`test_live_llm.py`) land in `tests/api/` / `tests/e2e/` by what they
drive.

**Known risk, mitigated before moving:** tests building fixture paths
via `Path(__file__).parent` break on move. First grep all
`__file__`-relative path usages and rewrite them to a shared conftest
fixture-path helper.

**Docs/config sweep (same commit):**

- AGENTS.md: full rewrite of "Key Files" table, "Core Paths" table,
  plugin-migration paths, Web Notes path references; bump stamp.
- ARCHITECTURE.md / DEPLOYMENT.md / README.md: path updates.
- `.github/workflows`: `test_ui.py` → `e2e/test_ui.py` in the e2e job.
- `pyproject.toml`: check `testpaths` / ruff / mypy path globs for
  stale entries (script entries unchanged).
- `scripts/`: update imports of moved modules.

Gate: full fast gate.

## C5 — Sub-group `tests/core` and `tests/api` (follow-up, `28e4c1b`)

C4's two-level mirror left `tests/core/` (68) and `tests/api/` (61)
as flat listings, breaching the ≤ 25 metric. C5 completes the
"mirror the src layout" decision at subpackage depth: every test
moves under the directory matching its subject module's home
(`tests/core/{translate,writers,recall,llm,imaging,ocr,ocr_quality,pdf,grounded,processors,lexicon,glossary_sources,workflows}/`,
`tests/api/{routers,middleware,services,services/ocr,services/state}/`).
`git mv` only; zero logic changes; path-depth anchors
(`Path(__file__).parents[N]`) adjusted for the new depth; cross-test
imports and stale path references repointed.

Gate: full fast gate + directory-count audit (max 25).

## Final validation (before merge)

1. Full gate: `uv run pytest`, `uv run pytest -m slow`,
   `uv run pytest tests/test_aligner.py -v` (post-C4 path:
   `tests/core/test_aligner.py`).
2. Frontend gate skipped (no frontend changes); `live_llm` manual.
3. Re-run the structure probe and assert the success-metrics table.

## Out of scope

- Splitting oversized modules purely for per-file read cost
  (`provider_manager.py` at 1126 lines, `schemas/requests.py` at 854
  lines) — noted as future work, not part of this restructure.
- Any frontend, pipeline-behavior, or API-surface changes.
- Plugin-context migration status changes (`api/plugin/` untouched).
