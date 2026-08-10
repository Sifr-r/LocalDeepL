# OCR Quality Trust Layer — Design

**Date:** 2026-08-10
**Status:** Design — awaiting user review
**Author:** Brainstorming session
**Scope:** Foundation / robustness cluster of OCR accuracy & coverage gaps

## 1. Problem

OmniScribe's hybrid and grounded OCR pipelines return text + a per-block VLM confidence score. That confidence is:
- **Uncalibrated** — the same `0.7` from two different VLMs means different things
- **Silent on hallucination** — VLMs can fabricate text (repetition, invented characters) with high raw confidence
- **Indifferent to visual context** — watermarks, stamps, and script mismatches don't affect the score
- **Unflagged downstream** — low-confidence text flows unchanged into structure, table extraction, layout enrichment

The result: a single low-quality extraction propagates through the entire document-intelligence chain.

## 2. Goal

Add a thin `core/ocr_quality/` layer that wraps the existing OCR pipeline and attaches a per-block **trust score** combining:
- Calibrated VLM confidence
- Hallucination risk (repetition, length-plausibility, optional cross-check)
- Visual context (watermark hits, script mismatch)

The layer must:
- Be **additive** — no existing test, schema field, or behavior changes
- Be **fail-open** — every sub-module falls back gracefully; OCR never blocks
- Cost <5% of total OCR time (target: <100ms per page for typical 20-block pages; hard ceiling: 500ms for worst-case 50-block pages)
- Be **independently trainable** — confidence calibration fits from labeled data (OCR-Quality); hallucination guard validates against KIE-HVQA

## 3. Non-Goals

- Replacing or modifying the existing `OCRPipeline` or any of the 8 doc-intelligence processors
- Multi-VLM consensus (Consensus Entropy approach) — deferred to v2
- Cross-check hallucination by default — opt-in only, off in v1
- Learned trust model (logistic regression on labeled blocks) — deferred to v2; needs ~5k labeled blocks
- Watermark *removal* quality (i.e. re-rendering text under the watermark) — only detection in v1

## 4. Architecture

A new package `src/omniscribe/core/ocr_quality/` wraps the existing pipeline. Six small modules, each with a single responsibility and a typed I/O.

```
src/omniscribe/core/ocr_quality/
├── __init__.py          # public API: run_trust_scored_ocr(page, settings) -> Blocks
├── watermark.py         # WatermarkRemover (preprocessor)
├── script_detector.py   # ScriptDetector (router)
├── hallucination.py     # HallucinationGuard (post-OCR)
├── calibration.py       # ConfidenceCalibrator (post-OCR)
├── trust_scorer.py      # TrustScorer (combines the above)
├── types.py             # TrustScore, BlockTrust, ScriptHint
└── config.py            # Pydantic OCrQualitySettings
```

**Why this lives outside `core/ocr/`:** the existing `core/ocr/` package owns "how to run OCR" (engines, prompts, parsers). The trust layer owns "how to evaluate OCR output" — a separate concern. Cross-package import is fine; mixing them would tangle engine evolution with quality evolution.

**Why a separate package, not a processor:** the existing `core/processors/` (reading-order, structure, sections, etc.) runs *after* OCR returns blocks. The trust layer needs hooks at *two* points: pre-OCR (watermark removal) and post-OCR (scoring). Forcing it into the processor model would either add a "pre-OCR processor" concept (invasive) or move watermark removal to a separate preprocessing package (more packages, same effect).

## 5. Components

### 5.1 WatermarkRemover

- **Input:** `PIL.Image`, optional `WatermarkHint` (region bbox)
- **Output:** cleaned `PIL.Image` + `WatermarkHit` (bool + bbox + confidence)
- **Default strategy:** morphological opening on near-white pixels + connected-component analysis
- **Optional Fourier pass:** off by default; detects repeating background patterns
- **Cost:** <50ms (default), <300ms (Fourier)
- **Fallback:** passthrough image; `WatermarkHit = None`
- **Tunable:** `aggressiveness: 0..1` (0 = no removal, 1 = aggressive mask)

