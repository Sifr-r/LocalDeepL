# Anything-to-Markdown / rich-text converter landscape — consolidated evidence inventory

> Scout for LocalDeepL. Compiled 2026-06-14. This file is the index + cross-cut
> of five per-vendor evidence files produced by parallel research subagents:
>
> 1. `track-md-evidence-ms.md` — Microsoft (Markitdown, markitdown extras, Azure Document Intelligence, M365 Copilot parsing)
> 2. `track-md-evidence-google.md` — Google (Document AI, Gemini structured output, NotebookLM)
> 3. `track-md-evidence-adobe-apple.md` — Adobe (Acrobat Extract, Sensei, PDF Services API) + Apple (Vision, Shortcuts, Notes, Intelligence)
> 4. `track-md-evidence-oss1.md` — OSS first half (Pandoc, Mammoth, Marko, Docling, Unstructured)
> 5. `track-md-evidence-oss2.md` — OSS second half (Marker, PDFMiner, PyMuPDF4LLM, markitdown ecosystem + Zerox / Docling / MinerU / LlamaParse)
>
> Each vendor file lists every factual claim with an inline source. This index points
> to the source files and surfaces the cross-cutting facts and conflicts that the
> main deliverable (`track-md.md`) is built on.
>
> `[F]` = fact, `[A]` = analysis, `[C]` = conflict/caveat.

---

## 0. Headline findings (the 8 things the scout team agreed on)

1. **No single "anything → Markdown" service exists in the cloud.** Microsoft
   Doc Intel is the strongest first-party PDF→MD API; Google's Document AI has
   no native Markdown field; NotebookLM produces responses, not Markdown; Adobe
   PDF-to-Markdown is PDF-only. None of the cloud players is a general
   "anything-to-MD" service. `[A]` synthesis of all four vendor files.
2. **OSS has converged on three architectural patterns** for "anything→MD":
   **A. Local layout/ML pipeline (no LLM)** — PyMuPDF4LLM, PDFMiner, Marker's
   "plain" mode. **B. Local layout/ML + VLM post-processor (hybrid)** — Marker
   (`--use_llm`), Docling (vlm pipeline), MinerU (hybrid-engine), LocalDeepL.
   **C. VLM-only / pure-vision** — Zerox, LlamaParse. `[A]`
   [track-md-evidence-oss2.md §5.1].
3. **LocalDeepL's hybrid approach is the most defensible B-mode design** because
   it has both `dense_mode="auto"` per-page routing AND pluggable
   `grounded_backend` for the VLM leg. Marker defaults to A with B as opt-in;
   Docling is mostly A with a small 258M VLM; MinerU ships both but no per-page
   routing. `[A]` [track-md-evidence-oss2.md §5.6].
4. **License posture is a real LocalDeepL wedge.** Marker = GPL-3.0 + RAIL-M
   ($2M revenue/funding cap) [MODEL_LICENSE]; PyMuPDF4LLM = AGPL v3 or paid
   commercial; Pandoc = GPL-2.0+. Docling, Markitdown, PDFMiner, Zerox, MinerU
   are MIT / Apache-2.0 / Apache-2.0-based. Any mid-market or enterprise
   customer cannot freely ship Marker's weights. `[F]`
   [track-md-evidence-oss2.md §1.7, §3.7, §5.3].
5. **Markdown schema fragmentation is the #1 integration friction.** Markitdown
   uses GFM; Azure Doc Intel's `prebuilt-layout` Markdown uses **HTML tables** +
   LaTeX math + `<!--PageBreak-->` comments; Adobe's PDF-to-Markdown uses
   base64-embedded images; Docling ships a separate `DocTags` lossless format.
   RAG pipelines expecting GFM pipe tables break on Azure's HTML. `[F]`
   [track-md-evidence-ms.md §3].
6. **The two mainline consumers want opposite things.** Marker targets
   95.67 heuristic on a Common-Crawl-style benchmark, with `--use_llm` as
   optional. Markitdown's README explicitly disclaims fidelity ("meant to be
   consumed by text analysis tools — and may not be the best option for
   high-fidelity document conversions for human consumption"). LocalDeepL sits
   in the middle. `[F]`
   [track-md-evidence-oss2.md §4.1].
