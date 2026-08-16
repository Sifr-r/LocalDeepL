# CEO Plan Review — Whitespace Recall Booster (Phase 1, /autoplan)

- **Plan:** `docs/superpowers/plans/2026-08-14-whitespace-recall.md`
- **Spec:** `docs/superpowers/specs/2026-08-14-whitespace-recall-design.md` (Approved, approach A)
- **Mode:** SELECTIVE EXPANSION (fixed by /autoplan override — logged as decision D1)
- **Posture:** Adversarial. Plan is ALREADY IMPLEMENTED (commit `da7f49b`); code verified against plan.
- **Interaction model:** No AskUserQuestion available — every judgment auto-decided per the 6
  auto-decision principles and recorded in the Decision Audit Trail (final section).
- **Section 11 (Design):** SKIPPED — no UI scope in this plan.

---

## PRE-REVIEW SYSTEM AUDIT

### Git history (`git log --oneline -30`)

```
da7f49b  Grounded parser            <-- omnibus commit; CONTAINS the whitespace-recall implementation
843f518  typo
22dbaa6  depen update
a64b000  test
136af37  ,.
17eda28  chore: bump pre-commit ruff pin to v0.15.15
9b55a2c  docs: document the quality repair loop and its env seeds
a91e806  style: apply ruff format ...
222c536  fix(api): bounds-check quality loop env seeds ...
ea49a75..42cbb5f  fix(security): Phase 1-5 review fixes (17 issues across 3 commits)
47bb109..06b8088  quality repair loop feature train (HybridEngine + GroundedEngine wiring)
...
```

**Finding (process):** the plan prescribes 4 focused commits (Task 1-3 + triage). The actual
implementation landed inside `da7f49b "Grounded parser"` — an omnibus commit touching 100+
files (frontend, bug-repro PNGs at repo root, `.lint-output.txt`, etc.) with a commit message
unrelated to this feature. Verified via
`git show --stat da7f49b -- src/omniscribe/core/text_recall.py ...` → +400 lines across the 6
plan files. Consequences: the feature cannot be reverted or bisected in isolation, and the
plan's per-task commit discipline was not honored. See M5.

### Implementation status vs plan

| Plan deliverable | Status | Notes |
|---|---|---|
| `src/omniscribe/core/text_recall.py` | IMPLEMENTED (171 lines) | Matches plan code verbatim incl. constants |
| `tests/test_text_recall.py` | IMPLEMENTED (98 lines) | All 6 planned test cases present |
| `HybridEngine.recall_booster` + `_apply_recall` | IMPLEMENTED (hybrid.py L99, L116-119, L431-436, L452-496) | One improvement over plan: fallback decode now re-populates LRU (`self._decoded_put(p_num, image)`, L475) — plan code omits it |
| `OCRPipeline` wiring | IMPLEMENTED (pipeline.py L25, L101-103) | Always injects booster in hybrid branch |
| Wiring tests | IMPLEMENTED (test_pipeline.py L508, test_workflows_hybrid.py L186) | Matches plan |

### In-flight work (context flag)

`git status` shows ~43 modified + several untracked files UNRELATED to this plan:
frontend workstation/websocket work, `state_backend_sqlite.py`, `llm_temperatures.py`,
translation changes, `debug_websocket_frames.py`. Also committed junk in HEAD: three
`bug_repro_*.png` files at repo root, `.lint-output.txt`. Blast-radius review is unaffected,
but the working tree is noisy — a future recall-related change could be accidentally swept
into unrelated commits (already happened once: da7f49b).

### TODO/FIXME/HACK in plan-touched files

`Select-String TODO|FIXME|HACK|XXX` over `text_recall.py`, `workflows/hybrid.py`,
`pipeline.py`, `preprocessing.py`, `aligner.py` → **zero matches**. Clean.

**TODOS.md: does not exist** (Glob over workspace → 0 files). Prime Directive #7
("TODOS.md or it doesn't exist") currently has no home; deferred items from this review
have nowhere canonical to go. Flagged; creation proposed as expansion E9 (auto-decided DEFER
to avoid new-file scope creep — see audit trail D14).

### Recently touched files (30 days)

`pyproject.toml` (12), `.qoder/deep_refactor_report.md` (11), **`src/omniscribe/core/workflows/hybrid.py` (11)**,
`uv.lock` (11), `tests/test_api_safety.py` (10), `tests/test_repair_loop.py` (10),
`ARCHITECTURE.md` (9), `AGENTS.md` (8), `api/routers/ocr.py` (8).

**hybrid.py is the repo's hottest file.** This plan lands its 11th change in 30 days into a
file already carrying the quality-repair loop, decode-cache LRU, and chunked detection.
Recurring churn area → reviewed with extra aggression per retrospective rule.

### Retrospective check

Last 30 commits contain a full review-driven cycle: security Phase 1-5 fix trains
(17 fixes), quality-repair-loop feature train (~12 commits), then formatting/typo cleanup.
No reverts. The repair loop touches the same `_detect_layout`/`_ocr_pages` region this plan
modifies — interaction verified: repair loop runs post-alignment on blocks, recall boxes flow
through alignment first, so recall-origin blocks are eligible for repair re-OCR (a free
quality backstop — noted as a genuine strength, not a finding).

### AGENTS.md conventions check (plan compliance)

| Convention | Plan complies? |
|---|---|
| uv, not pip | YES |
| BBoxes normalized 0..1 | YES (text_recall.py L132-133) |
| pytest-asyncio auto mode | YES (plan Task 2 tests are bare `async def`) |
| mypy explicit annotations in core | YES (all defs annotated) |
| Aligner gate for `core/workflows/` changes | YES (Task 4 Step 1) |
| Full fast gate | YES (Task 4 Step 2) |
| Keep tqdm_patch ordering | N/A |

### Taste calibration

**Style references (well-designed):**
1. `core/workflows/repair.py` — frozen options dataclass, engine-agnostic loop, fail-open
   semantics, byte-identical-when-None injection policy documented in the module docstring.
   The recall plan deliberately copies this pattern — good taste.
2. `core/preprocessing.py` — lazy `import cv2` inside methods with graceful degradation;
   text_recall.py mirrors it exactly.
3. `api/services/security_config.py` `SecuritySettings.from_env()` — the established
   env-seeding pattern; `WhitespaceRecallOptions.from_env()` follows it (disable-value set,
   default-on semantics).

**Anti-patterns to avoid (present in repo):**
1. Omnibus commits with meaningless messages (`da7f49b "Grounded parser"`, `a64b000 "test"`,
   `136af37 ",."`) — destroys bisect/revert.
2. `pages_structured` legacy dict as internal working format (documented tech debt in
   AGENTS.md) — intermediate conversion debt; the plan correctly avoids adding to it.

### Landscape check

Two WebSearches run (results thin but usable): Surya/Docling/Marker recall discussion;
projection-profile text-line segmentation literature.

- **[Layer 1] Tried-and-true:** classical document image analysis — binarize (Otsu/adaptive),
  horizontal projection profiles or morphological dilation + connected components for text-line
  detection. 40 years of literature; exactly what the plan uses. It is the standard *fallback*
  detector when learned layout models miss content.
- **[Layer 2] Search results:** the ecosystem (Marker/Docling/Surya) converges on learned
  layout detection as the *primary* detector; none of them ship a whitespace-masking recall
  backstop — recall gaps like OmniScribe's are a known community complaint (Surya detection
  misses isolated lines on dense/sparse pages). Projection-profile methods remain the accepted
  cheap secondary signal. Nobody exposes "recall booster" as a product knob — OmniScribe's
  default-ON backstop is a differentiator for local-first quality.
- **[Layer 3] First principles:** learned detectors fail on out-of-distribution line geometry
  (very long single lines, sparse pages, atypical margins). Pixel-statistics methods fail in
  the *opposite* regime (noise, photos, rules). The two failure modes are anti-correlated, so
  a conservative pixel-statistics second opinion is theoretically sound. Where conventional
  wisdom may be wrong: the assumption that *conservative filters alone* prevent junk — filters
  tuned on clean digital PDFs are blind to straddling (one blob spanning two columns) and
  photographic ink, which are precisely the cases Surya also struggles with. Feeds F1/H2.

---

## STEP 0A — PREMISE CHALLENGE

