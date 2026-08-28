# Flutter Takeover Phase B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Atomically delete the Svelte reference UI (`frontend/`), its Playwright smoke test (`e2e/test_ui.py`), the `axe-playwright-python` dev dependency, and every launcher / config / doc reference that exists only to support the Svelte UI, leaving the Flutter client as the sole UI surface.

**Architecture:** Single atomic commit per the user-selected PR strategy. The plan executes 10 logical tasks (each a coherent edit group) that all land in one commit at the end. The historical `frontend/` commits remain in git history (recoverable via `git checkout <sha>~1 -- frontend/`); this sweep only deletes the tree as it stands today.

**Tech Stack:** PowerShell on Windows (user shell); Flutter 3.24+; `uv` for Python; git for VCS; markdown for spec/plan.

---

## File structure

### Files deleted

| Path | Purpose (before deletion) |
| --- | --- |
| `frontend/` | Svelte 5 + Tailwind v4 + Vite + Vitest UI source (~85 files) |
| `e2e/test_ui.py` | Playwright smoke test against the Svelte UI |

### Files modified

| Path | Change |
| --- | --- |
| `pyproject.toml` | Drop `axe-playwright-python` from `[dependency-groups] dev` |
| `.github/workflows/test.yml` | Drop `frontend` + `e2e` jobs; drop `axe-playwright-python` install step |
| `install.sh` | Drop Node / `npm ci` / `npm run build` blocks |
| `install.bat` | Drop Node / `npm ci` / `npm run build` blocks |
| `install.ps1` | Drop Node / `npm ci` / `npm run build` blocks |
| `start_app.vbs` | Drop the Vite dev-server child window launch |
| `Dockerfile` | Drop Vite build stage (if present) |
| `compose.yaml` | Drop `frontend` service block (if present) |
| `.pre-commit-config.yaml` | Drop frontend-specific hooks (if any) |
| `.gitignore` | Drop `frontend/node_modules/`, `frontend/dist/`, `frontend/build/` |
| `README.md` | Replace `web workspace` / Svelte install with Flutter client references |
| `ARCHITECTURE.md` | Drop Svelte UI sections + file-ledger entries |
| `AGENTS.md` | Drop `frontend/` row from Core Paths table; drop peripheral-validation row |
| `DEPLOYMENT.md` | Drop Svelte/Vite build + serve references |
| `SECURITY.md` | Drop Svelte-specific threat-model references |
| `docs/superpowers/specs/2026-08-27-flutter-takeover-phase-a-design.md` | Update "reference Svelte UI" -> "previous Svelte UI" wording |
| `uv.lock` | Regenerated from `pyproject.toml` change (committed alongside) |

---

## Phase 1 - Baseline capture

### Task 1: Capture pre-deletion baseline

**Files:** none (verification only)

- [ ] **Step 1.1: Confirm working tree is clean**

Run:
```bash
git -C d:\OmniScribe status
```
Expected: nothing to commit (or only `uv.lock` modified from session churn - note this for the post-deletion comparison).

- [ ] **Step 1.2: Record current HEAD**

Run:
```bash
git -C d:\OmniScribe log --oneline -1
```
Expected: prints the latest commit SHA. Save the SHA.

- [ ] **Step 1.3: Run the backend fast gate**

Run:
```bash
cd d:\OmniScribe
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow" --ignore=tests/core/lexicon --ignore=tests/core/translate/test_translation_lexicon_integration.py
```
Expected: all green, ~1290 passed in pytest.

- [ ] **Step 1.4: Run the Flutter gate**

Run:
```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\flutter.bat" analyze
& "C:\src\flutter\bin\flutter.bat" test
```
Expected: analyze clean; test passes.

- [ ] **Step 1.5: Backend smoke with Phase A routes**

Boot server:
```bash
cd d:\OmniScribe
uv run omniscribe-server --port 8000
```
In another terminal:
```bash
curl.exe -s http://127.0.0.1:8000/api/health
```
Expected: `{"status":"ok"}`. Then POST to `/api/providers/active` with a Phase A payload, expect 200 with echo JSON. Stop the server.

- [ ] **Step 1.6: Continue** (no commit yet).

## Phase 2 - Deletion sweep

### Task 2: Delete `frontend/` and `e2e/test_ui.py`

**Files:**
- Delete: `frontend/` (entire tree)
- Delete: `e2e/test_ui.py`

- [ ] **Step 2.1: Delete the `frontend/` directory via git**

