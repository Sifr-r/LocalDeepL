# TODOS

Deferred items from the /autoplan review of the Whitespace Recall Booster
(`docs/superpowers/plans/2026-08-14-whitespace-recall.md`, 2026-08-15).
All plan tasks (T2–T7, eng-new) are closed; this file holds what was
explicitly deferred, with its deferral rationale. Struck-through items
were resolved during the 2026-08-16 triage pass.

**Triage 2026-08-16** — pass-2 walk-through of every open deferral against
the current repo. Verdict on every item: **KEEP DEFERRED / KEEP CLOSED**
— see the inline evidence below each bullet. No new work spawned; no
priority changes. The deferral picture is stable.

## Whitespace Recall Booster deferrals

- **E4 — Per-request recall knob** (form field / runtime setting, mirror the
  `quality_loop_enabled` pattern). Deferred: spec defers v1 knobs; blast
  radius >5 files incl. frontend. TASTE-flagged — env-only vs per-request is
  a reasonable-disagreement call. Revisit if junk-box reports arrive and
  users need per-document opt-out. *(audit D9/D18)*
  - **Triage 2026-08-16 — keep deferred.** No per-request recall knob exists
    in `api/schemas/requests.py`, `api/routers/ocr.py`, or anywhere in
    `frontend/src` (grep for `recall` returns 0 matches in those trees).
    The reference pattern (`quality_loop_enabled` / `quality_target` /
    `quality_max_retries`) is wired into the backend form fields
    (`ocr.py:427-429`, `ocr.py:662-664`) but **also not yet surfaced in
    the frontend** — so the per-request frontend plumbing is a missing
    prerequisite, not a solved one. Adding recall knobs on top of an
    unshipped quality-loop UI would be a 2-feature blast for 1 user
    benefit. Revisit triggers, in order: (1) junk-box report from a real
    user, (2) `quality_loop_enabled` lands in the frontend, (3) the
    recall story is actually used per-document.
- **E7 — Box provenance tagging / detector-fusion registry.** Deferred: one
  plugin does not justify the abstraction yet. Becomes worth doing when a
  second box source (PDF text layer, projection profiles) lands. **Landed
  2026-08-16 (E7-lite):** the PDF text-layer source is the second box
  source; per-source INFO tallying ("Whitespace recall summary" /
  "Text-layer recall summary") shipped with it. Keep the registry
  abstraction deferred until a third source appears. *(audit D12)*
  - **Triage 2026-08-16 — keep deferred.** Two box sources remain: whitespace
    recall (`core/text_recall.py`) and text-layer recall
    (`core/text_layer_recall.py`). No third candidate is on the roadmap
    (projection profiles, header/footer detection, table-region crops
    are not scoped). No D9/D12-flagged TASTE call to revisit.
- ~~**PDF text-layer recall alternative**~~ **Landed 2026-08-16**
  (independent CEO voice). `core/text_layer_recall.py` /
  `PdfTextLayerRecall`: on digital PDFs, lines Surya missed are recovered
  from `page.get_text("words")` and merged after the whitespace booster
  (dedup sees both sources' extras). Boxes-only contract — recovered lines
  flow through normal OCR/alignment/trust. Kill switch
  `OMNISCRIBE_TEXT_LAYER_RECALL` (default on), INFO run summary, fail-open
  per page, strict no-op for scans and image inputs. Complementary to the
  booster, not a replacement — as proposed.
- ~~**Calibration A/B eval.**~~ **Closed 2026-08-16 (superseded, no-action).**
  The stated purpose — "turns T7 measurements into filter constants" — was
  fulfilled by the T7 harness itself: two retune candidates were measured
  and both rejected (junk-box amplification / dense-flips), so the shipped
  filter constants are frozen with measured rationale recorded in the plan
  file. The harness also measured 0 recovered GT blocks, so a live-VLM
  recall-ON/OFF confidence comparison has no remaining signal to surface
  (`scripts/confidence_eval.py` requires a live LM Studio endpoint for
  marginal confirmation only). Reopen if a corpus arrives on which the
  booster recovers blocks. *(audit D22/D27)*
- **T9 — Limitation-pinning edge test** for text-like noise (photo edges /
  figure borders passing the line filters). Deferred: pins a known
  limitation, adds no protection. *(audit D24/D33)*
  - **Triage 2026-08-16 — keep deferred.** Adjacent coverage is in place
    at `tests/test_text_recall.py:148` (`test_photo_region_does_not_become_box`,
    solid dark blob → density-filtered), `:119`
    (`test_straddle_guard_rejects_gutter_crossing_candidate`), `:159`
    (`test_dark_inverted_page_yields_no_boxes`). T9 is the line-shaped
    photo-edge case that survives height + density — distinct from
    those, and a true limitation pin. Deferral rationale (no protection,
    known limitation) still holds. Side note: for digital PDFs the
    text-layer source won't extract photo borders as text, so the risk
    surface shrinks; scanned pages are unchanged.
- **A2 — Route `OMNISCRIBE_WHITESPACE_RECALL` through `config.py` Settings.**
  Deferred: `from_env` matches the house env-seed style (`security_config`,
  quality-loop seeds). Revisit only if env seeds consolidate into Settings.
  *(audit D36)*
  - **Triage 2026-08-16 — keep deferred.** Sibling env var
    `OMNISCRIBE_TEXT_LAYER_RECALL` uses the same `from_env` direct-read
    pattern (not `config.py` Settings either). A solo migration of just
    whitespace recall would create inconsistency. The right shape, if
    it ever happens, is a batch: `config.py` consolidates the
    `OMNISCRIBE_*` env seeds that currently read `os.environ` directly
    (recall flags, quality-loop seeds, state backend). No triggering
    signal today.
- **Form-blank underscore recovery.** T7 measured that fill-in-the-blank
  underscore segments render at ~6 px post-dilation and cannot be separated
  from hairline rules on pixel statistics alone (height and density overlap),
  so `_MIN_COMPONENT_HEIGHT_PX = 10` keeps them excluded. Recovering them
  needs a non-pixel signal — **the PDF text-layer source landed 2026-08-16
  and now covers digital PDFs with underscore glyphs in their text layer;
  scanned forms still need stroke-shape analysis**. *(T7 retune, 2026-08-15)*
  - **Triage 2026-08-16 — keep deferred.** Digital side is closed (text
    layer recovers underscore glyphs on any PDF with a text layer).
    Scanned side requires a stroke-shape classifier (e.g. long-thin-ratio
    + low-curvature feature) — speculative until a scanned-form corpus
    lands. The limitation is already documented in code at
    `text_recall.py:68-70` with a TODOS.md pointer, so the "users need
    to know" surface is covered. Revisit triggers: (1) scanned form
    corpus arrives with measurable underscore loss, (2) someone proposes
    a non-pixel signal that's cheaper than a full classifier.
- ~~**Split-at-ink-gap straddle handling.**~~ **Closed 2026-08-16 (condition
  did not fire).** Revisit clause was "only if harness data shows rejected
  straddling candidates recovering real lines"; the T7 harness measured 0
  recovered GT corpus-wide, so no straddle rejection is costing a real
  line. The reject-first guard stands. *(audit D26)*