7. **The Microsoft 365 Copilot parsing pipeline is closed and not a direct
   competitor.** No "Microsoft Document Transformer" arXiv paper exists;
   LayoutLMv3 and UDOP are pre-training papers, not the production pipeline.
   The real Microsoft cloud competitors are Azure Document Intelligence
   (prebuilt-layout Markdown) and Azure Content Understanding (multimodal
   umbrella). `[F]` [track-md-evidence-ms.md §4].
8. **None of the Google products has a first-class Markdown output.** Document
   AI returns the `Document` JSON proto; Gemini API has no Markdown mode (you
   prompt for Markdown or use `application/json` + `responseSchema`); NotebookLM
   outputs chat, audio overviews, mind maps, slide decks, infographics — no
   Markdown export. `[A]` [track-md-evidence-google.md §5].

---

## 1. Player inventory (consolidated, with vendor-file pointers)

| # | Name | Vendor | License | Primary output | Vendor file |
|---|---|---|---|---|---|
| 1 | Markitdown (core) | Microsoft / AutoGen Team | MIT | Markdown | [ms §1](../track-md-evidence-ms.md#1-markitdown-core-repo) |
| 2 | Markitdown extras (11 pip extras) | Microsoft | MIT | Markdown | [ms §2](../track-md-evidence-ms.md#2-markitdown-extras--coverage-detail) |
| 3 | Azure Document Intelligence (Layout / Read) | Microsoft (Azure) | Cloud + connected/disconnected container | Markdown (HTML tables) / JSON | [ms §3](../track-md-evidence-ms.md#3-azure-document-intelligence-formerly-form-recognizer) |
| 4 | Microsoft 365 Copilot parsing | Microsoft | Closed SaaS | Grounded chat response (no MD export) | [ms §4](../track-md-evidence-ms.md#4-microsoft-365-copilot-parsing-pipeline) |
| 5 | Google Document AI — Form Parser | Google Cloud | Cloud | JSON `Document` proto | [google §1.1](../track-md-evidence-google.md#11-form-parser) |
| 6 | Google Document AI — Enterprise OCR | Google Cloud | Cloud | JSON `Document` proto | [google §1.2](../track-md-evidence-google.md#12-enterprise-document-ocr) |
| 7 | Google Document AI — Layout Parser | Google Cloud | Cloud | JSON `Document` proto (Gemini-grounded) | [google §1.3](../track-md-evidence-google.md#13-layout-parser-gemini-layout-parser) |
| 8 | Google Document AI — Custom Extractor | Google Cloud | Cloud | JSON `Document` proto (English-only generative) | [google §1.4](../track-md-evidence-google.md#14-custom-extractor) |
| 9 | Document AI Schema API (incl. automated schema gen) | Google Cloud | Cloud (Preview) | JSON schema | [google §1.5](../track-md-evidence-google.md#15-schema-api-custom-extractor-schema-tooling-broader-sense) |
| 10 | Gemini structured output / document understanding | Google | Cloud (API + Vertex) | Text / JSON | [google §2](../track-md-evidence-google.md#2-gemini-structured-output--document-understanding) |
| 11 | NotebookLM | Google Labs | Cloud (UI) | Chat, audio overview, mind map, study guide, infographic, slide deck | [google §3](../track-md-evidence-google.md#3-notebooklm--ingest-pipeline-publicly-documented) |
| 12 | Adobe Acrobat Extract API (JSON + PDF→MD) | Adobe | Cloud SaaS | JSON, Markdown, CSV, XLSX | [adobe-apple §1](../track-md-evidence-adobe-apple.md#1-adobe-acrobat-extract-api) |
| 13 | Adobe PDF Services API (umbrella) | Adobe | Cloud SaaS | PDF / DOCX / XLSX / PPTX / RTF | [adobe-apple §3](../track-md-evidence-adobe-apple.md#3-adobe-pdf-services-api--markdown--structured-export) |
| 14 | Apple Vision `VNRecognizeTextRequest` (iOS/macOS) | Apple | OS-bundled (closed) | Text observations (flat, no structure) | [adobe-apple §4.1](../track-md-evidence-adobe-apple.md#41-apple-vision-framework--vnrecognizetextrequest-macos--ios) |
| 15 | Apple Shortcuts "Extract from PDF" / "Make Rich Text from Markdown" | Apple | OS-bundled | Plain text, rich text | [adobe-apple §4.2](../track-md-evidence-adobe-apple.md#42-apple-shortcuts--extract-from-pdf--make-rich-text-from-markdown--markdown-to-html) |
| 16 | Apple Notes (iOS 26 / macOS Tahoe 26 Markdown I/O) | Apple | OS-bundled | Markdown (basic) | [adobe-apple §4.3](../track-md-evidence-adobe-apple.md#43-apple-notes--markdown-import-export-tahoe-26--ios-26) |
| 17 | Pandoc | John MacFarlane / community | **GPL-2.0+** | 44+ output formats incl. Markdown | [oss1 §1](../track-md-evidence-oss1.md#1-pandoc--jgmpandoc) |
| 18 | Mammoth | mwilliamson | BSD-2-Clause | HTML (primary); MD deprecated | [oss1 §2](../track-md-evidence-oss1.md#2-mammoth--mwilliamsonpython-mammoth) |
| 19 | Marko (frostming) | Frost Ming | MIT | MD→HTML/AST (parser only — wrong direction) | [oss1 §3](../track-md-evidence-oss1.md#3-marko--frostmingmarko-and-microsoft-markitdown) |
| 20 | Docling | IBM Research Zurich / LF AI & Data | MIT (code) | Markdown, HTML, JSON, DocTags | [oss1 §4](../track-md-evidence-oss1.md#4-docling--docling-projectdocling) |
| 21 | Unstructured | Unstructured Technologies | Apache-2.0 | `list[Element]` (typed); MD is secondary | [oss1 §5](../track-md-evidence-oss1.md#5-unstructured--unstructured-iounstructured) |
| 22 | Marker | Datalab (Vik Paruchuri) | **GPL-3.0 + RAIL-M ($2M cap)** | Markdown, JSON, HTML, chunks | [oss2 §1](../track-md-evidence-oss2.md#1-marker-datalab-tomarker--the-single-closest-competitor-to-localdeepl) |
| 23 | PDFMiner.six | pdfminer | MIT | Text, hOCR, HTML, XML | [oss2 §2](../track-md-evidence-oss2.md#2-pdfminer-pdfminersix) |
| 24 | PyMuPDF4LLM | Artifex Software | **AGPL v3 OR commercial**; Layout mode is closed-source | Markdown, JSON, plain text | [oss2 §3](../track-md-evidence-oss2.md#3-pymupdf4llm-pymupdfpymupdf4llm) |
| 25 | Markitdown (re-listed for OSS bucket) | Microsoft | MIT | Markdown | [oss2 §4.1](../track-md-evidence-oss2.md#41-microsoftmarkitdown-the-oss-bellwether) |
| 26 | Zerox (getomni-ai) | Omni | MIT | Markdown (via vision-LLM) | [oss2 §4.2](../track-md-evidence-oss2.md#42-zerox-getomni-aizerox) |
| 27 | Docling (re-listed in ecosystem scan) | IBM / LF AI & Data | MIT | Markdown, HTML, JSON, DocTags | [oss2 §4.3](../track-md-evidence-oss2.md#43-docling-docling-projectdocling) |
| 28 | MinerU | OpenDataLab (Shanghai AI Lab) | Apache-2.0-based (since v3.1.0) | Markdown, JSON | [oss2 §4.4](../track-md-evidence-oss2.md#44-mineru-opendatalabminerU) |
| 29 | LlamaParse (run-llama/llama_cloud_services) | LlamaIndex | MIT (SDK) / cloud pay-per-page | Markdown, JSON | [oss2 §4.5](../track-md-evidence-oss2.md#45-llamaparse--run-llamallama_cloud_services) |

---

## 2. GitHub stats worth noting (only those that were fetched)

| Project | Stars | Forks | Latest release | License | Source |
|---|---|---|---|---|---|
| microsoft/markitdown | 153k | 10.6k | v0.1.6 / 2026-05-26 | MIT | [github.com/microsoft/markitdown](https://github.com/microsoft/markitdown) |
| docling-project/docling | 61.5k | 4.3k | v2.102.1 / 2026-06-12 | MIT (code) | [github.com/docling-project/docling](https://github.com/docling-project/docling) |
| jgm/pandoc | 44.8k | 3.9k | 3.10 / 2026-06-04 | **GPL-2.0+** | [github.com/jgm/pandoc](https://github.com/jgm/pandoc) |
| datalab-to/marker | 36.1k | 2.5k | v1.10.2 / 2026-01-31 | **GPL-3.0 + RAIL-M** | [github.com/datalab-to/marker](https://github.com/datalab-to/marker) |
| opendatalab/MinerU | 67.5k | 5.7k | 3.3 / 2026-06-11 | Apache-2.0-based | [github.com/opendatalab/MinerU](https://github.com/opendatalab/MinerU) |
| google-gemini/cookbook | 17.4k | 2.7k | (rolling) | Apache-2.0 | [github.com/google-gemini/cookbook](https://github.com/google-gemini/cookbook) |
| Unstructured-IO/unstructured | 14.9k | 1.3k | 0.23.1 / 2026-06-11 | Apache-2.0 | [github.com/Unstructured-IO/unstructured](https://github.com/Unstructured-IO/unstructured) |
| getomni-ai/zerox | 12.2k | 847 | v0.1.06 / 2024-12-18 | MIT | [github.com/getomni-ai/zerox](https://github.com/getomni-ai/zerox) |
| pdfminer/pdfminer.six | 7.0k | n/a | 20260107 / 2026-01-07 | MIT | [github.com/pdfminer/pdfminer.six](https://github.com/pdfminer/pdfminer.six) |
| GoogleCloudPlatform/document-ai-samples | 323 | 115 | (rolling) | Apache-2.0 | [github.com/GoogleCloudPlatform/document-ai-samples](https://github.com/GoogleCloudPlatform/document-ai-samples) |
| run-llama/llama_cloud_services | 4.3k | 471 | 0.6.94 / 2026-02-13 (EOL 2026-05-01) | MIT (SDK) | [github.com/run-llama/llama_cloud_services](https://github.com/run-llama/llama_cloud_services) |
| pymupdf/PyMuPDF4LLM | 1.8k | 226 | v0.3.4 / 2026-02-14 | **AGPL v3 OR commercial** | [github.com/pymupdf/PyMuPDF4LLM](https://github.com/pymupdf/PyMuPDF4LLM) |
| mwilliamson/python-mammoth | 1.1k | 148 | (low activity) | BSD-2-Clause | [github.com/mwilliamson/python-mammoth](https://github.com/mwilliamson/python-mammoth) |
| frostming/marko | 458 | 53 | v2.2.3 / 2026-05-28 | MIT | [github.com/frostming/marko](https://github.com/frostming/marko) |
| adobe/pdfservices-python-sdk-samples | 163 | 54 | 4.2.0 / 2025-07-11 | MIT (SDK samples) | [github.com/adobe/pdfservices-python-sdk-samples](https://github.com/adobe/pdfservices-python-sdk-samples) |
| adobe/pdfservices-node-sdk-samples | 109 | 23 | 4.1.0 / 2025-01-02 | MIT (SDK samples) | [github.com/adobe/pdfservices-node-sdk-samples](https://github.com/adobe/pdfservices-node-sdk-samples) |
| adobe/PDFServices.NET.SDK.Samples | 47 | 22 | (rolling) | MIT (SDK samples) | [github.com/adobe/PDFServices.NET.SDK.Samples](https://github.com/adobe/PDFServices.NET.SDK.Samples) |

---

## 3. Cross-cutting cloud pricing (only fields where the value was actually fetched)

| Service | Free tier | Pay-as-you-go | Source |
|---|---|---|---|
| Azure Document Intelligence Read | 500 pages/mo F0 | ~$1.50 / 1k pages | [ms §3](../track-md-evidence-ms.md#3-azure-document-intelligence-formerly-form-recognizer) |
| Azure Document Intelligence prebuilt (Layout/Document/Invoice/Receipt/ID…) | 500 pages/mo F0 | ~$10 / 1k pages | same |
| Azure Document Intelligence Custom Extraction | (none) | ~$30 / 1k pages | same |
| Google Document AI Form Parser | 1k pages/mo free | $30 / 1k pages | [google §1.1, §1.2 pricing](../track-md-evidence-google.md#12-enterprise-document-ocr) |
| Google Document AI Enterprise OCR (digitize) | 1k pages/mo free | $1.50 / 1k pages | same |
| Google Document AI Layout Parser | (no free tier called out) | $10 / 1k pages | same |
| Google Document AI Custom Extractor | (no free tier called out) | $30 / 1k pages | same |
| Google Document AI Summarizer | n/a | $25 / 1k pages | same |
| Adobe PDF Services / Extract / PDF-to-Markdown | 500 Document Transactions/mo | 1 DT per 5 pages (Extract, PDF-to-MD) | [adobe-apple §1.8](../track-md-evidence-adobe-apple.md#18-pricing--quota) |
| Microsoft 365 Copilot | n/a (per-user) | $30/user/month (US list, secondary) | [ms §4](../track-md-evidence-ms.md#4-microsoft-365-copilot-parsing-pipeline) |
| NotebookLM | 50 sources × 500k words × 200 MB | Plus tier: 300 sources | [google §3.3](../track-md-evidence-google.md#33-source-limits-per-notebooklm-help-fetched-2026-06-14) |
| LlamaParse | $5 free credits (per Omni / per Datalab) | pay per page | [oss2 §4.5](../track-md-evidence-oss2.md#45-llamaparse--run-llamallama_cloud_services) |

Note: the Azure pricing page renders `$-` placeholders publicly; concrete dollar numbers
come from community trackers (aiproductivity.ai, Reddit r/AZURE) and are cited as
secondary. [track-md-evidence-ms.md §3].

---

## 4. Quality claims cross-cut (only what's directly cited in the evidence files)

| Player | Layout fidelity claim | CJK/RTL claim | Footnotes | Code fences | LaTeX/math | Source |
|---|---|---|---|---|---|---|
| Markitdown built-in PDF | No layout detection; pdfplumber/pdfminer only | "passable UTF-8"; no claim | No | No | No | [ms §1.2](../track-md-evidence-ms.md#1-markitdown-core-repo) |
| Markitdown docx (mammoth) | Headings/lists/hyperlinks; no table formatting | "passable UTF-8" | endnotes/footnotes | n/a | n/a | same |
| Azure DI prebuilt-layout | **HTML tables** (not GFM), LaTeX math, `<!--PageBreak-->` | 200+ langs | Yes (KVP→JSON) | n/a | `$$…$$` | [ms §3](../track-md-evidence-ms.md#3-azure-document-intelligence-formerly-form-recognizer) |
| Azure DI prebuilt-read | Searchable PDF NEW in v4.0 (free) | 200+ langs, CJK on images (v4.0) | n/a | n/a | n/a | same |
| Google Form Parser | KVP + tables + checkboxes; no spans | 200+ langs | n/a | n/a | n/a | [google §1.1](../track-md-evidence-google.md#11-form-parser) |
| Google Enterprise OCR | Math OCR (LaTeX) **OR** checkbox (mutually exclusive) | 200+ langs | n/a | n/a | LaTeX | [google §1.2](../track-md-evidence-google.md#12-enterprise-document-ocr) |
| Google Layout Parser | "Layout-aware chunking" w/ ancestral headings; **merged cells** in financial tables | n/a (no Markdown output) | n/a | n/a | n/a | [google §1.3](../track-md-evidence-google.md#13-layout-parser-gemini-layout-parser) |
| Google Custom Extractor | Up-trains with 10 docs (gen path) | English-only on generative path | n/a | n/a | n/a | [google §1.4](../track-md-evidence-google.md#14-custom-extractor) |
| Adobe PDF→MD | Path-style element classification (H1, L, Li, P, Table, TD) | "broad range" (no specific RTL/CJK claim) | n/a | n/a | n/a | [adobe-apple §1.3](../track-md-evidence-adobe-apple.md#13-quality--layout-fidelity) |
| Pandoc | Lossy by design; structural not visual | format-agnostic | Yes | Yes | Yes (TeX/KaTeX/MathML/OMML) | [oss1 §1.4](../track-md-evidence-oss1.md#14-quality--layout-fidelity) |
| Mammoth | Semantic clean HTML via style-map | n/a | footnotes/endnotes | n/a | n/a | [oss1 §2.4](../track-md-evidence-oss1.md#24-quality--layout-fidelity) |
| Docling | Full PDF: layout + reading order + table structure + code + formulas + chart-understanding | multilingual layout model; CJK OCR packs | Yes | Yes | LaTeX | [oss1 §4.4](../track-md-evidence-oss1.md#44-quality--layout-fidelity) |
| Unstructured | Element-level IR w/ coords, langs, links; Markdown is secondary | per-element language detection | n/a | n/a | n/a | [oss1 §5.4](../track-md-evidence-oss1.md#54-quality--layout-fidelity) |
| Marker | 95.67 heuristic / 4.24 LLM-judge on its own benchmark; `--use_llm` adds Gemini | "all languages" (Surya-backed) | superscript for footnotes | fenced | `$$…$$` LaTeX | [oss2 §1.3](../track-md-evidence-oss2.md#13-quality-claims) |
| PDFMiner | Layout analysis + reading order; CJK vertical writing; AcroForm; tagged PDF | explicit CJK + vertical | n/a | n/a | n/a | [oss2 §2.3](../track-md-evidence-oss2.md#23-quality-claims-from-readme-features) |
| PyMuPDF4LLM | GFM with bold/italic/code; GFM pipe tables; headings from font hierarchy | CJK fonts via MuPDF; no RTL claim | n/a (inferred) | fenced | n/a | [oss2 §3.3](../track-md-evidence-oss2.md#33-quality-claims) |
| Zerox | LLM-only; no own OCR | model-dependent | model-dependent | model-dependent | model-dependent | [oss2 §4.2](../track-md-evidence-oss2.md#42-zerox-getomni-aizerox) |
| MinerU | 109-language OCR; cross-page table merge; seal text; vertical text; interline formula numbering | explicit 109 langs | Yes | Yes | interline formula numbering | [oss2 §4.4](../track-md-evidence-oss2.md#44-mineru-opendatalabminerU) |

---

## 5. Pipeline patterns common to leaders (architectural observations)

| Pattern | Where it appears | Citation |
|---|---|---|
| **Format-keyed dispatch table** mapping `InputFormat` → `(backend, pipeline)` | Docling (`DocumentConverter`); Markitdown (`MarkItDown` priority registry) | [oss1 §4.3](../track-md-evidence-oss1.md#43-architecture-from-the-source); [ms §1](../track-md-evidence-ms.md#1-markitdown-core-repo) |
| **Multi-stage threaded pipeline** with bounded queues, per-run-id, document-timeout, partial-success semantics | Docling `StandardPdfPipeline` | [oss1 §4.3](../track-md-evidence-oss1.md#43-architecture-from-the-source), [oss2 §4.3](../track-md-evidence-oss2.md#43-docling-docling-projectdocling) |
| **Content-sniff dispatcher** using `magika` or `libmagic` to pick the right converter | Markitdown (`_magika = magika.Magika()`); Unstructured (`unstructured.partition.auto.partition`) | [oss1 §5.3](../track-md-evidence-oss1.md#53-architecture-from-the-source), [ms §1](../track-md-evidence-ms.md#1-markitdown-core-repo) |
| **Hybrid OCR** that uses page-level features (illegible chars, vector graphics) to decide whether to OCR | PyMuPDF4LLM's `OCRMode` enum; Marker's `OrderProcessor → TextProcessor` | [oss2 §3.3](../track-md-evidence-oss2.md#33-quality-claims), [oss2 §1.5](../track-md-evidence-oss2.md#15-architecture--pipeline) |
| **Plugin entry-points** for extensibility | Markitdown `markitdown.plugin`; Docling `pipeline_cls` factory | [ms §1](../track-md-evidence-ms.md#1-markitdown-core-repo), [oss1 §4.3](../track-md-evidence-oss1.md#43-architecture-from-the-source) |
| **Lossless structured IR** with multiple output renderers | Docling `DoclingDocument` (MD/HTML/DocTags/JSON); Marker `Schema` (28 block types, MD/JSON/HTML/chunks) | [oss1 §4.2](../track-md-evidence-oss1.md#42-input--output-coverage), [oss2 §1.3](../track-md-evidence-oss2.md#13-quality-claims) |
| **Heavy model caching** keyed by options-hash | Docling `initialized_pipelines: dict[(pipeline_class, options_md5_hash), pipeline_instance]` | [oss1 §4.3](../track-md-evidence-oss1.md#43-architecture-from-the-source) |
| **DI via reflection** to wire `artifact_dict` and `config` into processors | Marker `BaseConverter.resolve_dependencies` | [oss2 §1.5](../track-md-evidence-oss2.md#15-architecture--pipeline) |
| **Sliding-window memory + streaming writes** for long documents | MinerU v3.0.0 (sliding window) | [oss2 §4.4](../track-md-evidence-oss2.md#44-mineru-opendatalabminerU) |
| **Async orchestration** with task binning + bounded concurrency + live progress | MinerU CLI `mineru/cli/client.py` (`plan_pipeline_tasks`, `asyncio.Queue` worker pool) | [oss2 §4.4](../track-md-evidence-oss2.md#44-mineru-opendatalabminerU) |
| **Per-page context threading** to keep format consistent across pages | Zerox `maintainFormat` mode | [oss2 §4.2](../track-md-evidence-oss2.md#42-zerox-getomni-aizerox) |

---

## 6. Source conflicts surfaced (do not silently pick a side)

| # | Conflict | Sources | Interpretation |
|---|---|---|---|
| 1 | Brief said "H2OAI/marko" + "Pandoc has PDF reader at `src/Text/Pandoc/Readers/PDF.hs`" | brief | No `H2OAI/marko` exists; canonical is `frostming/marko` (parser, not converter). Pandoc has no PDF reader — the path does not exist. Likely the brief meant `microsoft/markitdown` for "Marko". |
| 2 | Azure `prebuilt-layout` Markdown uses HTML tables, not GFM | [ms §3](../track-md-evidence-ms.md#3-azure-document-intelligence-formerly-form-recognizer) | Downstream GFM-renderers and RAG chunkers expecting pipe tables break. |
| 3 | Gemini inline file size: 20 MB (Firebase AI Logic doc) vs 100 MB (Gemini API blog post, Jan 12 2026) | [google §2.5](../track-md-evidence-google.md#25-source-conflicts-surfaced) | These are different surfaces; Firebase AI Logic's `analyze-documents` has its own 20 MB cap. |
| 4 | Gemini PDF max pages: 1,000 (Developer API) vs 3,000 (Vertex AI doc-understanding) | same | The Vertex tables are the source of truth per-model as of 2026-06-14. |
| 5 | LiteLLM proxy flattens Azure `prebuilt-layout` Markdown response | [github.com/BerriAI/litellm/issues/25687](https://github.com/BerriAI/litellm/issues/25687) | Bug in LiteLLM response flattening, not Azure itself. Direct REST/SDK gets structured MD. |
| 6 | Adobe has no on-prem; PDF-to-MD is closed SaaS with 400-page limit, no XFA, no CAD, no encrypted | [adobe-apple §1.7](../track-md-evidence-adobe-apple.md#17-documented-limitations--known-issues) | n/a |
| 7 | Apple Vision / Shortcuts / Notes page bodies are JS-rendered; action names like "Make Rich Text from Markdown" only confirmed via 3rd-party blogs | [adobe-apple §4.2.3](../track-md-evidence-adobe-apple.md#422-make-rich-text-from-markdown--make-markdown-from-rich-text--make-html-from-markdown-actions) | Use 3rd-party blogs as evidence; not first-party. |
| 8 | `datalab-to/chandra` (Marker's next-gen model) returned 404 on README fetch | [oss2 §1.4](../track-md-evidence-oss2.md#14-execution-mode) | Either private or path changed. Worth investigating. |
| 9 | `pymupdf_layout` license terms are not fully public | [oss2 §3.5](../track-md-evidence-oss2.md#35-architecture--pipeline) | "Not open-source and has its own license" — needs deeper look before any legal positioning. |
| 10 | Adobe vs Microsoft "PDF→MD" Markdown schema differs (Adobe uses base64-embedded images; MS uses HTML comments + `<!--PageBreak-->`) | [adobe-apple §1.1](../track-md-evidence-adobe-apple.md#11-identity-vendor-license-output-formats), [ms §3](../track-md-evidence-ms.md#3-azure-document-intelligence-formerly-form-recognizer) | Friction for any cross-vendor RAG pipeline. |
| 11 | `marker/parallel.py` does not exist in current repo; orchestration lives in `marker/converters/__init__.py` via `BaseConverter.resolve_dependencies` + `initialize_processors` | [oss2 §1.5](../track-md-evidence-oss2.md#15-architecture--pipeline) | Brief's reference to `marker/parallel.py` is stale. |

---

## 7. Blockers / open questions (carried into the gaps section of the main deliverable)

- **`pymupdf_layout` license terms** are not public. `[B]` Recommendation:
  fetch the `pymupdf-layout` PyPI page and the actual license text.
  [oss2 §5.7]
- **Marker "Chandra" model** — repo `datalab-to/chandra` 404. Either private or
  renamed. `[B]` [oss2 §5.7]
- **Marker's $2M cap** — the MODEL_LICENSE says "you, your employer, or the
  entity you are affiliated with generated more than $2M in gross revenue" —
  does it apply per entity or per product? `[B]` Worth a lawyer review before
  any B2B positioning. [oss2 §1.7]
- **Docling vs MinerU head-to-head** — only Marker's own benchmark (which
  favors Marker) has Docling, but no neutral head-to-head Docling vs MinerU.
  `[B]` [oss2 §5.7]
- **Direct ai.google.dev pages** (`structured-output`, `document-processing`,
  `file-api`) were transport-blocked. Used Firebase AI Logic + Vertex AI
  mirrors instead. `[B]` [google §6]
- **`/document-ai/docs/processors-list` is 2,679 lines**; only the 4 primary
  processors (Form Parser, Document OCR, Layout Parser, Custom Extractor) were
  deep-dived. Bank Statement / W2 / US Passport / ID Proofing / US Driver
  License / Expense / Invoice parsers are out of scope for "anything-to-MD"
  framing but could matter for specific verticals. `[B]` [google §6]
- **Apple Vision and Shortcuts documentation is JS-rendered**; we relied on
  third-party blogs (cnblogs, MacScripter, IT之家, AppleInsider) for action
  names. `[B]` [adobe-apple §7]
- **No "Microsoft Document Transformer" arXiv paper exists**; the brief's
  mention of one is wrong. Closest Microsoft lineage is LayoutLMv3 (2022),
  UDOP (CVPR 2023), KOSMOS-2.5 (late 2023, not deep-read). `[B]`
  [ms §4]
- **KOSMOS-2.5** was not directly fetched — recommended follow-up.
  [ms §7]
- **Markitdown issues 1845, 296, 1361** titles/snippets fetched; bodies not
  opened. `[B]` [ms §7]

---

## 8. Source-quality summary (by type)

| Source type | Examples in this scout | Reliability |
|---|---|---|
| GitHub repo + source file (raw.githubusercontent) | marker, docling, pymupdf4llm, mammoth, pdfminer, frostming/marko, markitdown, docling-parse, pandoc, mineru, llama_cloud_services, adobe pdfservices samples | **High** — primary |
| Vendor docs at learn.microsoft.com / cloud.google.com / developer.adobe.com / firebase.google.com | Doc Intel, Doc AI, Adobe Extract, Adobe PDF Services, Firebase AI Logic, Vertex AI | **High** — primary |
| Vendor blog posts | blog.google (Gemini API), adobe tech blog, Microsoft Tech Community | **High** — primary, but dated |
| arXiv papers | arXiv 2408.09869 (Docling), 2504.09720v2 (NotebookLM), 2410.21169 (parsing survey) | **High** — primary |
| GitHub release / version pins (PyPI, GitHub Releases) | Marker v1.10.2, Docling v2.102.1, etc. | **High** — primary |
| 3rd-party blogs (cnblogs, MacScripter, IT之家, AppleInsider, aiproductivity.ai, Reddit) | Apple Shortcuts action names, Azure pricing triangulation | **Medium** — used only for confirmation or where 1st-party is JS-gated |
| PyPI metadata | pymupdf4llm, pymupdf-layout, marker-pdf | **High** — primary |
| Web search snippets (for blocked direct fetches) | ai.google.dev pages | **Medium** — used as fallback when direct fetch blocked |

---

## 9. How this inventory maps to the main deliverable

The main deliverable `track-md.md` will:

1. **Executive Summary** — built from §0 of this file (the 8 headline findings).
2. **Players (by tier)** — built from §1 (Player inventory) + §2 (GitHub stats).
3. **Feature Matrix** — built from §3 (pricing) + §4 (quality claims) + format coverage matrix from `oss2 §5.4`.
4. **Pipeline Patterns Common to Leaders** — built from §5 of this file.
5. **Open-Source Quality Tier** — built from `oss1` + `oss2` (Pandoc, Mammoth, Docling, Unstructured, Marker, PyMuPDF4LLM, PDFMiner, Markitdown, Zerox, MinerU, LlamaParse).
6. **Gaps LocalDeepL Could Fill** — built from §6 (conflicts) + §7 (blockers) + the cross-cut analysis in `oss1 §6.5` and `oss2 §5.6`.
7. **References** — every URL listed in §1's vendor-file pointers + the source index in each vendor file.