Run:
```bash
git -C d:\OmniScribe rm -rf frontend
```
Expected: `git rm` deletes the directory and stages the removal. If `git rm` errors with `fatal: pathspec ''frontend'' did not match any files` - fall back to `git -C d:\OmniScribe rm -r --cached frontend` followed by `Remove-Item -Recurse -Force d:\OmniScribe\frontend` to clear the working tree.

- [ ] **Step 2.2: Delete `e2e/test_ui.py`**

Run:
```bash
git -C d:\OmniScribe rm e2e/test_ui.py
```
Expected: file staged for removal.

- [ ] **Step 2.3: Verify the deletions are staged**

Run:
```bash
git -C d:\OmniScribe status --short
```
Expected: `D  frontend/` and `D  e2e/test_ui.py` listed (capital `D` = staged deletion).

- [ ] **Step 2.4: Confirm no orphaned top-level `frontend/` or `e2e/` references**

Run:
```bash
git -C d:\OmniScribe ls-files | Select-String -Pattern ''^frontend/|^e2e/''
```
Expected: empty output (all matching files staged for removal).

- [ ] **Step 2.5: Continue** (no commit yet - single atomic commit at the end).

### Task 3: Drop `axe-playwright-python` from `pyproject.toml`

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 3.1: Read the `axe-playwright-python` entry in `pyproject.toml`**

Run:
```bash
Get-Content d:\OmniScribe\pyproject.toml | Select-String -Pattern ''axe-playwright''
```
Expected: prints the `[dependency-groups] dev` line referencing `axe-playwright-python` (around line 183). Note the exact line text.

- [ ] **Step 3.2: Remove the entry**

Use `SearchReplace` to remove the entire `axe-playwright-python` line. The line is part of a list of dev deps. Make sure to also remove the surrounding comment block that explains it (lines around `e2e-only and only exercised by e2e/test_ui.py, which is invoked with...`).

Replace the block:

```toml
# e2e-only and only exercised by `e2e/test_ui.py`, which is invoked with
# it for no gain; the e2e/test_ui.py invocation already pulls it via the
# pip `--with axe-playwright-python` install hook.
"axe-playwright-python",
```

with no replacement (just an empty string).

- [ ] **Step 3.3: Verify the entry is gone**

Run:
```bash
Get-Content d:\OmniScribe\pyproject.toml | Select-String -Pattern ''axe-playwright''
```
Expected: empty output.

- [ ] **Step 3.4: Re-sync the lockfile**

Run:
```bash
cd d:\OmniScribe
uv lock
```
Expected: lockfile regenerated without the `axe-playwright-python` entry.

- [ ] **Step 3.5: Verify ruff + mypy still pass**

Run:
```bash
uv run ruff check pyproject.toml
uv run mypy src
```
Expected: ruff and mypy pass.

- [ ] **Step 3.6: Continue** (no commit yet).

### Task 4: Update `.github/workflows/test.yml`

**Files:**
- Modify: `.github/workflows/test.yml`

- [ ] **Step 4.1: Read the workflow file**

Run:
```bash
Get-Content d:\OmniScribe\.github\workflows\test.yml
```
Expected: lists jobs including `frontend` and `e2e`. Note the line ranges for those jobs (and any `pip install axe-playwright-python` or `npm ci` / `npm test` / `npm run build` steps).

- [ ] **Step 4.2: Remove the `frontend` job**

Delete the entire `frontend:` job block. Use `SearchReplace` with the full job block as `original_text` and empty string as `new_text`.

- [ ] **Step 4.3: Remove the `e2e` job**

Same approach as Step 4.2.

- [ ] **Step 4.4: Remove any remaining npm/node steps**

If any other job (e.g., `lint`, `windows-build`) still references npm/node, remove those steps.

- [ ] **Step 4.5: Verify no stale references**

Run:
```bash
Get-Content d:\OmniScribe\.github\workflows\test.yml | Select-String -Pattern ''npm|node|frontend|e2e|axe-playwright|vite''
```
Expected: empty output (or only historical-context comments).

- [ ] **Step 4.6: Continue** (no commit yet).

### Task 5: Update `install.sh`

**Files:**
- Modify: `install.sh`

- [ ] **Step 5.1: Read `install.sh`**

Run:
```bash
Get-Content d:\OmniScribe\install.sh
```
Expected: Bash script with an `npm ci` block around line 81.

- [ ] **Step 5.2: Remove the `npm` block**

Delete the entire block. Use `SearchReplace` with the full block as `original_text` and empty string as `new_text`. The block shape is documented in the spec.

