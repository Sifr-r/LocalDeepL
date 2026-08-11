# Deep Refactor Report — Verification Audit Design

> **Date**: 2026-08-11
> **Scope**: Audit every numbered finding (35 total: §1–§5) plus the 7 §6 duplication rows in `deep_refactor_report.md` against the current codebase. The report's executive summary claims 47 findings but the actual numbered count is 35 + 7 duplication rows — this inconsistency itself is a quality issue worth flagging.
> **Method**: 5 parallel subagents (one per domain), static audit only, inline annotation
> **Status**: Approved by user — ready for execution

---

## Purpose

The `deep_refactor_report.md` (downloaded at `c:/Users/rahin/Downloads/deep_refactor_report.md`) catalogues 47 actionable refactor findings across 5 domains of the OmniScribe codebase. Before acting on the prioritized action plan (§7), we want to confirm each finding is accurate — wrong line numbers, refuted claims, or already-fixed issues must be filtered out so the plan reflects reality.

This audit does **not** implement fixes. It only marks findings as confirmed, refuted, or partially confirmed, with brief evidence, inline on the report.

---

## Scope

### In scope
- Verify line numbers cited in each finding against the actual source files
- Verify the claim in each finding matches what the code does
- Flag findings where the recommendation is questionable or over-scoped
- Add inline audit annotations to `deep_refactor_report.md`

### Out of scope
- Implementing any refactor
- Running runtime tests, benchmarks, or profilers
- Verifying recommendations work as written (only that the problem statement is accurate)
- Editing code

---

## Audit Schema

Each finding gets a single-line inline annotation under its `> Recommendation:` block, in the form:

```markdown
> **Audit (2026-08-11)**: ✅/❌/⚠️ <one-sentence evidence> — <one-line note if needed>
```

### Status semantics
- **✅ Confirmed** — finding exists at the cited line and the claim accurately describes what the code does
- **❌ Refuted** — finding is incorrect: wrong line number, claim doesn't match code, or issue doesn't exist
- **⚠️ Partial** — finding exists but is overstated, missing nuance, or the recommendation needs scoping (e.g., would break a public API)

### Counts
A short summary table will be appended at the end of the report:

```markdown
## 9 · Verification Summary (2026-08-11)

| Section | ✅ Confirmed | ⚠️ Partial | ❌ Refuted | Total |
|---------|--------------|------------|------------|-------|
| §1 Memory & Performance | ? | ? | ? | 6 |
| §2 LLM Code Execution | ? | ? | ? | 8 |
| §3 API Layer | ? | ? | ? | 7 |
| §4 Document Processing | ? | ? | ? | 9 |
| §5 Architecture | ? | ? | ? | 5 |
| §6 Duplication rows | ? | ? | ? | 7 |
| **Total** | ? | ? | ? | **42** |
```

---

## Execution Plan

### Step 1 — Dispatch 5 parallel subagents

One subagent per report section, each scoped tightly:

| Domain | Findings |
|---|--------|----------|
| §1 Memory & Performance | 1.1–1.6 (6 findings) |
| §2 LLM Code Execution | 2.1–2.8 (8 findings) |
| §3 API Layer | 3.1–3.7 (7 findings) |
| §4 Document Processing | 4.1–4.9 (9 findings) |
| §5 Architecture | 5.1–5.5 (5 findings) |
| §6 Duplication summary | 7 rows (each references §1–§5 findings) |

**Files in scope per subagent** (passed in each task description):
- **§1**: `core/workflows/hybrid.py`, `core/preprocessing.py`, `core/handwriting_preprocessor.py`, `core/pdf/embedder.py`, `core/pdf/rasterizer.py`
- **§2**: `core/translation.py`, `core/ocr/resilience.py`, `core/ocr/multi_format_client.py`, `core/ocr/processor.py`, `core/grounded/prompted.py`, `api/services/ai.py`
- **§3**: `api/routers/ocr.py`, `api/services/security_middleware.py`, `api/routers/state.py`, `server.py`, `api/schemas/requests.py`
- **§4**: `core/aligner.py`, `core/handwriting_preprocessor.py`, `core/preprocessing.py`, `core/workflows/base.py`, `core/workflows/hybrid.py`, `core/workflows/grounded.py`, `core/processors/table.py`, `core/document.py`, `core/pdf/rasterizer.py`, `core/postprocess.py`
- **§5**: `core/aligner.py`, `api/services/ocr_pipeline_factory.py`, `core/translation_config.py`, `tests/`

Each subagent's task description:
1. Open every cited file and read the cited line range
2. For each finding, return: `{finding_id, status, evidence (file:line + quote), recommendation_valid (yes/no), notes}`
3. Format output as a fenced code block with one JSON object per finding

### Step 2 — Consolidate

I read each subagent's output and:
1. Edit `deep_refactor_report.md` to insert the inline annotation under each finding's `> Recommendation:` block
2. Append the §9 Verification Summary table at the end
3. Surface any ⚠️ Partial findings to the user with a short list of "items needing scoping discussion"

### Step 3 — User review

Present the audit summary, counts, and the list of ⚠️ items. Do not invoke writing-plans until user approves.

---

## Key Design Choices

### Why parallel dispatch
- 5 domains are independent — no shared file dependencies across subagent boundaries
- Estimated ~5× speedup over sequential (file I/O is the bottleneck)
- Each subagent has ~10 findings — fits comfortably in a single context window

### Why inline annotations (not separate doc)
- The user wants the report itself updated
- Inline annotations keep finding + audit adjacent, easier to read
- No risk of two documents drifting apart

### Why quick static audit (no runtime evidence)
- User chose "quick static audit"
- Race conditions and OOM risks are noted but flagged as ⚠️ Partial rather than confirmed by execution
- This keeps the audit fast and reproducible

### Why one subagent per domain (not per file)
- Several findings span multiple files (e.g., §4.2 image decode/encode across `handwriting_preprocessor.py` + `preprocessing.py`)
- Domain-level subagent catches cross-file duplication findings more naturally

---

## Risks

- **Drift risk**: If subagents interpret status semantics differently, results may not be comparable. Mitigated by the explicit schema and the ✅/❌/⚠️ glossary above.
- **Stale findings**: Some findings may already have been partially fixed since the report was generated. Subagents will surface these as ✅ with a "may be in-flight" note.
- **Missing evidence**: For findings whose recommendations would break public APIs (e.g., `BBox` → tuple), the subagent may flag ⚠️ even if the problem statement is correct.

---

## Success Criteria

- All 35 numbered findings + 7 §6 duplication rows have an inline audit annotation
- §9 Verification Summary table is populated and counts add up to 42
- ⚠️ Partial findings are listed back to the user with their rationale
- No code was changed during the audit
