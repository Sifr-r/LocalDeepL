# OCR Quality Trust Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a thin `core/ocr_quality/` package that scores every OCR block with a trust value (0..1) combining calibrated VLM confidence, hallucination risk, watermark hits, and script mismatch. All sub-modules default off and fail open; no existing test or schema changes.

**Architecture:** Six small modules under `src/omniscribe/core/ocr_quality/` (`types.py`, `config.py`, `watermark.py`, `script_detector.py`, `hallucination.py`, `calibration.py`, `trust_scorer.py`) wrapped by an `orchestrator.py` entry point. Phase 1 ships the package standalone (callable as a function, not wired into `OCRPipeline`). Phase 2 wires it via a new `trust_orchestrator` constructor arg. Phase 3 adds calibration training and dataset-driven regression.

**Tech Stack:** Python 3.11+, Pydantic v2, Pillow, existing `core/ocr/` (LiteLLM), `hypothesis` (property tests), pytest. No new heavy deps.

---

## File Structure

### New files
- `src/omniscribe/core/ocr_quality/__init__.py` — public API surface (re-exports)
- `src/omniscribe/core/ocr_quality/types.py` — TrustScore, BlockTrust, TrustFlag, WatermarkHit, ScriptHint, HallucinationRisk
- `src/omniscribe/core/ocr_quality/config.py` — OCrQualitySettings (Pydantic)
- `src/omniscribe/core/ocr_quality/watermark.py` — WatermarkRemover
- `src/omniscribe/core/ocr_quality/script_detector.py` — ScriptDetector
- `src/omniscribe/core/ocr_quality/hallucination.py` — HallucinationGuard
- `src/omniscribe/core/ocr_quality/calibration.py` — ConfidenceCalibrator
- `src/omniscribe/core/ocr_quality/trust_scorer.py` — TrustScorer (pure)
- `src/omniscribe/core/ocr_quality/orchestrator.py` — `run_trust_scored_blocks()`
- `src/omniscribe/core/ocr_quality/events.py` — log channel + observability helper
- `tests/test_ocr_quality_types.py`
- `tests/test_ocr_quality_config.py`
- `tests/test_ocr_quality_watermark.py`
- `tests/test_ocr_quality_script_detector.py`
- `tests/test_ocr_quality_hallucination.py`
- `tests/test_ocr_quality_calibration.py`
- `tests/test_ocr_quality_trust_scorer.py` (with hypothesis property tests)
- `tests/test_ocr_quality_orchestrator.py`
- `tests/test_ocr_quality_integration.py` — passthrough golden test
- `docs/ocr_quality.md`
- `resources/calibration/.gitkeep`

### Modified files (Phase 1)
- `src/omniscribe/core/document.py` — add optional `trust_score: float | None`, `trust_flags: tuple[str, ...] | None` to `DocumentBlock`
- `pyproject.toml` — add `[tool.omniscribe.ocr_quality]` defaults, `hypothesis` test extra, `slow_dataset` marker
- `CHANGELOG.md` — Phase 1 entry
- `README.md` — one paragraph linking to `docs/ocr_quality.md`

### Modified files (Phase 2)
- `src/omniscribe/api/schemas/requests.py` — add `quality_options: OCrQualitySettings | None` to `ProcessSettings`
- `src/omniscribe/api/routers/ocr.py` — forward `quality_options` to `OCRPipeline.run(...)`
- `src/omniscribe/pipeline.py` — add `trust_orchestrator=None` constructor param; pass through to engine
- `src/omniscribe/core/workflows/base.py` — add `_apply_trust(blocks, page_image, settings)` hook
- `src/omniscribe/core/workflows/hybrid.py`, `grounded.py` — invoke hook after OCR + before output writer
- `frontend/src/lib/components/TrustPanel.svelte` — read-only distribution + flagged count (frontend work)

### New files (Phase 3)
- `scripts/calibrate_model.py` — fits Platt scaling from OCR-Quality-format JSON
- `resources/calibration/qwen2_5_vl_72b.json` — shipped calibrated parameters
- `tests/fixtures/datasets/ocr_quality_sample.json` — small OCR-Quality slice
- `tests/fixtures/datasets/kie_hvqa_sample.json` — small KIE-HVQA slice
- `tests/test_ocr_quality_calibration_regression.py` (slow_dataset marker)
- `tests/test_kie_hvqa_hallucination_regression.py` (slow_dataset marker)

---

## Phase 1 — Foundation (PR #1)

Defaults: all sub-modules off. Standalone package; no integration with `OCRPipeline`. `DocumentBlock.trust_score` defaults to `None`. Public API `run_trust_scored_blocks(...)` is callable but not invoked by the engine.

