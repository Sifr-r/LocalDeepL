# Token-Efficiency Codebase Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the OmniScribe repo for minimum crawler/discovery token cost: prune tracked junk, harden `.gitignore`, regroup `core/` and `api/` into self-describing subpackages, and mirror `tests/` to the new `src/` layout — with zero behavior change.

**Architecture:** Single feature branch, four gate-green commits (C1 prune & ignore → C2 `core/` regroup → C3 `api/` regroup → C4 test mirror + docs sweep). All moves use `git mv`; all import strings are rewritten by one throwaway script driven by explicit old→new mapping tables; behavior is verified by the existing test suite (AGENTS.md gates), not new tests.

**Tech Stack:** Python 3.11+, `uv`, ruff, mypy, pytest (pytest-asyncio auto mode), git, PowerShell (Windows host — use `;` not `&&`).

**Spec:** `docs/superpowers/specs/2026-08-23-token-efficiency-restructure-design.md` (local, untracked by repo policy).

**Ground rules for every task:**
- Work from the repo root `d:\OmniScribe` unless stated otherwise.
- After every commit's gate step, ALL of these must pass before committing:
  ```powershell
  uv run ruff check src tests
  uv run ruff format src tests --check
  uv run mypy src
  uv run pytest -m "not slow"
  ```
- If a rewrite leaves stragglers, the verification grep in each task is the source of truth — it must print **zero** lines before you commit.
- Do NOT use `git add -A` (the working tree contains unrelated staged deletions that C1 folds in deliberately, and untracked scratch files that must stay untracked). Add files by explicit path.

---

## Task 0: Create the feature branch

**Files:** none

- [ ] **Step 1: Verify clean-enough state and branch**

```powershell
git status --short
git switch -c refactor/token-efficiency-restructure
```

Expected: you see the pre-existing unstaged deletions (`.fallowrc.json`, `ast_checks.txt`, `audit_dump.txt`, `audits/*.md`, `mypy_report.txt`) — these are folded into C1 deliberately. Untracked files under `.mavis/scratch/` and `docs/superpowers/` stay untracked.

---

## Task 1: Throwaway import-rewrite script

**Files:**
- Create: `.mavis/scratch/rewrite_imports.py` (never committed; `.mavis/scratch/` becomes gitignored in Task 3)

- [ ] **Step 1: Write the script**

