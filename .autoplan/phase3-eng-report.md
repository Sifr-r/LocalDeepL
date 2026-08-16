# Phase 3 — Eng Review Report (FULL DEPTH)

- Generated: 2026-08-15 by /autoplan Phase 3 (plan-eng-review 1.58.5, auto-decision mode)
- Plan: `docs/superpowers/plans/2026-08-14-whitespace-recall.md` (implemented + committed)
- Spec: `docs/superpowers/specs/2026-08-14-whitespace-recall-design.md`
- CEO report: `.autoplan/phase1-ceo-report.md` (D1–D25 settled — NOT re-litigated; open tasks carried forward)
- Test plan artifact: `C:\Users\rahin\.gstack\projects\Sifr-r-OmniScribe\rahin-main-test-plan-20260815-230014.md` (copy: `.autoplan/rahin-main-test-plan-20260815-230014.md`)
- Review mode: READ-ONLY. No source/test/config files modified.

---

## Step 0 — Scope challenge (plan vs. implementation, task-by-task)

### Sub-problem → existing code map

| Sub-problem | Implementation | Status |
|---|---|---|
| Pixel-statistics text-line discovery | `src/omniscribe/core/text_recall.py` (179 lines) — grayscale → Otsu+invert → dilate → `connectedComponentsWithStats` → filters → dedup | DONE |
| Env kill-switch | `WhitespaceRecallOptions.from_env` (text_recall.py:66–75), `OMNISCRIBE_WHITESPACE_RECALL`, disable values `0/false/no/off` case-insensitive, default ON | DONE |
| Layout-stage merge hook | `HybridEngine._detect_layout` merge point (hybrid.py:431–436); `_apply_recall` (hybrid.py:452–496) | DONE |
| Fail-open contract | catch-all `except Exception` (hybrid.py:479) + per-page fallback to Surya boxes | DONE |
| Pipeline wiring | `pipeline.py:25` import; `pipeline.py:101–103` constructor injection in hybrid branch only | DONE |
| Cache-coherent image access | `_decoded_cache` LRU (`_DECODED_CACHE_MAX_ENTRIES = 16`, hybrid.py:58) vs `DETECT_CHUNK_SIZE = 10` (utils.py:55) → same-chunk hits guaranteed; fallback decode + re-put (hybrid.py:471–475) | DONE |
| Unit tests | `tests/test_text_recall.py` (7 tests), `TestHybridWhitespaceRecall` (test_workflows_hybrid.py:186, 3 tests), `TestWhitespaceRecallWiring` (test_pipeline.py:508–521, 2 tests) | DONE |
| GT floor harness (not in plan) | `tests/test_pipeline_recall.py` (182 lines, slow, 3 params) — exists on disk, closest asset to T7 but does NOT isolate booster delta | EXISTS |

### Complexity check

- New module: 1 file, 179 lines, zero new dependencies beyond the already-landed `cv2` (`preprocessing` extra — install parity pinned by test_repo_hygiene.py:83,154).
- Integration surface: exactly ONE merge point (`_detect_layout`), ONE constructor param, ONE pipeline wiring line. Constructor injection mirrors the established `trust_orchestrator` / `page_preprocessor` pattern → low coupling, byte-identical legacy when `recall_booster=None`.
- No new I/O, no new threads, no new config files, no schema changes. Verdict: **scope is right-sized; no over-engineering, no hidden second system.**

### Task-by-task divergence check (plan Tasks 1–4)