### Task 1: Add types module

**Files:**
- Create: `src/omniscribe/core/ocr_quality/__init__.py` (placeholder)
- Create: `src/omniscribe/core/ocr_quality/types.py`
- Create: `tests/test_ocr_quality_types.py`

- [ ] Write tests in `tests/test_ocr_quality_types.py` for the public dataclasses / enums: `TrustFlag` enum, `HallucinationRisk` enum, `WatermarkHit` dataclass (immutable), `ScriptHint` dataclass, `BlockTrust` dataclass (holds `score: float`, `flags: tuple[TrustFlag, ...]`, `explanations: tuple[str, ...]`).
- [ ] Run `pytest tests/test_ocr_quality_types.py -v` — must fail (module not found).
- [ ] Implement `src/omniscribe/core/ocr_quality/types.py` with frozen `@dataclass(slots=True)` for `WatermarkHit`, `ScriptHint`, `BlockTrust`; `StrEnum` for `TrustFlag` (`HALLUCINATION_RISK`, `WATERMARK_HIT`, `SCRIPT_MISMATCH`, `LOW_CALIBRATED_CONF`, `LENGTH_PLAUSIBILITY`) and `HallucinationRisk` (`NONE`, `LOW`, `MEDIUM`, `HIGH`).
- [ ] Run tests — must pass.
- [ ] Commit `feat(ocr-quality): add trust scoring types`.

### Task 2: Add config module

**Files:**
- Create: `src/omniscribe/core/ocr_quality/config.py`
- Create: `tests/test_ocr_quality_config.py`

- [ ] Tests: defaults all off; toggling each flag persists; `phase2_default`/`phase3_default` default False; rejects out-of-range `watermark_aggressiveness` and `trust_flag_threshold`.
- [ ] Run — must fail.
- [ ] Implement `OCrQualitySettings(BaseModel)` with `model_config = ConfigDict(extra="forbid")`, all flags per spec section 5.6.
- [ ] Run — must pass.
- [ ] Commit `feat(ocr-quality): add OCrQualitySettings config`.

### Task 3: Add watermark module

**Files:**
- Create: `src/omniscribe/core/ocr_quality/watermark.py`
- Create: `tests/test_ocr_quality_watermark.py`

- [ ] Tests:
  - passthrough image (no watermark, returns image == input, `WatermarkHit.bbox is None`)
  - synthetic light-gray diagonal stripe across image → returns a hit with bbox
  - custom `hint=WatermarkHint(bbox=(x0,y0,x1,y1))` returns hit regardless of detection
  - `aggressiveness=0` returns image unchanged
  - large-image guard (20000×20000) returns passthrough with a logged warning
  - call with `None` image returns passthrough without crashing
- [ ] Run — must fail.
- [ ] Implement `WatermarkRemover.run(image, hint=None, aggressiveness=0.5) -> tuple[Image.Image, WatermarkHit | None]` using PIL `ImageChops` luminance threshold + connected-component labelling via `scipy.ndimage` (with fallback to PIL-only when scipy missing). Detect light/near-white pixels; if connected-component area > 1% of image and aspect ratio consistent with text-band, flag it. Return passthrough + `None` on any exception; log via `core.ocr_quality.events` channel.
- [ ] Run — must pass.
- [ ] Commit `feat(ocr-quality): add WatermarkRemover`.

### Task 4: Add script detector module

**Files:**
- Create: `src/omniscribe/core/ocr_quality/script_detector.py`
- Create: `tests/test_ocr_quality_script_detector.py`

- [ ] Tests:
  - latin text → `ScriptHint(script="Latin", confidence>=0.7)` (heuristic path, 0ms)
  - CJK text → `ScriptHint(script="CJK", confidence>=0.7)`
  - mixed latin+CJK → primary script wins (>=0.5)
  - empty text → `None`
  - default model load failure → `None`, debug log
- [ ] Run — must fail.
- [ ] Implement `ScriptDetector.run(image, ocr_text=None) -> ScriptHint | None` using Unicode-range analysis (Latin, CJK, Arabic, Devanagari, Cyrillic ranges) on `ocr_text` if provided. If text unavailable, fall back to PIL pixel-density + small CNN lazy-loaded from `surya` (try/except with passthrough). Always return `None` on any failure.
- [ ] Run — must pass.
- [ ] Commit `feat(ocr-quality): add ScriptDetector`.

### Task 5: Add hallucination guard module

**Files:**
- Create: `src/omniscribe/core/ocr_quality/hallucination.py`
- Create: `tests/test_ocr_quality_hallucination.py`