| # | Premise | Verdict | Evidence / challenge |
|---|---------|---------|----------------------|
| P1 | Missed Surya boxes are a real recall problem (lost text on dense pages, mis-placed text on sparse pages) | **VALID** | Spec states observed failures; `bug_repro_*.png` artifacts in HEAD corroborate real incidents. Caveat: frequency is unquantified — no baseline metric exists (ties to M1). |
| P2 | Whitespace masking finds what Surya misses | **ASSUMED** | True for crisp digital pages where ink/whitespace contrast is binary. On scans, low-contrast or gray-background pages Otsu picks poor thresholds; on dark-mode/inverted pages the "whitespace" model inverts. No test covers non-white backgrounds. |
| P3 | Default-ON is safe | **CHALLENGED** | Three problems: (a) junk-box blast radius lands in every user's output with no per-request opt-out (env only, read at pipeline construction); (b) recall boxes count toward `dense_threshold` and can flip sparse pages to per-box OCR — a cost/latency regime change (M2); (c) in every shipped install path the cv2 dependency is ABSENT, so "default ON" is actually "default silently OFF" in Docker/one-click installs (H1). A default that differs by install path is not a default. |
| P4 | Conservative filters won't add junk boxes | **ASSUMED** | Filters are heuristics tuned on synthetic dashed-line fixtures. Two untested failure classes: gutter-straddling blobs (aspect + density pass, dedup misses — each Surya box covers <50%) and photographic/figure regions with mid-range Otsu density. See H2. |
| P5 | Byte-identical-OFF behavior is achievable | **VALID** | Verified in code: `supplement` short-circuits before any cv2 work when `enabled=False` (text_recall.py L89-90); `recall_booster=None` keeps engine byte-identical (hybrid.py L431 guard); tests pin both (`test_disabled_options_return_no_boxes`, `test_detect_layout_unchanged_without_booster`, kill-switch wiring tests). One residue: disabled booster still costs a per-page `_apply_recall` pass (L3) — output identical, CPU not zero. |
| P6 | cv2/numpy availability where the feature runs | **CHALLENGED** | `opencv-python-headless` lives in the `preprocessing` extra (pyproject.toml L47-50). Dockerfile installs `web + async-translation`; install.ps1/Makefile install `web`. **No shipping path installs `preprocessing`.** numpy is a core dep, cv2 is not. The one-time warning (L96-99) is the only signal. |

**Premise gate verdict:** P3 and P6 are the load-bearing challenges. Neither blocks the plan
(bias toward action), but both produce mandatory tasks (T1, T3/T4) and both are flagged to the
user premise gate in the final message.

## STEP 0B — EXISTING CODE LEVERAGE MAP

| Sub-problem | Existing code | Plan reuses it? |
|---|---|---|
| Page binarization | `OCRProcessor._apply_adaptive_threshold` (core/ocr/processor.py L182-184, adaptive threshold for OCR input); `LocalPagePreprocessor` (core/preprocessing.py, cv2-based deskew/contrast) | NO — and correctly so: those binarize for OCR *quality*, not ink/whitespace *segmentation*. Otsu-invert inside the booster is purpose-built; no DRY violation. |
| Layout detection | `HybridAligner.get_detected_boxes_batch` (core/aligner.py L42-86) | YES — recall runs per chunk right after it and merges into its output. |
| Decoded page image | `_decoded_cache` LRU + `_decoded_get/_decoded_put` (hybrid.py L56-58, L129-136), populated by `_decode_chunk_bytes` | YES — same-chunk cache hit is the fast path; fallback decode covers eviction. |
| Crop extraction for extra boxes | `crop_for_ocr_from_image` (utils/image.py L14-20, 0.005 padding + blank-region detection) | YES — zero changes; recall boxes ride the existing per-box path. |
| Dense selection | `_select_dense_pages` (hybrid.py L498-514) | YES (passive) — recall boxes inflate `n_boxes`; intentional per spec, but carries M2. |
| DP alignment | `HybridAligner.align_text` (aligner.py L88+) | YES (passive) — extra boxes give the DP more anchors; fixes sparse-page mis-placement. |
| Env-seeding pattern | `SecuritySettings.from_env`, quality-loop env seeds (`OMNISCRIBE_QUALITY_LOOP` etc.) | YES — `WhitespaceRecallOptions.from_env` matches house style. |
| Lazy optional cv2 | `core/preprocessing.py` lazy imports | YES — mirrored exactly (plan even documents the RUF100 nuance). |

Nothing is rebuilt. Leverage score: excellent.

## STEP 0C — DREAM STATE

```
  CURRENT STATE                       THIS PLAN                          12-MONTH IDEAL
  ┌───────────────────────┐   ┌──────────────────────────────┐   ┌──────────────────────────────────┐
  │ Surya = ONLY box      │   │ Surya + whitespace-masking    │   │ Multi-signal box discovery:     │
  │ source. Missed line = │──▶│ recall backstop, default-ON,  │──▶│ learned detection + pixel-stats │
  │ silent text loss      │   │ fail-open, env kill-switch.   │   │ recall + projection profiles,   │
  │ (dense) or DP glue    │   │ Conservative filters + dedup. │   │ each signal scored; boxes carry │
  │ (sparse). Invisible   │   │ Invisible to users; no metric │   │ provenance; per-request toggle; │
  │ failure, no metric.   │   │ of how much it rescues.       │   │ recall measured per-run and fed │
  │                       │   │                               │   │ to calibration (confidence_eval); │
  │                       │   │                               │   │ zero junk boxes, straddle-safe.   │
  └───────────────────────┘   └──────────────────────────────┘   └──────────────────────────────────┘
```

Direction: toward the ideal (adds a second independent signal at the right pipeline point).
Gap to ideal: no provenance tagging on recall boxes, no measurement, no straddle safety (H2).

## STEP 0C-bis — IMPLEMENTATION ALTERNATIVES (mandatory)

```
APPROACH A: Secondary whitespace-masking recall pass (THE PLAN — implemented)
  Summary: Post-Surya pixel-statistics discovery; merge conservative line candidates
           before dense selection/OCR/DP. Fail-open, kill-switch.
  Effort:  S-M (done: +400 LOC incl. tests)
  Risk:    Med (junk boxes, dense-threshold flip — H2/M2)
  Pros:    - Independent signal; anti-correlated failures with Surya (Layer 3)
           - Zero changes downstream (crop/OCR/DP/refine all ride through)
           - Fail-open + env kill-switch = trivial rollback
  Cons:    - Heuristic filters; no calibration data
           - Adds CPU per page (grayscale+Otsu+dilate+CC ~tens of ms)
  Reuses:  decode LRU, crop_for_ocr_from_image, DP, dense selection, env-seed pattern

APPROACH B: Lower Surya detection threshold / second Surya pass
  Summary: Re-run DetectionPredictor with relaxed confidence; union boxes.
  Effort:  S (if Surya exposes the knob) to M (0.17.x API is not wired for it —
           aligner.py constructs DetectionPredictor() with defaults only)
  Risk:    High
  Pros:    - Same signal family as primary detector (consistent box semantics)
  Cons:    - Doubles detection inference cost on EVERY page (Surya is the slow local step)
           - More false positives globally, not targeted at missed regions
           - No dedup story: relaxed pass re-emits most existing boxes
  Reuses:  aligner only

APPROACH C: Horizontal projection-profile line segmentation
  Summary: Row ink-histogram valleys → line bands; no morphology.
  Effort:  S
  Risk:    Med-High
  Pros:    - Even simpler than A; no cv2 morphology needed (numpy only)
  Cons:    - Fundamentally single-column: projection across a 2-column page merges
             both columns into every "line" — WORSE straddle behavior than A
           - Band boundaries imprecise → poor crop geometry for per-box OCR
  Reuses:  same downstream as A

APPROACH D: Do nothing / wait for a better Surya release
  Summary: Accept missed lines; upgrade surya-ocr when upstream improves.
  Effort:  zero
  Risk:    product quality stagnation
  Pros:    - No risk, no maintenance
  Cons:    - Pain is real and user-visible (P1 VALID); upstream timeline unknown;
             surrendering a differentiator (local-first quality)
  Reuses:  n/a
```

**RECOMMENDATION: Approach A** — it is the only alternative that adds an independent signal,
reuses the entire downstream pipeline, and is reversible with one env var. Spec already
approved A; the comparison confirms it. **Not a TASTE decision** — B is strictly dominated
(cost ↑, precision ↓), C is dominated on multi-column documents, D ignores a validated pain.

## STEP 0D — SELECTIVE EXPANSION ANALYSIS

### HOLD-SCOPE analysis first

1. **Complexity check:** plan touches 3 source files + 3 test files (6 total, ≤ 8 OK);
   introduces 2 new classes in ONE new module (`WhitespaceRecallOptions`,
   `WhitespaceRecallBooster`) — at the 2-new-class threshold but tightly cohesive. **PASS.**
2. **Minimum-change check:** everything in the plan is load-bearing except Task 4 Step 4's
   conditional commit (verification hygiene, fine). Nothing deferrable inside the stated goal.
   **PASS.**

### Expansion scan

- **10x check:** the 10x version is *measured, provable recall*: every recall box tagged with
  provenance (`source: "whitespace_recall"`), a per-run recall summary surfaced in the job
  metadata/WebSocket, and a calibration harness (`scripts/confidence_eval.py` already exists)
  that scores recall ON vs OFF against the examples/ ground-truth fixtures. Same feature,
  provable. That is E2 + E6' + provenance (E7).
- **Delight opportunities (≥5):**
  1. Run summary log line "whitespace recall recovered N line(s) across M page(s)".
  2. `.env.example` documents `OMNISCRIBE_WHITESPACE_RECALL` (discoverability).
  3. ARCHITECTURE.md pipeline diagram updated (readers see the real pipeline).
  4. Recall boxes participate in the repair loop automatically — document that synergy.
  5. Straddle-safe candidate splitting (two-column pages stop being a junk source).
  6. CHANGELOG entry — users learn the feature exists.