- [ ] **Step 5.3: Verify**

Run:
```bash
Get-Content d:\OmniScribe\install.sh | Select-String -Pattern ''npm|node|frontend|vite''
```
Expected: empty output.

- [ ] **Step 5.4: Continue** (no commit yet).

### Task 6: Update `install.bat`

**Files:**
- Modify: `install.bat`

- [ ] **Step 6.1: Read `install.bat`**

Run:
```bash
Get-Content d:\OmniScribe\install.bat
```
Expected: Windows batch file.

- [ ] **Step 6.2: Remove the `npm` block**

Delete any `call npm ci` / `npm run build` lines plus surrounding `if exist` guards. Use `SearchReplace`.

- [ ] **Step 6.3: Verify**

Run:
```bash
Get-Content d:\OmniScribe\install.bat | Select-String -Pattern ''npm|node|frontend|vite''
```
Expected: empty output.

- [ ] **Step 6.4: Continue** (no commit yet).

### Task 7: Update `install.ps1`

**Files:**
- Modify: `install.ps1`

- [ ] **Step 7.1: Read `install.ps1`**

Run:
```bash
Get-Content d:\OmniScribe\install.ps1
```
Expected: PowerShell script.

- [ ] **Step 7.2: Remove the `npm` block**

Delete the equivalent npm-related lines. Use `SearchReplace`.

- [ ] **Step 7.3: Verify**

Run:
```bash
Get-Content d:\OmniScribe\install.ps1 | Select-String -Pattern ''npm|node|frontend|vite''
```
Expected: empty output.

- [ ] **Step 7.4: Continue** (no commit yet).

### Task 8: Update `start_app.vbs`

**Files:**
- Modify: `start_app.vbs`

- [ ] **Step 8.1: Read `start_app.vbs`**

Run:
```bash
Get-Content d:\OmniScribe\start_app.vbs
```
Expected: VBScript that launches Redis + Celery + uvicorn + Vite child windows.

- [ ] **Step 8.2: Remove the Vite launch block**

Delete the block that creates the Vite dev-server console window. Use `SearchReplace`. If any Vite-specific variables/constants become orphaned, remove those too.

- [ ] **Step 8.3: Verify**

Run:
```bash
Get-Content d:\OmniScribe\start_app.vbs | Select-String -Pattern ''npm|node|frontend|vite|Vite''
```
Expected: empty output.

- [ ] **Step 8.4: Continue** (no commit yet).

### Task 9: Update `Dockerfile`

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 9.1: Read `Dockerfile`**

Run:
```bash
Get-Content d:\OmniScribe\Dockerfile
```
Expected: multi-stage Dockerfile. Check for any `FROM ... node:*`, `npm ci`, `npm run build`, or Vite-related stage.

- [ ] **Step 9.2: If a Node/Vite stage exists, delete it**

Use `SearchReplace` to remove the entire stage block. If no such stage exists, skip this step.

- [ ] **Step 9.3: Verify**

Run:
```bash
Get-Content d:\OmniScribe\Dockerfile | Select-String -Pattern ''node|npm|vite|frontend''
```
Expected: empty output.

- [ ] **Step 9.4: Continue** (no commit yet).

### Task 10: Update `compose.yaml`

**Files:**
- Modify: `compose.yaml`

- [ ] **Step 10.1: Read `compose.yaml`**

Run:
```bash
Get-Content d:\OmniScribe\compose.yaml
```
Expected: docker compose file. Check for any `frontend` service block.

- [ ] **Step 10.2: If a `frontend` service exists, delete it**

Use `SearchReplace` to remove the entire service block. If no `frontend` service exists, skip this step.

- [ ] **Step 10.3: Verify**

Run:
```bash
Get-Content d:\OmniScribe\compose.yaml | Select-String -Pattern ''frontend|node|npm|vite''
```
Expected: empty output.

- [ ] **Step 10.4: Continue** (no commit yet).

### Task 11: Update `.pre-commit-config.yaml`

**Files:**
- Modify: `.pre-commit-config.yaml`

- [ ] **Step 11.1: Read `.pre-commit-config.yaml`**

Run:
```bash
Get-Content d:\OmniScribe\.pre-commit-config.yaml
```
Expected: pre-commit hooks config. Check for any frontend-specific hooks.

- [ ] **Step 11.2: If frontend hooks exist, delete them**

Use `SearchReplace` to remove any repo entries with `language: node`, `npm`, etc. If none exist, skip this step.

- [ ] **Step 11.3: Verify**

