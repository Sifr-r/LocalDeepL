# Flutter Takeover — Phase B: Svelte Frontend Deletion

> **For agentic workers:** This spec defines the Phase B cutover. Phase A
> (Flutter↔backend wiring) is complete and committed; Phase B removes the
> Svelte reference UI and its surrounding build infrastructure. Phase C
> (deferred backend feature subsystems: translation, transcription,
> extraction, export, glossary) is a separate scope.

**Date:** 2026-08-28
**Status:** Approved — ready for implementation plan
**Owner:** rahin2uddin

## Context

The Flutter client is now the canonical UI surface (Phase A complete;
see [2026-08-27-flutter-takeover-phase-a-design](file:///d:/OmniScribe/docs/superpowers/specs/2026-08-27-flutter-takeover-phase-a-design.md)).
The Svelte 5 reference UI still ships alongside it as a deprecation
candidate. Phase B removes the Svelte workspace and every launcher,
config, and documentation reference that exists only to support it,
leaving the Flutter client as the sole UI surface and the FastAPI plugin
harness as the sole backend surface.

## Goals

1. Delete the `frontend/` Svelte workspace.
2. Delete the `e2e/test_ui.py` Playwright smoke test.
3. Drop `axe-playwright-python` from Python dev dependencies.
4. Remove the `frontend` and `e2e` jobs from `.github/workflows/test.yml`.
5. Strip Node.js / npm / Vite install steps from
   `install.sh`, `install.bat`, `install.ps1`, `start_app.vbs`.
6. Drop the Vite build stage from `Dockerfile` and any `frontend`
   service block from `compose.yaml`.
7. Remove frontend hooks from `.pre-commit-config.yaml`.
8. Prune `frontend/*` rules from `.gitignore`.
9. Replace Svelte / Vite / Playwright / npm references in
   `README.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DEPLOYMENT.md`,
   `SECURITY.md` with Flutter-equivalent or simply-deleted statements.
10. Land the entire sweep in one atomic commit.

## Non-Goals (kept as-is, intentionally)

- The Python backend plugin harness (Phase A) and the Flutter client.
- Historical commit log entries that mention frontend/ — these describe
  work that was done at the time; rewriting them would falsify history.
- Historical superpowers plans under `docs/superpowers/plans/` and
  `docs/superpowers/specs/` that mention Svelte — they describe the
  design decisions taken when Svelte was the canonical UI.
- `CHANGELOG.md` entries mentioning `frontend/` — historical record.
- Flutter client comments referencing Svelte (e.g.,
  `config_repository.dart` "resilient Svelte fallback",
  `auth_required_banner.dart` "Matches the Svelte `AuthRequiredBanner.svelte`")
  — these explain *why* the code looks the way it does; removing them
  would lose historical rationale.
- The Phase A spec/plan references to "reference Svelte UI" (describing
  the state when Phase A was designed). These become "previous Svelte UI"
  in a small wording update so future readers aren't confused, but the
  Phase A history is not rewritten.
- The `docs/_build/` gitignore rule (added in Phase A follow-up #5).
- The 26 pre-existing `lancedb`-dependent pytest failures in
  `tests/core/lexicon/` and `tests/core/translate/test_translation_lexicon_integration.py`.

## Architectural decisions (recorded)

- **Decomposition:** Single atomic commit. One PR, one reviewable diff.
  Historical frontend commits remain in git history (recoverable via
  `git checkout <sha>~1 -- frontend/`).
- **History rewrite (filter-repo / BFG):** rejected. Rewrites commit
  hashes, breaks tags/branches, requires force-push. Not worth the
  churn.
- **Transitional feature flag (`OMNISCRIBE_LEGACY_WEB_UI`):** rejected.
  AGENTS.md establishes OmniScribe as a dev-only workstation (no
  public users), so the rollback safety isn't buying anything.
- **E2E coverage:** drop Playwright e2e entirely. The Flutter widget
  tests + Flutter integration tests (added in a later slice) replace it.

---

## Deletion scope

### Files / directories deleted

| Path | Reason |
| --- | --- |
| `frontend/` (~85 files) | Svelte 5 + Tailwind v4 + Vite + Vitest UI source |
| `e2e/test_ui.py` | Playwright smoke against the Svelte UI |

### Files modified

| Path | Change |
| --- | --- |
| `pyproject.toml` | Drop `axe-playwright-python` from `[dependency-groups] dev` |
| `.github/workflows/test.yml` | Remove `frontend` and `e2e` jobs; drop `axe-playwright-python` install step |
| `install.sh` | Drop Node.js / npm ci / npm run build |
| `install.bat` | Drop Node.js / npm ci / npm run build |
| `install.ps1` | Drop Node.js / npm ci / npm run build |
| `start_app.vbs` | Drop the Vite dev-server child window; keep Redis/Celery/uvicorn as the boot sequence |
| `Dockerfile` | Drop Vite build stage |
| `compose.yaml` | Drop `frontend` service block if present |
| `.pre-commit-config.yaml` | Drop frontend-specific hooks if any |
| `.gitignore` | Drop `frontend/node_modules/`, `frontend/dist/`, `frontend/build/` |
| `README.md` | Replace `web workspace` / Svelte install references with Flutter client references |
| `ARCHITECTURE.md` | Drop Svelte UI sections; remove `frontend/`, `e2e/test_ui.py`, Vite-related entries from the file ledger |
| `AGENTS.md` | Drop `frontend/` row from the Core Paths table; drop the peripheral-validation row for the frontend |
| `DEPLOYMENT.md` | Drop Svelte/Vite build + serve references |
| `SECURITY.md` | Drop Svelte-specific threat-model references (e.g., XSS via Vite-rendered templates) |

### Files kept as-is (see Non-Goals for rationale)

- `CHANGELOG.md`
- `docs/superpowers/plans/2026-08-24-*.md` and similar historical plans
- `docs/superpowers/specs/2026-08-27-flutter-takeover-phase-a-design.md`
  (with minor wording update: "reference Svelte UI" → "previous Svelte UI")
- Flutter client comments referencing Svelte as the historical rationale

---

## Edge cases1. **AGENTS.md line 73** has the critical peripheral-validation entry
   `cd frontend && npm run check && npm test && npm run build`. The
   *entire* frontend peripheral row must be removed, not just edited,
   since the peripheral no longer exists. Same for the `frontend/` row in
   the Core Paths table above.

2. **`src/omniscribe/static/`** historically held the Vite-built Svelte
   bundle (`vite.config.ts` outputted there). After deletion, this
   directory either stays empty or is removed. FastAPI still serves it
   as a static mount, so verify it has no other content before leaving it
   in place. If empty, leave it (FastAPI static mount + the
   index.html/error.html fixtures in the workspace tests still rely on
   the path existing).

3. **Historical references in `CHANGELOG.md`** are kept as-is (commit
   history preserves them; CHANGELOG entries describe releases).

4. **Historical references in `docs/superpowers/plans/2026-08-24-*.md`**
   are kept as-is (they describe work that was done at the time;
   rewriting would falsify the history).

5. **Flutter client comments mentioning Svelte**
   (`config_repository.dart` line 16 "resilient Svelte fallback";
   `auth_required_banner.dart` line 9 "Matches the Svelte
   `AuthRequiredBanner.svelte`") are kept as-is. These explain *why*
   the code looks the way it does; removing them would lose historical
   rationale.

6. **Spec/plan files** — `2026-08-27-flutter-takeover-phase-a-design.md`
   and `2026-08-27-flutter-takeover-phase-a.md` mention "reference Svelte
   UI". Update wording to "previous Svelte UI" so future readers aren't
   confused. Don't rewrite the Phase A history — just update the
   "what was at the time" framing.

7. **`start_app.vbs`** — currently launches 4 windows (Redis, Celery,
   uvicorn, Vite per AGENTS.md "Windows quick-start"). After Phase B, it
   should drop the Vite window. The remaining 3 windows keep their
   purpose.

8. **`uv.lock` dirty** — Phase B commit regenerates `uv.lock` (removing
   `axe-playwright-python` from dev deps), and that regenerated lockfile
   gets committed alongside.

9. **The recently-fixed `docs/_build/` gitignore rule** (added in Phase A
   follow-up #5) stays — it's correct and orthogonal to Phase B.

10. **`.gitignore` `frontend/*` rules** at lines 199-201 become redundant.
    Remove for cleanliness.

---

## Verification strategy

### Pre-deletion baseline capture

- `git status` (clean working tree expected)
- `git log --oneline | head -1` (current HEAD)
- Backend: `uv run pytest -m "not slow" --ignore=tests/core/lexicon --ignore=tests/core/translate/test_translation_lexicon_integration.py`
  (expect ~1290 passed)
- Flutter: `cd client && flutter test` (expect ~192 passed; +3 from
  follow-up commits may bring it higher)
- Backend fast gate: `ruff check src tests`, `ruff format src tests --check`,
  `mypy src`

### Post-deletion gates (same commands, expect identical results)

- Backend: ruff/mypy/pytest all green (the 26 pre-existing `lancedb`
  failures in `tests/core/lexicon/` and
  `tests/core/translate/test_translation_lexicon_integration.py` should
  be unchanged — Phase B doesn't touch them).
- Flutter: `flutter analyze` clean, all tests pass, web build still
  produces `client/build/web/index.html`.
- Backend smoke: boot `uv run omniscribe-server --port 8000`,
  curl `/api/health` → 200,
  curl `/api/providers/active` with a Phase A payload → 200 (validates
  Phase A regressions haven't been touched).

### Reference sweep (manual grep, must be clean after commit)

```bash
grep -rn --include='*.md' --include='*.py' --include='*.sh' \
  --include='*.bat' --include='*.ps1' --include='*.vbs' \
  --include='*.yaml' --include='*.yml' --include='*.toml' \
  --include='*.gitignore' \
  -E 'Svelte|svelte|\.svelte|vite\.config|playwright|axe-playwright|frontend/|e2e/test_ui\.py|npm ci|npm run' \
  /d/OmniScribe --exclude-dir=node_modules --exclude-dir=.venv \
  --exclude-dir=.git --exclude-dir=docs/superpowers \
  --exclude-dir=client/build
```

- Expected matches: only the "kept as-is" set (historical plans/specs,
  Flutter client comments, CHANGELOG.md). The `docs/superpowers`
  exclusion is intentional because those plans/specs legitimately
  reference Svelte as the reference UI at the time.
- If grep finds ANY new match outside the kept set → fix before commit.

### Acceptance criteria

1. `frontend/` directory deleted; `git ls-files frontend/` returns
   nothing.
2. `e2e/test_ui.py` deleted.
3. `axe-playwright-python` removed from `pyproject.toml [dependency-groups] dev`.
4. `.github/workflows/test.yml` has no `frontend` or `e2e` jobs.
5. `install.sh` / `install.bat` / `install.ps1` have no `npm` references
   (only Python / `uv`).
6. `start_app.vbs` has no Vite window launcher.
7. `Dockerfile` has no `FROM ... node:*` or `npm` stage.
8. `compose.yaml` has no `frontend` service block.
9. `AGENTS.md` peripheral-validation table has no frontend row.
10. `README.md`, `ARCHITECTURE.md`, `DEPLOYMENT.md`, `SECURITY.md` have no
    Svelte / frontend references (Flutter replaces them).
11. `.gitignore` has no `frontend/*` rules.
12. `.pre-commit-config.yaml` has no frontend-specific hooks.
13. Backend fast gate + Flutter gate + Flutter web build all green.
14. Reference sweep is clean (only kept-as-is matches).

---

## See Also

- [2026-08-27-flutter-takeover-phase-a-design](file:///d:/OmniScribe/docs/superpowers/specs/2026-08-27-flutter-takeover-phase-a-design.md) — Phase A spec; Phase B supersedes its "Phase B preview" section.
- [2026-08-27-flutter-takeover-phase-a](file:///d:/OmniScribe/docs/superpowers/plans/2026-08-27-flutter-takeover-phase-a.md) — Phase A plan.
- [AGENTS.md](file:///d:/OmniScribe/AGENTS.md) — contributor guide; the peripheral-validation table is the most consequential Phase B edit.
- [ARCHITECTURE.md](file:///d:/OmniScribe/ARCHITECTURE.md) — file ledger and pipeline section need a refresh.

_Last updated: 2026-08-28_