| Plan task | Verdict | Divergences |
|---|---|---|
| Task 1: `text_recall.py` module | MATCHES + improvements | (a) Extended docstring documenting P2 text-like-noise limitation (text_recall.py:11–17) — better than plan. (b) Expanded dedup-constant comments (L55–57). (c) **No per-page cap, no straddle guard** — plan's conservative filters shipped as-is; CEO T3 remains open (correct: plan never promised them). |
| Task 2: hybrid integration | MATCHES + improvement | (a) Fallback decode **re-puts** the image into the LRU cache (hybrid.py:471–475) — plan omitted this; implementation is better (avoids double-decode if the page is re-read). (b) **`assert self.recall_booster is not None` at hybrid.py:466** — plan's if-guard semantics not realized; CEO T6 open. (c) No skip when `options.enabled=False` — booster object exists but `supplement` returns `[]`; works but pays per-page `to_thread` hop (T6). |
| Task 3: pipeline wiring | MATCHES exactly | Grounded branch untouched (pipeline.py — injection only in hybrid branch, L101–103). |
| Task 4: tests | MATCHES + additions | (a) EXTRA test `test_overlaps_surya_iou_branch` (test_text_recall.py:62–68) closes CEO gap G2 — landed after CEO report. (b) Cosmetic divergence: `test_detect_layout_merges_recall_boxes_and_resorts` asserts mixed tuple/list `boxes == [(0.1, 0.02, 0.9, 0.05), [0.1, 0.1, 0.9, 0.2]]` where the plan sketched all-lists. Equality across tuple/list is exactly the contract, so this is a *stronger* assertion, not a regression. |
| Not in plan | `tests/test_pipeline_recall.py` GT floor harness exists on disk | Pre-existing/adjacent asset; runs booster-ON pipeline but cannot attribute recall deltas to the booster → T7 must extend it. |

**Divergence verdict: no functional divergence from plan. Two plan-level gaps remain open by design of the CEO phase (T6 if-guard; T3 guards) and are carried as tasks.**

---

## Section 1 — Architecture

### Dependency graph (new components vs. existing)

```
                         env: OMNISCRIBE_WHITESPACE_RECALL
                                      │ (read once, at construction)
                                      ▼
                     WhitespaceRecallOptions.from_env()
                                      │
                                      ▼
                    WhitespaceRecallBooster  ──(lazy import)──> cv2 (preprocessing extra)
                    src/omniscribe/core/text_recall.py
                                      │ supplement(page_pixels, surya_boxes) -> extra boxes
                                      │  grayscale → Otsu+invert → dilate → CC → filters → dedup
                                      ▼
  OCRPipeline (pipeline.py:101-103) ──constructor injection──> HybridEngine(recall_booster=...)
                                      │
                                      ▼
   HybridEngine._detect_layout (hybrid.py:431-436)
        │  per DETECT_CHUNK_SIZE=10 chunk:
        │  Surya boxes ──► _apply_recall (hybrid.py:452-496)
        │       ├── cache hit:  _decoded_cache LRU(16) ── same-chunk invariant holds
        │       ├── cache miss: fallback decode + re-put (hybrid.py:471-475)
        │       ├── exception:  keep Surya boxes, warn (hybrid.py:479)
        │       └── merge + row-major sort (hybrid.py:494)
        ▼
   n_boxes (possibly inflated) ──► _select_dense_pages (dense_threshold=60)
        ▼                            CEO measured 0 flips / 27 pages → no regime change
   dense selection → OCR → DP align → refine → embed  (all UNCHANGED)
```

### Coupling
- Booster knows nothing about HybridEngine; receives raw numpy arrays + Surya boxes, returns boxes. Pure leaf module — **coupling: minimal**.
- HybridEngine depends on an optional injected object (`recall_booster: WhitespaceRecallBooster | None`), same pattern as `trust_orchestrator`/`page_preprocessor`. Removing the feature = delete 3 wiring lines + 1 module.
- One shared hidden dependency: the `_decoded_cache` semantics. The 16 > 10 LRU-vs-chunk invariant is **documented nowhere as a contract** — finding A-1 (minor).

### Scaling
- Per-chunk cost is O(pages × pixels); runs in `asyncio.to_thread`, so the event loop stays responsive. No batching amplification (booster runs per page inside the chunk loop).
- Dense-flip interaction: recall boxes inflate `n_boxes` feeding `dense_threshold=60`. CEO measured 0/27 flips; junk classes (photo blobs) are mostly filtered by aspect/area gates today. Post-T3 junk suppression lowers this risk further. **Scaling: sound, monitor via T2 run summary.**

### Security
- Evaluated in full in Section 6 below. Headline: no new I/O, cv2 receives in-memory numpy arrays (never untrusted file bytes), all allocations bounded by `max_image_dim`.