Run:
```bash
Get-Content d:\OmniScribe\.pre-commit-config.yaml | Select-String -Pattern ''npm|node|frontend|vite|eslint''
```
Expected: empty output.

- [ ] **Step 11.4: Continue** (no commit yet).

### Task 12: Update `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 12.1: Locate the `frontend/` block**

Run:
```bash
Get-Content d:\OmniScribe\.gitignore | Select-String -Pattern ''frontend''
```
Expected: lines around 199 (`# Frontend build artifacts...`, `frontend/node_modules/`, `frontend/dist/`, `frontend/build/`).

- [ ] **Step 12.2: Remove the `frontend/` block**

Use `SearchReplace` to delete the comment line and the three `frontend/*` lines.

- [ ] **Step 12.3: Verify**

Run:
```bash
Get-Content d:\OmniScribe\.gitignore | Select-String -Pattern ''frontend''
```
Expected: empty output.

- [ ] **Step 12.4: Continue** (no commit yet).

### Task 13: Update `AGENTS.md`

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 13.1: Read the Core Paths and Peripheral Validation tables**

Run:
```bash
Get-Content d:\OmniScribe\AGENTS.md | Select-String -Pattern ''frontend|Svelte|svelte|vite|playwright''
```
Expected: matches include `frontend/src/` in Core Paths (line 73) and `cd frontend && npm run check && npm test && npm run build` in Peripheral Validation.

- [ ] **Step 13.2: Remove the `frontend/src/` row from the Core Paths table**

Use `SearchReplace` to delete that row.

- [ ] **Step 13.3: Remove the `frontend/` peripheral-validation row**

Use `SearchReplace` to delete that entire row including the validation command.

- [ ] **Step 13.4: Search for other frontend/ references**

Run:
```bash
Get-Content d:\OmniScribe\AGENTS.md | Select-String -Pattern ''frontend|Svelte|svelte|vite|playwright|axe-playwright''
```
Expected: empty output (or only documentation links).

- [ ] **Step 13.5: Continue** (no commit yet).

### Task 14: Update `README.md`

**Files:**
- Modify: `README.md`

- [ ] **Step 14.1: Locate Svelte / frontend references**

Run:
```bash
Get-Content d:\OmniScribe\README.md | Select-String -Pattern ''frontend|Svelte|svelte|vite|playwright|web workspace|web UI''
```
Expected: matches for `web workspace`, install snippets, web UI section, etc.

- [ ] **Step 14.2: Replace `web workspace` references with Flutter equivalents**

Use `SearchReplace` to change "web workspace" to "Flutter client" or similar.

- [ ] **Step 14.3: Remove Svelte/Vite/Playwright sections**

Delete any Svelte-specific sections.

- [ ] **Step 14.4: Verify**

Run:
```bash
Get-Content d:\OmniScribe\README.md | Select-String -Pattern ''frontend|Svelte|svelte|vite|playwright|axe-playwright''
```
Expected: empty output.

- [ ] **Step 14.5: Continue** (no commit yet).

### Task 15: Update `ARCHITECTURE.md`

**Files:**
- Modify: `ARCHITECTURE.md`

- [ ] **Step 15.1: Locate Svelte references**

Run:
```bash
Get-Content d:\OmniScribe\ARCHITECTURE.md | Select-String -Pattern ''frontend|Svelte|svelte|vite|playwright|axe-playwright''
```
Expected: many matches - file-ledger entries, pipeline descriptions, historical slice tables.

- [ ] **Step 15.2: Update the file ledger**

Use `SearchReplace` to remove these entries (if present): `frontend/`, `e2e/test_ui.py`, `frontend/src/lib/components/workstation/RightControlDock.svelte`, `frontend/src/lib/components/workstation/BottomProgressDock.svelte`, and any other `frontend/...` file in the ledger sections.

- [ ] **Step 15.3: Remove Svelte-specific historical slice sections**

Find and delete sections like `### 2026-08-12: Full Svelte 5 + TailwindCSS v4 Frontend Migration & Legacy Cleanup`.

- [ ] **Step 15.4: Update the Pipeline diagram**

Replace any Svelte/Vite/web UI mentions with a Flutter client note (Phase A description already in the file).

- [ ] **Step 15.5: Verify**

Run:
```bash
Get-Content d:\OmniScribe\ARCHITECTURE.md | Select-String -Pattern ''frontend|Svelte|svelte|vite|playwright|axe-playwright''
```
Expected: empty output.

- [ ] **Step 15.6: Continue** (no commit yet).