- [ ] Tests:
  - clean text → `HallucinationRisk.NONE`
  - repetition `("ab" * 20)` → `MEDIUM` (or higher)
  - known marker (`▢▢▢▢▢▢`) → at least `MEDIUM`
  - length-plausibility: extremely low density (1 char in huge bbox) → `LOW`
  - cross-check divergence >0.4 → bumps risk one level
  - cross-check VLM exception → `LOW` (zero penalty)
  - empty text → `NONE`
- [ ] Run — must fail.
- [ ] Implement `HallucinationGuard.run(text, bbox, page_image, *, cross_check=False, cross_check_fn=None) -> HallucinationRisk`. Heuristic signals: (1) windowed repetition scan with `repetition_window=6`; (2) length-vs-bbox regression with `length_plausibility_min_chars_per_pixel²=0.0001`; (3) optional `cross_check_fn(text, bbox) -> str` for second-pass read, normalized Levenshtein > threshold raises one level. All exceptions → `LOW`.
- [ ] Run — must pass.
- [ ] Commit `feat(ocr-quality): add HallucinationGuard`.

### Task 6: Add confidence calibrator module

**Files:**
- Create: `src/omniscribe/core/ocr_quality/calibration.py`
- Create: `tests/test_ocr_quality_calibration.py`
- Create: `resources/calibration/.gitkeep`
- Create: `resources/calibration/identity.json` (placeholder for tests)

- [ ] Tests:
  - unknown model_id → identity passthrough + info log
  - known model_id with `{a:1.0, b:0.0}` → output == input (linear)
  - `{a:2.0, b:0.0}` → monotonic (raw=0.5 → calibrated > 0.5)
  - clamping: extreme inputs land in `[0,1]`
  - identity.json shipped file → `sigmoid(raw + 0)` ≈ raw at midpoint
- [ ] Run — must fail.
- [ ] Implement `ConfidenceCalibrator.run(raw: float, model_id: str) -> float`. Loads `resources/calibration/{model_id}.json` lazily. Cache loaded params. Missing file → identity + info log. `calibrated = sigmoid(a*raw + b)`, clamped to `[0,1]`.
- [ ] Run — must pass.
- [ ] Commit `feat(ocr-quality): add ConfidenceCalibrator`.

### Task 7: Add trust scorer module (pure, property-tested)

**Files:**
- Create: `src/omniscribe/core/ocr_quality/trust_scorer.py`
- Create: `tests/test_ocr_quality_trust_scorer.py`

- [ ] Tests:
  - empty flags + conf=0.8 → score ≈ 0.8
  - `HALLUCINATION_RISK` with risk `HIGH` (value=1.0) → 0.5×0.8=0.4
  - all flags on → score in [0, 1]
  - purity: same inputs → same output
  - monotonic in calibrated_conf (other signals fixed)
  - score always clamped to [0, 1]
  - hypothesis property test: for any (conf, flags), score ∈ [0, 1] and monotonic in conf.
- [ ] Run — must fail.
- [ ] Implement `TrustScorer.score(calibrated_conf: float, *, hallucination: HallucinationRisk, watermark_in_block: bool, script_mismatch: bool) -> BlockTrust`. Formula from spec §5.5: `trust = conf * (1 - 0.5*hval) * (1 - 0.3*w) * (1 - 0.2*s)` where `hval = 0.0/0.0/0.5/1.0` for `NONE/LOW/MEDIUM/HIGH`. Clamp. Generate `explanations` tuple from flags.
- [ ] Run — must pass.
- [ ] Commit `feat(ocr-quality): add TrustScorer (pure)`.

### Task 8: Add events log channel

**Files:**
- Create: `src/omniscribe/core/ocr_quality/events.py`
- Create: `tests/test_ocr_quality_events.py`

- [ ] Tests:
  - `emit(sub_module, doc_id, page, duration_ms, decision, fallback_used)` logs at debug with structured fields
  - missing fields don't crash
- [ ] Run — must fail.
- [ ] Implement thin wrapper around `logging.getLogger("omniscribe.core.ocr_quality.events")` with `emit(...)` that formats `extra={...}`.
- [ ] Run — must pass.
- [ ] Commit `feat(ocr-quality): add events log channel`.

### Task 9: Add orchestrator module

**Files:**
- Create: `src/omniscribe/core/ocr_quality/orchestrator.py`
- Create: `tests/test_ocr_quality_orchestrator.py`