- **Platform potential:** a `BoxSource` provenance field would let future detectors
  (projection profiles, a second model) plug into the same merge/dedup machinery — the
  booster becomes the first plugin in a detector-fusion platform. Deferred (E7) — real but
  premature for one plugin.

### Cherry-pick ceremony (auto-decided; principles in audit trail)

| # | Candidate | Effort | Risk | Decision | Rationale / Principle |
|---|-----------|--------|------|----------|----------------------|
| E1 | Add `preprocessing` extra to Dockerfile, install.ps1, Makefile so default-ON is real in shipped installs | S | Low | **ADD** | P1-completeness + P2 blast radius (3 deploy files, <1 day, no new infra). Without it the feature is vaporware in Docker. |
| E2 | Run-level recall summary (info log: boxes added / pages affected) | S | Low | **ADD** | P1 completeness; "observability is scope". Impossible to validate success criteria otherwise. |
| E3 | Straddle guard: reject/split candidates significantly overlapping ≥2 Surya boxes | M | Med | **ADD** | Fixes H2 (junk→garbage OCR text in output). P1 + P5 (explicit guard > clever filter tuning). Algorithm choice flagged TASTE. |
| E4 | Per-request form field / runtime setting (mirror quality_loop pattern) | M | Med | **DEFER → TODOS** | Spec explicitly defers v1 knobs; touches schemas+routers+frontend (>5 files). TASTE flag: reasonable people could disagree on env-only vs per-request. |
| E5 | End-to-end test: recall box receives OCR text in final DocumentResult (success criterion 2) | S | Low | **ADD** | P1 completeness; currently zero automated coverage of the feature's headline promise. |
| E6 | Docs: ARCHITECTURE.md diagram, AGENTS.md pipeline block, `.env.example`, CHANGELOG | S | Low | **ADD** | "Diagram maintenance is part of the change" (engineering preference); ARCHITECTURE.md L13 diagram is now stale. |
| E7 | Box provenance field (`source` tag on recall boxes) as detector-fusion platform seed | M | Med | **DEFER → TODOS** | P4 DRY/platform: touches Document model + downstream consumers (>5 files); one plugin does not justify the abstraction yet. |
| E8 | Expose filter constants via options for a calibration script | S | Low | **SKIP** | P4/P5: spec explicitly says constants are not user-facing knobs; YAGNI until calibration data exists. |
| E9 | Create TODOS.md (no deferral home exists in repo) | S | None | **DEFER (noted)** | Meta-item; autoplan parent owns repo-hygiene decisions. Deferred items above are recorded in this report meanwhile. |

**Accepted into scope for remaining sections:** E1, E2, E3, E5, E6.
**Deferred:** E4, E7, E9. **Skipped:** E8.

## STEP 0E — TEMPORAL INTERROGATION

(Human-hour scale; CC scale ≈ 10-20x faster — decisions identical.)

- **HOUR 1 (foundations):** Where does the image come from? Plan resolves it (decode LRU +
  fallback). Residual: implementer must know `_decoded_cache` max=16 vs `DETECT_CHUNK_SIZE=10`
  — same-chunk hits are guaranteed; the plan never states this invariant. *Resolve now: state
  the cache-size ≥ chunk-size invariant in the plan.* (Not currently documented anywhere.)
- **HOUR 2-3 (core logic):** Filter tuning ambiguity — what is "a legitimate text region"?
  Plan Task 4 Step 3 gives a triage rule (good). Unresolved: multi-column behavior (the plan
  is silent on straddling) → surfaced as E3/H2.
- **HOUR 4-5 (integration):** Surprise: recall boxes can flip a sparse page past
  `dense_threshold=60` → page suddenly takes per-box OCR (many VLM calls). Spec says
  intentional; plan never quantifies or bounds it. *Resolve now: cap recall boxes per page
  (e.g. ≤10) — added as part of E3 scope.* Second surprise: Docker has no cv2.
- **HOUR 6+ (polish/tests):** Implementer wishes there were an end-to-end test for success
  criterion 2 (E5) and a run summary to eyeball (E2). Both accepted.

## STEP 0F — MODE

**SELECTIVE EXPANSION** — fixed by /autoplan override; consistent with the context-dependent
default for "feature enhancement on existing system". Approach A (implemented) confirmed as the
active approach under this mode. Logged as D1.

---

## SECTION 1 — ARCHITECTURE REVIEW

### System architecture (required diagram)

```
                          OCRPipeline.__init__  (pipeline.py L92-104)
                          constructs WhitespaceRecallBooster(from_env()) — ALWAYS, hybrid branch
                                          │
                                          ▼
 PDF/image ──▶ raster ──▶ HybridEngine._detect_layout (hybrid.py L404-450)
                           │
                           │  for each chunk of DETECT_CHUNK_SIZE=10 pages:
                           │
                           ├─1─ _decode_chunk_bytes ──▶ _decoded_cache (LRU max 16) ──┐
                           │                                                            │
                           ├─2─ aligner.get_detected_boxes_batch (Surya)                │
                           │                                                            │
                           ├─3─ if recall_booster: _apply_recall  ◀─────── image ───────┘
                           │       │   per page: _decoded_get → (miss: _decode_page_image)
                           │       │   asyncio.to_thread(booster.supplement)
                           │       │   exception → warn + keep Surya boxes (fail-open)
                           │       └─ merge + re-sort (y0,x0)
                           ▼
                 pages_structured {page: [(box, "")]}
                           │
                ┌──────────┴───────────┐
                ▼                      ▼
       _select_dense_pages        sparse: full-page VLM OCR
       (n_boxes counts recall     dense : per-box crop OCR (crop_for_ocr_from_image)
        boxes too — M2)                │
                └──────────┬───────────┘
                           ▼
                 align_text (DP, Needleman-Wunsch) ──▶ refine (incl. repair loop)
                           ▼
                 DocumentResult ──▶ post-process ──▶ embed/output
```

### Coupling (before/after)

Before: `pipeline.py → workflows/hybrid.py → aligner.py`; `text_recall.py` did not exist.
After: `pipeline.py → text_recall.py` (construct) and `hybrid.py → text_recall.py` (type
import + call). New coupling is one-directional and constructor-injected; `text_recall.py`
depends only on `core.document.BBox` + PIL. `GroundedEngine` untouched. **Coupling justified
and minimal** — it follows the established `trust_orchestrator` / `page_preprocessor`
injection pattern.

### Data flow — all four paths (supplement entry point)

- **Happy:** decoded PIL image + Surya boxes → extra boxes merged, re-sorted. Covered by tests.
- **Nil:** `_decoded_get` miss → fallback decode (hybrid.py L471-475); `images_dict[p_num]`
  absent would raise `KeyError` → caught by the per-page `except` → Surya boxes preserved.
  A page absent from `images_dict` would already have failed Surya decode, so this is
  belt-and-braces. OK.
- **Empty:** 0x0 image → `gray.size == 0` → `[]` (text_recall.py L104-105, tested via blank
  page); `surya_boxes == []` → fallback min-height 0.006 path (unit-tested indirectly);
  `count <= 1` (no components) → `[]` (L118-119).
- **Error:** any exception inside `supplement`/decode → `_apply_recall` catches, logs
  warning with page number + exception type, appends original boxes (hybrid.py L479-487).
  Tested (`test_booster_exception_keeps_surya_boxes`).

### State machines

One stateful object: the one-shot `_cv2_warned` flag (False → True on first ImportError,
terminal). No invalid transitions possible. The `_decoded_cache` LRU state machine predates
this plan; recall only reads/writes through the existing accessors. No new stateful objects.

### Scaling

- **10x pages:** supplement is per-page, in-thread, O(pixels); chunk loop already serializes
  detection. Extra cost ≈ 10-50 ms/page CPU. No memory growth beyond the already-bounded LRU.
- **100x:** the real scaling pressure is VLM calls: each recall box on a dense page is one
  extra per-box VLM call. Unbounded boxes/page is unbounded cost — see E3 per-page cap.
- **Single points of failure:** none added. Surya remains the detection SPOF it always was;
  recall is strictly additive and fail-open.

### Security architecture

No new endpoints, params, file paths, or background jobs. No auth-boundary change. (Section 3.)

### Production failure scenario (per integration point)

Integration point = `booster.supplement` in a worker thread. Realistic failure: a photo-heavy
page where Otsu splits on photo texture producing a wide mid-density blob → passes all filters
→ becomes a crop → VLM hallucinates text from photo content → hallucinated text enters
DocumentResult and, via DP, can displace real text on sparse pages. Plan's answer: density/area
filters (insufficient for this class — H2). Partially accounted for; fix in E3 scope.

### Rollback posture

1. **Instant:** set `OMNISCRIBE_WHITESPACE_RECALL=off` — read at pipeline construction
   (per-request factory `api/services/ocr_pipeline_factory.py`), effective for new jobs once
   the process sees the env value (process restart needed to change env).
