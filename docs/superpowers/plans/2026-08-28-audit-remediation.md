# 5-Domain Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve every finding from the 2026-08-28 5-domain audit report across 5 sprints in audit order.

**Architecture:** Domain-by-domain execution. Each sprint fixes one audit domain end-to-end. TDD discipline: regression test first, then minimal fix, then verification. Frequent commits (one task per commit).

**Tech Stack:** Python 3.11+, uv, pytest, ruff, mypy, Flutter (Dart 3.3+), Dio, Riverpod, FastAPI, Cordis plugin harness.

**Source audit:** 2026-08-28 5-Domain Audit Report (see conversation history for full report; 16 Critical, 25 High, 49 Medium, 40 Low/Nit across 5 domains).

---

## Sprint Status

- [ ] **Sprint 1: Core Pipeline (Domain 1)** — see `2026-08-28-audit-remediation-sprint1-core.md` — 26 findings (2C / 4H / 10M / 10L)
- [ ] **Sprint 2: API & Security (Domain 2)** — see `2026-08-28-audit-remediation-sprint2-api.md` — 24 findings (4C / 6H / 6M / 8L)
- [ ] **Sprint 3: Frontend (Domain 3)** — see `2026-08-28-audit-remediation-sprint3-frontend.md` — 27 findings (3C / 6H / 9M / 9L)
- [ ] **Sprint 4: Testing & QA (Domain 4)** — see `2026-08-28-audit-remediation-sprint4-testing.md` — 21 findings (3C / 6H / 7M / 5L)
- [ ] **Sprint 5: DevOps & Config (Domain 5)** — see `2026-08-28-audit-remediation-sprint5-devops.md` — 31 findings (2C / 5H / 16M / 8L)

## Cross-Cutting Concerns

### Testing Discipline (TDD)
- Every fix lands a regression test FIRST.
- Test names: `test_<fix_id>_<behavior>` (e.g. `test_C1_logs_warning_on_malformed_multi_format_response`).
- Bug-class tests should fail BEFORE the fix and pass AFTER.

### Verification Gate (run after every task)
```bash
# Fast gate (run after every task that touches core paths):
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow" -x

# Full gate (run at end of each sprint):
uv run pytest
uv run pytest -m slow
```

### Commit Cadence
- One commit per task. Format: `fix(<domain>): <id> <one-line description>` (e.g. `fix(core): C1 log warning on malformed multi-format LLM response`).

### Environment Notes
- Working on Windows 25H2 with PowerShell — `&&` is not a statement separator; use `;`.
- All shell commands assume `d:\OmniScribe` as workspace root.
- Use `uv run` for all Python invocations.
- `.env` secrets in this workspace are already placeholders per user confirmation — no external rotation needed; just fix the `OCR_API_BASE` URL typo (stray space).

### Pre-existing Constraints (do NOT change)
- Tqdm-patch ordering before `surya.detection` import in `core/aligner.py`.
- Bbox contract `[x0, y0, x1, y1]` in `0..1` until `PDFHandler.embed_structured_text`.
- OCR system-role gating routed through `_resolve_page_system` / `_resolve_crop_system` / `select_system_message`.
- All public Protocol seams (Context, ArtifactStore, JobQueue, StateBackend, ProgressService, ProviderCatalog, HealthService, OCRService) — do not break their contracts.

---

## Out of Scope (call out before fixing)
- Real provider-side credential rotation — `.env` secrets are confirmed placeholders.
- Architecture redesigns (e.g. moving auth from middleware plugin to per-route dependency).
- Changes that conflict with `AGENTS.md` contracts.
- Upgrading pinned dependency versions (e.g. `surya-ocr` upper bound tightening) — these need release planning.

## Verification at Sprint Boundary
- Each sprint ends with: full fast gate + `pytest -m slow` + CHANGELOG entry + report back to user.
- Final cross-sprint verification gate after Sprint 5.