**Verdict: architecture is sound. Constructor injection at a single merge point with fail-open fallback is exactly the right shape for this feature.**

---

## Section 2 — Code quality (verified, actual results)

### Commands run (2026-08-15)

| Command | Actual result |
|---|---|
| `uv run ruff check src/omniscribe/core/text_recall.py src/omniscribe/core/workflows/hybrid.py src/omniscribe/pipeline.py tests/test_text_recall.py` | **All checks passed!** |
| `uv run ruff format --check` (all 7 radius files incl. test_workflows_hybrid.py, test_pipeline.py, test_pipeline_recall.py) | **7 files already formatted** |
| `uv run mypy src` | **Success: no issues found in 147 source files** |
| `uv run pytest tests/test_text_recall.py tests/test_pipeline.py tests/test_workflows_hybrid.py -v` | **90 passed in 4.78s** |
| `uv run pytest tests/test_aligner.py -v` (AGENTS.md gate — core/workflows/ touched) | **36 passed in 4.16s** |
| `uv run pytest tests/test_repo_hygiene.py -v` | **8 passed** (pins `--extra preprocessing` in Dockerfile L83 + pyproject extra L154) |
| `uv run pytest tests/test_pipeline_recall.py --collect-only` | **3 slow tests collected** |

The plan's lint/type claims are **verified true**.

### DRY
- No duplication found. Dedup geometry (`_overlaps_surya`) lives only in text_recall.py; the pipeline does not re-implement IoU math elsewhere for this feature. Fallback decode reuses `workflows.utils._decode_page_image` (utils.py:81) — correct reuse.

### Naming
- Consistent with repo conventions (`_MIN_*` / `_MAX_*` module constants, underscore-private, snake_case). `recall_booster` param name reads well at call sites.

### Complexity findings (reference: file:line)

| # | Finding | Sev | Fix |
|---|---|---|---|
| CQ-1 | `assert self.recall_booster is not None` (hybrid.py:466) — asserts can be stripped under `python -O`; production correctness must not depend on `__debug__`. | MED | T6: replace with if-guard; also skip `_apply_recall` entirely when `options.enabled` is False |
| CQ-2 | Median min-height uses **all** Surya box heights incl. zero/degenerate ones (text_recall.py:129–133): `median_h = statistics.median(b[3] - b[1] for b in surya_boxes)` — a page of zero-height boxes yields `min_height = 0`, disabling the height floor. (CEO G1.) | MED | T3: filter to positive heights before median; fallback `_FALLBACK_MIN_HEIGHT` on empty |
| CQ-3 | Mixed tuple/list box types after merge (hybrid.py:494): Surya boxes are lists, recall boxes are tuples; both flow downstream. Works (equality/sequence protocol), but heterogeneous. | LOW | Normalize recall boxes to lists in `_apply_recall` |
| CQ-4 | LRU-vs-chunk invariant (16 > 10) is implicit. If someone lowers `DETECT_CHUNK_SIZE`'s sibling or raises chunk size past 16, cache misses silently degrade to fallback decode (still correct, slower). | LOW | A-1: add a comment/assert tying `_DECODED_CACHE_MAX_ENTRIES` to `DETECT_CHUNK_SIZE` |
| CQ-5 | Only debug-level logging in `_apply_recall`; no run-level summary of recall activity → ops cannot tell if the feature is doing anything. | LOW | T2: INFO run summary |

---

## Section 3 — Test review (NEVER SKIP)

Full diagram + gaps live in the test plan artifact; condensed here:

```
[+] text_recall.py
  from_env: default-on [TESTED] | 6 disable values [TESTED] | unrecognized stays on [TESTED]
  supplement:
    disabled → []            [TESTED]
    cv2 missing → [] no raise [TESTED]
    gray.size==0 (0x0 image) [GAP]          ← blank-page test hits count<=1, NOT this branch
    count<=1 (uniform page)  [TESTED]
    filters: height floor    [TESTED via rules page]
             density/height  [TESTED, not isolated]
             aspect-ratio    [GAP]
             max-area >0.25  [GAP]
             max-density >0.75 [GAP]
             zero-height Surya median (G1) [GAP]
    dedup: containment branch [TESTED] | IoU branch [TESTED — closes CEO G2]
           multi-box straddle [GAP → T3]
    per-page cap [GAP → T3] | junk-class fixtures [GAP → T3]

[+] hybrid.py (_apply_recall)
  merge + re-sort        [TESTED]
  booster=None unchanged [TESTED]
  exception → Surya kept [TESTED, single page]
  multi-page partial failure [GAP → G3]
  LRU miss → fallback decode + re-put [GAP → G4]
  disabled-options skip [GAP → T6]

[+] wiring (test_pipeline.py): env default-on + kill-switch [TESTED, 2 tests]

[+] E2E
  recall box receives OCR text in DocumentResult [GAP → T4]  (spec success criterion 2!)
  slow GT floor harness [EXISTS: test_pipeline_recall.py, 3 params, does NOT isolate booster delta → T7]

COVERAGE: 12/26 codepaths tested (fast tier 12/22 = 55%) | GAPS: 14, all mapped to tasks below
```

### pytest results (actual)
- `tests/test_text_recall.py tests/test_pipeline.py tests/test_workflows_hybrid.py` → **90 passed in 4.78s** (includes all 12 recall tests).
- `tests/test_pipeline_recall.py --collect-only` → 3 slow tests; NOT executed (slow tier; runs in nightly).
- AGENTS.md aligner gate satisfied: `tests/test_aligner.py` → 36 passed.

### Verdict
Core fail-open and wiring behavior is well covered. The gap surface is concentrated exactly where the CEO found quality risk (junk classes, calibration) plus spec success criterion 2 (E2E text flow, T4). **Test coverage: PART — sufficient for shipping the fail-open skeleton, insufficient to claim recall benefit until T7.**

---

## Section 4 — Performance

| Concern | Analysis | Verdict |
|---|---|---|
| Per-page supplement cost | grayscale + Otsu + one dilate (3×9 kernel) + CC-with-stats on ≤1024² images ≈ single-digit ms per page; dwarfed by Surya detection (~100s of ms/page) and LLM OCR (seconds). | NEGLIGIBLE |
| asyncio interaction | Runs via `asyncio.to_thread` inside `_apply_recall` — event loop never blocked; consistent with the detect stage's own threading. | OK |
| DETECT_CHUNK_SIZE interaction | Chunk=10 ≤ LRU=16 → every page in a chunk is guaranteed a cache hit for the decoded image; fallback decode exists only as defense-in-depth and re-puts into cache (hybrid.py:471–475). | OK, invariant undocumented (CQ-4) |
| Memory at max_image_dim | 1024×1024: gray 1MB, binary 1MB, dilated 1MB, CC int32 labels 4MB → ~8–10MB transient per page, released per call; sequential per-chunk, not per-page-parallel. | BOUNDED, OK |
| Disabled-state overhead | With `options.enabled=False` the booster object still exists → `_apply_recall` is still awaited per chunk → per-page `to_thread` hop + `supplement` short-circuit (text_recall.py:97–98). Correct but wasteful. | T6 fix: skip `_apply_recall` when disabled → zero overhead |
| Dense-flip cost regime | Recall boxes inflate `n_boxes` vs `dense_threshold=60` → potential flip to dense OCR path (expensive). CEO measured 0 flips / 27 pages; reasoning verified: filters suppress most junk today, and real text lines add only a few boxes per page vs the 60-box threshold. T3 (cap + junk guards) makes this structurally safe. | OK NOW, hardened by T3 |
| Kill-switch ON default | Every default install pays the supplement cost above (~ms/page). Acceptable for a recall feature; env OFF is one line. | ACCEPTED |

---

## Failure modes registry

CRITICAL GAP rule: RESCUED=N AND TEST=N AND (silent OR wrong output).