2. **Code:** `recall_booster=None` for direct engine users already preserved.
3. **Git revert:** should be `git revert` of 4 commits; actually impossible in isolation —
   implementation is fused into omnibus `da7f49b` (M5). Rollback time: env = seconds;
   revert = manual extraction, hours.

### EXPANSION/SELECTIVE additions

- **Beautiful version:** recall boxes carry `source` provenance; the merge point becomes a
  `BoxSource` registry; every detector plugin dedups against all prior sources. Deferred (E7).
- Accepted cherry-picks E1/E2/E3/E5/E6 architectural fit: all bolt-on, no new coupling. E3
  lives inside `text_recall.py` (or `_apply_recall`), E2 is a log line, E5/E6 are tests/docs.
  Clean fit — no revisit needed.

**Section 1 findings:** H2 (straddle/photo junk class), M2 (dense flip), M5 (revert story).
Auto-decided per audit trail; no blocking.

## SECTION 2 — ERROR & RESCUE MAP

### Error & Rescue Registry (required output)

```
METHOD/CODEPATH                     | WHAT CAN GO WRONG                    | EXCEPTION CLASS
------------------------------------|--------------------------------------|-----------------------------
WhitespaceRecallOptions.from_env    | env var unset / garbage value        | (none — defaults enabled)
WhitespaceRecallBooster.supplement  | cv2/numpy not installed              | ImportError
                                    | 0x0 / degenerate image               | (guarded: gray.size == 0)
                                    | cv2.threshold on odd array layout    | cv2.error
                                    | image mode weirdness on convert("L") | ValueError/OSError (PIL)
HybridEngine._apply_recall          | LRU miss + fallback decode failure   | ValueError/OSError (PIL)
                                    | images_dict missing page             | KeyError
                                    | booster raises anything              | Exception (catch-all)
                                    | chunk_pages/chunk_boxes len mismatch | (none — zip strict=False, L4)
OCRPipeline.__init__ (wiring)       | from_env raises (it cannot)          | n/a
```

```
EXCEPTION CLASS        | RESCUED? | RESCUE ACTION                                   | USER SEES
-----------------------|----------|-------------------------------------------------|---------------------------
ImportError (cv2)      | Y        | one-time logger.warning, return []              | Nothing (silent no-op) ← WARNING W1
cv2.error / PIL errors | Y        | per-page catch in _apply_recall → Surya boxes   | Nothing (recall skipped)
KeyError (images_dict) | Y        | same per-page catch                             | Nothing
Exception (catch-all)  | Y        | warn(page, type, msg) + keep Surya boxes        | Nothing
zip length mismatch    | N ← GAP  | strict=False silently truncates (L4)            | Silent box loss ← LOW (parity w/ aligner L58)
```

Rules compliance:
- **Catch-all smell:** `except Exception` at hybrid.py L479. Per Prime Directive 2 this is a
  smell, BUT the fail-open contract ("recall must never fail a job") makes a narrow exception
  list brittle against cv2's wide error surface. Verdict: justified; keep WARNING terse.
  Auto-decided D7 — logged as finding F-L1, severity low, no plan change required.
- **Swallow-and-continue:** the rescue degrades to a defined fallback (Surya-only) and logs
  per page — acceptable per the rules ("degrade gracefully").
- **W1 (one-time cv2 warning):** the warning is the ONLY signal that default-ON is actually
  OFF in shipped installs (H1). One-time + warning-level + no user surface = functionally
  silent at the product level. Fixed by E1 (make the dep present) rather than louder logging.
- **LLM/AI calls:** none introduced by this plan (recall boxes FEED existing VLM calls; their
  failure modes are pre-existing and covered by the ocr/resilience layer).

**Mapped error paths: 9. GAPS: 1 low (strict=False), 1 product-level warning (W1).**

## SECTION 3 — SECURITY & THREAT MODEL

- **Attack surface:** unchanged. No endpoints, no new params, no new file paths, no jobs.
- **Input validation:** the only "input" is the env var (trusted, operator-controlled) and
  page pixels that already passed PIL decode + Surya. Malformed env values fail safe
  (disable requires an explicit value; garbage stays enabled).
- **Authorization / secrets / PII:** none introduced. Document pixels already in-process.
- **Dependency risk:** `opencv-python-headless` newly REQUIRED at runtime for the feature
  (already an optional extra for preprocessing). Track record: OpenCV has periodic parser
  CVEs, but this code feeds cv2 *numpy arrays*, never file bytes — parser surface not reached.
  Low.
- **Injection vectors:** none (no SQL/cmd/template/LLM-prompt construction).
- **Indirect risk:** junk recall boxes send photo/rule crops to the VLM — hallucination
  surface, treated as a quality failure (H2), not a security one; the existing hallucination
  guard (`ocr_quality`) and blank-crop detection apply to recall crops exactly as to Surya crops.
- **Audit logging:** recall activity logged per page at debug/warning — adequate for a
  local-first app; E2 adds the summary.

**Threats: 0 new High/Med. Section verdict: clean.**

## SECTION 4 — DATA FLOW & INTERACTION EDGE CASES

### supplement() data flow (shadow paths annotated)

```
 PIL image ─▶ convert("L") ─▶ Otsu+invert ─▶ dilate ─▶ CC stats ─▶ filters ─▶ dedup ─▶ out
    │             │               │            │           │           │          │
    ▼             ▼               ▼            ▼           ▼           ▼          ▼
 [0x0→[]]    [mode ok]      [threshold     [kernel     [count<=1   [aspect/    [containment
 [disabled→[]]               picks weird    clamped]     →[]]        density/    ≥0.5 / IoU
 [cv2 absent→[]              split on                    [height     area drop]  ≥0.3 drop]
  +1 warn]                   photo bg →                   floor]
                             junk blobs — H2]
```

### surya_boxes edge inputs

- Empty list → fallback height 0.006 (tested via blank/rules pages with `[]`).
- Degenerate Surya box (y1==y0) → `median` of heights could be 0 → `min_height = 0` →
  height filter disabled → junk small boxes can pass. Surya output is clamped/normalized in
  the aligner, so degenerate boxes are unlikely, but the booster does not defend. **Gap G1
  (low): filter non-positive heights before the median.** Added to T3.
- Unsorted/duplicate Surya boxes: irrelevant to dedup correctness (pairwise). OK.

### Interaction edge cases (engine side)

```
INTERACTION / EDGE                          | HANDLED? | HOW
--------------------------------------------|----------|------------------------------------
Booster raises mid-chunk                    | Y        | per-page catch → Surya boxes (tested)
LRU evicted before recall reads it          | Y        | fallback decode + re-put (L471-475)
Kill-switch OFF but booster injected        | Y        | supplement returns [] pre-cv2 (byte-identical output;
                                            |          |  per-page loop still runs — L3 minor)
Page gains boxes crossing dense_threshold   | PARTIAL  | spec-intentional; UNBOUNDED — M2/E3 cap
Multi-column gutter straddle                | N ← GAP  | no guard, no test — H2/E3
Photo/figure mid-density blob               | N ← GAP  | same — H2/E3
Cancellation mid-recall (OCRCancelled)     | Y-ish    | cancel checks live at OCR stage; recall is fast,
                                            |          |  bounded per page — acceptable
Two jobs concurrently on one engine instance| N/A      | engine is per-request via factory
```

**Edge cases mapped: 8. Unhandled: 2 (both H2/E3).**

## SECTION 5 — CODE QUALITY REVIEW

- **Module structure / house fit:** excellent — frozen slotted dataclass, module-level
  commented constants, lazy-import mirroring, docstrings explaining WHY (e.g. the 10px floor
  rationale at text_recall.py L42-45). Matches taste refs (repair.py, preprocessing.py).
- **DRY:** no violations found (0B map). `_clamp` duplicates aligner's `_clamp` in name only
  (different signature: int bounds vs float 0..1) — acceptable; not worth a shared util.
- **Naming:** `supplement`, `WhitespaceRecallBooster`, `_overlaps_surya` — behavior-named, good.
- **Error handling patterns:** see Section 2; the two smells (catch-all, assert) are both
  conscious trade-offs, logged low.
- **Missing edge cases:** G1 (zero-height median), H2 classes — Section 4.
- **Over-engineering:** none. 171 lines, zero abstractions beyond the two classes.
- **Under-engineering:** per-page box cap absent (M2); median robustness (G1).
- **Cyclomatic complexity:** `supplement` body branches ≈ 7 (enabled, import, empty, count,
  height px, aspect, height/area, density) — over the 5-branch guideline but every branch is a
  flat, commented filter gate in a single loop. Auto-decided D8: leave as-is — flat filter
  gates read better here than indirection; explicit over clever cuts both ways. Not blocking.
- `assert self.recall_booster is not None` (hybrid.py L466) — stripped under `python -O`;
  the call site guards with `is not None` anyway. **Low (F-L2).**

**Section 5 issues: 2 low (assert; filter robustness G1 folded into T3).**

## SECTION 6 — TEST REVIEW

