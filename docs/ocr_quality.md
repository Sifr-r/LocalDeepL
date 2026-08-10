# OCR Quality Trust Layer

> **Status:** Phase 1 shipped — foundation package, all sub-modules **off** by
> default, no behavioural change for existing callers. Phase 2 (defaults on,
> Web UI panel) and Phase 3 (calibration training, dataset regression) are
> planned but not yet implemented.

The OCR Quality Trust Layer is a thin, additive wrapper around OmniScribe's
hybrid and grounded OCR pipelines. For every OCR block, it produces a
`trust_score ∈ [0, 1]` and a list of human-readable `trust_flags`. The score
combines:

- **Calibrated VLM confidence** (Platt scaling per model)
- **Hallucination risk** (repetition, giveup markers, length plausibility,
  optional cross-check)
- **Watermark hits** (mid-gray band detection on the page image)
- **Script mismatch** (block script vs. page-dominant script)

The layer is **additive** (no existing test, schema field, or behaviour
changes), **fail-open** (every sub-module returns a passthrough on failure —
OCR never blocks), and **independent** (the trust formula is pure Python,
fully property-tested, and reused by the Web UI previews and evaluation
scripts).

## When to enable

The trust layer ships **off** by default. Enable it per workspace or per run
when any of the following are true:

- You use VLM models whose raw confidences are known to be poorly calibrated
  (cross-model comparison, e.g. Qwen-VL vs. InternVL).
- You process long documents where a single hallucinated block silently
  poisons downstream structure analysis, table extraction, or layout
  enrichment.
- You want a UI histogram of `trust_score` to spot low-confidence pages at a
  glance.
- You're exporting to downstream systems that benefit from per-block
  confidence metadata (RAG indexing, structured extraction, glossary lookup).

For local single-VLM workflows on well-formed inputs, keep it off — the
penalty is <1 ms per block, but it's also pure overhead when nothing needs
flagging.

### Per-workspace defaults (`pyproject.toml`)

```toml
[tool.omniscribe.ocr_quality]
watermark_enabled = false
watermark_aggressiveness = 0.5
script_detect_enabled = false
hallucination_enabled = false
hallucination_cross_check = false      # second VLM call — expensive
hallucination_cross_check_threshold = 0.4
hallucination_repetition_window = 6
hallucination_length_plausibility_min = 0.0001
calibration_enabled = false
trust_flag_threshold = 0.5             # UI auto-flag when score < this
phase2_default = false
phase3_default = false
```

Every flag is opt-in. The orchestrator short-circuits to a no-op when
`any_submodule_enabled()` returns `False`, so the disabled path adds a
single boolean check.

### Per-run override

Phase 2 wires `OCrQualitySettings` into `POST /api/process` under the
`quality_options` body field; until that ships, the orchestrator is callable
directly from Python:

```python
from omniscribe.core.ocr_quality import (
    OCrQualitySettings,
    run_trust_scored_blocks,
)
from omniscribe.core.document import DocumentBlock, BBox

settings = OCrQualitySettings(
    watermark_enabled=True,
    hallucination_enabled=True,
    calibration_enabled=True,
)
blocks = [
    DocumentBlock(bbox=BBox(0.1, 0.1, 0.9, 0.2), text="...", confidence=0.8),
]
scored = run_trust_scored_blocks(blocks, page_image, settings, model_id="qwen2_5_vl_72b")
for b in scored:
    print(b.trust_score, b.trust_flags)
```

The orchestrator never mutates input blocks — it returns new `DocumentBlock`
copies with `trust_score` and `trust_flags` populated. With every flag off,
the returned blocks are byte-identical to the inputs (both trust fields are
`None`).

## Flag reference

Every `OCrQualitySettings` field and what it controls:

| Field | Type | Default | Phase | Effect |
| --- | --- | --- | --- | --- |
| `watermark_enabled` | `bool` | `False` | 1 | Enables mid-gray band watermark detection. False = passthrough. |
| `watermark_aggressiveness` | `float ∈ [0, 1]` | `0.5` | 1 | `0.0` keeps the page unchanged; `1.0` fully inpaints the band with paper-white. |
| `script_detect_enabled` | `bool` | `False` | 1 | Computes the page-dominant script via Unicode-range analysis and flags per-block mismatches. |
| `hallucination_enabled` | `bool` | `False` | 1 | Turns on heuristic checks: repetition, giveup markers, length plausibility. |
| `hallucination_cross_check` | `bool` | `False` | 1 | Adds a second VLM call per block. **Off by default** — costs an extra round-trip per block. |
| `hallucination_cross_check_threshold` | `float ∈ [0, 1]` | `0.4` | 1 | Normalised Levenshtein divergence above which the cross-check bumps risk one level. |
| `hallucination_repetition_window` | `int ∈ [2, 64]` | `6` | 1 | Substring length scanned for repeated chunks (≥3 hits triggers). |
| `hallucination_length_plausibility_min` | `float ∈ [0, 1]` | `0.0001` | 1 | Minimum text density (chars per pixel²) for a block to be considered plausible. |
| `calibration_enabled` | `bool` | `False` | 1 | Applies Platt scaling to the raw VLM confidence using `resources/calibration/{model_id}.json`. |
| `trust_flag_threshold` | `float ∈ [0, 1]` | `0.5` | 1 | Below this, the Web UI auto-flags the block (independent of `trust_flags`). |
| `phase2_default` | `bool` | `False` | 2 | Soft-rollout toggle for the Phase 2 default-flip (watermark/script-detect/hallucination/calibration all on, cross-check off). |
| `phase3_default` | `bool` | `False` | 3 | Soft-rollout toggle for Phase 3 (calibration training + dataset regression). |