### 5.2 ScriptDetector

- **Input:** `PIL.Image`
- **Output:** ranked list of `ScriptHint` (`script: str`, `confidence: float`, `bbox: tuple | None`)
- **Strategy:**
  - Cheap: heuristic Unicode-range analysis on first OCR pass text (grounded path) — 0ms
  - Default: small image classifier (Surya-based) — <200ms
- **Cost:** <200ms
- **Fallback:** assume Latin; `ScriptHint = None`
- **Returned script is consumed by:** the existing `OCRPipeline` engine-selection logic as an additional signal (does not override it). The trust layer records `script_mismatch` for blocks whose detected script differs from the page-dominant script.

### 5.3 HallucinationGuard

- **Input:** `Block` (text + bbox + page image crop)
- **Output:** `HallucinationRisk` ∈ {`none`, `low`, `medium`, `high`}
- **Three signals:**
  1. **Repetition** — windowed check for "TextTextText" patterns and known hallucination markers (▢, �, repeated punctuation runs ≥6 chars)
  2. **Length plausibility** — per-script length-vs-bbox-area regression; flags implausible densities
  3. **Cross-check** (opt-in, off by default) — second VLM call: *"read the text inside this bounding box verbatim"*; if normalized Levenshtein divergence > `cross_check_divergence_threshold` (default 0.4), raise risk one level
- **Cost:** <5ms/block (heuristics), +1 VLM call (cross-check, off by default)
- **Fallback:** `HallucinationRisk = low` (zero penalty)
- **Thresholds (tunable):**
  - `repetition_window: int = 6`
  - `length_plausibility_min_chars_per_pixel²: float = 0.0001`
  - `cross_check_divergence_threshold: float = 0.4`

### 5.4 ConfidenceCalibrator

- **Input:** raw VLM confidence ∈ [0, 1], `model_id: str`
- **Output:** calibrated confidence ∈ [0, 1]
- **Strategy:** per-model **Platt scaling** — `calibrated = sigmoid(a * raw + b)`
- **Storage:** `resources/calibration/{model_id}.json` with `{a, b}` parameters
- **Training:** `scripts/calibrate_model.py` fits parameters on labeled data (OCR-Quality format)
- **Cost:** <1ms/block (table lookup)
- **Fallback:** identity passthrough for unknown `model_id`; one info log per unknown model

### 5.5 TrustScorer

- **Input:** `Block`, `WatermarkHit | None`, `ScriptHint`, `HallucinationRisk`, `model_id`
- **Output:** `BlockTrust` with `score: float ∈ [0, 1]`, `flags: set[TrustFlag]`, `explanations: list[str]`
- **Formula:**
  ```
  trust = calibrated_conf
        * (1 - 0.5 * hallucination_risk_value)   # none=0.0, low=0.0, medium=0.5, high=1.0
        * (1 - 0.3 * watermark_in_block)
        * (1 - 0.2 * script_mismatch)
  ```
- **Guarantees:**
  - `0.0 ≤ trust_score ≤ 1.0` (clamped)
  - Monotonic in `calibrated_conf` (holding other signals constant)
  - Pure function — same inputs always produce same output
- **Fallback:** missing flag = no penalty; if all post-OCR signals unavailable, `trust == calibrated_conf`
- **Cost:** <1ms/block (pure compute)
- **`TrustFlag` enum:** `HALLUCINATION_RISK`, `WATERMARK_HIT`, `SCRIPT_MISMATCH`, `LOW_CALIBRATED_CONF`, `LENGTH_PLAUSIBILITY`

### 5.6 config.py — OCrQualitySettings (Pydantic)