```
NEW UX FLOWS:            none (no UI)

NEW DATA FLOWS:
  D1 supplement(image, surya_boxes) -> extra boxes
  D2 _apply_recall per-page merge + re-sort
  D3 OCRPipeline wiring (env -> options -> booster -> engine)

NEW CODEPATHS:
  C1 enabled=False short-circuit
  C2 cv2-missing one-time warn path
  C3 empty-image / no-components path
  C4 filter gates (height px, aspect, height frac, area, density)
  C5 dedup (containment + IoU)
  C6 LRU hit vs fallback decode in _apply_recall
  C7 booster exception path in _apply_recall
  C8 recall boxes entering dense selection / per-box OCR / DP (downstream)

NEW BACKGROUND JOBS / ASYNC:  asyncio.to_thread wrappers only (no new jobs)
NEW INTEGRATIONS / EXTERNAL:  cv2/numpy runtime dep (optional)
NEW ERROR/RESCUE PATHS:       Section 2 registry rows
```

Coverage matrix (plan's tests vs the above):

| Path | Test exists? | Verdict |
|---|---|---|
| D1 happy (missed line recovered) | YES `test_recovers_line_missed_by_surya` | OK |
| C1 disabled | YES `test_disabled_options_return_no_boxes` | OK |
| C2 cv2 missing | YES `test_missing_cv2_is_graceful` | OK |
| C3 blank / rules-only | YES 2 tests | OK |
| C4 density/height filters | PARTIAL (rules test exercises height+density) | OK-ish |
| C5 dedup containment | YES `test_candidate_inside_surya_box_is_dropped` | IoU branch UNTESTED (gap G2, low) |
| D2 merge + re-sort | YES `test_detect_layout_merges_recall_boxes_and_resorts` | OK |
| D2 booster=None byte-identical | YES `test_detect_layout_unchanged_without_booster` | OK |
| C7 exception path | YES `test_booster_exception_keeps_surya_boxes` | single page only — multi-page partial failure UNTESTED (G3) |
| C6 LRU fallback decode | NO test (G4) | low — path is 3 lines, mirrors existing decode util |
| C8 end-to-end (recall box receives OCR in DocumentResult) | NO test (G5) — **success criterion 2 unverified by automation** | E5/T4 |
| H2 classes (straddle, photo, dark bg) | NO tests (G6) | E3/T3 must add |
| from_env matrix | YES (default/disable/unrecognized) | OK |

**Test ambition check:**
- 2am-Friday confidence test: the missing E5 end-to-end test — "booster ON changes output for
  a missed-line page; booster OFF is byte-identical on the same page."
- Hostile QA test: a 2-column page with a tight gutter + a wide photo + a dark-background
  page. None exist today (G6).
- Chaos test: run the full `examples/*.pdf` suite with recall ON and diff against the
  committed ground-truth fixtures (`tests/fixtures/`) — the repo already has the harness
  (`scripts/confidence_eval.py`). Not wired into CI (nightly runs `-m slow` only).

**Pyramid:** healthy (9 unit / 3 integration / 0 E2E → E2E gap is G5).
**Flakiness risk:** none — synthetic deterministic PIL images, no time/randomness/network.
**LLM/prompt check:** no prompt changes; no eval suites required by AGENTS.md patterns.

**Section 6 gaps: 6 (G2-G6 + end-to-end), 4 converted to tasks.**

## SECTION 7 — PERFORMANCE REVIEW

- **N+1 / queries / DB:** none (no persistence layer involvement).
- **Memory:** per-page numpy grayscale (W×H bytes) + binary + dilated ≈ 3×W×H transient,
  freed per page; ≤ ~3MB at 1024×1400. LRU unchanged (bounded 16). OK.
- **Caching:** image decode reused via `_decoded_cache` — implementation even re-puts after
  fallback decode (better than plan). Good.
- **Slow paths (p99 estimates, 1024px page, desktop CPU):**
  1. `cv2.dilate` with 21×6 kernel ≈ 5-15 ms
  2. `connectedComponentsWithStats` ≈ 2-8 ms
  3. grayscale convert + Otsu ≈ 3-10 ms
  Total ≈ 10-35 ms/page, in worker thread, sequential after Surya. Dwarfed by Surya inference
  itself — acceptable.
- **The real cost is downstream:** each survivor on a dense page = one extra per-box VLM call
  (seconds + tokens). Unbounded survivors = unbounded cost → per-page cap (E3/T3).
- **Disabled-state overhead:** `_apply_recall` still iterates pages with to_thread hops when
  `enabled=False` (output identical). A 1-line guard in `_apply_recall` on
  `self.recall_booster.options.enabled` would zero it. Low (F-L3, optional).

**Section 7 issues: 1 medium (cost cap → E3), 1 low (disabled overhead).**

## SECTION 8 — OBSERVABILITY & DEBUGGABILITY REVIEW

- **Logging:** per-page debug on additions (hybrid.py L488-493), per-page warning on failure
  (L479-485), one-time warning on missing cv2 (text_recall.py L96-99). Entry/exit coverage OK.
- **Metrics:** NONE. There is no counter for "boxes recovered per run" — the feature's entire
  value proposition is invisible in production. Default log level (INFO) hides the debug lines.
  **Gap (M1):** add an INFO run summary (accepted as E2/T2):
  `whitespace recall: +N box(es) on M page(s) this run`.
- **Tracing:** single-process; page number is in every line. OK.
- **Alerting/dashboards:** local-first app — N/A; logs are the surface.
- **Debuggability (3-weeks-later bug):** "user reports junk text on page 7" → reconstructable
  ONLY if debug logging was on. With E2's summary at INFO, operator knows recall fired; that's
  the right bar for this product.
- **Runbook:** kill-switch = `OMNISCRIBE_WHITESPACE_RECALL=off` + restart. Document it
  (.env.example — E6/T5).
- **SELECTIVE addition:** "joy to operate" = E2 summary + provenance (E7, deferred).

**Section 8 gaps: 1 (M1 → T2).**

## SECTION 9 — DEPLOYMENT & ROLLOUT REVIEW

- **Migration safety:** none (no schema/state migration).
- **Feature flags:** env kill-switch present, tested. Read at pipeline construction per
  request (factory) — env change still requires process restart; acceptable.
- **Environment parity — CRITICAL GAP (H1):** the feature's runtime dependency
  (`opencv-python-headless`, `preprocessing` extra) is installed by NONE of the shipping
  paths: Dockerfile (`web + async-translation`), install.ps1 (`web`), Makefile (`web`).
  Result: default-ON locally for developers (who ran `uv sync --extra preprocessing` per plan
  Task 1 Step 4 note) but silently OFF in Docker and one-click Windows installs. The spec's
  success criterion "booster ON yields extra boxes" is false for shipped deployments. This is
  the single highest-severity finding. Fix: E1/T1 — add the extra to all three install paths.
  Auto-decided ADD (principles 1+2, blast radius 3 files, <1 day).
- **Rollout order:** single deploy; flag effective immediately for new jobs.
- **Rollback plan:** (1) env OFF + restart — seconds; (2) git revert — BLOCKED by omnibus
  commit da7f49b (M5) unless the feature is extracted first. Noted; not fixable retroactively
  without history surgery (bias toward action: don't).
- **Deploy-time risk window:** N/A (single local instance; no old/new coexistence).
- **Post-deploy verification (first run):** process a dense example PDF; expect the E2 summary
  line (once T2 lands) or debug logs; process same file with env OFF; diff outputs.
- **Smoke tests:** `test_ui.py` (Playwright vs examples/dense.pdf) already covers the happy path.

**Deployment sequence diagram**

```
 deploy new build ─▶ env default: OMNISCRIBE_WHITESPACE_RECALL unset
                     │
                     ├─ cv2 present? ──NO──▶ one warning, no-op (today: ALL shipped installs) ← H1
                     │
                     └─YES─▶ recall active for all hybrid jobs
```

**Rollback flowchart**

```
 junk output reported ─▶ set OMNISCRIBE_WHITESPACE_RECALL=off ─▶ restart ─▶ verify byte-identical
        │                                                                        │
        └─ persists? ─▶ not recall-related (investigate elsewhere)              └─▶ done
```

**Section 9 risks: 1 HIGH (H1/E1), 1 MEDIUM (M5 rollback granularity).**

## SECTION 10 — LONG-TERM TRAJECTORY REVIEW

- **Tech debt introduced:** (a) filter constants tuned by eye with zero calibration data —
  operational debt; the repo HAS the calibration harness pattern (`scripts/calibrate_model.py`,
  `confidence_eval.py`) — a recall on/off A/B eval is the natural next step (deferred);
  (b) docs debt (E6/T5); (c) no TODOS.md home for deferrals (E9).
- **Path dependency:** minimal — injection point is one call site; removing the feature is a
  constructor arg + one guarded block. Good.
- **Knowledge concentration:** module docstring + spec + plan = strong for a new engineer.
  ARCHITECTURE.md omission weakens it (T5).
- **Reversibility: 4/5** — env kill-switch + injection default make behavior reversible in
  seconds; the fifth point is lost to the omnibus commit entanglement.
- **Ecosystem fit:** classical CV fallback beside learned detectors is standard practice
  (Layer 1); optional-dependency posture matches repo conventions.
- **1-year question:** a new engineer reading `text_recall.py` understands it immediately —
  constants are commented with physical rationale. PASS.
- **Phase 2/3:** Phase 2 = calibration A/B + provenance tagging (E7); Phase 3 = detector
  fusion registry. Architecture supports both without rewrites.
- **Retrospective on cherry-picks:** accepted set (E1,E2,E3,E5,E6) is exactly the set that
  turns "implemented" into "shippable"; E7 is load-bearing-adjacent (provenance would make
  E2's summary richer) — acceptable to defer since E2 works without it.

---

## REQUIRED OUTPUTS

### NOT in scope (explicitly deferred)

| Item | One-line rationale |
|---|---|
| Per-request / form-field kill-switch (E4) | Spec defers v1 knobs; blast radius >5 files incl. frontend (deferred, TASTE-flagged) |
| Box provenance tagging / detector-fusion registry (E7) | One plugin does not justify the abstraction yet (deferred) |
| Filter-constant calibration harness (E8 + deferred A/B eval) | No calibration data exists; constants are commented heuristics (skipped/deferred) |
| Grounded path recall | Spec: grounded backend emits its own bboxes; no booster needed |
| DP cost constant / dense threshold / refine changes | Spec explicitly out of scope; recall rides existing paths |
| WebSocket frames / API schema for recall | Spec: env var only in v1 |
| TODOS.md creation (E9) | Repo-hygiene decision belongs to user/autoplan parent |
| Projection-profile segmentation (Approach C) | Dominated on multi-column documents |
| Surya threshold tuning (Approach B) | Cost ↑ precision ↓; Surya API not wired for it |

### What already exists (and whether the plan reuses it)

| Existing asset | Reused? |
|---|---|
| `_decoded_cache` LRU + `_decode_chunk_bytes` (hybrid.py) | YES — primary image source |
| `crop_for_ocr_from_image` w/ padding + blank detection (utils/image.py) | YES — zero changes |
| `_select_dense_pages`, `_ocr_per_box`, `align_text`, repair loop | YES — passive downstream |
| Lazy optional cv2 pattern (preprocessing.py) | YES — mirrored |
| `from_env` env-seed pattern (security_config.py, quality-loop seeds) | YES — mirrored |
| `_apply_adaptive_threshold` binarization (ocr/processor.py) | NO — different purpose (OCR quality, not segmentation); no DRY violation |
| `confidence_eval.py` / fixtures A/B harness | NO — opportunity for recall on/off eval (deferred) |

### Dream state delta

Plan moves OmniScribe from "single-signal detection with silent misses" to "dual-signal
detection with fail-open recall". Remaining gap to the 12-month ideal: (1) no measurement of
recall's contribution (E2 closes the logging half; calibration eval still missing),
(2) no provenance on boxes (E7), (3) straddle/photo safety (E3), (4) shipped-install parity
(E1). After T1-T5 land, the delta is cosmetic only.

### Failure Modes Registry (required output)

```
CODEPATH                    | FAILURE MODE                        | RESCUED? | TEST? | USER SEES?              | LOGGED?
----------------------------|-------------------------------------|----------|-------|-------------------------|--------
supplement: cv2 absent      | feature silently inactive           | Y        | Y     | Silent no-op ← H1/W1    | Y (1x warn)
supplement: 0x0 image       | returns []                          | Y        | Y     | Nothing                 | n/a
supplement: Otsu on photo   | junk blob passes filters (H2)       | N ← GAP  | N     | Junk text in output ← BAD | N
supplement: gutter straddle | cross-column blob (H2)              | N ← GAP  | N     | Garbled reading order ← BAD | N
supplement: zero-height     | min_height=0 → junk small boxes (G1)| N ← GAP  | N     | Possible junk box       | N
median on surya boxes       | n/a (pure math)                     | n/a      | n/a   | n/a                     | n/a
_apply_recall: booster raise| per-page fallback to Surya boxes    | Y        | Y     | Nothing                 | Y (warn)
_apply_recall: decode fail  | per-page fallback                   | Y        | N (G4)| Nothing                 | Y (warn)
_apply_recall: KeyError     | per-page fallback                   | Y        | N     | Nothing                 | Y (warn)
_apply_recall: zip mismatch | silent truncation (L4)              | N ← GAP  | N     | Silent box loss         | N
wiring: env garbage value   | stays enabled (fail-safe direction) | Y        | Y     | Nothing                 | n/a
deploy: no preprocessing xtra| default-ON becomes silent-OFF (H1) | N/A      | N     | Feature absent, 1 warning | Y (1x)
```

CRITICAL GAP rule (RESCUED=N AND TEST=N AND USER SEES=Silent): rows "Otsu on photo" and
"gutter straddle" qualify as **CRITICAL GAPS** — unrescued, untested, and user-visible as
wrong output (not silent, but *wrong-and-unattributable*, which is worse for debugging).
Both are addressed by E3/T3. The zip-mismatch row is Silent but likelihood is near-zero
(parity with aligner behavior) — classified low, not critical.

**Failure modes total: 12. CRITICAL GAPS: 2 (both H2 class, fix path E3/T3).**

### Stale Diagram Audit

| Diagram | File | Still accurate? |
|---|---|---|
| Pipeline paths ASCII | AGENTS.md L90-95 | **STALE** — no recall pass shown between Surya detection and dense/sparse split |
| Pipeline diagram | ARCHITECTURE.md L13 | **STALE** — same omission |
| (none in code comments) | text_recall.py / hybrid.py | Module docstrings describe flow accurately; hybrid.py has no pipeline ASCII (missed opportunity, not stale) |

Fix included in E6/T5.

### Scope Expansion Decisions

- Accepted: E1 (install extras), E2 (run summary), E3 (straddle guard + per-page cap), E5 (E2E test), E6 (docs/env/changelog)
- Deferred: E4 (per-request knob), E7 (provenance/platform), E9 (TODOS.md)
- Skipped: E8 (expose filter constants)

## Implementation Tasks

Synthesized from this review's findings. Each task derives from a specific finding above.

- [ ] **T1 (P1, human: ~30min / CC: ~5min)** — deploy — Add `--extra preprocessing` to Dockerfile (L37, L41), install.ps1 (L32), Makefile (L9)
  - Surfaced by: Section 9 — H1 environment parity gap
  - Files: Dockerfile, install.ps1, Makefile
  - Verify: `docker build` + `python -c "import cv2"` inside container; fresh install.ps1 run on a scratch env
- [ ] **T2 (P1, human: ~30min / CC: ~5min)** — observability — Emit INFO run summary of recall activity (boxes added / pages affected) at end of detection or execute()
  - Surfaced by: Section 8 — M1 no metric exists
  - Files: src/omniscribe/core/workflows/hybrid.py
  - Verify: run examples/dense.pdf, assert summary line at INFO; zero-count line when env OFF
- [ ] **T3 (P1, human: ~2h / CC: ~15min)** — text_recall — Straddle/photo guard: reject (or split) candidates significantly overlapping ≥2 Surya boxes; cap recall boxes per page (e.g. 10); filter non-positive heights before median (G1); add tests for gutter-straddle, photo-density, dark background
  - Surfaced by: Section 1/4 — H2 CRITICAL GAP rows; Section 6 — G6; Section 4 — G1
  - Files: src/omniscribe/core/text_recall.py, tests/test_text_recall.py
  - Verify: new tests green + full fast gate; manual check on a 2-column examples page
- [ ] **T4 (P2, human: ~1h / CC: ~10min)** — tests — End-to-end test: recall box receives OCR text in final DocumentResult (booster ON changes output; OFF byte-identical)
  - Surfaced by: Section 6 — G5, spec success criterion 2 unverified
  - Files: tests/test_workflows_hybrid.py (or new tests/test_text_recall_integration.py)
  - Verify: test passes with stubbed VLM; fails when wiring is removed
- [ ] **T5 (P2, human: ~30min / CC: ~5min)** — docs — Update ARCHITECTURE.md L13 diagram + AGENTS.md pipeline block + .env.example (OMNISCRIBE_WHITESPACE_RECALL) + CHANGELOG entry
  - Surfaced by: Stale Diagram Audit; Section 8 runbook; Section 10 docs debt
  - Files: ARCHITECTURE.md, AGENTS.md, .env.example, CHANGELOG.md
  - Verify: diagram matches hybrid.py flow; env var documented with disable values
- [ ] **T6 (P3, human: ~15min / CC: ~2min)** — hybrid — Guard `_apply_recall` skip when `options.enabled` is False (zero disabled-state overhead); replace `assert` with `if ... return` (F-L2)
  - Surfaced by: Section 7 — F-L3; Section 5 — F-L2
  - Files: src/omniscribe/core/workflows/hybrid.py
  - Verify: existing recall tests still pass
- [ ] **T7 (P3, human: ~30min / CC: ~5min)** — tests — IoU dedup branch test (G2) + multi-page partial-failure test (G3)
  - Surfaced by: Section 6 — G2/G3
  - Files: tests/test_text_recall.py, tests/test_workflows_hybrid.py
  - Verify: both new tests pass

### Completion Summary

```
  +====================================================================+
  |            MEGA PLAN REVIEW — COMPLETION SUMMARY                   |
  +====================================================================+
  | Mode selected        | SELECTIVE EXPANSION (autoplan override)     |
  | System Audit         | implemented in omnibus da7f49b; hybrid.py   |
  |                      | 11 commits/30d churn; no TODOS.md; noisy    |
  |                      | unrelated working tree                      |
  | Step 0               | approach A confirmed; 5 expansions accepted |
  | Section 1  (Arch)    | 3 issues (H2, M2, M5)                       |
  | Section 2  (Errors)  | 9 error paths mapped, 1 GAP (+W1)           |
  | Section 3  (Security)| 0 issues, 0 High severity                   |
  | Section 4  (Data/UX) | 8 edge cases mapped, 2 unhandled (H2)       |
  | Section 5  (Quality) | 2 issues (low)                              |
  | Section 6  (Tests)   | diagram produced, 6 gaps                    |
  | Section 7  (Perf)    | 2 issues (1 med cap, 1 low)                 |
  | Section 8  (Observ)  | 1 gap (M1)                                  |
  | Section 9  (Deploy)  | 2 risks (H1 HIGH, M5 MED)                   |
  | Section 10 (Future)  | Reversibility: 4/5, debt items: 3           |
  | Section 11 (Design)  | SKIPPED (no UI scope)                       |
  +--------------------------------------------------------------------+
  | NOT in scope         | written (9 items)                           |
  | What already exists  | written (7 assets, 6 reused)                |
  | Dream state delta    | written                                     |
  | Error/rescue registry| 5 methods, 0 registry-critical gaps         |
  | Failure modes        | 12 total, 2 CRITICAL GAPS (H2 class)        |
  | TODOS.md updates     | 3 items proposed (file does not exist)      |
  | Scope proposals      | 9 proposed, 5 accepted                      |
  | CEO plan             | captured in this report (autoplan mode)     |
  | Outside voice        | skipped (handled by parent /autoplan)       |
  | Lake Score           | 5/5 in-blast-radius recs chose completeness |
  | Diagrams produced    | 6 (system arch, data flow, deploy seq,      |
  |                      |  rollback, dream state, supplement shadows) |
  | Stale diagrams found | 2 (AGENTS.md, ARCHITECTURE.md)              |
  | Unresolved decisions | 2 TASTE flags for final gate (below)        |
  +====================================================================+
```

### Unresolved decisions (flagged to final gate)

**UNRESOLVED DECISIONS:**
- TASTE-1: E4 — env-only kill-switch (ship as-is) vs per-request form field (deferred). Reasonable people could disagree; user should confirm deferral.
- TASTE-2: E3 guard algorithm — reject straddling candidates outright vs split them at ink gaps. Both defensible; recommend reject-first (simpler), split as Phase 2.

---

## DECISION AUDIT TRAIL

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|----------------|-----------|-----------|----------|
| D1 | 0F | Mode = SELECTIVE EXPANSION | MECHANICAL | autoplan override | Fixed by parent; matches "feature enhancement" default | other 3 modes |
| D2 | audit | Flag unrelated uncommitted work as context, do not review it | MECHANICAL | 2 (blast radius boundary) | Outside plan blast radius | reviewing it |
| D3 | 0C-bis | Recommend approach A; not TASTE | MECHANICAL | 3, 4 | B/C/D strictly dominated; spec pre-approved A | B (2nd Surya pass), C (projection profiles), D (do nothing) |
| D4 | 0D | E1 ADD: preprocessing extra in Dockerfile/install.ps1/Makefile | MECHANICAL | 1, 2 | Default-ON feature must actually run in shipped installs; 3 files, S effort | leaving default-OFF-in-Docker |
| D5 | 0D | E2 ADD: INFO run summary | MECHANICAL | 1 | Zero visibility today; observability is scope | silent feature |
| D6 | 0D | E3 ADD: straddle guard + per-page cap + G1 fix | MECHANICAL | 1, 5 | Fixes 2 CRITICAL GAP rows; explicit guard > filter tuning | shipping with junk-box class open |
| D7 | Sec 2 | Accept catch-all `except Exception` in _apply_recall as justified | TASTE | 5, 6 | Fail-open contract vs cv2's wide error surface; degrade+log present | narrow exception list (brittle) |
| D8 | Sec 5 | Leave supplement's ~7 flat filter gates unrefactored | TASTE | 5 | Flat commented gates read better than helper indirection here | extracting `_passes_filters` |
| D9 | 0D | E4 DEFER: per-request knob | TASTE | 2, 6 | >5 files incl. frontend; spec defers; flag to gate | adding now |
| D10 | 0D | E5 ADD: end-to-end recall→OCR test | MECHANICAL | 1 | Spec success criterion 2 has zero automated coverage | trusting unit tests alone |
| D11 | 0D | E6 ADD: docs/.env.example/CHANGELOG | MECHANICAL | 1, 5 | 2 diagrams stale; engineering prefs make diagram upkeep part of change | leaving docs stale |
| D12 | 0D | E7 DEFER: provenance/platform | MECHANICAL | 4, 5 | One plugin ≠ platform; premature abstraction | building registry now |
| D13 | 0D | E8 SKIP: expose filter constants | MECHANICAL | 4, 5 | Spec: constants not user-facing; YAGNI | knobs without data |
| D14 | audit | E9 DEFER: TODOS.md creation | MECHANICAL | 6 | Repo-hygiene call belongs to user; deferrals recorded in this report | creating TODOS.md unprompted |
| D15 | Sec 7 | Disabled-state overhead + assert → optional P3 task T6 | MECHANICAL | 6 | Flag, don't block; trivial fix available | blocking on it |
| D16 | Sec 9 | No history surgery to fix omnibus commit; note only | MECHANICAL | 6 | Rewriting committed history is higher risk than the debt | git rebase/filter |
| D17 | Sec 6 | No CI wiring of examples-diff harness now | MECHANICAL | 6 | Existing nightly `-m slow` covers regressions; harness run manually | new CI job |

**USER CHALLENGES: none** — no premise where both reviewer models would oppose a user-stated direction.

### Top findings (severity-ordered)

| # | Sev | Finding | Fix |
|---|-----|---------|-----|
| H1 | HIGH | `preprocessing` extra absent from Dockerfile/install.ps1/Makefile → default-ON recall is silently OFF in every shipped install path | T1: add `--extra preprocessing` to all three |
| H2 | HIGH (2 CRITICAL GAP rows) | Junk-box classes unguarded & untested: multi-column gutter straddle; photo/figure mid-density blobs → garbled/hallucinated text in output | T3: straddle reject/split + per-page cap + tests |
| M1 | MED | No run-level metric/log of recall activity; feature value invisible; success criteria unverifiable | T2: INFO summary |
| M2 | MED | Recall boxes inflate `n_boxes` → can flip sparse page past dense_threshold=60 into per-box OCR (cost/latency regime change), unbounded | T3 per-page cap; document in T5 |
| M3 | MED | Spec success criterion 2 (extra box receives OCR in DocumentResult) has no automated test | T4 |
| M4 | MED | Docs stale: ARCHITECTURE.md/AGENTS.md pipeline diagrams omit recall; `.env.example` + CHANGELOG silent | T5 |
| M5 | MED | Implementation squashed into unrelated omnibus commit da7f49b "Grounded parser" — violates plan's 4-commit structure; blocks isolated revert/bisect | process note; no retro fix (D16) |
| L1-L4 | LOW | Catch-all smell (justified), `assert` under -O, disabled-state loop overhead, `zip strict=False` | T6 / noted |

---

# PREMISE GATE OUTCOMES (Phase 1.5 — post-gate addendum)

Gate verdicts from the user: P1 VALID+measure, P2 ASSUMED acceptable+document, P3 CHALLENGED+measure+decide,
P4 ASSUMED+audit filters, P5 VALID, P6 CHALLENGED+resolve+implement. All addressed below.

## G1. P1 measurement — how often does Surya actually miss text lines?

Method: 5 example PDFs, 27 pages, 910 GT text blocks (`omniscribe.evaluation.load_ground_truth`,
axis-order auto-detect), dpi=200/max_dim=1024 rasterization, 40×40 grid-point coverage.
Missed = GT block with <50% of sample points inside any Surya box. Script: `.autoplan/measure_p1.py`,
raw output `.autoplan/measure_p1_out.txt`.

| file | pages | blocks | missed | Surya block-recall |
|------|-------|--------|--------|--------------------|
| dense.pdf | 3 | 365 | 4 | 99% |
| digital.pdf | 1 | 16 | 4 | **75%** |
| handwritten.pdf | 1 | 14 | 0 | 100% |
| hybrid.pdf | 1 | 38 | 0 | 100% |
| notes.pdf | 21 | 477 | 4 | 99% |
| **TOTAL** | **27** | **910** | **12** | **99%** |

Verdict: P1 VALID but the miss problem is **concentrated, not uniform**. Whole-block misses are ~1.3%
overall, but digital.pdf (a fill-in form) loses 4/16 blocks — all form-fill lines
(`Student Name (Last, First): ____`, `Student e-mail address: ____`, `Student G#: ____`, and a two-line
faculty-name prompt). notes.pdf misses are table-markup GT blocks (`<tr>`, `</tr> </table>`), i.e. GT noise,
not real misses. dense.pdf misses are tiny fragments (`(100% Organic)`, `p q`, `p m`).
The plan's premise holds specifically for **thin, sparse-ink lines on forms** — exactly the class the
whitespace approach targets.

## G2. P4 audit — do the filters exclude rules/figures/photos? Do the extras help at all?

Same run measured every booster extra box against GT:

**TOTAL: extra=27, recovered=0, junk=17 (63%).**

| file | extra | recovered | junk | worst page |
|------|-------|-----------|------|------------|
| dense.pdf | 6 | 0 | 2 | — |
| digital.pdf | 5 | 0 | 1 | extras are header band + 3 paragraph-sized blobs GT doesn't annotate |
| notes.pdf | 16 | 0 | 14 | p15: 6 extras / 5 junk |

Two honest caveats on "junk": (1) GT fixtures are partial — digital.pdf GT annotates 16 blocks while
Surya itself returns 35 boxes, so some "junk" extras are likely real text GT never labeled; the 63% figure
is an upper bound. (2) Even granting that, **recovered = 0/12 is unambiguous**: on this corpus the booster
adds boxes but recovers not a single missed block.

### Root cause (probe `.autoplan/probe_missed.py`): the booster SEES the missed lines; the filters kill them

digital.pdf p0, median Surya height 0.0137 → `min_height` 0.0062, kernel (16,6), 24 components:

| missed block | component found | verdict |
|--------------|-----------------|---------|
| label halves ("Student Name…", etc.) | comps #4/#6/#8, 16-19 px tall, density 0.15-0.17 | PASS all filters → **rejected by dedup** (`_overlaps_surya` containment ≥0.5: Surya boxes cover the label text but not the blank rule) |
| blank rule runs after each label | comps #5/#7/#9, 285×6 px | **`_MIN_COMPONENT_HEIGHT_PX=10` rejects** (6 px) + `min_height` rejects (0.0059 < 0.0062) |
| two-line faculty prompt | comp #10, 514×38 px | **ink density 0.08 < `_MIN_INK_DENSITY=0.10`** rejects |

So H2's concern is confirmed with mechanism: the filter set is tuned to reject precisely the target class
(thin sparse-ink lines), while admitting paragraph-scale blobs and photo/figure regions (notes.pdf p15,
digital.pdf y 0.64-0.90 extras). Straddle guard (T3) still needed, but the dominant defect is filter
miscalibration, not missing guards.

New finding **H3 (HIGH)**: booster filters are miscalibrated — 0/12 recovery, 63% junk ceiling on the
shipped examples corpus. Fix direction (NOT implemented — out of this gate's authorization):
relax `_MIN_COMPONENT_HEIGHT_PX` for high-aspect components, drop `_MIN_INK_DENSITY` to ~0.05,
and make dedup containment width-aware (a candidate 3× wider than the covering Surya box should not
die on containment). Requires a GT-backed regression harness first (T7, new).

## G3. P3 measurement + decision — dense-flip risk, per-request opt-out

Measured flips = `surya ≤ 60 < surya+extra` per page across the corpus: **0 flips on 27 pages**.
Margins: notes.pdf p15 is the closest (70→76, already dense before boost); p20 is 169 boxes;
dense.pdf pages are 146-168. The largest boost on a non-dense page is +6 (p15), and no page sits in
the 55-60 band. M2 (dense-threshold flip) is real in theory, **unobserved in practice** on this corpus.

**DECISION (D18): NO per-request opt-out now.** Rationale: env kill-switch already gives process-level
emergency off; measured flip risk is zero on shipped examples; adding a per-request knob touches
pipeline.py + hybrid.py + API request schema + frontend (>5 files, M effort) for a risk not yet
observed. Re-open if a real document flips. This upgrades D9 from DEFER-with-flag to
DEFER-with-measurement; TASTE-1 from Phase 1 is resolved by data.

## G4. P2 — documented limitation

Booster limitation now documented: it discovers line-shaped ink blobs; it cannot distinguish text from
text-like noise (photo edges, figure borders, filled form rules), and it merges stacked lines when
inter-line gaps fall under the dilation kernel height. Edge test deferred (T9, new; user authorized
"add an edge test later").

## G5. P6 — install-path decision + implementation (DONE)

**DECISION (D19): ADD `preprocessing` to every install path.** Alternatives weighed: (a) add everywhere
[default-ON feature must actually run; opencv-python-headless is ~40 MB, headless, no system libs];
(b) keep optional + warn [contradicts default-ON contract; every shipped surface would silently
disable the feature]. (a) wins on principles 1, 2, 5. Not TASTE — the default-ON premise forces it.

Implemented (verified: `tests/test_repo_hygiene.py` 8/8 pass; `uv sync --extra web --extra preprocessing --dry-run` resolves clean, lockfile already contains opencv-python-headless):

| file | change |
|------|--------|
| `Dockerfile` L37, L41 | `--extra preprocessing` added to both `uv sync` layers |
| `install.ps1` L32 | `uv sync --extra web --extra preprocessing` |
| `Makefile` L9 + `help` text | `setup` target adds the extra |
| `README.md` L25/L31/L40 | all three quick-start variants include it |
| `AGENTS.md` L9-L10 | quick-start updated |
| `DEPLOYMENT.md` L15, L158 | laptop + async profiles updated (L158 fix also repairs a latent bug: old `uv sync --extra async-translation --extra memory` would have pruned the web deps) |
| `ARCHITECTURE.md` L115 | install.ps1 description updated |
| `tests/test_repo_hygiene.py` | asserts `--extra preprocessing` in Dockerfile + `preprocessing` extra exists in pyproject |
| `CHANGELOG.md` | Unreleased entries for the feature AND the install-path fix (M4 partially closed) |

H1 from Phase 1 is **RESOLVED**.

## Post-gate decision audit trail (continued)

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|----------------|-----------|-----------|----------|
| D18 | gate P3 | No per-request opt-out now; env kill-switch suffices | TASTE | 3, 6 | Measured 0 flips / 27 pages; knob costs >5 files for unobserved risk | per-request knob now |
| D19 | gate P6 | Add `preprocessing` extra to every install path (implemented) | MECHANICAL | 1, 2, 5 | Default-ON feature must run in shipped installs; blast-radius doc fixes included | keep optional + warn |
| D20 | gate P1/P4 | Use `evaluation.load_ground_truth` in measurement script (DRY) | MECHANICAL | 4 | Repo already normalizes mixed GT axis orders; hand-parsing reproduced a bug | manual fixture parsing |
| D21 | gate P4 | Report junk=63% as an upper bound with GT-partiality caveat, recovered=0 as unambiguous | MECHANICAL | 6 | Honest adversarial reporting; don't overclaim junk when GT under-annotates | raw junk% only |
| D22 | gate P4 | Do NOT retune filters in this gate — only root-cause + fix direction (H3, T7) | MECHANICAL | 6 | Gate authorized measure/decide/implement-P6 only; filter retuning needs a regression harness first | ad-hoc constant tweaks |
| D23 | gate P6 | Also fix DEPLOYMENT.md async-profile `uv sync` latent prune bug while touching it | MECHANICAL | 2 | Same file, same line class, <1-line delta | leaving the latent bug |
| D24 | gate P2 | Document limitation in report; defer edge test (T9) | MECHANICAL | 6 | User explicitly authorized "later" | writing the test now |
| D25 | gate P3 | Keep TASTE-1 resolved-by-data; TASTE-2 (reject-vs-split straddle) still open for eng phase | TASTE | 6 | Measurement did not adjudicate split semantics | forcing a choice now |

## Updated open task list (supersedes T1-T7 where noted)

| # | Task | Status |
|---|------|--------|
| T1 | `--extra preprocessing` in all install paths | **DONE** (this gate, D19) |
| T2 | INFO run summary of recall activity | open (eng phase) |
| T3 | Straddle guard + per-page cap + junk-class tests | open; subsumed priority by T7 |
| T4 | E2E test for success criterion 2 | open (eng phase) |
| T5 | Docs: ARCHITECTURE/AGENTS pipeline diagrams, `.env.example` | partially closed (CHANGELOG + install docs done) |
| T6 | `assert` under -O + disabled-state overhead | open (trivial) |
| T7 | **NEW** GT-backed recall regression harness; then retune `_MIN_COMPONENT_HEIGHT_PX` / `_MIN_INK_DENSITY` / dedup containment per G2 root cause (H3) | open — blocks claiming any recall benefit |
| T9 | **NEW** Edge test for text-like-noise limitation (P2) | deferred per user |

*End of Phase 1 CEO report + premise-gate addendum. Scratch artifact under `.autoplan/` (not currently in `.gitignore` — add if this directory persists).*
