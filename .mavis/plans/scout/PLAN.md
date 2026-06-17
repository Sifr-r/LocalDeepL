# LocalDeepL "Best Possible" — Synthesis Plan

> **Audience**: solo maintainer of LocalDeepL (FastAPI/OCR service, Windows / uv / pytest-uv workflow, hybrid OCR + grounded pipeline).
> **Depth contract**: deep-report. Multi-section, evidence-backed, every recommendation traces to an upstream track section and/or a `file_path:line_number` in the LocalDeepL repo.
> **Date**: 2026-06-14.
> **Inputs consumed** (read in full before drafting):
> - [track-md.md](track-md.md) — Anything-to-Markdown landscape (1,336 lines, 4 sub-evidence files)
> - [track-schema.md](track-schema.md) — Schema / table-extraction landscape (396 lines + evidence ledger)
> - [track-ocr.md](track-ocr.md) — AI OCR vision models (626 lines + evidence file)
> - [track-localdeepl.md](track-localdeepl.md) — Internal state map (381 lines, every claim sourced `[path:line]`)
>
> **Markers**: `[F]` = fact from source; `[A]` = analysis/inference/synthesis; `[C]` = contradiction surfaced; `[open]` = unresolved question.

---

## 1. Executive Summary

LocalDeepL is a mature, narrowly-scoped local-first OCR service. Its hybrid path (Surya detection → VLM OCR → DP alignment → refine → post-process → document processors → PDF embed) sits in the **2026 architectural center of gravity** — the same Surya+VLM hybrid used by Marker, Docling, and MinerU, but with a Windows one-click install story (`install.bat`/`start_app.vbs`) and a per-page dense/sparse `dense_mode="auto"` router that no competitor exposes. [F — `AGENTS.md:39`; track-md §2.2.1–2.2.3; track-ocr §5.4]

**The headline finding**: LocalDeepL is *already in the right neighborhood*. The path to "best possible" is **not** a re-architecture — it is **12 surgical extensions into 7 existing slots** (`grounded_backend`, `document_processors`, `aligner`, `ocr_processor`, `page_preprocessor`, `OutputWriter`, `ProcessSettings`) plus 4 production-readiness fixes (auth, metrics, async, IR round-trip). Every recommended extension has a working upstream OSS artifact, a published benchmark, and a precise drop-in location in this repo. [A — synthesis of track-ocr §7, track-md §6, track-schema §6, track-localdeepl §4–5]

**Top-line recommendations** (ranked by ease-of-integration / impact ratio, full evidence in §6):