```python
class OCrQualitySettings(BaseModel):
    # Phase 1: all sub-modules default OFF (passthrough). Phase 2 flips watermark,
    # script_detect, hallucination, and calibration to True.
    watermark_enabled: bool = False
    watermark_aggressiveness: float = 0.5
    script_detect_enabled: bool = False
    hallucination_enabled: bool = False       # heuristics-only when on; cross-check is a separate opt-in
    hallucination_cross_check: bool = False   # second VLM call; ALWAYS off unless user enables
    calibration_enabled: bool = False
    trust_flag_threshold: float = 0.5        # below this, auto-flag in UI
    phase2_default: bool = False             # workspace opt-in
    phase3_default: bool = False             # workspace opt-in
```

## 6. Data flow

```
[user uploads PDF page]
        │
        ▼
[render + existing preprocess: deskew, denoise, contrast, crop]
        │
        ▼ (new)
[WatermarkRemover.run(page_image) → cleaned_image, watermark_hit]
        │
        ▼ (new)
[ScriptDetector.run(cleaned_image) → script_hint]
        │
        ▼
[existing OCR call (grounded|hybrid) → blocks]
        │
        ▼ (new)
[For each block:
    calibrated = ConfidenceCalibrator.run(block.conf, model_id)
    risk = HallucinationGuard.run(block, page_image, cross_check_opt)
    trust = TrustScorer.run(calibrated, watermark_hit, script_hint, risk, model_id)
    block.trust = trust
]
        │
        ▼
[existing downstream: structure, table extraction, layout, quality routing]
        │
        ▼
[API response: blocks[] + new trust fields; Web UI renders badges]
```

**Invariants:**
- Existing `OCRPipeline.run()` signature is unchanged
- `Block` schema is a strict superset — new fields are additive
- All sub-modules are individually opt-in via `OCrQualitySettings`
- All sub-modules fail open (passthrough + log) — OCR never blocks
- `TrustScorer` is pure; everything else is data-driven (loaded models, JSON config, no hidden state)

**Latency budget:** target <100ms per page (typical 20-block page), hard ceiling 500ms (worst-case 50-block page with all sub-modules on). Existing OCR is 1–10s, so the trust layer stays under 5% of total time. If a sub-module routinely blows the budget on real `examples/` PDFs, it gets an opt-in flag (default off) in the next minor release.

## 7. Error handling and fallbacks

| Sub-module | Failure | Fallback | Logged? |
|---|---|---|---|
| `WatermarkRemover` | Image too large, OOM, timeout | passthrough image; `WatermarkHit = None` | warning once per image-size class |
| `ScriptDetector` | Model load, timeout, no text available | assume Latin; `ScriptHint = None` | debug once per session |
| `HallucinationGuard` | Heuristic throws, cross-check VLM fails | `HallucinationRisk = low` (zero penalty) | warning per failure |
| `ConfidenceCalibrator` | Missing `model_id` in `resources/calibration/` | identity passthrough | info once per model_id |
| `TrustScorer` | Missing input fields | treat as no penalty | none |

**Observability:** a single `core.ocr_quality.events` log channel emits `{sub_module, doc_id, page, duration_ms, decision, fallback_used}` per call. Per-run aggregates (`{low_trust_pct, hallucination_pct, watermark_pct, script_diversity}`) are attached to the existing OCR job's artifact metadata (the same `Artifact` record that already carries `created_at`, `model_id`, `token_count`, etc.).

## 8. Configuration

Configuration surfaces, in increasing specificity:
1. `pyproject.toml` `[tool.omniscribe.ocr_quality]` block — workspace-level defaults
2. Per-workspace override in the existing workspace settings panel
3. Per-run override via `POST /api/ocr` body field `quality_options: OCrQualitySettings`
4. Per-block override (rare): users can mark a region as "high priority, ignore trust" in the UI

**pyproject.toml example (Phase 1 default — all off):**
```toml
[tool.omniscribe.ocr_quality]
watermark_enabled = false
watermark_aggressiveness = 0.5
script_detect_enabled = false
hallucination_enabled = false
hallucination_cross_check = false
calibration_enabled = false
trust_flag_threshold = 0.5
phase2_default = false
phase3_default = false
```