| # | Failure mode | Trigger | Current rescue | Test? | Flag |
|---|---|---|---|---|---|
| F1 | **Otsu-on-photo junk**: photographic regions binarize into dense "text-like" components that can pass filters (mid-density blobs near text aspect) | Scans with photos/figures | Aspect/area gates catch most, not all; no photo detection | N | **CRITICAL GAP** (CEO row, verified: no rescue, no test, wrong boxes silently emitted) |
| F2 | **Gutter straddle**: dilate bridges a tight 2-column gutter; one wide CC spans both columns → merged junk box covering text from both columns | 2-column layouts, tight gutters | None — no straddle guard | N | **CRITICAL GAP** (CEO row, verified; T3 adds the guard + fixture) |
| F3 | Zero-height Surya boxes → `min_height=0` → height floor disabled → tiny noise components survive | Degenerate detector output on odd pages | None (G1) | N | GAP → T3 (median over positive heights) |
| F4 | No per-page cap → pathological page (dark background, inverted scan) emits dozens of junk boxes, inflating n_boxes toward dense flip | Inverted/dark pages | None | N | GAP → T3 cap (≤10) |
| F5 | Booster exception mid-job | cv2 internal error, corrupt array | Per-page fallback to Surya boxes + warning (hybrid.py:479) | Y (single page) | RESCUED=Y; multi-page partial failure untested (G3) |
| F6 | `OCRCancelled` swallowed by catch-all | User cancels during recall | NOT possible: `OCRCancelled(BaseException)` (base.py:91) bypasses `except Exception` — verified | n/a (by construction) | OK |
| F7 | cv2 not installed | Missing `preprocessing` extra | Lazy import → one-time warning, booster returns [] (text_recall.py:99–109) | Y | RESCUED=Y; install parity pinned by test_repo_hygiene.py |
| F8 | Empty/0×0 image | Corrupt render | `gray.size==0` guard → [] (text_recall.py:112–113) | N (branch uncovered — blank test hits count<=1) | Minor gap → eng-new batch |
| F9 | Cache miss on decoded image | LRU eviction | Fallback decode + re-put (hybrid.py:471–475) | N (G4) | RESCUED=Y, untested |
| F10 | Dense-flip cost explosion | Junk boxes inflate n_boxes ≥ 60 | Filters today; cap post-T3 | N (measured 0 flips) | Watch via T2 run summary |

**Both CEO CRITICAL GAP rows verified against current code — still open; both resolved by T3. No new CRITICAL gaps found.**

---

## Section 5 — Security review

- **New attack surface: essentially none.** The booster consumes numpy arrays already decoded by the existing pipeline — cv2 never parses untrusted file bytes/formats; all parsing risk pre-exists in the PDF/image decode path (out of radius).
- **Resource exhaustion:** all arrays bounded by `max_image_dim` (default 1024); CC component count bounded by pixel count; no loops over untrusted counts without bound except CC output, which is inherently ≤ pixels. Per-page cap (T3) additionally bounds downstream fan-out.
- **No new I/O, no network, no shell, no deserialization of user-controlled formats, no new secrets/env sensitivity** (env var is a boolean switch, no credentials).
- **Cancellation integrity preserved:** `OCRCancelled(BaseException)` cannot be swallowed by the fail-open `except Exception` (base.py:91, verified).

**Verdict: security threats covered — YES.**

## Section 6 — Deployment risk

- **Kill-switch semantics:** `OMNISCRIBE_WHITESPACE_RECALL` default ON; `0/false/no/off` (any case) disables; anything else keeps ON. Explicit-over-clever: unrecognized values fail toward the feature being on, which matches "recall improvement by default". Documented behavior, tested (test_text_recall.py wiring + test_pipeline.py::TestWhitespaceRecallWiring).
- **Install parity:** the `preprocessing` extra / cv2 install fix (CEO D19) is **test-pinned**: test_repo_hygiene.py:83 asserts `--extra preprocessing` in Dockerfile, L154 asserts the pyproject extra. Verified passing (8 passed).
- **Rollback story:** three options, all cheap — (1) set env OFF (no redeploy needed if env injection point restarts pipeline); (2) delete 3 wiring lines (pipeline.py:101–103) → `recall_booster=None` → byte-identical legacy; (3) revert the feature commit. `booster=None` byte-identity is test-covered.
- **Risk:** default-ON ships an uncalibrated booster (CEO measured 0/12 recovery of missed blocks; ≤63% of emitted boxes junk). **Mitigation is procedural: no recall-benefit claims until T7 harness + retune. Deployment risk is manageable because the failure mode is "adds junk boxes on edge layouts", never "breaks the job".**