1. **Adopt `dots.mocr` 3B as a first-class `grounded_backend` candidate** — Apache-style license, olmOCR-bench 83.9, vLLM-integrated, 1-2 days of wiring. (track-ocr §7.2.1) [F]
2. **Add a `Pydantic`-native `structured_extraction` processor** (the canonical "give me `List[Invoice]`" API). Marker has it as `ExtractionConverter` (beta); LocalDeepL can ship it cleaner. (track-schema §6 G1) [A]
3. **Fix the `pages_structured ↔ DocumentResult` lossy round-trip** (track-localdeepl §9 finding #8, §6.7 here). The IR round-trip is the precondition for ~half of the other recommendations.
4. **Document the Markdown schema + add a `markdown_flavor` enum** (`gfm` / `gfm_html_tables` / `docling_like`). The #1 integration friction in 2026 is Markdown-schema divergence. (track-md §6.1, §3.2) [A]
5. **Adopt `pymupdf_layout` as opt-in `aligner` swap** — only if a customer demands it; closed-source license makes it default-off. (track-md §6.3) [A]
6. **Replace `ZAIHostedOCR` with `PaddleOCR-VL-1.5` as the default `grounded_backend` for the experimental slot** — Apache-2.0, OmniDocBench v1.5 94.93, 109 languages. (track-ocr §7.2.4; track-schema §6 G7) [F]
7. **Add a Magika content-sniff dispatcher** at the head of the pipeline so file-extension-only routing is replaced with content-aware routing. (track-md §6.1, §4.3) [A]
8. **Add `xlsx`, `html`, `jats-xml`, `chunks` output writers** — current surface is `docx_writer` only. (track-md §6.6) [A]
9. **Add an `effort` knob** to `ProcessSettings` (`low`/`medium`/`high`) — borrow MinerU v3.3 design. (track-md §6.1) [A]
10. **Wire `TATR-v1.1-All` for structure** on top of the existing `TableExtractionProcessor` (column-separator heuristic), so scientific/financial tables stop being the worst fixture in `scripts/confidence_eval.py`. (track-schema §6 G3; track-localdeepl §8) [A]
11. **Replace greedy IoU matching with Hungarian** in `src/local_deepl/evaluation.py:20-22` so the confidence harness stops under-reporting on multi-column pages. (track-localdeepl §8.1) [A]
12. **Production-readiness work** that should be parallelised: bearer-token auth on `/api/*`, Prometheus metrics, Celery-backed async `/process`, persistent job history. (track-localdeepl §9) [A]

**Sequencing** (full roadmap in §7): **Phase 1 (Week 1-2, S+M each)** = Markdown schema doc + Dots.mocr wired + `pages_structured`/IR round-trip fix + Hungarian matching + dead `ai.py` cleanup. **Phase 2 (Week 3-5, M each)** = Pydantic structured extraction + PaddleOCR-VL-1.5 swap + Magika dispatch + xlsx/html/chunks output writers. **Phase 3 (Week 6-10, L each)** = TATR-v1.1-All + pymupdf_layout opt-in + async OCR + metrics + auth + benchmark CI lane.

**The bar for "best possible"** (full definition in §5):
- **Quality** — match or beat the OmniDocBench v1.5 overall leaderboard (PaddleOCR-VL-1.6 96.3) on the existing `examples/*.pdf` fixtures; olmOCR-bench ≥ 80 on a 50-doc mini subset; F1 ≥ 0.9 on forms (currently the worst class across the industry per Marker README). [F — track-schema §4, track-ocr §4.1]
- **Latency** — match Surya 2's 5.35 pages/s on RTX 5090 for the hybrid path; no regression on the existing `examples/dense.pdf` wall-clock. [F — track-ocr §4.4]
- **Format coverage** — at minimum: PDF, image (PNG/JPG/AVIF/TIFF), DOCX, HTML, EPUB via shelling; PPTX/XLSX/email/audio as opt-in extensions. [A — gap analysis from track-md §3.1]
- **Structured output** — first-class Pydantic / JSON Schema round-trip with per-page typed results. [A — track-schema §6 G1]
- **UX** — Windows one-click install (already done); error recovery that doesn't lose page indices; visible progress for the 5-stage hybrid pipeline. [A — track-localdeepl §9 friction]
- **License posture** — remain MIT/Apache-2.0-only for the default install; treat Surya-2 (modified-OpenRAIL-M, $5M gate) and Chandra OCR 2 (modified-OpenRAIL-M, $2M gate + non-compete) as opt-in. [F — track-ocr §6; track-md §3.4]

The **non-recommendation** is equally important: do **not** chase broad cloud-style "anything-to-MD" coverage (audio, video, email, WebVTT). The Docling / Markitdown / Unstructured space already has those, and trying to match them dilutes LocalDeepL's wedge. [A — track-md §5.3, §6]

---

## 2. Scope and Methodology

### 2.1 Scope

This plan covers LocalDeepL as it exists on 2026-06-14 at `C:\Users\rahin\LocalDeepL`. The audience is the solo maintainer; the deliverable is a sequenced implementation roadmap, not a feature manifesto. Out of scope: re-branding, multi-tenant SaaS, cloud deployment, on-prem enterprise packaging.

### 2.2 Method

1. **Read all four upstream tracks in full** (≈ 2,700 lines of scout output) before writing any recommendation. The scout deliverables each carried inline `[F]/[A]/[C]` markers and `file_path:line_number` citations.
2. **Cross-reference each recommendation against at least two tracks** where possible. Single-source claims are explicitly flagged.
3. **Trace every recommendation to a concrete LocalDeepL extension point** (`grounded_backend`, `document_processors`, `aligner`, `ocr_processor`, `page_preprocessor`, `OutputWriter`, `ProcessSettings`) per the task brief's hard rules.
4. **Map each recommendation to a phase** with rough effort (S/M/L or days) and acceptance criteria.
5. **Surface — do not silently resolve — contradictions** flagged by the upstream tracks (§9).
6. **Honour the report-writing Hard Principles** from `references/report.md`: Traceability, Synthesis-not-concatenation, Contradictions-explicit, Fact-vs-analysis markers, Executive Summary first. (See the reasoning-chain in §6 for the synthesis quality bar.)

### 2.3 Limits and caveats

- **No live benchmark numbers were collected by this synthesis task.** All quality numbers are quoted from upstream tracks. Re-verify any benchmark before quoting externally (track-ocr §1 caveat: "model state and benchmark numbers are a moving target"). [F]
- **No user research was conducted.** The "best possible" bar in §5 is an inference from the four scout tracks, the maintainer's profile (Windows / uv / pytest-uv), and the existing `AGENTS.md` constraints. The bar is revisable. [A]
- **The grounded web route** was re-verified by reading `track-localdeepl.md` (a re-derivation would require running the server). The dead `ai.py` claim is sourced from track-localdeepl.md:53 and `server.py:85-91` was not opened in this synthesis. [open — see §9]
- **License posture** for `dots.mocr` model weights (separate from code) is *not* verified by this synthesis. Track-ocr §10.9 explicitly defers. [open]

---

## 3. Coverage Matrix (Track → Section → Contribution)

| Upstream track | Section that consumes it | What was taken from the track | What was excluded (and why) |
|---|---|---|---|
| **track-md** (Anything-to-MD) | §4.1, §4.2, §5, §6.6, §6.7, §6.9, §8 | Pricing matrix, license matrix, Markitdown plugin pattern, Mammoth style-map DSL, Zerox `maintainFormat`, MinerU `effort`, Pandoc shell-out for non-PDF, DocTags lossless IR | Microsoft 365 Copilot internals (not a competitor — no public MD export, track-md §2.1.1); Apple Vision per-character confidence (overkill for LocalDeepL's use case); Box / Dropbox Sign (different product category, track-md §2.1.5); vLLM-vs-LiteLLM technicalities (covered in track-ocr) |
| **track-schema** (Schema/tables) | §4.1, §4.2, §5, §6.7, §6.8, §8 | OmniDocBench v1.6 leaderboard (96.3 SOTA), Marker's `ExtractionConverter` shape, PaddleOCR-VL table quality, TATR-v1.1-All specifics, Instructor multi-provider glue, FormParser-vs-LayoutParser-vs-CustomExtractor comparison | Mathpix ($0.004/page) and Mistral OCR service (cloud-only, not local-compatible); PubTables-1M GriTSTop micro-numbers (covered in track-ocr); per-row OmniDocBench TextEdit/ReadOrderEdit columns (too granular for the bar) |
| **track-ocr** (AI OCR VLMs) | §4.1, §4.2, §5, §6.1, §6.3, §6.4, §8 | olmOCR-bench leaderboard (Datalab API 86.7, Chandra 2 85.9, dots.mocr 83.9, Surya 0.65B 83.3), license matrix, vLLM-first provider pattern, Qwen3-VL family grounding, Phi-4-multimodal as a small ocr_processor, throughput numbers | 12 "negative findings" from track-ocr §2 (NV-OCR doesn't exist, Cosmos-OCR doesn't exist, VISTA-3D is medical, Florence-VL is paper-only) — excluded from recommendations but kept in §9 open questions; Pixtral Large 124B (cloud/closed); Nemotron Parse 1.1 numbers (track-ocr defers) |
| **track-localdeepl** (state map) | §4, §5, §6 (all subsections), §7, §8, §9 | Pipeline stage line numbers, extension-point slot table, all 6 document-processor summaries, the 20 known-tech-debt items, the friction-specific-to-current-extension-points list, the 5 open questions | Nothing excluded — the state map is the *target*; the synthesis reads it as ground truth and binds the upstream scout findings onto it |

**Important excluded findings**:
- `track-md` sources an `azure.microsoft.com/en-us/pricing/details/document-intelligence/` page that renders "$-" placeholders. The pricing rows in track-md §3.3 are best-effort secondary citations. The synthesis does not re-quote pricing for LocalDeepL — the product is local-first; cloud pricing is reference-only.
- `track-ocr` cites 3 "NV-OCR" / "Cosmos-OCR" / "VISTA-3D" as non-existent in the user's brief. These are dropped — they were brand-naming mistakes. (track-ocr §10 items 1, 2, 3) [C]
- `track-schema` cites a Markitdown vs LocalDeepL benchmark script `scripts/markitdown_compare.py` as a recommended gap. LocalDeepL's `scripts/confidence_eval.py` already covers the regression case; adding Markitdown specifically is *not* recommended in this plan because Markitdown's "low-fidelity by design" positioning makes a side-by-side mostly measure format compatibility, not quality. (track-md §6.9) [A]

---

## 4. Where LocalDeepL Stands Today

This section is the synthesis: it reads the state map against the upstream tracks and surfaces the four-corners honest self-assessment.

### 4.1 Strengths (cited)

- **Hybrid architecture matches the 2026 winner's circle.** LocalDeepL's `HybridEngine` (`src/local_deepl/core/workflows/hybrid.py:89-320`) implements "Surya detection → VLM OCR → DP alignment → refine" — the same pattern Marker uses (`marker/converters/pdf.py:101-138`) and the same pattern Docling's `StandardPdfPipeline` runs in 5 threaded stages (`docling/pipeline/standard_pdf_pipeline.py:393-435`). [F — track-ocr §5.4; track-md §2.2.1–2.2.2] The differentiator: LocalDeepL's per-page sparse/dense auto-routing (`dense_mode="auto"`, `core/workflows/hybrid.py:198-204`) is a more refined trigger logic than Marker's blanket `--use_llm` flag.
- **Six document processors, all wired.** `src/local_deepl/core/processors.py:77-509` ships `reading_order`, `quality_analysis`, `structure_analysis`, `section_analysis`, `layout_enrichment`, `table_extraction` with a clean Protocol + registry + factory pattern. The body of work done here (per-page metadata for `quality`, `structure`, `sections`; per-block metadata for `layout`, `table`) is genuinely better-architected than Marker's flat processor list. [F — track-localdeepl §5]
- **Token-bound artifact store + WebSocket progress.** `src/local_deepl/api/services/artifacts.py:67-` plus `api/routers/websocket.py:103` is a non-trivial production pattern that the 2026 OSS leaders generally don't ship (Docling exposes CLI / FastAPI / Gradio but not the same channel+token abstraction; Markitdown is single-shot CLI). [F — track-localdeepl §2; track-md §2.2.2–2.2.3]
- **Windows one-click install + hidden start + stop + Playwright smoke test** (`install.bat` / `start_app.vbs` / `stop_app.bat` / `test_ui.py`). This is the single most underrated moat — no OSS competitor in the track-md survey tells the Windows story. [F — track-md §2.2.1, §2.2.3]
- **SSRF guard in `utils/security.py` + bearer-token artifact retrieval** — `is_ssrf_target(api_base)` is fail-closed; the default `ALLOW_SSRF_LOCAL=true` is the local-dev default with a clear escape hatch. The cloud half of the field (Azure / Google / Adobe) does not have an SSRF guard story because they never see an arbitrary user-supplied `api_base`. [F — track-localdeepl §2, `AGENTS.md:118`]
- **OCR-pipeline evaluation harness.** `scripts/confidence_eval.py:108-142` and `scripts/confidence_image.py:136-167` output a Rich table with `block_recall` / `avg_iou` / `avg_text_similarity` and per-document unmatched-GT snippets. The cross-axis-order auto-detect (`src/local_deepl/evaluation.py:8-13`) is a small but real production detail. [F — track-localdeepl §8.1]
- **Lossless PDF embed is the default output.** `PDFHandler.embed_structured_text` writes a sandwich PDF (image + invisible OCR text) — a feature that only Azure `prebuilt-read` v4.0 explicitly returns (`learn.microsoft.com/.../prebuilt/read`, track-md §2.1.1) and is rare in the OSS field. [F]

### 4.2 Gaps (cited)

- **No first-class Pydantic schema extraction.** `api/routers/extraction.py:18-111` + `api/services/ai.py` only does freeform-prompt structured extraction against `ExtractionTemplate` enum (`invoice` / `resume` / `academic` / `custom`). Marker ships `ExtractionConverter` (beta, `marker/converters/extraction.py`) which is the canonical "give me `List[MySchema]`" workflow. The gap is acute for downstream RAG/ETL consumers. [F — track-schema §6 G1; track-localdeepl §6.5]
- **Markdown schema is implicit, not documented.** The output of `embed_structured_text` is a sandwich PDF; the parallel `pages_text` dict drives `docx_writer` and the export routes. There is no `markdown_flavor` field, no documented heading/list/table convention, no "are tables GFM pipe-tables or HTML-tables?" answer in the public API. The four upstream tracks converge on this as the #1 integration friction. [A — track-md §1.4, §6.1]
- **Lossy `pages_structured ↔ DocumentResult` round-trip.** `core/document.py:80-86` accepts `source_processor` from the engines (`"hybrid"` / `"grounded"`) but `to_pages_data()` (`document.py:94-98`) drops `kind`, `confidence`, `spans`, and `metadata`. So a custom processor that writes `block.metadata["my_custom_thing"]` is invisible to the legacy output writer. This is the precondition bug for half the recommendations below. [F — track-localdeepl §9 finding #8]
- **Greedy IoU matching in the confidence harness.** `src/local_deepl/evaluation.py:20-22` uses "deterministic, close enough for a confidence summary" greedy matching. Under multi-column pages this under-reports; the digital/hybrid/handwritten fixtures are hand-built so they don't show the bias, but the dense.pdf fixture (bootstrapped from the hybrid pipeline's own output) is a regression-only signal, not an absolute one. [F — track-localdeepl §8.1, §9]
- **`ZAIHostedOCR` is a skeleton.** `src/local_deepl/core/grounded.py:281-373` and `__init__.py:43` export it; `SUBMIT_PATH` / `TASK_PATH` are unverified placeholders (`grounded.py:304-310`). Anyone reading the public exports and instantiating it gets a 404. (track-localdeepl §7 #10)
- **Dead `api/routers/ai.py` router.** Defines 4 routes, none mounted in `server.py:85-91`. ARCHITECTURE.md:54 still claims it's "consumed by extraction.py and translation.py" — both claims are wrong. (track-localdeepl §7 #4)
- **No auth / rate-limit / metrics on `/api/*`.** Bearer token is on artifact GETs + WebSocket only. A single client can flood `/process` and consume the entire GPU/LLM budget; no Prometheus counter, no per-page latency histogram. (track-localdeepl §9 friction)
- **Sync `/process` blocks the uvicorn worker for the entire OCR duration.** A 100-page dense document takes minutes; one request, one worker, no internal queueing. `/api/translate/async` uses Celery but `/process` doesn't. (track-localdeepl §9 friction)
- **In-memory job history, 50-cap, lost on process restart.** `api/services/jobs.py` + `state.py:1-9` are mutable process globals. Two workers behind a load balancer won't share state. (track-localdeepl §9 friction)
- **No `pip-licenses` audit / no documented license posture.** Surya-2 (modified-OpenRAIL-M, $5M gate) and Chandra OCR 2 (modified-OpenRAIL-M, $2M gate + non-compete) are bundled; the README does not call this out. (track-ocr §6.2; track-localdeepl §7 #9)
- **The `quality_routing` slot records decisions but no consumer acts on them.** `core/routing.py:30-53` writes `page.metadata["routing"]`; no API surface exposes it. (track-localdeepl §9 open question #4)
- **Layout/table processor metadata never appears in response headers.** Compare to `X-Document-Quality`, `X-Document-Structure`, `X-Document-Sections` which do. (track-localdeepl §9 open question #5)

### 4.3 Synthesis: the four-corners honest read

| Corner | Verdict | Source |
|---|---|---|
| Architecture | **Mature**, in the 2026 winner's circle | track-ocr §5, track-md §5.1 |
| Extension points | **Well-designed** but under-populated | track-localdeepl §4 |
| Quality measurement | **Functional** but absolute-quality-blind (regression-only on 2 of 5 fixtures) | track-localdeepl §8 |
| Production readiness | **Lacking** (no auth, no metrics, no async OCR, no horizontal scaling) | track-localdeepl §9 |

The implication for the plan: **the architecture investment has paid off; the next 6 months of work is *extension density* and *production hardening*, not re-architecture.** [A]

---

## 5. What "Best Possible" Means Here

The brief asked for "measurable targets where possible." This section defines the bar, scoped to LocalDeepL's actual user (the solo maintainer + the LocalDeepL install base on Windows).

### 5.1 Quality targets

- **Hybrid path** (default): match or beat the OmniDocBench v1.5 overall leaderboard (PaddleOCR-VL-1.6 96.3) *on the existing `examples/*.pdf` fixtures*. Concretely: `block_recall ≥ 0.95` on `digital.pdf`, `≥ 0.90` on `hybrid.pdf`, `≥ 0.85` on `handwritten.pdf`, `≥ 0.80` on `dense.pdf`, `≥ 0.90` on `notes.pdf` — measured against the hand-built ground truth for the first 3 and the bootstrapped regression for the last 2. [F — track-schema §4.1; track-localdeepl §8.1]
- **Grounded path**: olmOCR-bench ≥ 80 on a 50-doc mini subset. The bar is the 2026 PaddleOCR-VL-1.5 94.93 / dots.mocr 83.9 / Chandra 2 85.9 cluster; the floor is Marker 76.1. [F — track-ocr §4.1]
- **Forms F1 ≥ 0.9** — currently the worst class across the industry per Marker README ("Forms may not be rendered well"; Docling 68.4/3.40 on forms per track-schema §2.2.2). A target of 0.9 is aggressive but achievable with TATR-v1.1-All + VLM hybrid. [A]
- **CJK and RTL**: Chinese 82.5 → 88; Arabic 72.7 → 80; Hebrew parity with the current English baseline ± 5 points. [F — track-ocr §2.6, language table]

### 5.2 Latency targets

- **Hybrid path** on 1× RTX 5090 (32 GB): 5.35 pages/s as the existing reference (Surya 2's measured throughput, track-ocr §4.4). LocalDeepL should match or exceed this with the current processor chain *turned off*. With the full chain on, a 2× regression is acceptable for the first call (one-time model load), but steady-state should be within 1.5× of Surya-only. [F]
- **Grounded path** on 1× H100 80GB: 1.44 pages/s as the Chandra 2 reference (track-ocr §4.4). LocalDeepL's `GroundedEngine` is one forward pass, so it should be on par with dots.mocr (~0.9 s/page) or PaddleOCR-VL-1.5 (1.86 s/page on A100). [F]
- **CPU path** (no GPU, Apple M-series, low-end Windows): Surya 2 via llama-server at 0.108 pages/s (track-ocr §4.4) is the floor. PP-OCRv6 medium at 0.13s on A100 / 6.1× speedup on M4 OpenVINO (track-ocr §4.4) is the ceiling for the CPU-only fallback. [F]
- **No regression on `examples/dense.pdf` wall-clock** as a hard regression rule in CI. (track-localdeepl §9) [A]

### 5.3 Format-coverage targets

- **Tier 1 (in-box, no shelling)**: PDF, image (PNG/JPG/AVIF/TIFF) — already done; tighten.
- **Tier 2 (in-box, opt-in)**: DOCX via existing `docx_writer` reversed; HTML via new `html_writer`.
- **Tier 3 (shell-out, opt-in)**: PPTX, XLSX, EPUB via pandoc with license acceptance. LocalDeepL is *not* the right place to host a Pandoc-equivalent. (track-md §2.2.8, §6.7) [A]
- **Out of scope (do not chase)**: audio, video, email, WebVTT. (track-md §5.3, §6.2) [A]

### 5.4 Structured-output targets

- **Pydantic-native `extract()`** that takes a `BaseModel` subclass and returns `list[BaseModel]` per page. Marker `ExtractionConverter` is the reference shape; LocalDeepL can ship cleaner. (track-schema §6 G1) [A]
- **JSON Schema round-trip** on the input side: mirror Gemini's `responseSchema` (OpenAPI 3.0 subset) and the broader JSON Schema keywords (`anyOf`, `$ref`, `minimum/maximum`, `additionalProperties`, `type:'null'`, `prefixItems`). (track-md §6.7) [A]
- **No silent coercion** — if the LLM returns malformed JSON, the response is a typed `ExtractionError`, not a defaulted object. (track-schema §6 G5) [A]

### 5.5 UX targets

- **Windows one-click install** — already done. Don't regress.
- **Visible 5-stage progress** (convert / detect / ocr / refine / embed) — already done. Don't regress.
- **No silent page loss** — failed pages are visible via the `X-Failed-Pages` header (already done, `ocr.py:469-470`). Extend to a per-page `X-Failed-Pages-Detail` header.
- **Per-page confidence score in the response** — currently absent; should be the next UX-driven addition.
- **Error recovery that does not lose the artifact ID** — currently a 500 in `/process` loses the artifact; should at least persist the partial result.

### 5.6 License targets

- **Default install is MIT/Apache-2.0-only.** No modified-OpenRAIL-M in the default pipeline.
- **`surya-ocr`** (the current aligner) is currently Apache-2.0 code with modified-OpenRAIL-M weights (track-ocr §6.2, $5M gate). Document the gate in the README; surface an opt-out path for users above the threshold.
- **`chandra-ocr`** (currently *not* a LocalDeepL dep — only mentioned as the next experimental slot): the $2M gate + non-compete clause is a real ceiling. (track-ocr §6.2)
- **No GPL or AGPL dependency in the default install.** Pandoc is GPL-2.0+; the *use* is fine, the *link* is not. (track-md §3.4) [A]

### 5.7 Non-targets (explicit "do not chase")

- **Audio/video/email transcript** — Docling already does audio via `AsrPipeline`; Markitdown via `audio-transcription` / `az-content-understanding` (video). LocalDeepL's Wedge is local-first, higher-fidelity PDF + image, VLM-as-escape-hatch. Audio/video is *not* LocalDeepL's wedge. (track-md §5.3, §6.2; track-ocr §5.1) [A]
- **Multilingual universal coverage** — Surya's 90+ languages is good enough for the default; PaddleOCR-VL-1.5's 109 languages is good enough for the grounded fallback. 200+ languages (Azure / Google) is not a target. (track-ocr §6.1) [A]
- **Cloud-only accuracy parity** — Gemini 3 Pro 92.91 on OmniDocBench is the cloud reference, not the local target. (track-schema §4.1) [A]
- **LlamaIndex / LangChain / RAGFlow integration breadth** — Marker, MinerU, Docling all ship these; the LocalDeepL wedge is the *core* pipeline, not the integration breadth. (track-md §2.2.1–2.2.3) [A]
- **CSS-faithful HTML / DOCX round-trip** — Mammoth's `style-map` DSL is impressive but niche; LocalDeepL's `docx_writer` should produce a clean readable DOCX, not a style-perfect one. (track-md §6.6) [A]

---

## 6. Recommendations, Grouped by LocalDeepL Extension Point

Each recommendation carries: **evidence chain** (upstream track + LocalDeepL file:line), **trigger/condition**, **impact** (S/M/L or % delta), **confidence** (F or A), **verification path**, **mitigation** (if any). Per-recommendation evidence chains are also in Appendix C; this section is the reader-friendly view.

### 6.1 `grounded_backend`

The `grounded_backend` slot is a single Protocol field on `OCRPipeline` (`src/local_deepl/pipeline.py:50-55`) with two implementations: `PromptedGroundedOCR` (`core/grounded.py:414-…`) and `ZAIHostedOCR` (`core/grounded.py:281-373`, experimental/skeleton). The slot is exercised only when `settings.pipeline_mode == "grounded"` (`api/routers/ocr.py:312-325`).

#### R-G1. Adopt `dots.mocr` 3B as a first-class `grounded_backend` candidate. **PRIORITY: HIGH**

- **Evidence**: track-ocr §7.2.1, §3, §4.1 — olmOCR-bench 83.9, MIT code, vLLM-integrated, 3.0B params, OmniDocBench v1.5 1059 Elo, DocVQA 91.85, OCRBench 86.0. The `GroundedOCRBackend` Protocol contract (`core/grounded.py:66-85`) already expects per-element layout JSON; dots.mocr's output shape matches.
- **Trigger/condition**: `grounded_backend="dotsmocr"` in `ProcessSettings`; default still `PromptedGroundedOCR` until eval is run.
- **Impact**: M (expected olmOCR-bench lift from 78-ish baseline to 83+ on the test fixtures; throughput parity on A100).
- **Confidence**: F (track-ocr cites both a benchmark table and a run command from the upstream README).
- **Verification**: add a 50-doc `olmocr-bench-mini` runner to `scripts/` (track-ocr §7.2.11) and re-run `scripts/confidence_image.py` head-to-head `PromptedGroundedOCR` vs `DotsMOCRBackend`.
- **Mitigation**: the model weight license is "separate from MIT" per the upstream README; track-ocr §10.9 defers. Pin a `pip-licenses` audit gate.
- **File touch**: new `core/grounded_dotsmocr.py` (~200 lines) + a `grounded_backend` string in `ProcessSettings.grounded_backend` field validation.

#### R-G2. Replace `ZAIHostedOCR` with `PaddleOCR-VL-1.5` (or `PaddleOCR-VL-1.6`) as the next-experimental `grounded_backend`. **PRIORITY: MEDIUM**

- **Evidence**: track-schema §6 G7; track-ocr §7.2.4. PaddleOCR-VL-1.5 94.93 on OmniDocBench v1.5, 109 languages, Apache-2.0, vLLM-supported, `OmniDocBench v1.5 = 94.5%`. PaddleOCR-VL-1.6 96.3 on OmniDocBench v1.6 (track-schema §4.1).
- **Trigger/condition**: add a new `PaddleOCRVLBackend` class; expose behind `grounded_backend="paddleocr-vl"`.
- **Impact**: M (grounded path on multilingual documents gets 5-15 point lift on language spread).
- **Confidence**: F (PaddleOCR's own README; cross-cited in dots.ocr README Elo table).
- **Verification**: run `scripts/confidence_eval.py` with a non-English fixture (Arabic PDF, Chinese PDF) and confirm block recall on the new fixture ≥ existing English baseline.
- **Mitigation**: PaddlePaddle install is large; provide a `paddle-ocr` opt-in extra in `pyproject.toml`.
- **File touch**: new `core/grounded_paddleocr.py`; update `core/grounded.py` Protocol to keep the existing `PromptedGroundedOCR` and `ZAIHostedOCR` exports for backward compatibility.

#### R-G3. Wire `Phi-4-multimodal` 5.6B as a small-class `grounded_backend` for low-VRAM installs. **PRIORITY: MEDIUM**

- **Evidence**: track-ocr §7.2.3, §2.2 — MIT, 93.2 DocVQA, 84.4 OCRBench, vLLM-supported, single-GPU fits at A100/H100 class.
- **Trigger/condition**: `grounded_backend="phi4-multimodal"`.
- **Impact**: M (5.6B is bigger than dots.mocr 3B but smaller than Chandra 2 5.3B and has the highest DocVQA in the small-class).
- **Confidence**: F.
- **Verification**: throughput bench (target: ≥ 1 page/s on A100 80GB) + olmOCR-bench mini.
- **Mitigation**: flash-attn requirement; document `pip install flash-attn` prereq.
- **File touch**: same shape as R-G1; new `core/grounded_phi4.py`.

#### R-G4. Add `maintain_format: bool` to `GroundedEngine` — thread prior-page Markdown into the VLM prompt. **PRIORITY: MEDIUM**

- **Evidence**: track-md §6.1, §4.11 — Zerox's `maintainFormat` mode passes prior page's markdown as context.
- **Trigger/condition**: opt-in via `ProcessSettings.maintain_format=True`.
- **Impact**: S-M (table styling, heading hierarchy, and code-fence decisions stay consistent across pages; lift on multi-page tables and listings).
- **Confidence**: A (the pattern is sound but no published benchmark validates the lift).
- **Verification**: A/B test on `examples/notes.pdf` (10.8 MB, multi-page) — `block_recall` and `avg_text_similarity` deltas.
- **Mitigation**: token-cost increase; document it.
- **File touch**: extend `core/workflows/grounded.py:49-54` to read `pages_text` from previous page and pass to `grounded_backend.ocr_document`; add a `format_context_pages: int` field to `GroundedOCRBackend` Protocol.

#### R-G5. Delete (or mount) the dead `api/routers/ai.py`. **PRIORITY: LOW** (cleanup)

- **Evidence**: track-localdeepl §7 #4. The router defines 4 routes that are duplicated by `translation.py` / `extraction.py`; it is not mounted in `server.py:85-91`. `ARCHITECTURE.md:54` is wrong.
- **Trigger/condition**: code-review trigger, no runtime effect.
- **Impact**: S (confusion removal).
- **Confidence**: F.
- **Verification**: grep `app.include_router` in `server.py:85-91`; confirm `ai` is not in the list.
- **Mitigation**: n/a.
- **File touch**: delete `api/routers/ai.py` and update `ARCHITECTURE.md:54`.

#### R-G6. **Do not adopt** PaliGemma 2 / Gemma 4 / Florence-2 as a `grounded_backend`. **PRIORITY: NEGATIVE**

- **Evidence**: track-ocr §6.2 — Gemma terms are non-commercial-friendly; Florence-2 is 2023-vintage and not SOTA.
- **Mitigation**: surface this as a documented "intentional non-choices" in the README so a future contributor doesn't re-propose.

### 6.2 `document_processors` (new ones)

The catalog at `src/local_deepl/core/processors.py:512-522` ships 6 processors. Each new processor is a class implementing the `DocumentProcessor` Protocol (`processors.py:34-39`) and is wired through `build_document_processors` and the `DocumentProcessorName` enum in `api/schemas/requests.py:30-36`.

#### R-P1. `cross_page_table_merge` processor. **PRIORITY: MEDIUM**

- **Evidence**: track-md §6.2 — MinerU v3.0 explicit cross-page table merge; Marker's `LLMTableMergeProcessor`. track-schema §6 G5 — current `TableExtractionProcessor` (`processors.py:392-509`) operates per-page and emits per-block `table_index/row_index/column_index`, so the seam exists; merge is the missing step.
- **Trigger/condition**: new processor class; opt-in via `document_processors=["cross_page_table_merge", "table_extraction", ...]`.
- **Impact**: M (multi-page tables stop being split into 2 tables in the output).
- **Confidence**: A (heuristic: same column count + similar row heights + adjacent page-break marker).
- **Verification**: A/B on a 3-page table fixture; check that the output `page.metadata["tables"]` has 1 table spanning 3 pages, not 3 tables each on 1 page.
- **File touch**: new `core/processors.py` class `CrossPageTableMergeProcessor` (~80 lines).

#### R-P2. `form_extraction` processor. **PRIORITY: L (high effort, high value)**

- **Evidence**: track-md §6.2 — every OSS tool admits weakness on forms (Marker README, Docling 68.4/3.40 on forms).
- **Trigger/condition**: opt-in via `document_processors=["form_extraction"]`.
- **Impact**: L (forms F1 is the worst class across the industry; a 0.9 F1 is a real differentiator).
- **Confidence**: A.
- **Verification**: needs a form fixture (IRS W-2 / 1099 / bank statement); `block_recall` on key-value pairs.
- **Mitigation**: limit scope to AcroForm PDF + VLM for non-AcroForm in the first cut; full handwriting forms is a Phase 4 stretch.
- **File touch**: new `core/processors.py` class `FormExtractionProcessor` + a `tests/fixtures/ground_truth_form.json`.

#### R-P3. `audio_transcription` / `video_caption_extraction` processors. **PRIORITY: DEFERRED** (not LocalDeepL's wedge)

- **Evidence**: track-md §6.2 — Docling has `AsrPipeline`; Markitdown has `audio-transcription`. The cross-track synthesis explicitly excludes audio/video from the bar (see §5.7).
- **Mitigation**: do not add. If a customer needs it, the right play is a `pandoc-shell` style external tool, not a LocalDeepL processor.

#### R-P4. `long_document_strategy` switch (`eager` / `sliding_window` / `streaming`). **PRIORITY: L**

- **Evidence**: track-md §6.2 — MinerU v3.0 (sliding window + streaming writes) and Docling (document_timeout + per-page partial success) handle long docs in core.
- **Trigger/condition**: `ProcessSettings.long_document_strategy`.
- **Impact**: L (a 1000-page document doesn't OOM the worker; per-page GC enables this).
- **Confidence**: A.
- **Verification**: 1000-page synthetic PDF; measure peak RSS and wall-clock.
- **File touch**: new field in `ProcessSettings`; `EngineBase._cross_page_merge` and the `_run_spellcheck` call sites get the strategy hint.

#### R-P5. `multilingual_ocr` processor (route non-English pages to a multilingual VLM). **PRIORITY: MEDIUM**

- **Evidence**: track-ocr §7.2.9 — Surya handles 90+ langs but Arabic 72.7 / Chinese 82.5 vs English 92.3; a 7B multilingual VLM (Qwen2.5-VL-7B AWQ or Pixtral 12B) as a fallback for non-English batches closes the gap.
- **Trigger/condition**: opt-in; pre-step needs a language detect (Surya provides it for free, or fastText langid).
- **Impact**: M (5-15 point lift on Arabic/Chinese/Hindi documents).
- **Confidence**: A (synthesis from Qwen2.5-VL README + Pixtral card).
- **Verification**: 5 non-English fixture PDFs.
- **File touch**: new processor class + a small `lang_detect` helper.

#### R-P6. `image_quality_routing` (move the existing `core/routing.py` advisory into a processor). **PRIORITY: S**

- **Evidence**: track-md §6.5; track-localdeepl §9 open question #4. The current `QualityRoutingPolicy` records decisions in `page.metadata["routing"]` but no consumer acts on them.
- **Trigger/condition**: refactor — turn the policy into a processor so the metadata side-effect is symmetric with the other 5.
- **Impact**: S (consistency; unblocks §6.9 R-Q2).
- **Confidence**: A.
- **File touch**: move `core/routing.py` to a `Rout*ingProcessor` in `core/processors.py`; update `api/routers/ocr.py:301-307` to run it via the processor chain instead of an inline call.

### 6.3 `aligner` / detector swap

The aligner slot currently has one class (`HybridAligner` at `core/aligner.py:24-…`) which loads Surya's `DetectionPredictor`. DP alignment runs twice (row-major + column-major, picking lower cost). The slot is **required** for the hybrid path (pipeline.py:57-61).

#### R-A1. Add `pymupdf_layout` as an opt-in `aligner` swap. **PRIORITY: M (opt-in, off by default)**

- **Evidence**: track-md §6.3 — PyMuPDF4LLM's advanced Layout Mode is the closed-source `pymupdf_layout` package with its own license. "10× faster / 250× lower cost" claims (track-md §2.2.5).
- **Trigger/condition**: opt-in extra `pymupdf-layout`; `aligner="pymupdf_layout"` in `ProcessSettings`.
- **Impact**: M (latency win on pure-PDF inputs; quality parity or slight regression vs Surya on complex layouts).
- **Confidence**: A (closed-source license, opt-in only).
- **Verification**: `scripts/confidence_eval.py` on `digital.pdf` and `hybrid.pdf`; ensure no regression on `block_recall` and a ≥ 2× wall-clock improvement.
- **Mitigation**: separate license file; `pyproject.toml` extra gate; README callout. **Do not enable by default** (closed-source license).
- **File touch**: new `core/aligner_pymupdf.py`; an `aligner` string field in `ProcessSettings` (currently the aligner is constructed inside `HybridEngine.__init__` only, `core/workflows/hybrid.py:23-…`).

#### R-A2. Add `docling_parse` as an alternative PDF text backend. **PRIORITY: M**

- **Evidence**: track-md §6.3 — Docling's `docling-parse` v6.x is the text-extraction layer; faster and more accurate than `pdfminer.six` for many cases.
- **Trigger/condition**: `aligner_text_backend="docling_parse"` in `ProcessSettings` (or just switch the default).
- **Impact**: M (latency + fidelity on text-based PDFs).
- **Confidence**: F.
- **Verification**: `scripts/confidence_eval.py` on `digital.pdf`; expected `block_recall ≥ 0.95` with sub-second per-page throughput.
- **File touch**: extend `core/aligner.py` text-fetch path; the `PDFHandler.convert_to_images` (`core/pdf.py`) might be the better hook.

#### R-A3. Replace the column-separator heuristic in `TableExtractionProcessor` with `TATR-v1.1-All` for structure recognition. **PRIORITY: M**

- **Evidence**: track-schema §6 G3; track-schema §2.2.2 — TATR-v1.1-All, DETR R18, 110 MB, MIT, GriTSTop 0.9849 on PubTables-1M. The current `TableExtractionProcessor` (`core/processors.py:392-509`) uses a column-separator heuristic; the table is the worst fixture in `scripts/confidence_eval.py`.
- **Trigger/condition**: opt-in via `ProcessSettings.table_structure_model="tatr-v1.1-all"` (or default-on in the next minor).
- **Impact**: M (table-block F1 lift, especially on borderless / scientific / financial tables).
- **Confidence**: F.
- **Verification**: `scripts/confidence_eval.py` on a table-rich fixture (one of `digital.pdf` / `hybrid.pdf`); track `block_recall` and a `table_count` metric (already in `core/evaluation.py:10-25`).
- **File touch**: add `microsoft/table-transformer` as a dep; extend `TableExtractionProcessor` to call TATR's `structure_transform` for table-candidate crops.

#### R-A4. Wire `PaddleOCR-VL-1.5` as an `aligner` swap (or a first-pass `page_preprocessor`). **PRIORITY: M**

- **Evidence**: track-ocr §7.2.4, §7.2.7 — Apache-2.0, 96.3% on OmniDocBench v1.6, multi-tier CPU+GPU deployment, 1.86 pages/s on A100.
- **Trigger/condition**: opt-in extra `paddle-ocr`; `aligner="paddleocr_vl"`.
- **Impact**: M (a different layout detector for layouts Surya misclassifies).
- **Confidence**: A.
- **Verification**: A/B vs Surya on `examples/hybrid.pdf` and `examples/dense.pdf`.
- **Mitigation**: PaddlePaddle install is large; provide a `paddle-ocr` opt-in extra.
- **File touch**: new `core/aligner_paddleocr.py`.

### 6.4 `ocr_processor` (provider selection, fallback chain)

The current `OCRProcessor` (`core/ocr.py:138-497`) is one class wrapping LiteLLM `acompletion` over an OpenAI-compat endpoint. The slot is required for the hybrid path.

#### R-O1. Make `ocr_processor` a fallback chain (list) rather than a single class. **PRIORITY: M**

- **Evidence**: track-md §6.4 — Markitdown / Docling / Unstructured all let the user pick (Tesseract / RapidOCR / EasyOCR / macOCR). LocalDeepL's slot is locked to one class.
- **Trigger/condition**: `ProcessSettings.ocr_fallback_chain=["surya", "paddleocr-vl", "tesseract"]`; on first-engine failure, try the next.
- **Impact**: M (resilience; PP-OCRv6 medium at 0.13s on A100 is the obvious low-end fallback — track-ocr §4.4).
- **Confidence**: A.
- **Verification**: simulate a Surya timeout, confirm `paddleocr-vl` picks up; check `X-Failed-Pages` accuracy.
- **File touch**: refactor `core/ocr.py` into `core/ocr/{processor.py, fallback.py, prompts.py, filters.py}`; add `ocr_fallback_chain` field to `ProcessSettings`.

#### R-O2. Add `Phi-4-multimodal` 5.6B as an `ocr_processor` candidate. **PRIORITY: M**

- **Evidence**: track-ocr §7.2.3 — MIT, 93.2 DocVQA, 84.4 OCRBench, vLLM-supported.
- **Trigger/condition**: `ocr_processor="phi4-multimodal"`.
- **Impact**: M (small-class, MIT, high DocVQA).
- **Confidence**: F.
- **File touch**: new `core/ocr_phi4.py`; extend the `OCRProcessor` class (or new sibling class) to dispatch by model name.

#### R-O3. Add `Florence-2-large` 0.77B as a low-VRAM `ocr_processor` tier. **PRIORITY: L (low priority but low effort)**

- **Evidence**: track-ocr §7.2.6 — MIT, 0.77B, task-token routing (`<OCR>` / `<OCR_WITH_REGION>` / `<OD>`). 5.02 GB min VRAM class. (track-ocr §3)
- **Trigger/condition**: `ocr_processor="florence2"`.
- **Impact**: L (low-VRAM users get a working pipeline).
- **Confidence**: F.
- **File touch**: new `core/ocr_florence2.py`.

#### R-O4. Document and surface the `surya-ocr` modified-OpenRAIL-M gate. **PRIORITY: S (but mandatory for a commercial user above the threshold)**

- **Evidence**: track-ocr §6.2, §7.2.12; track-localdeepl §7 #9.
- **Trigger/condition**: README callout + a `pip-licenses` check in CI.
- **Impact**: S (legal hygiene).
- **Confidence**: F.
- **File touch**: README, `pyproject.toml`, a new `scripts/license_audit.py` (track-ocr §7.2.12).

### 6.5 `page_preprocessor`

The current `PagePreprocessor` Protocol (`core/preprocessing.py:33-38`) is a single class `LocalPagePreprocessor` (`core/preprocessing.py:42-92`) with 5 toggles. It's opt-in (`page_preprocessor=None` unless `preprocessing_options.enabled`).

#### R-PP1. Make `page_preprocessor` format-keyed (image / audio / video dispatch). **PRIORITY: M (defer audio/video to non-targets)**

- **Evidence**: track-md §6.5 — currently one class, no MIME dispatch.
- **Trigger/condition**: `page_preprocessor: Mapping[str, PagePreprocessor]` keyed by MIME.
- **Impact**: M (different preprocessors for line-art scans vs photographs vs PDFs-with-text).
- **Confidence**: A.
- **File touch**: extend `core/preprocessing.py` to a registry pattern; add image-only and pdf-only preprocessors.

#### R-PP2. Add an 8-dimension image-quality score (mirroring Google Enterprise OCR) as a `preprocessing_metadata` field. **PRIORITY: M**

- **Evidence**: track-md §6.5 — Google Enterprise OCR exposes an 8-dimension image-quality score that drives routing decisions (blurriness, noise, dark, faint, text_too_small, document_cutoff, text_cutoff, glare).
- **Trigger/condition**: always on (cheap).
- **Impact**: M (drives `dense_mode` and VLM fallback decisions; unblocks R-Q2 below).
- **Confidence**: A.
- **File touch**: extend `LocalPagePreprocessor`; add 8 fields to `preprocessing_metadata`; consume in `QualityRoutingPolicy`.

#### R-PP3. PP-OCRv6 / Tesseract 5 as CPU-only `aligner` fallback. **PRIORITY: M**

- **Evidence**: track-ocr §7.2.10 — PP-OCRv6 34.5M model, 5.2× OpenVINO / 6.1× Apple M4 speedup, 0.13s on A100.
- **Trigger/condition**: opt-in via `aligner="ppocr-cpu"` or auto-fallback when no GPU detected.
- **Impact**: M (true CPU-only path).
- **Confidence**: F.
- **File touch**: new `core/aligner_ppocr.py`.

### 6.6 Output writers (`docx_writer`, new ones)

The current surface is `OutputWriter = Callable[[str, str, dict, int], None]` (`core/workflows/base.py:7`) with a default of `pdf_handler.embed_structured_text` (`pipeline.py:47`). The web API exposes `POST /api/export/document` (`api/routers/artifacts.py:92`) with `DocumentExportFormat` enum (`json` / `markdown` / `text` / `docling` / `mineru`).

#### R-W1. Add `xlsx_writer`. **PRIORITY: L**

- **Evidence**: track-md §6.6 — Docling exports Markdown, HTML, WebVTT, DocLang, DocTags, lossless JSON. Markitdown exports Markdown only. LocalDeepL exports the same plus `docling` / `mineru` JSON shapes.
- **Trigger/condition**: `DocumentExportFormat.xlsx`.
- **Impact**: L (tables-only export to spreadsheet is a real consumer win for finance/ops).
- **Confidence**: A.
- **File touch**: new `core/xlsx_writer.py` using `openpyxl`.

#### R-W2. Add `html_writer`. **PRIORITY: M**

- **Evidence**: track-md §6.6.
- **Trigger/condition**: `DocumentExportFormat.html`.
- **Impact**: M (HTML is a stepping stone for RAG chunkers that prefer DOM over Markdown).
- **Confidence**: A.
- **File touch**: new `core/html_writer.py`; semantic HTML similar to Mammoth's `div.aside > h2:fresh` style.

#### R-W3. Add `jats_xml_writer`. **PRIORITY: L (specialist)**

- **Evidence**: track-md §6.6 — JATS is the scientific-publishers' standard.
- **Trigger/condition**: `DocumentExportFormat.jats`.
- **Impact**: L (niche but real for scientific-publishing customers).
- **Confidence**: A.
- **File touch**: new `core/jats_xml_writer.py`.

#### R-W4. Add `chunks_writer` (RAG-friendly flat list). **PRIORITY: M**

- **Evidence**: track-md §6.6 — Marker's `chunks` output (flat list of top-level blocks with full HTML per block, designed for RAG).
- **Trigger/condition**: `DocumentExportFormat.chunks`.
- **Impact**: M (RAG chunkers don't have to re-parse Markdown).
- **Confidence**: A.
- **File touch**: new `core/chunks_writer.py`.

#### R-W5. Expose a `style_map` option in `docx_writer`. **PRIORITY: S**

- **Evidence**: track-md §6.6 — Mammoth's `p[style-name='Aside Heading'] => div.aside > h2:fresh` style-map DSL.
- **Trigger/condition**: `ExportDocxRequest.style_map`.
- **Impact**: S (DOCX fidelity is already fine for the common case; the DSL is for the long tail).
- **Confidence**: A.
- **File touch**: extend `core/docx_writer.py`.

### 6.7 Anything-to-MD richness

#### R-M1. Document the Markdown schema + add a `markdown_flavor` enum to `ProcessSettings`. **PRIORITY: S (foundational)**

- **Evidence**: track-md §1.4, §6.1 — every vendor's Markdown is subtly different. Azure uses HTML tables + `<!--PageBreak-->`; Adobe uses base64-embedded images; Marker uses GFM; Docling ships DocTags. LocalDeepL's output is configurable but not enumerated.
- **Trigger/condition**: `markdown_flavor: "gfm" | "gfm_html_tables" | "docling_like" | "markdown_only"` (default `gfm`).
- **Impact**: S (this is the #1 integration friction; documenting it is the lowest-effort, highest-clarity move).
- **Confidence**: A.
- **File touch**: new `ProcessSettings.markdown_flavor` field; a `docs/markdown-schema.md`; thread through `core/docx_writer.py` and the export routes.

#### R-M2. Add a `localdeepl.plugin` entry-point. **PRIORITY: S**

- **Evidence**: track-md §6.1, §4.5 — Markitdown's `markitdown.plugin` entry-point system lets third parties add a `DocumentConverter` and have it auto-registered (`packages/markitdown/src/markitdown/_markitdown.py:42-62`).
- **Trigger/condition**: any third party can `pip install localdeepl-pdf` and have it auto-registered.
- **Impact**: S (low effort, high future leverage).
- **Confidence**: A.
- **File touch**: new `core/plugin_loader.py`; `pyproject.toml` declares the `localdeepl.plugin` entry-point group.

#### R-M3. Add a `magika` content-sniff dispatcher. **PRIORITY: S**

- **Evidence**: track-md §6.1, §4.3 — Markitdown uses `magika.Magika()` (`_markitdown.py:105-109`); Unstructured uses `libmagic`.
- **Trigger/condition**: opt-in via `ProcessSettings.content_sniff=True` (default off for performance; on when extension is ambiguous).
- **Impact**: S (extension-only routing misses content-type mismatches; content-sniff catches `.txt` that's actually a CSV).
- **Confidence**: A.
- **File touch**: new `core/content_sniff.py`; thread into `OCRPipeline.run` at the head.

#### R-M4. Round-trip test for `DocumentResult` IR. **PRIORITY: M (precondition for half the rest)**

- **Evidence**: track-md §6.1, §4.6 — Docling's `DoclingDocument` is lossless; Marker's `Schema` has 28 block types. LocalDeepL's `DocumentResult` is closer to Unstructured's `list[Element]`. track-localdeepl §9 finding #8 — `pages_structured ↔ DocumentResult` is lossy.
- **Trigger/condition**: a test that round-trips `DocumentResult.from_pages_data(p) → ... → DocumentResult` and asserts no `kind` / `confidence` / `spans` / `metadata` is lost.
- **Impact**: M (precondition; unblocks the processor-metadata side-effects like R-P6).
- **Confidence**: F.
- **Verification**: new `tests/test_document_roundtrip.py`.
- **File touch**: extend `core/document.py` so `to_pages_data` accepts a "preserve" flag for the legacy dict shape; or move processors to consume `DocumentResult` end-to-end.

#### R-M5. Adopt Mammoth-style style-map DSL for DOCX ↔ MD. **PRIORITY: M**

- **Evidence**: track-md §6.1 — Mammoth's `p[style-name='Aside Heading'] => div.aside > h2:fresh` (`mammoth/__init__.py:1-42`).
- **Trigger/condition**: opt-in DSL on the docx export.
- **Impact**: M (clean declarative mapping tool; one of Mammoth's killer features).
- **Confidence**: A.
- **File touch**: extend `core/docx_writer.py`.

#### R-M6. Add an `effort` knob to `ProcessSettings`. **PRIORITY: S**

- **Evidence**: track-md §6.1 — MinerU v3.3 added an `effort: "medium" | "high"` parameter to the hybrid backend (medium disables image/chart analysis). README: "Linux: ~80% faster for text PDF scenarios".
- **Trigger/condition**: `ProcessSettings.effort: "low" | "medium" | "high"` (default `medium`).
- **Impact**: S (cheap knob; user can trade latency for image/chart analysis).
- **Confidence**: A.
- **File touch**: extend `ProcessSettings`; thread into `HybridEngine` and `GroundedEngine`.

#### R-M7. Pandoc shell-out for non-PDF inputs. **PRIORITY: M**

- **Evidence**: track-md §2.2.8, §6.7 — Pandoc is the gold standard for non-PDF markup interchange; DOCX/PPTX/XLSX/HTML/EPUB/ODT legs.
- **Trigger/condition**: `ProcessSettings.pandoc_path: str | None`; when input is DOCX/PPTX/XLSX/HTML/EPUB, route through `pandoc -t markdown_strict` first, then send to the OCR path only for image content.
- **Impact**: M (the DOCX/PPTX/XLSX/EPUB/HTML legs finally get a high-fidelity answer; currently they are entirely absent).
- **Confidence**: A.
- **Mitigation**: Pandoc is GPL-2.0+ (track-md §3.4); *use* via shell is fine; do not bundle Pandoc in a pyinstaller/frozen distribution without an LGPL exception.
- **File touch**: new `core/format_dispatch.py`; new `ProcessSettings.pandoc_path` field.

### 6.8 Schema / structured extraction (Pydantic, JSON Schema)

#### R-S1. `structured_extraction` processor — Pydantic-native `extract(schema=MyModel)`. **PRIORITY: HIGH (canonical gap)**

- **Evidence**: track-schema §6 G1 — Marker has `ExtractionConverter` (beta, `marker/converters/extraction.py`). No current product combines Surya layout + structured-output VLM into a single `extract()` workflow.
- **Trigger/condition**: `from localdeepl import extract; class Invoice(BaseModel): ...; extract("invoice.pdf", schema=Invoice)`.
- **Impact**: HIGH (the canonical "schema extraction" API every downstream developer wants).
- **Confidence**: A.
- **Verification**: 5 fixture PDFs (e.g. 5 W-2 forms), measure per-page F1 against ground truth.
- **File touch**: new `core/structured_extraction.py`; extend `api/routers/extraction.py` and `ExtractionRequest` schema (`api/schemas/requests.py:245-264`); use Instructor (`567-labs/instructor`, MIT) for multi-provider glue.

#### R-S2. JSON Schema round-trip on the input side. **PRIORITY: M**

- **Evidence**: track-md §6.7 — mirror Gemini's `responseSchema` (OpenAPI 3.0 subset) and the broader JSON Schema keywords (`anyOf`, `$ref`, `minimum/maximum`, `additionalProperties`, `type:'null'`, `prefixItems`).
- **Trigger/condition**: `ExtractionRequest.schema_: dict` accepts a JSON Schema directly.
- **Impact**: M.
- **Confidence**: F.
- **File touch**: `ExtractionRequest` extension; Pydantic-side validation of the input schema.

#### R-S3. Cloud-output normalizer (Azure / Google / Textract → Pydantic). **PRIORITY: L (niche)**

- **Evidence**: track-schema §6 G4 — cloud APIs return JSON in 3 mutually-incompatible shapes; a library that normalizes all 3 into a single `Page` / `Table` / `Cell` Pydantic model with confidence scores is a small OSS win.
- **Trigger/condition**: `from localdeepl.adapters import azure_di, google_docai, textract; azure_di.parse("result.json") → DocumentResult`.
- **Impact**: L.
- **Confidence**: A.
- **File touch**: new `core/adapters/{azure,google,textract}.py`.

#### R-S4. Cloud-out `grounded_backend` option (Azure `prebuilt-read` for searchable PDF). **PRIORITY: L (deferred; not LocalDeepL's wedge)**

- **Evidence**: track-md §6.4 — Azure `prebuilt-read` returns searchable PDF at no extra cost (`learn.microsoft.com/.../prebuilt/read`).
- **Mitigation**: defer — LocalDeepL's `embed_structured_text` already does the sandwich-PDF job locally.

### 6.9 Routing / quality scoring

#### R-Q1. Expose per-page quality scores in the response. **PRIORITY: M**

- **Evidence**: track-md §6.8 — Google's image-quality score is 8 dimensions; LocalDeepL's `core/routing.py` exists but is not in the public API. track-localdeepl §9 open question #4.
- **Trigger/condition**: extend `X-Document-Quality` header to include 8-dim scores.
- **Impact**: M (drives client-side routing decisions).
- **Confidence**: A.
- **File touch**: extend `quality_analysis` processor + `_document_quality_header` (`api/routers/ocr.py:482-484`).

#### R-Q2. Move `QualityRoutingPolicy` into a processor + wire to per-page confidence. **PRIORITY: M (paired with R-P6)**

- **Evidence**: track-localdeepl §9. The current policy is advisory only.
- **Trigger/condition**: refactor — make the routing a processor that runs after the OCR/spellcheck stage and consumes per-page confidence.
- **Impact**: M.
- **Confidence**: A.
- **File touch**: see R-P6.

#### R-Q3. Add `fallback_to_grounded: bool` to `ProcessSettings`. **PRIORITY: M**

- **Evidence**: track-md §6.8 — `dense_mode="auto"` switches when box count exceeds `dense_threshold`; no per-page *fallback*.
- **Trigger/condition**: when a dense-mode page's confidence is below threshold, automatically re-run with `grounded_backend`.
- **Impact**: M (closes the "low-confidence sparse page" gap).
- **Confidence**: A.
- **File touch**: extend `core/workflows/hybrid.py:271-285` (`_refine_uncertain` is the closest existing seam).

### 6.10 Eval / regression harness

#### R-E1. Replace greedy IoU with Hungarian matching in `src/local_deepl/evaluation.py`. **PRIORITY: S (small upgrade, real quality)**

- **Evidence**: track-localdeepl §8.1, §9 — greedy IoU is "close enough for a confidence summary" but biased toward early high-IoU pairs.
- **Trigger/condition**: swap in `scipy.optimize.linear_sum_assignment` (already a transitive dep via `surya`/`transformers` in most installs; if not, add `scipy`).
- **Impact**: S (closes a 5-10 point under-reporting on multi-column pages).
- **Confidence**: A.
- **File touch**: `src/local_deepl/evaluation.py:20-22`.

#### R-E2. Hand-build `dense.pdf` and `notes.pdf` ground truth (replace bootstrapped regression). **PRIORITY: L (medium effort, high value)**

- **Evidence**: track-localdeepl §9. The bootstrapped fixtures measure "regression against the baseline", not "absolute quality".
- **Trigger/condition**: human-labelled or carefully cross-validated ground truth for both fixtures.
- **Impact**: L (turns the confidence harness from regression-only into absolute-quality).
- **Confidence**: A.
- **File touch**: rewrite `tests/fixtures/ground_truth_dense.json` and `tests/fixtures/ground_truth_notes.json`; document the methodology in `docs/eval-methodology.md`.

#### R-E3. Add `scripts/olmocr_bench_mini.py`. **PRIORITY: M**

- **Evidence**: track-ocr §7.2.11 — olmOCR-bench is the de-facto 2026 OCR VLM leaderboard; running a 50-doc subset against the current default backend in CI catches regressions when a new release lands.
- **Trigger/condition**: a `scripts/olmocr_bench_mini.py` that runs the 50-doc subset and prints a per-doc table.
- **Impact**: M (the cheapest possible answer to "is there a better grounded backend?").
- **Confidence**: F.
- **File touch**: new `scripts/olmocr_bench_mini.py`; new `tests/fixtures/olmocr-bench-mini/` (50 docs from the public `allenai/olmocr-bench` dataset).

#### R-E4. Add `scripts/license_audit.py`. **PRIORITY: S**

- **Evidence**: track-ocr §7.2.12; track-localdeepl §7 #9.
- **Trigger/condition**: CI lane that calls `pip-licenses` and checks for `modified-OpenRAIL-M` / `GPL` / `AGPL` deps.
- **Impact**: S (legal hygiene).
- **Confidence**: F.

#### R-E5. Add A/B scaffold for `binarize` / `dual_engine` / `self_correction` / `deskew` / `denoise` / `normalize_contrast`. **PRIORITY: M**

- **Evidence**: track-localdeepl §9 — each toggle exists in `ProcessSettings` but none have an A/B test scaffold.
- **Trigger/condition**: an `--ab-test` flag on `scripts/confidence_eval.py` that runs the same fixture with and without the toggle and reports the delta.
- **Impact**: M (turns 6 untested toggles into measured ones).
- **Confidence**: A.

---

## 7. Sequenced Roadmap

Effort estimates use S (1 day), M (2-4 days), L (5+ days). Acceptance criteria are concrete and verifiable.

### Phase 1 — Cleanup + low-risk wins (Week 1-2)

| # | Recommendation | Effort | Acceptance criterion |
|---|---|---|---|
| 1.1 | R-G5 (delete dead `ai.py` router) | S | `app.include_router(ai)` not in `server.py:85-91`; `git grep` for `ai.py` shows no external consumers; `ARCHITECTURE.md:54` updated |
| 1.2 | R-M1 (Markdown schema doc + `markdown_flavor` enum) | S | `docs/markdown-schema.md` exists; `ProcessSettings.markdown_flavor` field passes `pytest`; 1 round-trip test against each of `gfm` / `gfm_html_tables` / `docling_like` |
| 1.3 | R-E1 (Hungarian matching) | S | `scipy.optimize.linear_sum_assignment` swapped in; `scripts/confidence_eval.py` reports non-empty `block_recall` deltas on `digital.pdf` |
| 1.4 | R-M3 (Magika content-sniff) | S | `magika` is an opt-in dep; new `core/content_sniff.py`; existing tests pass |
| 1.5 | R-O4 (license audit CI) | S | `scripts/license_audit.py` runs in CI; `pip-licenses --fail-on="modified-OpenRAIL-M"` |
| 1.6 | R-M6 (`effort` knob) | S | `ProcessSettings.effort` field passes validation; `HybridEngine` and `GroundedEngine` accept the field |
| 1.7 | R-W5 (style_map option in `docx_writer`) | S | `ExportDocxRequest.style_map` field; `core/docx_writer.py` parses a Mammoth-style DSL on input |
| 1.8 | R-M2 (`localdeepl.plugin` entry-point) | S | `pyproject.toml` declares `localdeepl.plugin`; a stub `localdeepl-pdf` test plugin auto-registers |

**Phase 1 total**: ~8 days, all S. Zero new heavy deps. No regression risk on existing fixtures.

### Phase 2 — Substantive feature additions (Week 3-5)

| # | Recommendation | Effort | Acceptance criterion |
|---|---|---|---|
| 2.1 | R-G1 (Dots.mocr as `grounded_backend`) | M | `core/grounded_dotsmocr.py`; new `grounded_backend` field accepts `"dotsmocr"`; `scripts/confidence_image.py` head-to-head vs `PromptedGroundedOCR` shows non-regression on `block_recall` |
| 2.2 | R-S1 (Pydantic-native `extract()`) | M (high) | `core/structured_extraction.py`; `ExtractionRequest` accepts a Pydantic model; a 5-form fixture shows ≥ 0.85 per-page F1; uses Instructor for retries/streaming |
| 2.3 | R-G2 (PaddleOCR-VL-1.5 as `grounded_backend`) | M | `core/grounded_paddleocr.py`; opt-in extra `paddle-ocr`; `grounded_backend="paddleocr-vl"` runs on a multilingual fixture |
| 2.4 | R-M4 (`DocumentResult` round-trip) | M | `tests/test_document_roundtrip.py` round-trips and asserts no metadata loss; all 6 document processors' metadata survives |
| 2.5 | R-A3 (TATR-v1.1-All for table structure) | M | `core/processors.py` extended; `tests/fixtures/ground_truth_table.json` added; `block_recall ≥ 0.85` on the new fixture |
| 2.6 | R-Q3 (`fallback_to_grounded`) | M | `ProcessSettings.fallback_to_grounded`; low-confidence sparse pages auto-re-run on the grounded backend; per-page confidence visible in `X-Document-Quality` |
| 2.7 | R-M7 (Pandoc shell-out) | M | `core/format_dispatch.py`; DOCX/HTML/EPUB inputs route through `pandoc -t markdown_strict` first; existing tests pass |
| 2.8 | R-P1 (`cross_page_table_merge` processor) | M | new `CrossPageTableMergeProcessor`; multi-page tables emit 1 table spanning N pages |
| 2.9 | R-P6 / R-Q2 (move `QualityRoutingPolicy` into a processor) | S-M | the policy is a processor; `page.metadata["routing"]` is set by the processor chain |
| 2.10 | R-E3 (`scripts/olmocr_bench_mini.py`) | M | a 50-doc subset from `allenai/olmocr-bench`; per-doc table; integrated with `pytest -m slow` |

**Phase 2 total**: ~22 days, mostly M. This is the substantive product work.

### Phase 3 — Production hardening + opt-in extensions (Week 6-10)

| # | Recommendation | Effort | Acceptance criterion |
|---|---|---|---|
| 3.1 | R-O1 (`ocr_processor` fallback chain) | M | `ProcessSettings.ocr_fallback_chain`; simulated Surya timeout triggers fallback to next engine; `X-Failed-Pages` accuracy maintained |
| 3.2 | R-A1 (`pymupdf_layout` opt-in `aligner` swap) | M | opt-in extra; `aligner="pymupdf_layout"`; `block_recall` no-regression on `digital.pdf` |
| 3.3 | R-A2 (`docling_parse` text backend) | M | opt-in; `block_recall ≥ 0.95` on `digital.pdf` |
| 3.4 | R-W2 (`html_writer`) | M | new `core/html_writer.py`; `DocumentExportFormat.html` |
| 3.5 | R-W4 (`chunks_writer`) | M | new `core/chunks_writer.py`; `DocumentExportFormat.chunks` |
| 3.6 | R-P5 (`multilingual_ocr` processor) | M | language-detect pre-step; 5 non-English fixture PDFs |
| 3.7 | R-PP2 (8-dim image-quality score) | M | `LocalPagePreprocessor` extended; `preprocessing_metadata` has 8 fields; consumed by `QualityRoutingPolicy` |
| 3.8 | R-O2 (Phi-4-multimodal as `ocr_processor`) | M | `core/ocr_phi4.py`; `ocr_processor="phi4-multimodal"`; throughput ≥ 1 page/s on A100 |
| 3.9 | R-E2 (hand-built `dense.pdf` and `notes.pdf` fixtures) | L | new ground truth files; methodology documented; harness becomes absolute-quality, not regression-only |
| 3.10 | R-A4 (PaddleOCR-VL-1.5 as `aligner` swap) | M | opt-in extra; `aligner="paddleocr_vl"` |
| 3.11 | R-P4 (`long_document_strategy`) | L | 1000-page synthetic PDF; peak RSS stays bounded; per-page GC works |
| 3.12 | Production: bearer-token auth on `/api/*` | M | new `api/services/auth.py`; all `/api/*` routes require a token; tests for 401 path |
| 3.13 | Production: Prometheus metrics | M | new `api/services/metrics.py`; counters for `pages_processed` / `pages_failed` / `pipeline_latency_seconds` / `llm_call_latency_seconds` |
| 3.14 | Production: Celery-backed async `/process` | L | new `api/tasks.py::process_ocr_task`; `/api/process/async` mirrors the translation async path |
| 3.15 | Production: persistent job history (SQLite) | M | `api/services/jobs.py` swap to SQLite; cap configurable; survives process restart |
| 3.16 | R-G3 (Phi-4-multimodal as `grounded_backend`) | M | `core/grounded_phi4.py`; `grounded_backend="phi4-multimodal"` |
| 3.17 | R-W1 (`xlsx_writer`) | L | new `core/xlsx_writer.py`; `DocumentExportFormat.xlsx` |
| 3.18 | R-O3 (Florence-2 as low-VRAM `ocr_processor`) | L | new `core/ocr_florence2.py`; `ocr_processor="florence2"` |
| 3.19 | R-A3 (productionize TATR swap — make it the default) | M | `ProcessSettings.table_structure_model` defaults to `"tatr-v1.1-all"`; no regression on existing fixtures |
| 3.20 | R-PP1 (format-keyed `page_preprocessor`) | M | registry; image-only and pdf-only preprocessors |

**Phase 3 total**: ~36 days, mix of M and L. This is the long tail.

### Phase 4 — Stretch (post-10 weeks; explicit non-targets unless user demand)

- R-P2 (`form_extraction` processor) — L+, high-value
- R-S3 (cloud-output normalizer) — L
- R-P3 (`audio_transcription` / `video_caption_extraction`) — only if user demand
- R-W3 (`jats_xml_writer`) — only if user demand
- R-PP3 (PP-OCRv6 / Tesseract 5 as CPU-only fallback) — only if user demand

**The roadmap assumes a solo maintainer working ~2-3 days per week.** Phase 1 = 1 month of part-time work; Phase 2 = 2.5 months; Phase 3 = 4.5 months. Total = ~8 months to "best possible" by this plan's bar.

### Acceptance criteria for "best possible" (composite)

The plan is done when:

1. `block_recall ≥ 0.95` on `digital.pdf`, `≥ 0.90` on `hybrid.pdf`, `≥ 0.85` on `handwritten.pdf` from `scripts/confidence_eval.py` (current baseline, with the new Dots.mocr/PaddleOCR-VL options as fallback paths).
2. Hungarian matching in the eval harness; 5 non-regression CI runs in a row.
3. `from localdeepl import extract; extract(pdf, schema=Invoice)` works end-to-end with `Instructor`-backed retries.
4. `ProcessSettings.markdown_flavor` is documented; `docs/markdown-schema.md` exists.
5. `pip-licenses` audit passes; `surya-ocr` and `chandra-ocr` license gates are called out in the README.
6. Bearer-token auth + Prometheus metrics + Celery-backed async `/process` are in.
7. `scripts/olmocr_bench_mini.py` returns olmOCR-bench ≥ 80 on the 50-doc subset.

---

## 8. Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| **Surya 2 license ceiling** — current default `aligner` is `surya-ocr` with modified-OpenRAIL-M ($5M gate). If LocalDeepL ships with a commercial customer above that gate, the customer's deployment is non-compliant. (track-ocr §6.2) | M | H | R-O4 (license audit); R-PP3 (CPU-only `aligner` fallback that doesn't depend on Surya); document the gate in the README. The non-Surya path (R-A1, R-A2, R-A4) is the long-term answer. |
| **PaddleOCR install bloat** — PaddlePaddle is a large dep; PaddleOCR-VL-1.5/1.6 are the best multilingual local options but the install footprint is real. (track-ocr §7.2.4) | M | M | R-G2, R-A4 are both behind opt-in `paddle-ocr` extras; the default install does not pull PaddlePaddle. |
| **Pydantic schema extraction quality** — `extract(schema=MyModel)` depends on the LLM emitting well-formed JSON conforming to the schema. On real-world forms, the conformance rate is < 100%. (track-schema §5 Pattern 5) | H | M | R-S1 uses Instructor for retries + streaming; the response is a typed `ExtractionError`, not a defaulted object (per §5.4). |
| **`pages_structured ↔ DocumentResult` round-trip is load-bearing** — half the recommendations depend on it. If not fixed first, downstream changes are blocked. (track-localdeepl §9 finding #8) | M | H | R-M4 is Phase 2 #4. Do it before R-P6 / R-Q2 / R-S1. |
| **Hungarian matching changes the numbers** — the absolute `block_recall` may go up or down depending on fixture; this is a one-time reset, not a regression. (track-localdeepl §8.1) | M | L | R-E1 + a documented "before/after" note in `docs/eval-methodology.md`; commit the new baseline. |
| **Pandoc licensing** — Pandoc is GPL-2.0+; shelling out via subprocess is fine for *use*, but bundling in a frozen distribution is a copyleft concern. (track-md §3.4) | L | M | R-M7 keeps Pandoc as an external tool; document the shell-out pattern; do not bundle. |
| **Dots.mocr model-weight license** — track-ocr §10.9 defers verification. (track-ocr §6.2) | M | M | R-O4 (license audit) catches it; if the license is non-commercial, R-G1 is opt-in only. |
| **Wedge dilution** — chasing audio/video/email coverage moves LocalDeepL toward Docling/Markitdown's space, which is crowded. (track-md §5.3) | M | M | §5.7 explicit non-targets; R-P3 deferred; no `audio_transcription` until user demand. |
| **Tech debt accumulates during Phase 2** — adding Dots.mocr + PaddleOCR + TATR + Phi-4 quadruples the `grounded_backend` / `aligner` / `ocr_processor` surface area. (track-localdeepl §7 friction #8) | H | M | R-G5 cleanup in Phase 1; the `localdeepl.plugin` entry-point (R-M2) lets third parties ship out-of-tree; a new `docs/extension-points.md` keeps the surface discoverable. |
| **Production-readiness lag** — the roadmap is heavy on features and light on auth/metrics/async (3.12-3.15 are the production work, deferred to Phase 3). (track-localdeepl §9) | M | H | Production work is in Phase 3 #12-15, not optional. The bar in §5.5/5.6 requires it. |
| **Benchmark drift** — every cited benchmark (OmniDocBench, olmOCR-bench, FinTabNet) is a moving target. (track-ocr §1 caveat) | H | L | Re-verify before quoting externally; the `scripts/olmocr_bench_mini.py` (R-E3) catches regressions. |
| **Scope creep on `form_extraction` (R-P2)** — forms are the worst class across the industry; tempting to over-invest. (track-schema §6 G3, §4.3) | M | M | Phase 4 / explicit non-go for Phase 1-3. |

---

## 9. Open Questions and Contradictions (Lifted from Upstream Tracks)

The plan does **not** silently resolve these. Each is flagged for the maintainer.

### 9.1 From `track-ocr` §10 (12 surfaced)

1. **"NV-OCR-1.0" naming** — does not exist; closest is Nemotron Parse 1.1 + Nemoretriever Page Elements v2. Drop the "NV-OCR" name from any future task brief. (track-ocr §10.1) [C]
2. **"Cosmos-OCR"** — does not exist; Cosmos is a world-foundation-model family. Drop. (track-ocr §10.2) [C]
3. **"VISTA-3D"** — is a medical-imaging 3D segmentation model. Drop. (track-ocr §10.3) [C]
4. **Florence-VL** — is a research paper, not a product. No candidate. (track-ocr §10.4) [open]
5. **Pixtral Large (124B)** — exists (Nov 2024) but model card not directly fetched in scout. Treat as cloud/closed reference only. (track-ocr §10.5) [open]
6. **Surya 2 license ceiling** — modified-OpenRAIL-M, $5M gate. If LocalDeepL scales past $5M, the default `aligner` becomes a ceiling. R-O4 + R-A1/R-A2 are the long-term answer. (track-ocr §10.6) [open]
7. **Mimo-7B-OCR and LightOnOCR-2** — not directly fetched in scout; cited only via third-party benchmark tables. Re-verify before quoting numbers. (track-ocr §10.7) [open]
8. **Nemotron Parse 1.1 specific benchmark numbers** — "competitive accuracy" per arXiv abstract; full tables are in the PDF body which was not deep-read. Re-verify. (track-ocr §10.8) [open]
9. **Dots.mocr model weight license** — README says "separate from MIT". The synthesis did not open the LICENSE file. R-O4 is the gate. (track-ocr §10.9) [open]
10. **DeepSeek-OCR 3B size** — allenai/olmocr says 3B; chandra says no size. The 3B is the consistent claim but should be re-verified. (track-ocr §10.10) [open]
11. **PaddleOCR PP-OCRv6 "surpasses Qwen3-VL-235B and GPT-5.5"** — vendor benchmark. Weight carefully. (track-ocr §10.11) [C]
12. **GOT-OCR-2.0 olmOCR-bench 48.3** — cited by surya README; GOT-OCR's own README has no DocVQA/OCRBench/OmniDocBench. Treat as sanity check. (track-ocr §10.12) [C]

### 9.2 From `track-md` §1.4 (1 surfaced)

13. **Markdown schema divergence** — every vendor emits slightly different Markdown. The plan's R-M1 documents LocalDeepL's schema; the *industry* divergence is unresolved. (track-md §1.4) [open — external]

### 9.3 From `track-schema` §6 (open product questions)

14. **Pydantic vs JSON Schema as the input format** — Marker accepts `Pydantic.model_json_schema()`; Gemini accepts `responseSchema` (OpenAPI 3.0 subset). The plan picks Pydantic as the primary input (R-S1) and JSON Schema as secondary (R-S2). The trade-off: Pydantic is friendlier to Python callers; JSON Schema is friendlier to polyglot callers. (track-schema §6 G1) [A — open]
15. **Cross-page table merge heuristic** — same column count + similar row heights + adjacent page-break marker. No published benchmark validates the heuristic. R-P1 is the first cut; expect 80% accuracy and iterate. (track-md §6.2) [open]
16. **PaddleOCR-VL-1.6 vs PaddleOCR-VL-1.5** — the synthesis picked 1.5 as the safer recommendation (R-G2) because 1.6 is "SOTA on OmniDocBench v1.6" but the 1.6 dataset card is the primary citation (no third-party replication yet). The maintainer can upgrade to 1.6 once third-party benchmarks reproduce. (track-schema §4.1) [A — open]

### 9.4 From `track-localdeepl` §9 (5 open questions)

17. **`ai.py` router — revive or delete?** — R-G5 picks delete. (track-localdeepl §9 #1) [A — picked]
18. **`PipelineMode` enum string-comparison** — is `settings.pipeline_mode == "grounded"` the contract, or should the engine advertise its mode? (track-localdeepl §9 #2) [open]
19. **`core/workflows/__init__.py` re-exports `_notify`** — is the underscore-prefixed helper part of the public API? (track-localdeepl §9 #3) [open]
20. **`quality_routing` is advisory-only** — records decisions in metadata, no consumer acts on them. R-P6/R-Q2 fixes this. (track-localdeepl §9 #4) [A — picked, see R-P6/R-Q2]
21. **`layout_enrichment` and `table_extraction` metadata never in response headers** — oversight or intentional? (track-localdeepl §9 #5) [open]

### 9.5 New contradictions surfaced by this synthesis

22. **Pipeline architecture: `core/ocr.py:138-497` is one class + 2 exception classes in 497 lines.** The recommendations split it into `core/ocr/{processor,fallback,prompts,filters}.py` (R-O1). The `core/document.py` IR is named in the public surface (`from local_deepl import DocumentResult` via `__init__.py` lazy exports per track-localdeepl §2) but the engines don't use it end-to-end (R-M4). These two refactors (R-O1 + R-M4) are coupled and should be sequenced together. (track-localdeepl §7 #9) [A]
23. **Track-md claims "Markit's positioning is LLM-feed by design, LocalDeepL rejects this"** (track-md §1 #5). The maintainer's profile shows the LocalDeepL repo *does* require an external VLM server (LM Studio at `http://localhost:1234/v1` per `AGENTS.md:9`). The two are not in tension (LocalDeepL is local *infrastructure*; the VLM is the model server, not the application), but the framing in track-md is loose. (track-md §1 #5) [C]
24. **Track-schema §2.2.1 cites TATR as "PubTables-1M GriTSTop 0.9849" but Marker's "Avg score 0.816 on FinTabNet" is the *table extraction* metric.** These are different benchmarks on different datasets; do not conflate. (track-schema §4) [C]

---

## 10. Appendix A — Source Index

### 10.1 LocalDeepL source files cited (every recommendation links to one or more)

- `AGENTS.md` — top-level project map, pipeline paths, extension points, validation commands
- `src/local_deepl/__init__.py:1-91` — lazy package-level exports
- `src/local_deepl/pipeline.py:1-133` — `OCRPipeline` facade
- `src/local_deepl/server.py:63-185` — FastAPI app + `local-deepl-server` CLI
- `src/local_deepl/evaluation.py:1-285` — package-root confidence eval
- `src/local_deepl/core/document.py:1-107` — `DocumentResult` IR
- `src/local_deepl/core/processors.py:1-560` — `DocumentProcessor` Protocol + 6 built-ins + factory
- `src/local_deepl/core/preprocessing.py:1-92` — `PagePreprocessor` + `LocalPagePreprocessor`
- `src/local_deepl/core/aligner.py:1-440` — Surya detection + DP alignment
- `src/local_deepl/core/ocr.py:1-497` — `OCRProcessor` + prompts + filters
- `src/local_deepl/core/pdf.py` — `PDFHandler` (convert_to_images + embed_structured_text)
- `src/local_deepl/core/grounded.py:1-676` — `GroundedOCRBackend` Protocol + 2 backends + parsers
- `src/local_deepl/core/postprocess.py:1-…` — `DictionaryPostProcessor`
- `src/local_deepl/core/routing.py:1-60` — `QualityRoutingPolicy`
- `src/local_deepl/core/evaluation.py:1-52` — lightweight processor scoring
- `src/local_deepl/core/translation_config.py` + `core/translation.py` — async translation
- `src/local_deepl/core/docx_writer.py` — Markdown → docx
- `src/local_deepl/core/workflows/base.py:1-83` — `EngineBase` + `_notify` + `_cross_page_merge` + `_run_spellcheck`
- `src/local_deepl/core/workflows/hybrid.py:1-442` — `HybridEngine`
- `src/local_deepl/core/workflows/grounded.py:1-86` — `GroundedEngine`
- `src/local_deepl/core/workflows/__init__.py:1-14` — engine re-exports
- `src/local_deepl/api/routers/config.py:83-…` — `GET/POST /api/config`, `GET /api/models`
- `src/local_deepl/api/routers/ocr.py:1-525` — `POST /process`
- `src/local_deepl/api/routers/websocket.py:86, 103` — progress transport
- `src/local_deepl/api/routers/jobs.py:10, 16` — job history
- `src/local_deepl/api/routers/artifacts.py:32, 58, 92, 137, 167` — artifact download
- `src/local_deepl/api/routers/translation.py:18, 65, 100` — sync + async translation
- `src/local_deepl/api/routers/extraction.py:18-111` — `POST /api/extract`
- `src/local_deepl/api/routers/ai.py:1-108` — **dead router** (R-G5)
- `src/local_deepl/api/routers/state.py:1-9` — module singletons
- `src/local_deepl/api/routers/common.py` — shared helpers
- `src/local_deepl/api/schemas/requests.py:1-291` — Pydantic request models
- `src/local_deepl/api/services/{security,artifacts,jobs,progress,document_metadata,document_exports,workflow,ai}.py` — service layer
- `src/local_deepl/utils/{image,security,litellm_provider,tqdm_patch}.py` — utilities
- `src/local_deepl/resources/dictionaries/` — `ara.json.gz`, `eng.json.gz` (per `ARCHITECTURE.md:269-275`)
- `pyproject.toml:65-66` — `local-deepl-server` entry point
- `examples/` — `dense.pdf` (4.6 MB), `digital.pdf` (126 KB), `handwritten.pdf` (146 KB), `hybrid.pdf` (103 KB), `image.avif` (271 KB), `image.png` (1.0 MB), `notes.pdf` (10.8 MB)
- `tests/fixtures/` — 6 ground-truth JSON files
- `scripts/confidence_eval.py:1-192`, `scripts/confidence_image.py:1-171`, plus 13 other developer scripts
- `install.bat` / `install.ps1` / `start_app.vbs` / `stop_app.bat` / `test_ui.py` — Windows UX

### 10.2 Upstream track sources

- `track-md.md` (1,336 lines) — Anything-to-MD landscape; companion `track-md-evidence.md` + 5 per-vendor files
- `track-schema.md` (396 lines) — Schema/table extraction; companion `track-schema-evidence.md`
- `track-ocr.md` (626 lines) — AI OCR vision models; companion `track-ocr-evidence.md`
- `track-localdeepl.md` (381 lines) — Internal state map

### 10.3 Upstream external sources (subset; the tracks have the full index)

- **Microsoft** — `github.com/microsoft/markitdown` (153k★, MIT, v0.1.6 / 2026-05-26); `learn.microsoft.com/en-us/azure/ai-services/document-intelligence/`; `learn.microsoft.com/.../concept/markdown-elements`; `learn.microsoft.com/.../prebuilt/read`; `github.com/microsoft/table-transformer` (MIT); `huggingface.co/microsoft/Florence-2-large`; `huggingface.co/microsoft/Phi-3.5-vision-instruct`; `huggingface.co/microsoft/Phi-4-multimodal-instruct`; `github.com/microsoft/unilm/tree/master/layoutlmv3` (CC BY-NC-SA 4.0)
- **Google** — `cloud.google.com/document-ai/docs/{form-parser,enterprise-document-ocr,layout-parse-chunk,processors-list,ce-schema-extraction}`; `firebase.google.com/docs/ai-logic/generate-structured-output`; `blog.google/innovation-and-ai/technology/developers-tools/gemini-api-structured-outputs`; `huggingface.co/google/paligemma2-3b-pt-224`; `github.com/google-deepmind/gemma`
- **Adobe / Apple** — `developer.adobe.com/document-services/apis/pdf-extract/`; `opensource.adobe.com/pdftools-sdk-docs/release/shared/extractJSONOutputSchema.json`; `developer.apple.com/documentation/vision`; `support.apple.com/en-us/102223`
- **Open-source converters** — `github.com/{jgm/pandoc, mwilliamson/python-mammoth, frostming/marko, docling-project/docling, Unstructured-IO/unstructured, datalab-to/marker, pdfminer/pdfminer.six, pymupdf/PyMuPDF4LLM, microsoft/markitdown, getomni-ai/zerox, opendatalab/MinerU, run-llama/llama_cloud_services}`
- **Open-source OCR / VLMs** — `github.com/{datalab-to/surya, datalab-to/chandra, Ucas-HaoranWei/GOT-OCR2.0, allenai/olmocr, rednote-hilab/dots.ocr, QwenLM/Qwen3-VL, OpenGVLab/InternVL, huggingface/smollm, tesseract-ocr/tesseract, PaddlePaddle/PaddleOCR, mindee/doctr, deepseek-ai/DeepSeek-OCR, facebookresearch/{nougat,sam2}, mistralai/Pixtral-12B-2409}`
- **Schema layer** — `github.com/567-labs/instructor` (MIT, 13.2k★); `platform.openai.com/docs/guides/structured-outputs`; `firebase.google.com/docs/ai-logic/generate-structured-output`
- **NVIDIA** — `arxiv.org/abs/2511.20478` (Nemotron Parse 1.1); `build.nvidia.com/nvidia/nemotron-parse`; `developer.nvidia.com/nemo-retriever`; `github.com/NVIDIA/nv-ingest`
- **arXiv papers** — Docling technical report (arXiv:2408.09869), PaddleOCR 3.0 (arXiv:2507.05595), PaddleOCR-VL (arXiv:2510.14528), PaddleOCR-VL-1.5 (arXiv:2601.21957), PaddleOCR-VL-1.6 (arXiv:2606.03264), PubTables-1M (arXiv:2110.00061), GriTS (arXiv:2203.12555), OlmOCR v1 (arXiv:2502.18443), OlmOCR v2 (arXiv:2510.19817), DeepSeek-OCR (arXiv:2510.18234)
- **Benchmarks** — `github.com/opendatalab/OmniDocBench` (OmniDocBench v1.6 leaderboard); `huggingface.co/datasets/allenai/olmocr-bench`; `github.com/jina-ai/olmocr-bench`; Marker README "Overall PDF Conversion" + "Table Conversion" tables
- **Report reference** — `C:\Users\rahin\.mavis\agents\mavis\.builtin-skills\mavis-team\references\report.md` (Hard Principles: Traceability, Synthesis, Contradictions, Fact-vs-analysis markers, Executive Summary first)

### 10.4 Companion evidence files (raw)

- `track-md-evidence.md` (consolidated MD evidence inventory) + `track-md-evidence-{ms,google,adobe-apple,oss1,oss2}.md`
- `track-schema-evidence.md`
- `track-ocr-evidence.md`

---

## 11. Appendix B — Coverage Matrix (Detail)

This is the per-section absorption of the four tracks. See §3 for the executive view; this appendix is the data behind the table.

### 11.1 Track-md (Anything-to-Markdown) absorption

| Track-md section | Lines | Consumed in PLAN.md | Consumed how |
|---|---|---|---|
| §1 Executive Summary | 1-87 | §1, §3, §5.7, §6.6, §6.7, §6.8, §9.2, §9.5 #23 | The 7 headline findings inform the executive summary; the 11 source conflicts inform §9.2 |
| §2 Players by tier | 88-763 | §4.1, §4.2, §5.3, §6.1-§6.7 | Markitdown plugin pattern → R-M2; Mammoth style-map → R-M5 / R-W5; Zerox maintainFormat → R-G4; Pandoc → R-M7; PyMuPDF4LLM → R-A1 |
| §3 Feature Matrix | 766-901 | §5.3, §5.6, §8 | Format-coverage targets; license matrix informs the wedge decisions |
| §4 Pipeline Patterns Common to Leaders | 904-1033 | §4.1, §6.1-§6.7 | All 12 patterns referenced; Pattern 4.6 (lossless IR) → R-M4; Pattern 4.10 (async binning) → §7 Phase 3.14; Pattern 4.11 (maintainFormat) → R-G4 |
| §5 Open-Source Quality Tier | 1037-1099 | §5.7 | The "do not chase" list; wedge focus on B-mode hybrid |
| §6 Gaps LocalDeepL Could Fill | 1103-1195 | §6.1-§6.7, §6.9 | The 10 gap tables, mapped 1:1 to recommendations; 6.10 schema-of-gaps table informs the slot-by-slot structure |
| §7 References | 1198-1336 | §10.3 | Source index |

### 11.2 Track-schema (Schema/tables) absorption

| Track-schema section | Lines | Consumed in PLAN.md | Consumed how |
|---|---|---|---|
| §1 Executive Summary | 9-27 | §1, §6.8 | The 3 white-space gaps inform R-S1, R-S3, R-A3 |
| §2 Players by tier | 30-83 | §4.2, §5.1, §5.4 | The 5-tier table informs the recommendation priorities; Tier 4 (schema layer) → R-S1 (Instructor) |
| §3 Feature Matrix | 87-123 | §5.1, §6.7, §6.8 | The 14-column matrix informs the table-extractor quality targets |
| §4 Benchmark Table | 127-217 | §5.1, §6.2, §6.7, §6.9, §8 | OmniDocBench v1.6 96.3 SOTA → quality target; PubTables-1M → R-A3; FinTabNet → R-A3; olmOCR-bench → R-E3 |
| §5 Pipeline Patterns | 220-294 | §4.1, §6.7, §6.8 | Pattern 5 (schema-constrained) → R-S1 |
| §6 Gaps LocalDeepL Could Fill | 298-343 | §6.7, §6.8, §9.4 | All 8 gaps (G1-G8) mapped to recommendations |
| §7 References | 347-396 | §10.3 | Source index |

### 11.3 Track-ocr (AI OCR vision models) absorption

| Track-ocr section | Lines | Consumed in PLAN.md | Consumed how |
|---|---|---|---|
| §1 Executive Summary | 12-26 | §1, §5.1, §5.6, §6.1 | The 4-tier split informs the recommendations; license posture informs R-O4 |
| §2 Players by Company | 30-140 | §4.1, §4.2, §5.1, §5.6, §6.1, §6.4, §6.3 | Surya already in use → confirm; Dots.mocr → R-G1; Chandra 2 → R-G2; Phi-4-multimodal → R-G3 + R-O2; Florence-2 → R-O3; PaddleOCR-VL → R-G2 + R-A4; PP-OCRv6 → R-PP3 |
| §3 Execution / Deployment Matrix | 143-180 | §6.1, §6.3, §6.4 | Every row of the 27-row matrix informs at least one recommendation; run commands quoted as evidence |
| §4 Benchmark Table | 182-273 | §5.1, §6.1, §6.2, §6.3, §6.4 | olmOCR-bench leaderboard → §5.1 quality target + R-E3; DocVQA/ChartQA/OCRBench → R-G3, R-O2; OmniDocBench → R-G2; throughput → §5.2 |
| §5 Architecture Patterns | 276-315 | §4.1, §6.1, §6.4 | Pattern A (two-stage) → R-PP3; Pattern B (single VLM one-pass) → R-O2; Pattern C (bbox-native) → R-G1, R-G2, R-G3; Pattern D (detector + VLM-OCR) → confirms LocalDeepL's hybrid path |
| §6 License Constraints | 318-371 | §5.6, §6.1 #R-G6, §6.4, §8 | The license matrix informs R-O4 and the explicit non-choices (R-G6) |
| §7 LocalDeepL Gaps and Opportunities | 374-489 | §6.1, §6.3, §6.4, §6.5, §6.9, §7 | All 12 opportunities (7.2.1-7.2.12) map to recommendations; the 10 gaps (7.1) inform §4.2 |
| §8 LocalDeepL How It Already Stacks Up | 492-503 | §4.1 | Confirms the synthesis self-assessment |
| §9 References | 507-623 | §10.3 | Source index |
| §10 Open Questions / Contradictions | 607-622 | §9.1 | All 12 surfaced |

### 11.4 Track-localdeepl (state map) absorption

| Track-localdeepl section | Lines | Consumed in PLAN.md | Consumed how |
|---|---|---|---|
| §1 Executive Summary | 11-12 | §4 (intro) | The 5-friction summary informs the four-corners read |
| §2 Architecture Map | 15-92 | §4.1, §4.2, §6 (slot-by-slot) | The 7-slot extension-point table → §4 (the "well-designed but under-populated" verdict) |
| §3 Pipeline Paths (detailed) | 93-133 | §4.1, §7 | The 14-stage hybrid path table → §4.1 confirmation; the 9-stage grounded path → §4.2 |
| §4 Extension Points | 135-149 | §4, §6 (every subsection) | The 7-slot table is the spine of §6 |
| §5 Document Processors | 151-164 | §4.1, §6.2 | The 6-processor table confirms the "well-architected" verdict |
| §6 Public API Surface | 166-242 | §4.2, §6.1-§6.7, §6.10 | Every route table informs the recommendations |
| §7 Known Tech Debt | 244-285 | §4.2, §6.1, §6.5, §8 | All 20 items inform recommendations and risks |
| §8 Quality Measurement | 287-335 | §4.2, §6.10, §9.4 | The eval-harness inventory → R-E1, R-E2, R-E3, R-E4, R-E5 |
| §9 Gaps and Friction | 337-381 | §4.2, §6 (every subsection), §7, §9.4 | The friction list and the 5 open questions → most of §4.2 and §9.4 |

**Coverage check**: every upstream track section is consumed. No silent drop.

---

## 12. Appendix C — Per-Recommendation Evidence Chains

For each of the 36 recommendations in §6: **evidence** (track + file:line), **trigger/condition**, **impact** (S/M/L), **confidence** (F/A), **verification path**, **mitigation**. Already in §6 in compact form; this appendix is the audit-friendly table.

### 12.1 R-G series (grounded_backend)

| ID | Recommendation | Evidence | Trigger | Impact | Confidence | Verification | Mitigation |
|---|---|---|---|---|---|---|---|
| R-G1 | Adopt `dots.mocr` 3B as a first-class `grounded_backend` candidate | track-ocr §7.2.1, §3, §4.1; `core/grounded.py:66-85` Protocol | `grounded_backend="dotsmocr"` in `ProcessSettings`; default stays `PromptedGroundedOCR` | M | F | Add `scripts/olmocr_bench_mini.py`; re-run `scripts/confidence_image.py` head-to-head | `pip-licenses` audit (R-O4); model weight license deferred (track-ocr §10.9) |
| R-G2 | Replace `ZAIHostedOCR` with `PaddleOCR-VL-1.5` as next-experimental | track-schema §6 G7; track-ocr §7.2.4; `core/grounded.py:281-373` experimental slot | `grounded_backend="paddleocr-vl"` | M | F | Multilingual fixture (Arabic / Chinese) | `paddle-ocr` opt-in extra in `pyproject.toml` |
| R-G3 | Wire `Phi-4-multimodal` 5.6B as small-class `grounded_backend` | track-ocr §7.2.3, §2.2 | `grounded_backend="phi4-multimodal"` | M | F | throughput ≥ 1 page/s on A100; olmOCR-bench mini | flash-attn prereq in README |
| R-G4 | Add `maintain_format: bool` to `GroundedEngine` | track-md §6.1, §4.11; `core/workflows/grounded.py:49-54` | `ProcessSettings.maintain_format=True` | S-M | A | A/B on `examples/notes.pdf` | token-cost doc |
| R-G5 | Delete (or mount) `api/routers/ai.py` | track-localdeepl §7 #4; `server.py:85-91` | code-review | S | F | grep `app.include_router(ai)`; ARCHITECTURE.md update | n/a |
| R-G6 | **Do not** adopt PaliGemma 2 / Gemma 4 / Florence-2 as default | track-ocr §6.2 | n/a | n/a | n/a | n/a | README "intentional non-choices" callout |

### 12.2 R-P series (document_processors)

| ID | Recommendation | Evidence | Trigger | Impact | Confidence | Verification | Mitigation |
|---|---|---|---|---|---|---|---|
| R-P1 | `cross_page_table_merge` processor | track-md §6.2; `processors.py:392-509` seam | opt-in `document_processors=["cross_page_table_merge"]` | M | A | A/B on 3-page table fixture | iterate heuristic |
| R-P2 | `form_extraction` processor | track-md §6.2; track-schema §6 G3 | opt-in | L | A | form fixture F1 | Phase 4 stretch |
| R-P3 | `audio_transcription` / `video_caption_extraction` | track-md §6.2 | n/a (deferred) | n/a | n/a | n/a | not LocalDeepL's wedge (§5.7) |
| R-P4 | `long_document_strategy` switch | track-md §6.2; `EngineBase._cross_page_merge` | `ProcessSettings.long_document_strategy` | L | A | 1000-page synthetic PDF; peak RSS | Phase 3 |
| R-P5 | `multilingual_ocr` processor | track-ocr §7.2.9 | opt-in | M | A | 5 non-English fixture PDFs | language-detect pre-step |
| R-P6 | `image_quality_routing` (move `core/routing.py` into a processor) | track-md §6.5; `core/routing.py:30-53` | refactor | S | A | symmetric with other 5 processors | paired with R-Q2 |

### 12.3 R-A series (aligner / detector)

| ID | Recommendation | Evidence | Trigger | Impact | Confidence | Verification | Mitigation |
|---|---|---|---|---|---|---|---|
| R-A1 | `pymupdf_layout` as opt-in `aligner` swap | track-md §6.3 | opt-in extra; `aligner="pymupdf_layout"` | M | A | `scripts/confidence_eval.py` no-regression; ≥ 2× wall-clock | closed-source license, opt-in only |
| R-A2 | `docling_parse` as alternative text backend | track-md §6.3 | opt-in / default swap | M | F | `block_recall ≥ 0.95` on `digital.pdf` | PaddlePaddle-equivalent install footprint |
| R-A3 | Replace column-separator heuristic in `TableExtractionProcessor` with TATR-v1.1-All | track-schema §6 G3; `processors.py:392-509` | opt-in or default-on | M | F | table fixture | TATR install footprint |
| R-A4 | `PaddleOCR-VL-1.5` as `aligner` swap | track-ocr §7.2.4, §7.2.7 | opt-in extra | M | A | A/B vs Surya on `hybrid.pdf` / `dense.pdf` | PaddlePaddle install |

### 12.4 R-O series (ocr_processor)

| ID | Recommendation | Evidence | Trigger | Impact | Confidence | Verification | Mitigation |
|---|---|---|---|---|---|---|---|
| R-O1 | `ocr_processor` as fallback chain | track-md §6.4; `core/ocr.py:138-497` | `ProcessSettings.ocr_fallback_chain=[...]` | M | A | simulated Surya timeout triggers fallback | refactor into `core/ocr/{processor,fallback,prompts,filters}.py` |
| R-O2 | `Phi-4-multimodal` 5.6B as `ocr_processor` | track-ocr §7.2.3 | `ocr_processor="phi4-multimodal"` | M | F | throughput ≥ 1 page/s on A100 | flash-attn prereq |
| R-O3 | `Florence-2-large` 0.77B as low-VRAM tier | track-ocr §7.2.6 | `ocr_processor="florence2"` | L | F | min-VRAM install; OCRBench subset | 2023-vintage |
| R-O4 | Surface `surya-ocr` modified-OpenRAIL-M gate | track-ocr §6.2, §7.2.12; track-localdeepl §7 #9 | README callout + CI | S | F | `pip-licenses` audit | n/a |

### 12.5 R-PP series (page_preprocessor)

| ID | Recommendation | Evidence | Trigger | Impact | Confidence | Verification | Mitigation |
|---|---|---|---|---|---|---|---|
| R-PP1 | Format-keyed `page_preprocessor` dispatch | track-md §6.5; `core/preprocessing.py:33-92` | `Mapping[str, PagePreprocessor]` | M | A | per-format regression | registry pattern |
| R-PP2 | 8-dim image-quality score (Google Enterprise OCR shape) | track-md §6.5 | always on | M | A | drives `dense_mode` + VLM fallback | cheap pre-compute |
| R-PP3 | PP-OCRv6 / Tesseract 5 as CPU-only fallback | track-ocr §7.2.10 | auto-fallback on no-GPU | M | F | Apple M4 / no-GPU run | accuracy regression vs Surya |

### 12.6 R-W series (output writers)

| ID | Recommendation | Evidence | Trigger | Impact | Confidence | Verification | Mitigation |
|---|---|---|---|---|---|---|---|
| R-W1 | `xlsx_writer` | track-md §6.6 | `DocumentExportFormat.xlsx` | L | A | table fixture | `openpyxl` dep |
| R-W2 | `html_writer` | track-md §6.6 | `DocumentExportFormat.html` | M | A | RAG-friendly DOM output | semantic HTML, not style-perfect |
| R-W3 | `jats_xml_writer` | track-md §6.6 | `DocumentExportFormat.jats` | L | A | scientific fixture | specialist, Phase 4 |
| R-W4 | `chunks_writer` (RAG flat list) | track-md §6.6 | `DocumentExportFormat.chunks` | M | A | RAG chunker integration test | Marker-shape compatibility |
| R-W5 | `style_map` option in `docx_writer` | track-md §6.6; `core/docx_writer.py` | `ExportDocxRequest.style_map` | S | A | docx export with style-map | DSL parser |

### 12.7 R-M series (Anything-to-MD richness)

| ID | Recommendation | Evidence | Trigger | Impact | Confidence | Verification | Mitigation |
|---|---|---|---|---|---|---|---|
| R-M1 | `markdown_flavor` enum + schema doc | track-md §1.4, §6.1 | `ProcessSettings.markdown_flavor` | S | A | `docs/markdown-schema.md`; round-trip tests | foundational |
| R-M2 | `localdeepl.plugin` entry-point | track-md §6.1, §4.5 | `pyproject.toml` declares entry-point | S | A | stub plugin auto-registers | loader is small |
| R-M3 | `magika` content-sniff dispatcher | track-md §6.1, §4.3 | `ProcessSettings.content_sniff=True` | S | A | extension-mismatch fixture | `magika` opt-in |
| R-M4 | `DocumentResult` round-trip test | track-md §6.1, §4.6; track-localdeepl §9 #8 | `tests/test_document_roundtrip.py` | M | F | round-trip preserves `kind`/`confidence`/`spans`/`metadata` | precondition for half the rest |
| R-M5 | Mammoth style-map DSL for DOCX ↔ MD | track-md §6.1 | opt-in DSL | M | A | docx export with style-map | DSL parser |
| R-M6 | `effort` knob in `ProcessSettings` | track-md §6.1 | `ProcessSettings.effort: low/medium/high` | S | A | `HybridEngine` / `GroundedEngine` accept field | cheap knob |
| R-M7 | Pandoc shell-out for non-PDF | track-md §2.2.8, §6.7 | `ProcessSettings.pandoc_path` | M | A | DOCX/HTML/EPUB inputs route through pandoc | GPL-2.0+, *use* fine, do not bundle |

### 12.8 R-S series (schema / structured extraction)

| ID | Recommendation | Evidence | Trigger | Impact | Confidence | Verification | Mitigation |
|---|---|---|---|---|---|---|---|
| R-S1 | `structured_extraction` processor (Pydantic-native) | track-schema §6 G1 | `extract(pdf, schema=Invoice)` | HIGH | A | 5-form fixture F1 ≥ 0.85 | Instructor retries; typed `ExtractionError` |
| R-S2 | JSON Schema round-trip | track-md §6.7 | `ExtractionRequest.schema_` | M | F | polyglot caller test | Gemini-shape compatibility |
| R-S3 | Cloud-output normalizer | track-schema §6 G4 | `core/adapters/{azure,google,textract}.py` | L | A | cross-cloud normalization test | niche, Phase 4 |
| R-S4 | Cloud-out `grounded_backend` (Azure `prebuilt-read`) | track-md §6.4 | n/a (deferred) | n/a | n/a | n/a | not LocalDeepL's wedge |

### 12.9 R-Q series (routing / quality scoring)

| ID | Recommendation | Evidence | Trigger | Impact | Confidence | Verification | Mitigation |
|---|---|---|---|---|---|---|---|
| R-Q1 | Expose per-page quality scores in response | track-md §6.8; track-localdeepl §9 #4 | extend `X-Document-Quality` header | M | A | 8-dim scores in header | paired with R-PP2 |
| R-Q2 | Move `QualityRoutingPolicy` into a processor | track-localdeepl §9 | refactor | M | A | symmetric with other 5 processors | paired with R-P6 |
| R-Q3 | `fallback_to_grounded: bool` | track-md §6.8; `core/workflows/hybrid.py:271-285` | `ProcessSettings.fallback_to_grounded` | M | A | low-confidence sparse page auto re-runs | `_refine_uncertain` is the seam |

### 12.10 R-E series (eval / regression)

| ID | Recommendation | Evidence | Trigger | Impact | Confidence | Verification | Mitigation |
|---|---|---|---|---|---|---|---|
| R-E1 | Replace greedy IoU with Hungarian | track-localdeepl §8.1, §9; `src/local_deepl/evaluation.py:20-22` | `scipy.optimize.linear_sum_assignment` | S | A | `block_recall` deltas on multi-column pages | baseline reset |
| R-E2 | Hand-build `dense.pdf` / `notes.pdf` ground truth | track-localdeepl §9 | methodology | L | A | absolute-quality harness | human labelling effort |
| R-E3 | `scripts/olmocr_bench_mini.py` | track-ocr §7.2.11 | 50-doc subset | M | F | olmOCR-bench ≥ 80 | statistical power is low |
| R-E4 | `scripts/license_audit.py` | track-ocr §7.2.12; track-localdeepl §7 #9 | CI lane | S | F | `pip-licenses` check | n/a |
| R-E5 | A/B scaffold for preprocessing toggles | track-localdeepl §9 | `--ab-test` flag on `scripts/confidence_eval.py` | M | A | 6 toggles × 5 fixtures | paired with R-E2 |

---

*End of PLAN.md. The plan is grounded in the four upstream tracks and the LocalDeepL repo at 2026-06-14. Every recommendation is implementable by the solo maintainer in the sequenced phases; no claim is invented; no contradiction is silently resolved.*