### Task 16: Update `DEPLOYMENT.md`

**Files:**
- Modify: `DEPLOYMENT.md`

- [ ] **Step 16.1: Locate Svelte/Vite references**

Run:
```bash
Get-Content d:\OmniScribe\DEPLOYMENT.md | Select-String -Pattern ''frontend|Svelte|svelte|vite|node|npm''
```
Expected: matches for build pipeline, deployment steps.

- [ ] **Step 16.2: Remove Svelte/Vite build + serve references**

Use `SearchReplace` to replace or delete.

- [ ] **Step 16.3: Verify**

Run:
```bash
Get-Content d:\OmniScribe\DEPLOYMENT.md | Select-String -Pattern ''frontend|Svelte|svelte|vite|node|npm''
```
Expected: empty output.

- [ ] **Step 16.4: Continue** (no commit yet).

### Task 17: Update `SECURITY.md`

**Files:**
- Modify: `SECURITY.md`

- [ ] **Step 17.1: Locate Svelte/XSS references**

Run:
```bash
Get-Content d:\OmniScribe\SECURITY.md | Select-String -Pattern ''frontend|Svelte|svelte|vite''
```
Expected: matches for Svelte-specific XSS threat-model notes.

- [ ] **Step 17.2: Remove Svelte-specific threat-model references**

Delete any sections that only apply to the Svelte UI. Keep generic web/XSS advice that applies to Flutter web too.

- [ ] **Step 17.3: Verify**

Run:
```bash
Get-Content d:\OmniScribe\SECURITY.md | Select-String -Pattern ''frontend|Svelte|svelte|vite''
```
Expected: empty output.

- [ ] **Step 17.4: Continue** (no commit yet).

### Task 18: Update Phase A spec wording

**Files:**
- Modify: `docs/superpowers/specs/2026-08-27-flutter-takeover-phase-a-design.md`

- [ ] **Step 18.1: Locate "reference Svelte UI" mentions**

Run:
```bash
Get-Content d:\OmniScribe\docs\superpowers\specs\2026-08-27-flutter-takeover-phase-a-design.md | Select-String -Pattern ''reference Svelte UI''
```
Expected: 1-2 mentions in the Phase A design rationale.

- [ ] **Step 18.2: Replace wording**

Use `SearchReplace` to change "reference Svelte UI" -> "previous Svelte UI". Do NOT rewrite any other Phase A history.

- [ ] **Step 18.3: Verify**

Run:
```bash
Get-Content d:\OmniScribe\docs\superpowers\specs\2026-08-27-flutter-takeover-phase-a-design.md | Select-String -Pattern ''reference Svelte UI''
```
Expected: empty output.

- [ ] **Step 18.4: Continue** (no commit yet).

## Phase 3 - Verification

### Task 19: Reference sweep + gates

**Files:** none (verification only)

- [ ] **Step 19.1: Reference sweep across the repo**

Run (PowerShell):
```powershell
cd d:\OmniScribe
$excludes = @(''node_modules'', ''.venv'', ''.git'', ''docs\superpowers'', ''client\build'', ''CHANGELOG.md'', ''frontend'')
$include = @(''*.md'',''*.py'',''*.sh'',''*.bat'',''*.ps1'',''*.vbs'',''*.yaml'',''*.yml'',''*.toml'',''*.gitignore'')
Get-ChildItem -Recurse -File -Path . -Include $include |
  Where-Object { -not ($excludes | Where-Object { $_.FullName -like "*\$_\*" }) } |
  Select-String -Pattern ''Svelte|svelte|\.svelte|vite\.config|playwright|axe-playwright|^frontend/|e2e/test_ui\.py|npm ci|npm run''
```
Expected: matches only in the kept-as-is set (CHANGELOG.md, docs/superpowers/plans/, docs/superpowers/specs/, Flutter client comments). If any new match appears outside these expected locations -> fix before committing.

- [ ] **Step 19.2: Re-run the backend fast gate**

Run:
```bash
cd d:\OmniScribe
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow" --ignore=tests/core/lexicon --ignore=tests/core/translate/test_translation_lexicon_integration.py
```
Expected: identical results to Task 1 baseline.

- [ ] **Step 19.3: Re-run the Flutter gate**

Run:
```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\flutter.bat" analyze
& "C:\src\flutter\bin\flutter.bat" test
& "C:\src\flutter\bin\flutter.bat" build web --release
```
Expected: same pass counts as baseline; web bundle produces `client/build/web/index.html`.