---

## NOT in scope (explicit)

- Grounded workflow branch (pipeline.py) — untouched by design.
- OCR providers, LLM calls, refine/embed/DP internals — no changes.
- Aligner internals (Surya detection) — consumed read-only.
- UI/daemon/API surface — no changes (Phase 2 design review skipped: no UI scope).
- Unrelated uncommitted working-tree changes — deliberately untouched; review stayed strictly in the feature blast radius.
- Re-litigating CEO decisions D1–D25.

## What already exists (leveraged, not rebuilt)

- `_decoded_cache` LRU + `_decode_page_image` (workflows/utils.py:81) — reused for image access.
- Constructor-injection pattern (`trust_orchestrator`, `page_preprocessor`) — mirrored for `recall_booster`.
- Evaluation module (`compute_report`, `load_ground_truth`) + GT fixtures — reused by test_pipeline_recall.py; T7 extends.
- `scripts/confidence_eval.py` — the A/B knob for ON-vs-OFF calibration (post-T7).
- `preprocessing` extra with cv2 — already landed + hygiene-pinned.
- CHANGELOG entries — already present (T5 is partially done: CHANGELOG yes; .env.example / diagrams no).

---

## Task list (adjudicated, prioritized)

| ID | Task | P | Effort | Files | Source finding |
|---|---|---|---|---|---|
| T7 | GT-backed recall harness: booster ON vs OFF delta over examples/*.pdf + GT fixtures; THEN retune `_MIN_COMPONENT_HEIGHT_PX` / `_MIN_INK_DENSITY` / dedup containment against measured data. **Blocks claiming any recall benefit.** | **P1** | human 1d (calibration judgment) / CC harness scaffolding | tests/test_pipeline_recall.py, scripts/, text_recall.py:45–57 | CEO H3/G2-addendum: 0/12 recovery, ≤63% junk |
| T3 | Straddle guard (reject-first — TASTE-2) + per-page cap ≤10 + median-over-positive-heights + junk-class fixtures (gutter/photo/dark) | **P1** | CC <1d | text_recall.py:129–155, tests/test_text_recall.py | F1–F4 CRITICAL GAPs, CQ-2 |
| T4 | E2E fast test: recall box receives OCR text in `last_document_result` (spec success criterion 2); env-OFF run byte-identical | **P2** | CC ~2h | tests/test_text_recall_integration.py (new) or test_workflows_hybrid.py | Test diagram E2E gap |
| T2 | INFO run summary of recall activity (pages touched, boxes added, boxes dropped) | **P2** | CC ~1h | hybrid.py:452–496 | CQ-5, F10 observability |
| T5 | Docs: `.env.example` entry, ARCHITECTURE.md:13 diagram, AGENTS.md:90–95 diagram + Key Files table (`text_recall.py`) | **P3** | CC ~30m | .env.example, ARCHITECTURE.md, AGENTS.md | Verified stale/missing |
| T6 | Replace `assert` (hybrid.py:466) with if-guard; skip `_apply_recall` when `options.enabled` False | **P3** | CC ~30m | hybrid.py:431,466 + test | CQ-1, disabled-overhead |
| eng-new | 0×0 image test; isolated aspect/area/max-density gate tests; multi-page partial failure (G3); LRU fallback-decode path (G4); normalize recall boxes to lists (CQ-3); LRU/chunk invariant comment (CQ-4) | **P3** | CC ~2h | tests/test_text_recall.py, tests/test_workflows_hybrid.py, hybrid.py:58 | Eng findings CQ-3/4, G3/G4 |
| T9 | Deferred edge test pinning text-like-noise limitation (photo edges / figure borders) | **P3→TODOS** | CC | tests/test_text_recall.py | CEO D24 deferred |

---

## Decision audit trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| 1 | Eng/TASTE-2 | Straddling candidates: REJECT-first (drop), no split | TASTE | 5 (explicit over clever) | Split needs ink-gap analysis = new complexity class; reject is fail-safe and matches filter philosophy; revisit only if T7 data shows split recovers real lines | Split-at-ink-gap; keep-as-is |
| 2 | Eng | T7 is P1 and gates all recall-benefit claims | MECHANICAL | 1, 6 | 0/12 measured recovery → no benefit exists to claim yet; harness first, retune second | Retune blindly; ship claims |
| 3 | Eng | T3 is P1, reject-first straddle guard + cap ≤10 | MECHANICAL | 1, 2 | Two CRITICAL GAP rows live here; in radius, <1d, no infra → auto-approved expansion | Defer to TODOS; cap=15 |
| 4 | Eng | T4 P2 fast-tier E2E (not slow) | MECHANICAL | 3 | Spec success criterion 2 deserves a fast regression, slow harness can't run in CI gate | Slow-only E2E |
| 5 | Eng | T2 P2 INFO summary, not DEBUG | MECHANICAL | 5 | Ops visibility for a default-ON feature must be visible without log-level surgery | DEBUG-only |
| 6 | Eng | T5 P3 docs; CHANGELOG already done, only .env.example + diagrams remain | MECHANICAL | 1 | Verified stale; trivial effort | Skip (docs lie about pipeline) |
| 7 | Eng | T6 P3 (not P1) despite assert smell | MECHANICAL | 3 | Assert only bites under `python -O`; disabled path still correct via supplement short-circuit; pragmatic ordering after P1 quality work | P1 hotfix |
| 8 | Eng | T9 stays deferred to TODOS.md per CEO D24 | MECHANICAL | 3 | Settled in CEO phase; test pins a limitation, adds no protection | Promote to P2 |
| 9 | Eng | eng-new gap batch approved as in-radius expansion | MECHANICAL | 2 | <1 day, 2 test files, no infra → boil-lakes auto-approve | Skip gaps |
| 10 | Eng | Mixed tuple/list box types: normalize to lists (CQ-3) | TASTE | 5 | Homogeneous types downstream beat clever equality; trivial cost | Keep mixed |
| 11 | Ops | Test plan artifact written to .autoplan then copied to .gstack (Write tool sandbox) | MECHANICAL | 6 | Tool cannot write outside workspace; shell copy achieves the required path | Skip artifact path |

**USER CHALLENGES: none.** All decisions auto-resolved by principles; no premise conflicts found with CEO phase.

---

## TODOS.md proposed content (parent writes file — see final message §g)

Collects: E4 per-request knob, E7 provenance tagging, E9 deferred-items-index, text-layer alternative (CEO voice), calibration A/B eval via confidence_eval, T9.

---

## Eng Completion Summary

- Step 0 scope challenge: DONE — sub-problem map, complexity check, task-by-task divergence audit (no functional divergence; 2 open plan-level gaps carried as tasks).
- Section 1 Architecture: DONE — ASCII graph, coupling/scaling/security evaluated. Sound.
- Section 2 Code quality: DONE — ruff/mypy/pytest claims verified with actual commands; 5 findings (CQ-1..5).
- Section 3 Test review: DONE — full codepath diagram (12/26 covered, 14 gaps all mapped), tests re-run green, artifact written to BOTH required locations.
- Section 4 Performance: DONE — per-page cost, threading, memory, disabled overhead, dense-flip regime all evaluated.
- Failure modes registry: DONE — 10 rows; CEO's 2 CRITICAL GAPs verified still open (F1/F2), no new CRITICALs.
- Security review: DONE — no new attack surface; cancellation integrity verified.
- Deployment risk: DONE — kill-switch semantics, install-parity pin verified (8 passed), 3-tier rollback.
- CEO open tasks adjudicated: T2-T7, T9, TASTE-2 all assigned P-levels and effort.
- NOT-in-scope + What-already-exists: DONE.
- Audit trail: 11 rows, 0 USER CHALLENGES.

**Overall eng verdict: implementation is architecturally clean and safe to run (fail-open proven), but the feature is NOT yet proven beneficial — T7 (harness + retune) and T3 (junk/straddle guards) are the P1 gate before any recall claim.**