- [ ] Tests:
  - `settings = OCrQualitySettings()` (all off) → returns input blocks unchanged with `trust_score=None`
  - watermark enabled on known-watermark image → at least one block has `WATERMARK_HIT` flag (or note no block intersects — passthrough acceptable)
  - unknown model_id, calibration enabled → blocks unchanged
  - exception inside any sub-module → orchestrator returns input blocks (fail-open)
- [ ] Run — must fail.
- [ ] Implement `run_trust_scored_blocks(blocks: list[DocumentBlock], page_image, settings: OCrQualitySettings, model_id: str) -> list[DocumentBlock]`. Returns a new list (does not mutate input). Each block gets `trust_score` and `trust_flags` populated only when at least one sub-module is on. Wrap each sub-module call in try/except + events log.
- [ ] Run — must pass.
- [ ] Commit `feat(ocr-quality): add trust orchestrator`.

### Task 10: Extend DocumentBlock with optional trust fields

**Files:**
- Modify: `src/omniscribe/core/document.py:51-60`
- Create: `tests/test_ocr_quality_block_fields.py`

- [ ] Test: `DocumentBlock(bbox=[0,0,1,1], text="hi").trust_score is None`; `DocumentBlock(bbox=[0,0,1,1], text="hi", trust_score=0.5, trust_flags=("X",)).trust_score == 0.5`; existing `from_pages_data` test still passes.
- [ ] Run — must fail.
- [ ] Add `trust_score: float | None = None` and `trust_flags: tuple[str, ...] | None = None` to `DocumentBlock` dataclass with defaults.
- [ ] Run `pytest tests/test_document.py -v` — must pass (existing tests).
- [ ] Run `pytest tests/test_ocr_quality_block_fields.py -v` — must pass (new test).
- [ ] Commit `feat(document): add optional trust fields to DocumentBlock`.

### Task 11: Public API + integration golden test

**Files:**
- Modify: `src/omniscribe/core/ocr_quality/__init__.py`
- Create: `tests/test_ocr_quality_integration.py`

- [ ] Test: import `from omniscribe.core.ocr_quality import OCrQualitySettings, run_trust_scored_blocks, BlockTrust, TrustFlag, HallucinationRisk, WatermarkHit, ScriptHint` and instantiate; orchestrator passthrough is byte-identical to input (excluding trust fields).
- [ ] Run — must fail.
- [ ] Fill `__init__.py` with re-exports.
- [ ] Run — must pass.
- [ ] Run full test sweep: `uv run pytest -m "not slow and not live_llm"` — must be all green.
- [ ] Commit `feat(ocr-quality): public API + golden integration test`.

### Task 12: Hypothesis property tests for TrustScorer

**Files:**
- Modify: `pyproject.toml:159-165` (add `hypothesis` to `[project.optional-dependencies].test`, add marker note)
- Create: `tests/test_ocr_quality_trust_scorer_props.py`

- [ ] Property tests:
  - `for all conf in [0,1]: 0 <= score <= 1`
  - `for all conf in [0,1]: monotonic — score(conf1) >= score(conf2) when conf1 > conf2 (other signals fixed)`
  - `for all inputs: deterministic — same input → same output`
- [ ] Run — must fail.
- [ ] Add `hypothesis>=6.100.0` to a new `[project.optional-dependencies].test` extra in `pyproject.toml`. Document the install: `uv sync --extra test`.
- [ ] Implement property tests with `@given(st.floats(0,1), st.sampled_from(HallucinationRisk), st.booleans(), st.booleans())`.
- [ ] Run — must pass.
- [ ] Commit `test(ocr-quality): add hypothesis property tests`.

### Task 13: User docs + CHANGELOG + README

**Files:**
- Create: `docs/ocr_quality.md`
- Modify: `CHANGELOG.md` (add Phase 1 entry)
- Modify: `README.md` (one paragraph + link in Advanced Configuration section)

- [ ] Write `docs/ocr_quality.md` covering: what the layer does, when to enable (per-workspace), flag reference, fallback semantics, dataset attribution, calibration instructions pointer.
- [ ] Append Phase 1 entry to `CHANGELOG.md`.
- [ ] Add a paragraph + link in `README.md` "Advanced Configuration" section.
- [ ] Commit `docs(ocr-quality): Phase 1 user-facing documentation`.

### Task 14: Full validation sweep

- [ ] Run `uv run pytest -m "not slow and not live_llm"` — all green
- [ ] Run `uv run ruff check src tests` — clean
- [ ] Run `uv run ruff format src tests --check` — clean
- [ ] Run `uv run mypy src` — clean
- [ ] Final commit: `chore(ocr-quality): Phase 1 validation sweep clean`.

---

## Phase 2 — Defaults on (PR #2)