`OCrQualitySettings` is a Pydantic v2 `BaseModel` with `extra="forbid"`,
so any typo in the API schema (e.g. `watermarkEnable` instead of
`watermark_enabled`) fails fast with a 422 instead of silently disabling
the flag.

## Trust flags

`BlockTrust.flags` is a sorted, deduplicated tuple of `TrustFlag` enum
members. The UI surfaces them as coloured badges; downstream consumers can
filter on them without parsing prose explanations.

| Flag | When it fires | Trust penalty |
| --- | --- | --- |
| `hallucination_risk` | Heuristic or cross-check raised `HallucinationRisk` above `LOW` (NONE/LOW carry zero penalty). | `0.5 * risk_value` (0.0 / 0.0 / 0.5 / 1.0 for NONE / LOW / MEDIUM / HIGH) |
| `watermark_hit` | The block's bbox intersects a detected mid-gray watermark band. | `0.3` |
| `script_mismatch` | The block's detected script differs from the page-dominant script (with confidence ≥ 0.5). | `0.2` |
| `low_calibrated_conf` | Calibrated (or raw, when calibration is off) confidence < 0.5. | None (informational) |
| `length_plausibility` | Heuristic flagged the block as implausibly sparse (rare; folded into `hallucination_risk` for the score). | None (informational) |

The trust formula (spec §5.5) is pure Python, lives in
`omniscribe.core.ocr_quality.trust_scorer.score`, and is property-tested
with `hypothesis`:

```python
trust = conf
      * (1 - 0.5 * hallucination_value)
      * (1 - 0.3 * watermark_in_block)
      * (1 - 0.2 * script_mismatch)
```

Output is clamped to `[0, 1]`. The formula is monotonic in `calibrated_conf`
(holding all other signals fixed) and pure (same inputs → same outputs).

## Fallback semantics

Every sub-module has a documented fallback. The orchestrator wraps each
call in a `_safe(...)` helper that catches every exception, logs at
`DEBUG` to the `omniscribe.core.ocr_quality.events` logger, and flips a
`fallback_used` flag on the page-level event. **No sub-module failure
propagates out of `run_trust_scored_blocks(...)`** — the worst case is a
page whose trust scores are equivalent to running with the affected flag
off.

| Sub-module | Failure mode | Fallback |
| --- | --- | --- |
| `watermark` | Image > 20000×20000 pixels, OOM, timeout | Passthrough image; `WatermarkHit = None`; `fallback_used=True` |
| `script_detect` | Empty / non-text input, Unicode DB lookup error | `ScriptHint = None`; page-dominant script stays `None` |
| `hallucination` | Heuristic throws, cross-check VLM errors | `HallucinationRisk = LOW` (zero trust penalty, but the failure is recorded) |
| `calibration` | Missing `resources/calibration/{model_id}.json`, malformed JSON | Identity passthrough (raw returned unchanged); one `INFO` log per unknown `model_id` |
| `trust_scorer` | Missing input fields | Treated as no penalty |

The structured event channel
(`omniscribe.core.ocr_quality.events.emit(...)`) emits one log line per
sub-module call with
`{sub_module, doc_id, page, duration_ms, decision, fallback_used}`. Wire
your log aggregator to filter on logger name
`omniscribe.core.ocr_quality.events` to surface these independently from
the rest of the OCR pipeline's noise.

## Dataset attribution

The calibration and hallucination sub-modules reference three datasets;
**no dataset artefacts are bundled in the repo**. Phase 3 will ship
calibration files derived from:

- **OCR-Quality** — 1,000 PDF pages (300 DPI, ZH/EN/multilingual, with
  Qwen2.5-VL-72B outputs and 4-level human scores). Source:
  [HuggingFace: Aslan-mingye/OCR-Quality](https://huggingface.co/datasets/Aslan-mingye/OCR-Quality),
  paper [arXiv:2510.21774](https://arxiv.org/html/2510.21774v1). Used for
  fitting Platt `a, b` per model (`resources/calibration/{model_id}.json`).
- **KIE-HVQA** — 2,000 train + 400 test, OCR hallucination with
  pixel-level reliability annotations (ByteDance). Paper
  [arXiv:2506.20168](https://arxiv.org/html/2506.20168v2). Used to validate
  the `HallucinationGuard` against per-region pixel-level reliability
  (target: ≥ 80% agreement).
- **HalluText** — 9 OCR hallucination subtypes.
  [OpenReview](https://openreview.net/forum?id=LRnt6foJ3q). Used as a coverage
  reference for the heuristic signal set (`_GIVEUP_MARKERS`, repetition,
  length plausibility).

Two related works inform the design without contributing datasets:

- **ConfBERT** ([arXiv:2409.04117](https://arxiv.org/html/2409.04117v1)) —
  method reference for integrating OCR confidence with language-model
  signals.
- **Consensus Entropy / CE-OCR** (CVPR 2026) — multi-VLM agreement research
  reference for the cross-check path (deferred to v2; needs ≥ 2 VLMs per
  call).

Phase 3 will confirm OCR-Quality and KIE-HVQA licenses before committing
derived calibration files. If either licence is incompatible with bundling
derivatives, we fall back to synthetic-only calibration and document the
limitation.

## Calibration instructions (Phase 3 preview)

Phase 3 ships `scripts/calibrate_model.py`, a CLI that fits Platt scaling
from an OCR-Quality-format JSON fixture:

```bash
uv run python scripts/calibrate_model.py \
    --input tests/fixtures/datasets/ocr_quality_sample.json \
    --model-id qwen2_5_vl_72b \
    --output resources/calibration/qwen2_5_vl_72b.json
```

The script:

1. Parses OCR-Quality JSON (image + VLM output + quality score 1–4).
2. Binarises the quality score (1–2 → wrong, 3–4 → correct).
3. Fits `sigmoid(a * raw + b)` via `scipy.optimize.minimize` (closed-form
   Newton when available) on an 80/20 train/test split.
4. Writes the `{a, b}` pair plus the pre/post calibration ECE
   (Expected Calibration Error) to the output file.
5. Logs the held-out ECE drop — Phase 3 acceptance criterion is ≥ 20%
   drop vs. raw confidence.

Once `resources/calibration/{model_id}.json` exists, the
`calibration_enabled=True` flag picks it up automatically via lazy load
on the first call (cached for the process lifetime). Missing files
degrade to identity passthrough with an info log — see the Fallback
semantics section above.

To calibrate a custom model that has no shipped JSON:

1. Collect ≥ 200 labelled samples (raw VLM confidence + correct/wrong
   label) — see `scripts/calibrate_model.py --help` for the input schema.
2. Run the CLI against your JSON.
3. Commit the resulting `resources/calibration/{model_id}.json` to the
   repo (or ship it with your workspace overlay).
4. Set `calibration_enabled=True` and verify the trust-score distribution
   on a known-good PDF (e.g. `examples/dense.pdf`) using
   `scripts/confidence_eval.py`.

## Testing the layer locally

```bash
# Unit tests (fast; no Surya, no LM Studio).
uv run pytest tests/test_ocr_quality_*.py -v

# Property tests (require `hypothesis`, declared in
# `[dependency-groups].dev` in pyproject.toml).
uv run pytest tests/test_ocr_quality_trust_scorer_props.py -v

# Full sweep — must remain green across Phase 1.
uv run pytest -m "not slow and not live_llm"

# Regression tests on real datasets (Phase 3, `slow_dataset` marker).
uv run pytest -m slow_dataset
```

The unit tests exercise every fallback path explicitly (large image,
unknown `model_id`, malformed JSON, cross-check exception, empty input).
The property tests verify the trust formula's invariants
(`0 ≤ score ≤ 1`, monotonic in confidence, deterministic) across thousands
of randomly-generated inputs.

## Logging and observability

Every sub-module call emits one `DEBUG` log line to
`omniscribe.core.ocr_quality.events` with structured `extra={...}` fields.
Sample Python consumer:

```python
import logging

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(message)s | %(ocr_quality_sub_module)s | %(ocr_quality_decision)s"))
logging.getLogger("omniscribe.core.ocr_quality.events").addHandler(handler)
logging.getLogger("omniscribe.core.ocr_quality.events").setLevel(logging.DEBUG)
```

For production observability, point your existing log pipeline at the
logger name and alert on non-zero `ocr_quality_fallback_used` rates per
sub-module.