- [ ] **Step 19.4: Re-run backend smoke**

Same as Step 1.5. Expected: identical 200 responses.

- [ ] **Step 19.5: Verify all 14 acceptance criteria**

Check each criterion from the spec:

| # | Criterion | Verification |
|---|---|---|
| 1 | `git ls-files frontend/` returns nothing | `git -C d:\OmniScribe ls-files frontend/` |
| 2 | `e2e/test_ui.py` deleted | `Test-Path d:\OmniScribe\e2e\test_ui.py` |
| 3 | `axe-playwright-python` removed from `[dependency-groups] dev` | grep pyproject.toml |
| 4 | `.github/workflows/test.yml` has no `frontend`/`e2e` jobs | grep |
| 5 | install scripts have no `npm` | grep all three |
| 6 | `start_app.vbs` has no Vite window | grep |
| 7 | `Dockerfile` has no node/npm stage | grep |
| 8 | `compose.yaml` has no `frontend` service | grep |
| 9 | `AGENTS.md` peripheral table has no frontend row | grep |
| 10 | README/ARCHITECTURE/DEPLOYMENT/SECURITY have no Svelte/frontend | grep each |
| 11 | `.gitignore` has no `frontend/*` rules | grep |
| 12 | `.pre-commit-config.yaml` has no frontend hooks | grep |
| 13 | Backend + Flutter + web build all green | steps 19.2 + 19.3 |
| 14 | Reference sweep is clean | step 19.1 |

If any criterion fails -> fix the corresponding file(s) before committing.

- [ ] **Step 19.6: Continue** (no commit yet).

## Phase 4 - Single atomic commit

### Task 20: Stage and commit everything

**Files:** all the deletions and edits from Phases 1-3 (no single-file change here)

- [ ] **Step 20.1: Verify `git status` lists all expected changes**

Run:
```bash
git -C d:\OmniScribe status --short
```
Expected: many `D` (deleted) entries for `frontend/` files; `D  e2e/test_ui.py`; `M` (modified) entries for `pyproject.toml`, `uv.lock`, all install scripts, all doc files, the workflow file, `Dockerfile`, `compose.yaml`, `.gitignore`, `.pre-commit-config.yaml`, `start_app.vbs`, and the Phase A spec wording update.

- [ ] **Step 20.2: Stage all changes**

Run:
```bash
git -C d:\OmniScribe add -A
git -C d:\OmniScribe status --short
```
Expected: every change is staged. The unstaged section should be empty.

- [ ] **Step 20.3: Single atomic commit**

Run:
```bash
git -C d:\OmniScribe commit -m "chore: delete Svelte frontend (Phase B takeover)

Per docs/superpowers/specs/2026-08-28-flutter-takeover-phase-b-design.md.

* Delete frontend/ (Svelte 5 + Tailwind v4 + Vite + Vitest workspace).
* Delete e2e/test_ui.py (Playwright smoke against the deleted UI).
* Drop axe-playwright-python from [dependency-groups] dev; regenerate uv.lock.
* Drop frontend + e2e jobs (and any npm/vite steps) from .github/workflows/test.yml.
* Drop npm/vite steps from install.sh / install.bat / install.ps1.
* Drop the Vite dev-server child window from start_app.vbs.
* Drop Vite build stage from Dockerfile (if present) and frontend service from compose.yaml (if present).
* Drop frontend/* rules from .gitignore; drop any frontend-specific hooks from .pre-commit-config.yaml.
* Replace Svelte/Vite/Playwright/npm references in README.md, ARCHITECTURE.md,
  AGENTS.md, DEPLOYMENT.md, SECURITY.md with Flutter client equivalents.
* Reword ''reference Svelte UI'' -> ''previous Svelte UI'' in the Phase A spec.

Historical frontend commits remain in git history (recoverable via
''git checkout <sha>~1 -- frontend/''). No code outside the Svelte
workspace is affected; the Flutter client remains the sole UI surface."
```
Expected: single commit on `main` with all 14 acceptance criteria satisfied.

- [ ] **Step 20.4: Verify the commit**

Run:
```bash
git -C d:\OmniScribe log --oneline -3
git -C d:\OmniScribe status
```
Expected: HEAD shows the new commit; `git status` is clean.

- [ ] **Step 20.5: Done.**

---

## Acceptance criteria (final check)

All 14 criteria from `docs/superpowers/specs/2026-08-28-flutter-takeover-phase-b-design.md` must be verified post-commit. See Task 19.5 for the full checklist.
