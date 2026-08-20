# `examples/` — on-disk sample documents for tests and developer scripts

The files in this directory are small, hand-picked public-domain samples
used by OmniScribe's test suite and developer-only scripts. They are
shipped in git so the test fixtures stay reproducible and so a fresh
clone can run the smoke tests without any extra download step.

## Files

| File | Source / origin | License | When added | Used by |
| --- | --- | --- | --- | --- |
| `digital.pdf` | Public-domain English text rendered as a digital PDF (embedded text layer, machine-generated). | Public domain | Initial sample corpus | `tests/test_integration.py` (Surya detection + DP alignment regression); `scripts/visualize_bboxes.py`, `scripts/visualize_comparison.py`, `scripts/debug_detection_only.py`, `scripts/inspect_pdf.py` |
| `hybrid.pdf` | Scanned page of a public-domain document with mixed embedded text + raster. | Public domain | Initial sample corpus | `tests/test_integration.py` (joined-paragraph regression, `tests/test_integration.py:346`); `scripts/debug_alignment.py`; `scripts/visualize_bboxes.py`, `scripts/visualize_comparison.py`, `scripts/debug_detection_only.py`, `scripts/inspect_pdf.py`, `scripts/test_check.py` |
| `handwritten.pdf` | Synthetic handwriting page used to exercise the handwriting preprocessor. | CC0 / synthetic | Initial sample corpus | `tests/test_integration.py`; `scripts/visualize_bboxes.py`, `scripts/visualize_comparison.py`, `scripts/debug_detection_only.py`, `scripts/inspect_pdf.py`, `scripts/test_check.py` |
| `dense.pdf` | A dense, multi-column public-domain document that pushes the box count over `dense_threshold` (forces per-box OCR instead of full-page). | Public domain | Initial sample corpus | `tests/test_aligner.py`, `tests/fixtures/ground_truth_dense.json`; `test_ui.py` (Playwright smoke); `scripts/confidence_eval.py`, `scripts/measure_recall_delta.py`, `scripts/build_fixture.py` |
| `notes.pdf` | Long public-domain textbook used as the multi-page / long-document stress fixture. | Public domain | Initial sample corpus | `tests/fixtures/ground_truth_notes.json`; `scripts/confidence_eval.py`, `scripts/measure_recall_delta.py`, `scripts/build_fixture.py` |
| `image.png` | Single-page raster (PNG) of a public-domain document page — exercises the image-input code path. | Public domain | Initial sample corpus | Image-input tests / debug scripts; hybrid and grounded pipelines accept PNG directly. |
| `image.avif` | Same source page as `image.png`, encoded as AVIF — exercises modern-format image decoding. | Public domain | Initial sample corpus | `scripts/confidence_image.py --image examples/image.avif`; AVIF support is opt-in via the `pillow-avif-plugin` extra. |

## Provenance

All files are either:

1. **Public-domain text** (Project Gutenberg, government-published
   documents, or other US-public-domain sources) rendered to PDF/image
   for the test corpus, or
2. **Synthetic / hand-generated** pages created for the test suite
   (e.g. the synthetic handwriting page).

No copyrighted material is included. If you find a file in this
directory that you believe is incorrectly sourced, open an issue and we
will replace or remove it.

## License

The files in this directory are released under **CC0 1.0 Universal**
(public domain dedication) to match the OmniScribe repo's
`LICENSE`-equivalent posture. The PDF/image wrappers themselves are
machine-generated and not subject to copyright in any jurisdiction we
are aware of; the underlying text content is also public domain.

## Adding a new sample

1. Drop the file in `examples/` (keep size reasonable — under ~15 MB
   unless it's a long-document stress test).
2. Add an entry to the table above with: source / origin, license,
   when added, and the tests or scripts that consume it.
3. If the file should be in the canonical test corpus, also add the
   filename to `EXAMPLE_PDF_NAMES` in `tests/conftest.py` so the
   `example_pdfs` fixture picks it up.
4. If the file is binary and large, prefer regenerating it from a
   source script in `scripts/build_fixture.py` rather than committing
   a one-off blob.

## Why these files live in git

The alternative — fetching them on first test run — was rejected because
it adds a network dependency to `pytest -m "not slow"` and obscures the
diff when a sample is updated. The largest file (`notes.pdf`, ~10 MB)
is the upper bound we'd accept; anything larger should go to a
dedicated fixture-generation script and the test should skip when the
fixture is missing.