After Phase 1 ships green, wire the orchestrator into `OCRPipeline` and add the Web UI panel.

### Task 15: Add `trust_orchestrator` to OCRPipeline

**Files:**
- Modify: `src/omniscribe/pipeline.py:38-90`
- Create: `tests/test_pipeline_trust_integration.py`

- [ ] Test: `OCRPipeline(..., trust_orchestrator=stub_orchestrator)` records that the engine called it once per page; without injection, no call.
- [ ] Add `trust_orchestrator: TrustOrchestrator | None = None` constructor param. Forward to `HybridEngine`/`GroundedEngine`.
- [ ] Run — must pass; existing `test_pipeline.py` unchanged.

### Task 16: Hook into HybridEngine / GroundedEngine

**Files:**
- Modify: `src/omniscribe/core/workflows/hybrid.py` (post-OCR block post-process)
- Modify: `src/omniscribe/core/workflows/grounded.py`
- Modify: `src/omniscribe/core/workflows/base.py` (add `_apply_trust` no-op method)

- [ ] Test: golden existing fixture runs through with `trust_orchestrator=None` and produces identical output bytes (snapshot test).
- [ ] Add post-OCR hook in both engines: if `self._trust_orchestrator is not None`, run `run_trust_scored_blocks(...)` on the page's blocks before output writers.
- [ ] Run — must pass.

### Task 17: Wire `quality_options` through API

**Files:**
- Modify: `src/omniscribe/api/schemas/requests.py:161-186`
- Modify: `src/omniscribe/api/routers/ocr.py`

- [ ] Test: `POST /api/process` accepts `quality_options` and forwards to `OCRPipeline.run(quality_options=settings)`.
- [ ] Add `quality_options: OCrQualitySettings | None = None` to `ProcessSettings`.
- [ ] Add `quality_options=quality_options` to the `OCRPipeline` constructor invocation in the router.
- [ ] Run — must pass.

### Task 18: Web UI Trust panel (read-only)

**Files:**
- Modify: `frontend/src/lib/components/...` (add TrustPanel.svelte)
- Modify: `frontend/src/App.svelte` (mount the panel)

- [ ] Test: when API response includes trust_* fields, panel renders distribution histogram and flagged-block count; when absent, panel is hidden.
- [ ] Run `cd frontend && npm run build` — must succeed.
- [ ] Capture screenshot showing the Trust panel rendering.

### Task 19: Flip defaults + soft-rollout flag

**Files:**
- Modify: `src/omniscribe/core/ocr_quality/config.py` (flip default values per spec §11 Phase 2)

- [ ] Flip `watermark_enabled=True`, `script_detect_enabled=True`, `hallucination_enabled=True` (heuristics only; cross-check stays False), `calibration_enabled=True`.
- [ ] Keep `hallucination_cross_check=False`.
- [ ] Existing tests that use `OCrQualitySettings()` to construct defaults now get the new defaults — verify each test still passes (and add explicit `OCrQualitySettings(watermark_enabled=False, ...)` to any test that relied on defaults).
- [ ] Run full sweep — all green.

---

## Phase 3 — Calibration + dataset-driven regression (PR #3)

### Task 20: Calibration script

**Files:**
- Create: `scripts/calibrate_model.py`

- [ ] CLI: `python scripts/calibrate_model.py --input ocr_quality.json --model-id qwen2_5_vl_72b --output resources/calibration/qwen2_5_vl_72b.json`.
- [ ] Fits Platt `a, b` on labeled data (1=correct, 0=wrong) via scipy `optimize.minimize` (or closed-form Newton when available). Logs ECE before/after.

### Task 21: Ship pretrained calibration

- [ ] Run the script on the OCR-Quality sample fixture.
- [ ] Commit `resources/calibration/qwen2_5_vl_72b.json` (~200 bytes).

### Task 22: Regression tests (slow_dataset marker)

**Files:**
- Create: `tests/test_ocr_quality_calibration_regression.py` (80/20 split, assert ECE drop)
- Create: `tests/test_kie_hvqa_hallucination_regression.py` (assert ≥80% agreement)

- [ ] Add `slow_dataset` marker to `pyproject.toml`.
- [ ] Tests opt-in only; nightly workflow runs them.

### Task 23: Nightly workflow update

**Files:**
- Modify: `.github/workflows/nightly.yml`

- [ ] Add `pytest -m slow_dataset` step.

---

## Out of scope (explicit)

- Multi-VLM consensus (CE-OCR)
- Learned trust model (logistic regression)
- Watermark *removal* (only detection)
- Form-field key-value, document classification (content-coverage cluster)