```python
"""Throwaway module-path rewriter for the token-efficiency restructure.

Usage: python .mavis/scratch/rewrite_imports.py <phase>
where <phase> is one of: c2, c3.

Rewrites fully-qualified module paths in every .py file under
src/omniscribe, tests, and scripts, plus the three forms:
  import OLD                     -> import NEW
  from OLD import names          -> from NEW import names
  from omniscribe.core import X  -> from NEWPKG import NEWLEAF as X  (c2 only)
Prints every changed file. Longest OLD first, word-boundary anchored,
so `translation` never matches `translation_config`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = [ROOT / "src" / "omniscribe", ROOT / "tests", ROOT / "scripts"]

# old dotted module -> new dotted module
C2 = {
    "omniscribe.core.translation_config": "omniscribe.core.translate.config",
    "omniscribe.core.translation_tree": "omniscribe.core.translate.tree",
    "omniscribe.core.translation": "omniscribe.core.translate.workflow",
    "omniscribe.core.dual_translator": "omniscribe.core.translate.dual",
    "omniscribe.core.nllb_engine": "omniscribe.core.translate.nllb",
    "omniscribe.core.glossary": "omniscribe.core.translate.glossary",
    "omniscribe.core.entity_memory": "omniscribe.core.translate.entity_memory",
    "omniscribe.core.docx_tree_writer": "omniscribe.core.writers.docx_tree",
    "omniscribe.core.docx_writer": "omniscribe.core.writers.docx",
    "omniscribe.core.html_writer": "omniscribe.core.writers.html",
    "omniscribe.core.tree_export": "omniscribe.core.writers.tree_json",
    "omniscribe.core.document_exporters.base_exporter": "omniscribe.core.writers.exporter_base",
    "omniscribe.core.document_exporters": "omniscribe.core.writers.exporter_base",
    "omniscribe.core.text_layer_recall": "omniscribe.core.recall.text_layer",
    "omniscribe.core.text_recall": "omniscribe.core.recall.whitespace",
    "omniscribe.core.llm_temperatures": "omniscribe.core.llm.temperatures",
    "omniscribe.core.llm_client": "omniscribe.core.llm.client",
    "omniscribe.core.provider_config": "omniscribe.core.llm.providers",
    "omniscribe.core.handwriting_preprocessor": "omniscribe.core.imaging.handwriting",
    "omniscribe.core.preprocessing": "omniscribe.core.imaging.page_preprocess",
    "omniscribe.core.image_utils": "omniscribe.core.imaging.utils",
    "omniscribe.core.trocr_engine": "omniscribe.core.ocr.trocr",
    "omniscribe.core.routing": "omniscribe.core.ocr_quality.routing",
}

C3 = {
    "omniscribe.api.services.ocr_chunked_runner": "omniscribe.api.services.ocr.chunked_runner",
    "omniscribe.api.services.ocr_pipeline_factory": "omniscribe.api.services.ocr.pipeline_factory",
    "omniscribe.api.services.ocr_response": "omniscribe.api.services.ocr.response",
    "omniscribe.api.services.ocr_settings": "omniscribe.api.services.ocr.settings",
    "omniscribe.api.services.ocr_jobs": "omniscribe.api.services.ocr.jobs",
    "omniscribe.api.services.state_backend_redis": "omniscribe.api.services.state.redis",
    "omniscribe.api.services.state_backend_sqlite": "omniscribe.api.services.state.sqlite",
    "omniscribe.api.services.state_backend": "omniscribe.api.services.state.base",
    "omniscribe.api.services.security_middleware": "omniscribe.api.middleware",
    "omniscribe.api.services.security_config": "omniscribe.api.middleware.settings",
    "omniscribe.api.services.security": "omniscribe.api.services.uploads",
    "omniscribe.api.services.api_helpers": "omniscribe.api.services.helpers",
    "omniscribe.api.services.config_helpers": "omniscribe.api.services.helpers",
}

MAPPING = {"c2": C2, "c3": C3}


def rewrite(text: str, mapping: dict[str, str]) -> tuple[str, int]:
    count = 0
    for old, new in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        pat = re.compile(r"(?<![\w.])" + re.escape(old) + r"\b")
        text, n = pat.subn(new, text)
        count += n
    return text, count


def main() -> None:
    phase = sys.argv[1]
    mapping = MAPPING[phase]
    changed = 0
    for base in SCAN_DIRS:
        for path in base.rglob("*.py"):
            original = path.read_text(encoding="utf-8")
            updated, n = rewrite(original, mapping)
            if n:
                path.write_text(updated, encoding="utf-8")
                print(f"{path.relative_to(ROOT)}: {n} replacements")
                changed += 1
    print(f"done: {changed} files changed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Sanity-check it parses**

Run: `python -c "import ast; ast.parse(open('.mavis/scratch/rewrite_imports.py', encoding='utf-8').read())"`
Expected: no output, exit 0.

- [ ] **Step 3: No commit** — this file is scratch and will be gitignored.

---

## Task 2 (C1): Delete tracked junk + move test_ui.py

**Files:**
- Delete: `pylint_report.json`, `.coverage`, `_check_eol.ps1`, `.poll_server.ps1`, plus any other tracked `*.log` / `*_report.*` found in Step 1
- Move: `test_ui.py` → `e2e/test_ui.py`
- Modify: `.github/workflows/test.yml` (e2e job path)

- [ ] **Step 1: Audit tracked junk**

```powershell
git ls-files | Select-String -Pattern '(\.log$|_report\.|\.coverage$|^ast_checks|^audit_dump|\.fallowrc)'
```

Expected hits (verify against actual output): `.coverage`, `pylint_report.json`, `ast_checks.txt`, `audit_dump.txt`, `.fallowrc.json`, `mypy_report.txt`, `start_app.log`, `pytest_co.log` (whichever are tracked). Anything tracked that matches is deleted in Step 2.

- [ ] **Step 2: Delete junk and fold in the staged deletions**

```powershell
git rm -q pylint_report.json .coverage _check_eol.ps1 .poll_server.ps1
git rm -q --ignore-unmatch start_app.log pytest_co.log ast_checks.txt audit_dump.txt .fallowrc.json mypy_report.txt
git rm -qr --ignore-unmatch audits
```

(Adjust the list to Step 1's actual output; never delete `.env.example`, `uv.lock`, or any file in the "keep at root" list from the spec.)

- [ ] **Step 3: Move the e2e test**

```powershell
New-Item -ItemType Directory e2e -Force | Out-Null
git mv test_ui.py e2e/test_ui.py
```

- [ ] **Step 4: Update the CI path**

Find the reference: `git grep -n "test_ui.py" -- .github`
In each hit (expected: `.github/workflows/test.yml` e2e job), replace `test_ui.py` with `e2e/test_ui.py` (the command is typically `uv run --with playwright ... python test_ui.py` → `python e2e/test_ui.py`).

- [ ] **Step 5: Verify**

```powershell
git grep -n "test_ui.py" -- .github
```
Expected: every hit shows `e2e/test_ui.py`.

- [ ] **Step 6: Do NOT commit yet** — Task 3's `.gitignore` changes land in the same C1 commit.

---

## Task 3 (C1): Harden .gitignore, gate, commit C1

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Append the hardening block**

Append to `.gitignore`:

```gitignore
# Token-efficiency restructure (C1): generated artifacts must never be tracked
*.log
*_report.txt
*_report.json
.coverage
.mavis/scratch/
.hypothesis/
.fallow/
```

- [ ] **Step 2: Audit root dot-directories**

```powershell
git ls-files | Select-String -Pattern '^\.'
```

For each tracked dot-entry: if it is tool *config* (`.gitattributes`, `.pre-commit-config.yaml`, `.semgrepignore`, `.dockerignore`, `.env.example`) keep it; if it is generated cache/log content, `git rm -q --cached <path>` it. (Expected generated candidates: anything under `.fallow/`, `.qoder/`, `.superpowers/` if tracked — most are already ignored.)

- [ ] **Step 3: Run the fast gate**

```powershell
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"
```

Expected: all pass (C1 touched no imports).

- [ ] **Step 4: Commit C1**

```powershell
git add .gitignore .github/workflows/test.yml e2e/test_ui.py
git status --short   # confirm only C1 changes are staged (deletions from Task 2 included)
git commit -m "refactor(repo): prune tracked artifacts, harden gitignore, move test_ui to e2e/"
```

---

## Task 4 (C2): Create core/ subpackages and move files

**Files:**
- Create dirs + `__init__.py`: `src/omniscribe/core/translate/`, `core/writers/`, `core/recall/`, `core/llm/`, `core/imaging/`
- Move: 23 loose `core/*.py` files + `document_exporters/base_exporter.py` (see mapping)

- [ ] **Step 1: Create the five packages**

```powershell
foreach ($d in 'translate','writers','recall','llm','imaging') {
    New-Item -ItemType Directory "src\omniscribe\core\$d" -Force | Out-Null
}
```

Create each `__init__.py` with a one-line docstring, e.g. `src/omniscribe/core/translate/__init__.py`:

```python
"""Translation engines and tree-aware translation workflows."""
```

Analogous one-liners: `writers/` → `"""Document export writers (DOCX, HTML, block-tree JSON)."""`; `recall/` → `"""Secondary text-recall sources merged into hybrid detection."""`; `llm/` → `"""LLM client, temperature constants, and provider config."""`; `imaging/` → `"""Page image preprocessing and handwriting enhancement."""`

- [ ] **Step 2: git mv everything (one block, copy-paste)**

```powershell
$B = 'src\omniscribe\core'
git mv $B\translation.py        $B\translate\workflow.py
git mv $B\translation_config.py $B\translate\config.py
git mv $B\translation_tree.py   $B\translate\tree.py
git mv $B\dual_translator.py    $B\translate\dual.py
git mv $B\nllb_engine.py        $B\translate\nllb.py
git mv $B\glossary.py           $B\translate\glossary.py
git mv $B\entity_memory.py      $B\translate\entity_memory.py
git mv $B\docx_writer.py        $B\writers\docx.py
git mv $B\docx_tree_writer.py   $B\writers\docx_tree.py
git mv $B\html_writer.py        $B\writers\html.py
git mv $B\tree_export.py        $B\writers\tree_json.py
git mv $B\document_exporters\base_exporter.py $B\writers\exporter_base.py
git mv $B\text_recall.py        $B\recall\whitespace.py
git mv $B\text_layer_recall.py  $B\recall\text_layer.py
git mv $B\llm_client.py         $B\llm\client.py
git mv $B\llm_temperatures.py   $B\llm\temperatures.py
git mv $B\provider_config.py    $B\llm\providers.py
git mv $B\preprocessing.py      $B\imaging\page_preprocess.py
git mv $B\handwriting_preprocessor.py $B\imaging\handwriting.py
git mv $B\image_utils.py        $B\imaging\utils.py
git mv $B\trocr_engine.py       $B\ocr\trocr.py
git mv $B\routing.py            $B\ocr_quality\routing.py
git rm $B\document_exporters\__init__.py
```

- [ ] **Step 3: Run the import rewrite**

```powershell
python .mavis/scratch/rewrite_imports.py c2
```

Expected: prints changed files across `src/`, `tests/`, `scripts/`; `done: N files changed`.

- [ ] **Step 4: Verify zero stragglers**

```powershell
git grep -nE "omniscribe\.core\.(translation|translation_config|translation_tree|dual_translator|nllb_engine|entity_memory|docx_writer|docx_tree_writer|html_writer|tree_export|document_exporters|text_recall|text_layer_recall|llm_client|llm_temperatures|provider_config|preprocessing|handwriting_preprocessor|image_utils|trocr_engine|routing)\b" -- src tests scripts
```

Expected: **zero lines**. Note: `omniscribe.core.glossary` must be checked separately (`git grep -n "omniscribe.core.glossary\b" -- src tests scripts` — zero lines expected; `glossary_sources` hits are fine and must NOT appear because of the word boundary).

Any straggler is a from-import of the form `from omniscribe.core import X` — fix by hand: replace with `from omniscribe.core.<pkg> import <newleaf>` and keep or drop the local alias to match usage in that file.

- [ ] **Step 5: Fix relative imports inside moved modules**

Moved modules may use relative imports (`from .document import ...`) that now cross package boundaries. Find them:

```powershell
git grep -n "^from \.\|^from \.\." -- src/omniscribe/core/translate src/omniscribe/core/writers src/omniscribe/core/recall src/omniscribe/core/llm src/omniscribe/core/imaging src/omniscribe/core/ocr/trocr.py src/omniscribe/core/ocr_quality/routing.py
```

Rewrite each hit to the absolute form (`from omniscribe.core.document import ...`). mypy in the next step catches any that were missed.

- [ ] **Step 6: Gate**

```powershell
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"
uv run pytest tests/test_aligner.py -v
```

Expected: all pass. (`test_aligner.py` run is required because C2 touches `core/ocr/`; it still lives at the tests root until C4.)

- [ ] **Step 7: Smoke the compat floor**

```powershell
uv run python -c "from omniscribe.pipeline import OCRPipeline; print(OCRPipeline)"
```

Expected: prints `<class 'omniscribe.pipeline.OCRPipeline'>`.

- [ ] **Step 8: Commit C2**

```powershell
git add src tests scripts
git status --short
git commit -m "refactor(core): regroup loose modules into translate/writers/recall/llm/imaging subpackages"
```

---

## Task 5 (C3): Regroup api/services

**Files:**
- Create dirs + `__init__.py`: `api/services/ocr/`, `api/services/state/`
- Move: 8 service modules (see mapping)
- Delete: `api/services/security_middleware.py`
- Merge: `api_helpers.py` + `config_helpers.py` → `helpers.py`

- [ ] **Step 1: Collision check before the merge**

```powershell
git grep -hnE "^(def|async def|class|[A-Z_]+ =)" -- src/omniscribe/api/services/api_helpers.py src/omniscribe/api/services/config_helpers.py
```

Expected: no symbol name appears in both files. If one does, prefix the `config_helpers` copy with `config_` at its definition and update its callers in the same task.

- [ ] **Step 2: Create packages and move files**

```powershell
$S = 'src\omniscribe\api\services'
New-Item -ItemType Directory $S\ocr, $S\state -Force | Out-Null
Set-Content $S\ocr\__init__.py   '"""OCR job execution services (runner, factory, response, settings)."""'
Set-Content $S\state\__init__.py '"""State backend implementations (local, SQLite, Redis)."""'
git mv $S\ocr_chunked_runner.py  $S\ocr\chunked_runner.py
git mv $S\ocr_pipeline_factory.py $S\ocr\pipeline_factory.py
git mv $S\ocr_response.py        $S\ocr\response.py
git mv $S\ocr_settings.py        $S\ocr\settings.py
git mv $S\ocr_jobs.py            $S\ocr\jobs.py
git mv $S\state_backend.py       $S\state\base.py
git mv $S\state_backend_redis.py $S\state\redis.py
git mv $S\state_backend_sqlite.py $S\state\sqlite.py
git mv $S\security_config.py     src\omniscribe\api\middleware\settings.py
git mv $S\security.py            $S\uploads.py
```

- [ ] **Step 3: Merge helpers, delete facade**

```powershell
Get-Content $S\api_helpers.py, $S\config_helpers.py | Set-Content $S\helpers.py
git rm $S\api_helpers.py $S\config_helpers.py $S\security_middleware.py
```

Open `$S\helpers.py`: merge the two import blocks (dedupe), keep one module docstring: `"""Shared router/config helper functions."""`.

`security_middleware.py` was a re-export facade for `omniscribe.api.middleware`; the rewrite script maps its import string directly to `omniscribe.api.middleware`, so deletion is safe once Step 4 shows zero stragglers.

- [ ] **Step 4: Run the import rewrite**

```powershell
python .mavis/scratch/rewrite_imports.py c3
```

- [ ] **Step 5: Verify zero stragglers**

```powershell
git grep -nE "omniscribe\.api\.services\.(ocr_chunked_runner|ocr_pipeline_factory|ocr_response|ocr_settings|ocr_jobs|state_backend|state_backend_redis|state_backend_sqlite|security_middleware|security_config|security|api_helpers|config_helpers)\b" -- src tests scripts
```

Expected: **zero lines** (the new `...services.ocr.` / `...services.state.` paths are fine).

Then fix relative imports inside moved modules exactly as Task 4 Step 5:

```powershell
git grep -n "^from \.\|^from \.\." -- src/omniscribe/api/services/ocr src/omniscribe/api/services/state src/omniscribe/api/middleware/settings.py src/omniscribe/api/services/uploads.py src/omniscribe/api/services/helpers.py
```

- [ ] **Step 6: pyproject per-file ruff overrides**

`pyproject.toml` has per-file lint overrides keyed by path. Update:
- `"src/omniscribe/api/services/security.py" = ["SIM115"]` → `"src/omniscribe/api/services/uploads.py" = ["SIM115"]`
- Check lines ~265–276 for any other moved path (`api/routers/ocr.py`, `api/routers/config.py`, `server.py` do not move — leave them).

- [ ] **Step 7: Gate**

```powershell
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"
```

- [ ] **Step 8: Do NOT commit yet** — Task 6's `routers/ocr.py` extraction is part of the same C3 commit.

---

## Task 6 (C3): Extract pipeline-execution internals from routers/ocr.py

**Files:**
- Create: `src/omniscribe/api/services/ocr/execution.py`
- Modify: `src/omniscribe/api/routers/ocr.py` (~924 → ~500 lines)

- [ ] **Step 1: Create execution.py by moving these eight helpers**

Read `routers/ocr.py` and cut these module-level helpers (they sit between the imports and the first `@router.post`, roughly lines 82–503):

| Helper | Note |
|---|---|
| `_fire_and_forget_awaitable` | |
| `_create_document_metadata_artifact` | |
| `stage_to_percent` | keep public name (no underscore) — tests import it |
| `_record_job` | |
| `_emit_job_submitted` | |
| `_emit_job_started` | |
| `_run_ocr_pipeline` | |
| `_execute_ocr_pipeline` | |

Paste them into `src/omniscribe/api/services/ocr/execution.py` with docstring:

```python
"""Pipeline-execution internals for the OCR process routes.

Extracted from ``omniscribe.api.routers.ocr`` so the router module
holds only route handlers.
"""
```

Move whatever imports those helpers need into `execution.py`; do not touch the route handlers' own imports.

- [ ] **Step 2: Slim the router**

In `routers/ocr.py`, delete the moved helpers and their now-unused imports, then add:

```python
from omniscribe.api.services.ocr.execution import (
    _create_document_metadata_artifact,
    _execute_ocr_pipeline,
    _fire_and_forget_awaitable,
    _record_job,
    _run_ocr_pipeline,
    stage_to_percent,
)
```

(Keep only the names the three route handlers actually reference — mypy flags unused ones.)

Route paths and behavior are unchanged: `POST /api/process`, `POST /api/process/async`, `GET /api/process/status/{job_id}`.

- [ ] **Step 3: Gate**

```powershell
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"
```

- [ ] **Step 4: Commit C3**

```powershell
git add src tests scripts pyproject.toml
git status --short
git commit -m "refactor(api): regroup services into ocr/state subpackages, slim ocr router"
```

---

## Task 7 (C4): Path helpers in tests/conftest.py + __file__ audit

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add stable path helpers**

Tests that compute paths from `__file__` will move in Task 8; route them through conftest (which stays at `tests/` root) first. Append to `tests/conftest.py` (dedupe if similar helpers already exist):

```python
def repo_root() -> Path:
    """Repository root, stable regardless of test file location."""
    return Path(__file__).resolve().parent.parent


def fixture_path(*parts: str) -> Path:
    """Path under tests/fixtures/, stable regardless of test file location."""
    return Path(__file__).resolve().parent.joinpath("fixtures", *parts)
```

(`Path` is already imported in conftest; if not, add `from pathlib import Path`.)

- [ ] **Step 2: Audit __file__-relative path usage**

```powershell
git grep -n "__file__" -- tests
```

For every hit outside `tests/conftest.py`: rewrite the path expression to use `fixture_path(...)` / `repo_root()` (import them from conftest only if the test already imports conftest symbols; otherwise compute via the same `Path(__file__)` chain adjusted for the new depth — prefer the helpers). Re-run the grep until only `tests/conftest.py` hits remain.

- [ ] **Step 3: Quick check**

```powershell
uv run pytest -m "not slow"
```

Expected: pass (nothing moved yet, helpers are additive).

- [ ] **Step 4: Do NOT commit yet** — lands with Task 8 in the C4 commit.

---

## Task 8 (C4): Mirror tests/ into core/, api/, scripts/, e2e/

**Files:**
- Create dirs: `tests/core/`, `tests/core/workflows/`, `tests/scripts/` (`tests/api/` and `tests/e2e/` exist)
- Move: ~140 top-level `tests/test_*.py` files

- [ ] **Step 1: Create directories**

```powershell
New-Item -ItemType Directory tests\core\workflows, tests\scripts -Force | Out-Null
```

- [ ] **Step 2: Placement rule + overrides**

Each top-level `tests/test_*.py` moves by the package of its primary `from omniscribe...` import:

| Primary import starts with | Destination |
|---|---|
| `omniscribe.core.workflows` | `tests/core/workflows/` |
| `omniscribe.core` | `tests/core/` |
| `omniscribe.api` or `omniscribe.server` | `tests/api/` |
| `omniscribe.cli` | `tests/cli/` (exists) |
| imports from `scripts.` / runs a script | `tests/scripts/` |

Explicit overrides (cross-cutting suites): `test_integration.py` → `tests/api/`, `test_live_llm.py` → `tests/api/`, `test_ui.py` is already in `e2e/`.

Determine the primary import per file mechanically:

```powershell
Get-ChildItem tests -File -Filter test_*.py | ForEach-Object {
    $hit = Select-String -Path $_.FullName -Pattern '^from (omniscribe\.[a-z_.]+)' | Select-Object -First 1
    "{0}`t{1}" -f $_.Name, ($hit.Matches[0].Groups[1].Value)
}
```

Then move each file with `git mv tests\<name>.py <destination>\<name>.py`. Work in batches per destination directory.

- [ ] **Step 3: Verify the top level is clean**

```powershell
Get-ChildItem tests -File
```

Expected: only `conftest.py` and `openapi.json`.

- [ ] **Step 4: Fix any path fallout**

```powershell
uv run pytest -m "not slow"
```

Failures will be residual path assumptions (Step 2 of Task 7 catches most). Fix each by routing through `fixture_path()` / `repo_root()`.

- [ ] **Step 5: Gate**

```powershell
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"
```

- [ ] **Step 6: Do NOT commit yet** — Task 9's docs sweep lands in the same C4 commit.

---

## Task 9 (C4): Docs and config sweep

**Files:**
- Modify: `AGENTS.md`, `ARCHITECTURE.md`, `README.md`, `DEPLOYMENT.md`, `.pre-commit-config.yaml`, `.github/workflows/*.yml`

- [ ] **Step 1: Find every stale path reference**

```powershell
git grep -nE "core/(translation|translation_config|translation_tree|dual_translator|nllb_engine|entity_memory|glossary|docx_writer|docx_tree_writer|html_writer|tree_export|document_exporters|text_recall|text_layer_recall|llm_client|llm_temperatures|provider_config|preprocessing|handwriting_preprocessor|image_utils|trocr_engine|routing)\.py" -- *.md .github .pre-commit-config.yaml
git grep -nE "services/(ocr_chunked_runner|ocr_jobs|ocr_pipeline_factory|ocr_response|ocr_settings|state_backend|security|api_helpers|config_helpers)" -- *.md .github
git grep -n "tests/test_" -- *.md .github
```

- [ ] **Step 2: Rewrite AGENTS.md**

This is the largest doc task. Update, in order:
1. **Core Paths** tables — paths unchanged (`core/`, `api/` roots are still the gate triggers), no change needed unless a listed file moved.
2. **Key Files table** — every row whose file moved gets the new path and, where the rename changed the class home, the new module (e.g. `core/text_recall.py` row → `core/recall/whitespace.py`; `api/services/state_backend.py` row → `api/services/state/base.py`; add rows for `core/translate/`, `core/writers/`, `core/recall/`, `core/llm/`, `core/imaging/`, `api/services/ocr/execution.py`).
3. **Plugin Context Migration Status** — `api/services/artifacts.py` did not move; verify each seam path in the table against the new tree.
4. **Web Notes / Known Tech Debt** — `api/routers/ocr.py` description gains "(execution internals live in `api/services/ocr/execution.py`)"; `test_ui.py` → `e2e/test_ui.py`.
5. Bump the `_Last updated:_` stamp to today.

- [ ] **Step 3: Sweep the remaining docs and configs**

Fix every hit from Step 1 in `ARCHITECTURE.md`, `README.md`, `DEPLOYMENT.md`, workflow ymls, and `.pre-commit-config.yaml` (check its `files:`/`exclude:` patterns reference moved paths).

- [ ] **Step 4: Gate**

```powershell
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"
```

- [ ] **Step 5: Commit C4**

```powershell
git add tests AGENTS.md ARCHITECTURE.md README.md DEPLOYMENT.md .pre-commit-config.yaml .github
git status --short
git commit -m "refactor(tests): mirror src layout; update docs and configs for restructure"
```

---

## Task 10: Full gate + metrics verification

**Files:**
- Read-only verification

- [ ] **Step 1: Full test gate**

```powershell
uv run pytest
uv run pytest -m slow
uv run pytest tests/core/test_aligner.py -v
```

Expected: all pass. (`live_llm` is manual — optionally `uv run pytest -m live_llm` if LM Studio is running.)

- [ ] **Step 2: Compat floor**

```powershell
uv run python -c "from omniscribe.pipeline import OCRPipeline; print(OCRPipeline)"
```

Expected: `<class 'omniscribe.pipeline.OCRPipeline'>`.

- [ ] **Step 3: Metrics verification**

Run the structure probe (`.mavis/scratch/structure_probe.ps1`) and assert against the spec table:

| Metric | Target |
|---|---|
| Root file entries | ≤ 15 (`Get-ChildItem -File` at repo root) |
| Largest dir listing | ≤ 25 entries; `tests/` root ≤ 10 |
| Tracked artifacts | `git ls-files` shows zero `*.log` / `*_report.*` / `.coverage` |
| Max depth under `src/omniscribe/` | ≤ 4 |

If any metric fails, fix before proceeding (usually: one more junk deletion or one more grouping).

- [ ] **Step 4: Final status**

```powershell
git log --oneline refactor/token-efficiency-restructure ^main
```

Expected: exactly four commits (C1–C4). The branch is ready to merge per the user's normal flow.