## 9. Datasets and training

| Dataset | What it gives us | Used for |
|---|---|---|
| **OCR-Quality** — 1,000 PDF pages (300 DPI, ZH/EN/multilingual, Qwen2.5-VL-72B outputs, 4-level human scores) — [HuggingFace: Aslan-mingye/OCR-Quality](https://huggingface.co/datasets/Aslan-mingye/OCR-Quality), paper [arXiv:2510.21774](https://arxiv.org/html/2510.21774v1) | Page-level ground truth: image + VLM output + quality score 1–4 | Training `ConfidenceCalibrator` (Platt scaling); committed output: `resources/calibration/qwen2_5_vl_72b.json` |
| **KIE-HVQA** — 2,000 train + 400 test, OCR hallucination with pixel-level reliability annotations (ByteDance) — [arXiv:2506.20168](https://arxiv.org/html/2506.20168v2) | Region-level ground truth: which characters are visible/hallucinated | Validating `HallucinationGuard` (target: ≥80% agreement on per-region risk) |
| **ConfBERT** (Shift Technology) — [arXiv:2409.04117](https://arxiv.org/html/2409.04117v1) | Method: integrate OCR confidence + BERT for error detection | Implementation reference for our hallucination signals |
| **Consensus Entropy / CE-OCR** (CVPR 2026) | Multi-VLM agreement for OCR self-verification | Research reference for the cross-check path |
| **HalluText** (OpenReview [LRnt6foJ3q](https://openreview.net/forum?id=LRnt6foJ3q)) | 9 OCR hallucination subtypes | Coverage list for heuristics |

**License check (Phase 3):** confirm OCR-Quality and KIE-HVQA licenses permit derivative calibration files committed to the repo. Fall back to "synthetic-only" calibration if any license is incompatible.

## 10. Testing strategy

**Unit tests** (per sub-module, fast):
- `test_watermark.py` — passthrough, synthetic hit, light-logo hit, custom hint, bounds check
- `test_script_detector.py` — Latin, CJK, mixed, heuristic fallback, empty image
- `test_hallucination.py` — repetition, length-plausibility, curly quotes, cross-check, cross-check failure
- `test_calibration.py` — identity passthrough, Platt formula, clamping, unknown model_id
- `test_trust_scorer.py` — purity, monotonicity, score bounds, empty flags, all flags

Use `hypothesis` for property tests on `TrustScorer` (purity + monotonicity + bounds).

**Integration tests** (~5–10s each):
- `test_trust_pipeline_integration.py` — known-good PDF → all blocks `trust > 0.7`, zero flags
- Known-degraded page → at least one block has non-empty `trust_flags`
- Disabled config → output byte-identical to running without the layer (golden test)
- API response includes new `trust_*` fields without breaking existing `Block` schema (OpenAPI snapshot)

**Regression tests** (dataset-driven, `slow_dataset` marker):
- `test_ocr_quality_calibration_regression.py` — fit Platt on 80% split, assert ECE drop on 20% held-out
- `test_kie_hvqa_hallucination_regression.py` — assert ≥80% per-region agreement with pixel-level reliability annotations
- Opt-in: `pytest -m "not slow_dataset"` skips them; nightly workflow runs all

**Coverage targets:**
- New code: ≥85% line coverage (matching existing `core/ocr/` baseline)
- `trust_scorer.py`, `calibration.py`: 100% branch coverage
- Mutation-test the trust formula — every mutation should fail a test

**Hard gate:** no existing test should change. The trust layer is additive; if any existing test starts failing, the design is wrong.

## 11. Rollout — three PRs

### Phase 1 — Foundation (PR #1, ~600 LOC)
- Land `core/ocr_quality/` package with all six modules
- Defaults: all sub-modules **off** (passthrough)
- `Block` schema: optional `trust_*` fields (always `None` until enabled)
- Web UI: no changes; trust fields hidden when `None`
- New unit tests
- Rollback: revert the PR. No callers depend on the layer yet.

### Phase 2 — Defaults on (PR #2, ~300 LOC)
- Flip defaults: `watermark.enabled=True`, `script_detect.enabled=True`, `calibration.enabled=True`
- `hallucination.enabled=True` (heuristics only; cross-check stays off)
- Soft-rollout flag `phase2_default: bool = False` per workspace
- Add "Trust" panel in Web UI (read-only, per-document: distribution histogram + flagged-block count)
- Capture baseline `trust_score` distributions for `examples/` PDFs
- Rollback: workspace toggle or PR revert

### Phase 3 — Calibration + dataset-driven regression (PR #3, ~400 LOC + dataset downloads)
- Land `scripts/calibrate_model.py` (CLI: takes OCR-Quality-format JSON → writes `resources/calibration/{model_id}.json`)
- Ship pre-trained `qwen2_5_vl_72b.json` (~200 bytes)
- Add KIE-HVQA + OCR-Quality fixtures under `tests/fixtures/datasets/`
- Enable `slow_dataset` regression tests in `.github/workflows/nightly.yml`
- `phase3_default: bool = False` per workspace
- Rollback: per-workspace toggle or PR revert

**Each phase is independently revertible.**

## 12. Documentation

- `docs/ocr_quality.md` (new): when to enable, what each flag does, dataset attribution, calibration instructions
- `README.md` — one paragraph + link in the Advanced Configuration section
- `CHANGELOG.md` — entry per phase
- Inline docstrings in every public function

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Dataset license incompatibility (OCR-Quality or KIE-HVQA) | Confirm in Phase 3 pre-flight; fall back to synthetic-only calibration |
| VLM cost increase from cross-check | Off by default; opt-in toggle surfaces cost in UI before enabling |
| Latency regression on existing `examples/` PDFs | Phase 1 captures baseline; Phase 2/3 must not regress by >5% |
| `Block` schema bloat | Only the `BlockTrust` is added; consumers ignore new fields |
| Calibration overfit on small dataset | 80/20 split; assert ECE drops on held-out 20%; min 200 samples per model |
| Watermark false-positive erases real text | `aggressiveness` slider; default 0.5 (conservative); users can disable per-document |

## 14. Out of scope (deferred)

- Multi-VLM consensus (CE-OCR approach) — needs ≥2 VLMs per call; cost prohibitive
- Learned trust model — needs ~5k labeled blocks; we have <1k from public datasets alone
- Stamp / seal / signature detection — content-coverage cluster, not foundation
- Form-field key-value detection — content-coverage cluster
- Document classification (auto-routing by doc type) — process / workflow cluster
- Watermark *removal* (i.e. recovering text under the watermark) — only detection in v1

## 15. Open questions

- KIE-HVQA download URL — paper says "available" but I haven't found the public link yet. Will confirm in Phase 3 pre-flight.
- OCR-Quality license — needs verification before committing derived calibration files.
- Whether to ship a small fallback `calibration/identity.json` for ALL VLM models out of the box, or only models we've measured on (more honest but requires users to opt in to calibration).

## 16. Acceptance criteria

The design is **complete** when all of:
1. The `core/ocr_quality/` package is added with all six modules, all unit tests passing
2. Default config is passthrough (no behavior change for existing callers)
3. Phase 2 default config reduces the per-block hallucination flag false-positive rate on `examples/` PDFs to <5% (baseline: untested)
4. Phase 3 calibration reduces ECE on the OCR-Quality held-out split by ≥20% vs. raw confidence
5. Hallucination guard achieves ≥80% agreement with KIE-HVQA per-region reliability annotations
6. No existing test changes; no existing API field changes
7. The new layer adds <100ms per page on `examples/` PDFs
8. Documentation is published; workspace opt-in is one toggle
