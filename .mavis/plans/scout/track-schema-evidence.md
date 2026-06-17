# Schema & Table Extraction Landscape — Evidence

> Collected 2026-06-14 for the LocalDeepL scout. Each entry cites primary source with date and URL.
> [F] = fact stated by source. [A] = synthesis / inference.

## Cloud Incumbents

### 1. Google Document AI

- Vendor: Google Cloud. Service name: Document AI. Pricing page: https://cloud.google.com/document-ai. [F, fetched 2026-06-14]
- Processors relevant to schema/table/form extraction: Enterprise Document OCR, Form Parser, Layout Parser, Custom Extractor, Custom Splitter, Custom Classifier, Summarizer. [F]
- Custom Extractor is "powered by generative AI" and "can be used out of the box to get accurate results across a wide array of documents. Furthermore, you can achieve higher accuracy by providing as few as 10 documents to fine-tune the large model—all with a simple click of a button or an API call." [F, cloud.google.com/document-ai#features, fetched 2026-06-14]
- Pricing per 1,000 pages (fetched 2026-06-14): Enterprise Document OCR $1.50; OCR add-ons $6; Custom Extractor $30; Form Parser $30; Layout Parser $10; Custom Splitter $5; Custom Classifier $5; Summarizer $25. [F]
- Output: JSON, with processor-specific schemas (Form Parser, Layout, Custom Extractor all expose `Document` proto with `pages`, `entities`, `formFields`, `tables`). Sample output: https://docs.cloud.google.com/document-ai/docs/output. [F]
- Architecture: layout analysis + VLM-powered extraction. [A]
- Self-host: No. Cloud only. [F]
- Failure modes: discuss.google.dev thread "Issue with Custom Extractor: Unexpected Fields in JSON Output" notes that the UI and API batch mode apply schemas differently (https://discuss.google.dev/t/issue-with-custom-extractor-unexpected-fields-in-json-output/179607, 2025-2026). [F]
- 3rd-party note (DocuPipe 2026): "Document AI's Custom Extractor requires 50-100 labeled documents before extraction works" (https://www.docupipe.ai/vs/google-document-ai, fetched 2026-06-14). [A — used as competitive baseline only]
- License: proprietary.

### 2. Azure AI Document Intelligence (formerly Form Recognizer)

- Vendor: Microsoft. Service name: Azure AI Document Intelligence (Foundry Tools). [F]
- Models: `prebuilt-layout`, `prebuilt-read`, `prebuilt-document`, prebuilt (invoices, receipts, business cards, IDs, contracts, W-2, tax 2025), custom (template + neural). [F, learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0, fetched 2026-06-14, page `document_id` 7c38afd5-0d67-48f8-9c68-433acf7fd956]
- Layout v4.0 (2024-11-30 GA) outputs: `pages`, `paragraphs` (roles: title, sectionHeading, footnote, pageHeader, pageFooter, pageNumber), `lines`, `words`, `selection_marks`, `tables` (rowIndex/columnIndex/columnSpan/rowSpan/columnHeader), `figures`, `sections`, and Markdown output format with HTML tables for merged cells. [F, layout docs]
- Table schema (verbatim from docs):
  ```json
  {
    "rowCount": 9, "columnCount": 4,
    "cells": [
      {"kind": "columnHeader", "rowIndex": 0, "columnIndex": 0, "columnSpan": 4,
       "content": "(In millions, except earnings per share)", "boundingRegions": [...], "spans": [...]}
    ]
  }
  ```
  [F]
- "For v4.0 2024-11-30 (GA), the representation of tables is changed to HTML tables to enable rendering of items like merged cells and multirow headers." [F]
- "Table analysis isn't supported if the input file is XLSX." [F]
- "For v4.0 2024-11-30 (GA), the bounding regions for figures and tables cover only the core content and exclude the associated caption and footnotes." [F]
- Input: PDF, JPEG/PNG/BMP/TIFF/HEIF, DOCX, XLS, PPTX, HTML. PDF/TIFF up to 2,000 pages; paid S0 500 MB, free F0 4 MB; image dimensions 50–10000 px; min text 12 px at 1024×768. [F]
- Self-host: Document Intelligence Docker container available for on-prem (referenced in product page: "on premises and in the cloud with the AI Document Intelligence studio or SDK"). [F, https://azure.microsoft.com/en-us/services/form-recognizer/]
- License: proprietary.

### 3. Amazon Textract

- Vendor: AWS. Service name: Amazon Textract. [F]
- Four AnalyzeDocument feature types: Forms, Tables, Queries, Signatures (https://aws.amazon.com/textract/pricing/, fetched 2026-06-14). [F]
- Table JSON: `TABLE` block with `CHILD` (cell IDs), `MERGED_CELL`, `TABLE_TITLE`, `TABLE_FOOTER` relationship types and `EntityType` of `STRUCTURED_TABLE` or `SEMI_STRUCTURED_TABLE`. Cells have `rowIndex`, `columnIndex`, `rowSpan`, `columnSpan`, `EntityTypes` ∈ `{TABLE_TITLE, TABLE_FOOTER, TABLE_SECTION_TITLE, COLUMN_HEADER, TABLE_SUMMARY}`. [F, https://docs.aws.amazon.com/textract/latest/dg/how-it-works-tables.html, fetched 2026-06-14]
- Confidence: example "Balance" word Confidence 99.957%; "Sheet" word 99.87%; title cell 77.44%. [F]
- Pricing: per-page, with separate feature pricing. [F]
- Latency: synchronous `AnalyzeDocument` ≤1 page; async `StartDocumentAnalysis` for multipage PDFs. [A]
- Self-host: No. Cloud only. [F]
- License: proprietary.

### 4. Amazon Bedrock Data Automation (BDA)

- Vendor: AWS. [F, https://aws.amazon.com/blogs/machine-learning/intelligent-document-processing-at-scale-with-generative-ai-and-amazon-bedrock-data-automation/, 2025]
- "As of June 2025, Amazon Bedrock Data Automation supports documents up to 20 pages for custom attributes extraction." [F]
- "BDA's automatic splitting is designed to divide documents based on semantic boundaries. It supports files with up to 1000 pages and individual documents of up to 20 pages." [F, https://repost.aws/questions/QUAx0fpXIiS2uX0yzDKN5AaQ/document-splitting-in-bedrock-data-automation]
- Output: standard output for docs/images/video/audio with predefined structures, plus custom blueprint with up to 10 representative document assets for instruction optimization. [F, https://aws.amazon.com/about-aws/whats-new/2025/12/bedrock-data-automation-optimization-document-blueprints/]
- Modality controls added April 2025 to preserve hyperlinks. [F, https://aws.amazon.com/about-aws/whats-new/2025/04/amazon-bedrock-data-automation-modality-controls-hyperlinks-larger-documents/]
- Architecture: generative AI multi-modal wrapper around Bedrock. [A]
- License: proprietary.

### 5. IBM watsonx Discovery / Datacap

- watsonx Discovery is the cloud IDP/search product; Datacap is the on-prem capture product. Both still in IBM catalog as of 2026. [A — to be expanded if needed in a deeper dive]

### 6. ABBYY Vantage / FlexiCapture

- ABBYY Vantage is the cloud skill-based IDP platform; FlexiCapture is the on-prem large-volume capture. Both are still primary ABBYY products. [A — to be expanded if needed]

## Open-Source Table & Form Extractors

### Microsoft Table Transformer (TATR)

- Repo: https://github.com/microsoft/table-transformer. License: MIT (LICENSE file in repo root). [F, fetched 2026-06-14]
- Papers: PubTables-1M (CVPR 2022, arXiv:2110.00061), GriTS (arXiv:2203.12555, ICDAR 2023), Aligning benchmark datasets (arXiv:2303.00716, ICDAR 2023). [F, README]
- Pre-trained weights released: TATR-v1.0, TATR-v1.1-Pub, TATR-v1.1-Fin, TATR-v1.1-All. [F, README "Pre-trained Model Weights" table]
- TATR-v1.0 PubTables-1M metrics (test set): AP 0.902, AP50 0.970, AP75 0.941, AR 0.935; GriTSTop 0.9849, GriTSCon 0.9850, GriTSLoc 0.9786, AccCon 0.8243. [F, README "Evaluation Metrics"]
- Table detection (DETR R18, PubTables-1M): AP 0.970, AP50 0.995, AP75 0.989, AR 0.985. [F]
- Inference architecture — class map for structure model includes 7 classes: `table, table column, table row, table column header, table projected row header, table spanning cell, no object` — file `src/inference.py:42-49` (L42 `class_map = {`, L43 `'table': 0`). [F, file_path:line_number]
- Detection transform pipeline: `MaxResize(800)` then `ToTensor` then `Normalize(mean, std)` — file `src/inference.py:24-35`. [F, file_path:line_number]
- Structure transform pipeline: `MaxResize(1000)` then `ToTensor` then `Normalize` — file `src/inference.py:37-41`. [F, file_path:line_number]
- HTML output uses `<table>` with `colspan`/`rowspan` and `th`/`td` — `cells_to_html` at `src/inference.py:545-578` (e.g. L545 `def cells_to_html(cells):`; L562-567 handle `colspan`/`rowspan`; L569-572 emit `<thead>`/`<tr>`). [F, file_path:line_number]
- CSV output flattens multi-row headers — `cells_to_csv` at `src/inference.py:516-542` (L516 `def cells_to_csv(cells):`; L533-538 join header rows with ` | `). [F, file_path:line_number]
- Architecture: object detection (DETR R18) on cropped page/table images. Inference takes image + extracted text (from OCR or PDF) to produce HTML or CSV. [F, README: "TATR is an object detection model that recognizes tables from image input. The inference code built on TATR needs text extraction (from OCR or directly from PDF) as a separate input..."]
- Self-host: yes (Python + PyTorch; conda env from `environment.yml`). [F]

### Camelot

- Repo: https://github.com/camelot-dev/camelot. License: MIT. [F, fetched 2026-06-14]
- Five parsers: `lattice` (ruled), `stream` (whitespace), text-alignment `network`/`hybrid`, and the optional neural `ml` (Table Transformer) for hard borderless tables; `flavor="auto"` picks one. [F, README "Features" section]
- `ml` backend "on FinTabNet roughly doubles borderless TEDS vs network/hybrid" (opt-in via `pip install "camelot-py[ml]"`). [F, README "Which parser should I use?" table]
- Output formats: CSV, JSON, Excel, HTML, Markdown, SQLite (each table is a pandas DataFrame). [F, README]
- Quality metrics per table: accuracy, whitespace, order, page — see `tables[0].parsing_report` example. [F, README]
- Multi-page stitch via `stack_contiguous()`. [F]
- Source line citations (file: `camelot/parsers/lattice.py`):
  - Three engines `'raster' | 'vector' | 'combined'` (default `combined`) — L60, L186-189 (`_resolve_engine` docstring). [F, file_path:line_number]
  - `_GRID_WHITESPACE_REJECT = 90.0` — L28-30 (rejects near-empty ruled grids as detection noise; the comment at L26-29 names the rationale). [F, file_path:line_number]
  - `_reject_table` returns `table.whitespace >= _GRID_WHITESPACE_REJECT` — L351-353. [F, file_path:line_number]
  - `_augment_masks_with_vector_lines` unions PDF vector ruled lines into OpenCV line masks (combined engine) — L260-285. [F, file_path:line_number]
- Self-host: yes. No external cloud dependency. [F]

### Tabula

- Repo: https://github.com/tabulapdf/tabula. License: MIT. [F, fetched 2026-06-14]
- Status note: "Tabula is, and always has been, a volunteer-run project... the end-user application... is unlikely to see updates from us in the near future. `tabula-java` sees updates and occasional bug-fix releases from time to time." [F, README "Is `tabula` an active project?"]
- "Tabula only works on text-based PDFs, not scanned documents." [F, README "Caveat"]
- Active extraction library: `tabula-java` (Java) plus bindings `tabula-py` (Python, community), `tabulizer` (R, community), `tabula-js` (Node, community). [F, README "Incorporating Tabula into your own project"]
- License of `tabula-java`: MIT. [F]

### pdfplumber

- Repo: https://github.com/jsvine/pdfplumber. License: MIT. [F, fetched 2026-06-14]
- Built on `pdfminer.six`. "Plumb a PDF for detailed information about each text character, rectangle, and line. Plus: Table extraction and visual debugging." [F, README]
- Approach to table detection "borrows heavily from Anssi Nurminen's master's thesis, and is inspired by Tabula." Five-step algorithm: (1) find explicit/implicit lines, (2) merge overlapping lines, (3) find intersections, (4) find rectangles, (5) group contiguous cells. [F, README "Extracting tables"]
- `find_tables`, `find_table`, `extract_tables`, `extract_table`, `debug_tablefinder` methods. [F, README]
- Highly configurable `table_settings` (vertical/horizontal strategies: `lines`, `lines_strict`, `text`, `explicit`). [F, README]
- Tested on Python 3.10–3.14. [F, README]
- Self-host: yes.

### PaddleOCR / PP-Structure

- Repo: https://github.com/PaddlePaddle/PaddleOCR. License: Apache-2.0. [F, fetched 2026-06-14]
- Stack includes PP-OCRv5 (50 languages unified, +4.6% detection / +5.1% recognition over v5_server), PP-OCRv6, PaddleOCR-VL-0.9B (VLM), PaddleOCR-VL-1.5, PaddleOCR-VL-1.6, and PP-StructureV3. [F, README "Recent updates"]
- PaddleOCR-VL-1.6 (released 2026-06-11): "Achieves over 96.3% on OmniDocBench v1.6, also sets new SOTA on OmniDocBench v1.5 and Real5-OmniDocBench, leading both open-source and proprietary solutions in text, formula, and table recognition." [F, README, arXiv:2606.03264]
- PaddleOCR-VL (0.9B VLM, 2025-10-16): integrates NaViT-style dynamic resolution visual encoder with ERNIE-4.5-0.3B; supports 109 languages; SOTA on page-level and element-level document parsing. [F, arXiv:2510.14528]
- PP-StructureV3: "seamlessly convert complex PDFs and images into Markdown or JSON. Unlike the PaddleOCR-VL series models, it provides more fine-grained coordinate information, including table cell coordinates, text coordinates, and more." [F, README]
- 100+ languages supported; 0.13 s per page on A100 GPU. [F, README]
- Self-host: yes (CPU/GPU/XPU). Datalab's Marker README records Marker "0.816 / 0.907 with use_llm / 0.829 Gemini" on FinTabNet (table HTML TEDS). [A, datalab-to/marker, https://github.com/datalab-to/marker]

### Docling (IBM)

- Repo: https://github.com/docling-project/docling. License: MIT. [F, fetched 2026-06-14]
- Technical report: arXiv:2408.09869 (v5, 9 Dec 2024). "This technical report introduces Docling, an easy to use, self-contained, MIT-licensed open-source package for PDF document conversion. It is powered by state-of-the-art specialized AI models for layout analysis (DocLayNet) and table structure recognition (TableFormer)." [F, arxiv.org/abs/2408.09869]
- Output: DoclingDocument (lossless JSON), Markdown, HTML, WebVTT, DocLang, DocTags (arXiv:2503.11576). [F, README]
- Supports: PDF, DOCX, PPTX, XLSX, HTML, EPUB, WAV, MP3, WebVTT, EML, MSG, images (PNG, TIFF, JPEG), LaTeX, DocLang, plain text. [F, README]
- "🔒 Local execution capabilities for sensitive data and air-gapped environments." [F, README]
- VLM support: GraniteDocling (https://huggingface.co/ibm-granite/granite-docling-258M). [F, README]
- New in 2026: "📊 Chart understanding (Barchart, Piechart, LinePlot): converting them into tables, code or adding detailed descriptions"; "Parsing of XBRL (eXtensible Business Reporting Language) documents for financial reports". [F, README "What's new"]
- Marker's benchmark comparison (2026): Docling heuristic 86.7073, LLM 3.70429 (overall PDF conversion). [F, https://github.com/datalab-to/marker, fetched 2026-06-14]

### Unstructured (Unstructured-IO)

- Repo: https://github.com/Unstructured-IO/unstructured. License: Apache-2.0. [F, fetched 2026-06-14]
- "Open-source components for ingesting and pre-processing images and text documents, such as PDFs, HTML, Word docs, and many more. The use cases of `unstructured` revolve around streamlining and optimizing the data processing workflow for LLMs." [F, README]
- `partition()` auto-detects filetype and routes to specific partitioner; supports PDF, DOCX, PPTX, EML, XLSX, HTML, etc. [F, README]
- Dependencies: `libmagic-dev`, `poppler-utils`, `tesseract-ocr`, `libreoffice`; `pypandoc-binary` (bundled). [F, README]
- Telemetry off by default (`UNSTRUCTURED_TELEMETRY_ENABLED=true` to opt in). [F, README "Analytics"]
- Output elements: `Title`, `NarrativeText`, `ListItem`, `Table`, `FigureCaption`, `Header`, `Footer`, etc. (auto-classified). [A, per docs.unstructured.io]
- Latest: 0.23.1 (11 Jun 2026). [F, releases]
- Self-host: yes.

### Marker (Datalab)

- Repo: https://github.com/datalab-to/marker. License: GPL-3.0 (code); model weights use modified AI Pubs Open Rail-M. [F, fetched 2026-06-14]
- "Marker converts documents to markdown, JSON, chunks, and HTML quickly and accurately. Converts PDF, image, PPTX, DOCX, XLSX, HTML, EPUB files in all languages. Formats tables, forms, equations, inline math, links, references, and code blocks." [F, README]
- Pipeline: providers → builders (initial blocks) → processors (per-block cleanup, including a table formatter) → renderers (markdown / HTML / JSON / chunks). [F, README "Internals"]
- Architecture pieces: `Providers`, `Builders`, `Processors`, `Renderers`, `Schema`, `Converters` — all under `marker/`. [F, README]
- Specialized `TableConverter` (per-page or whole doc table extraction) with `force_layout_block=Table` to skip layout detection. [F, README "Extract tables"]
- `ExtractionConverter` (beta) for structured extraction with a user-supplied Pydantic schema via `--page_schema`. [F, README "Structured Extraction (beta)"]
- **FinTabNet table extraction scores** (99 test tables, FinTabNet.c, HTML TEDS, H100):
  - Marker: 0.816
  - Marker with `use_llm`: 0.907
  - Gemini 2.0 Flash: 0.829
  [F, README "Table Conversion"]
- **Overall PDF conversion scores** (single PDF pages, H100):
  - Marker: heuristic 95.6709, LLM 4.23916, avg time 2.84 s
  - LlamaParse: heuristic 84.2442, LLM 3.97619, avg time 23.35 s
  - Mathpix: heuristic 86.4281, LLM 4.15626, avg time 6.36 s
  - Docling: heuristic 86.7073, LLM 3.70429, avg time 3.70 s
  [F, README "Overall PDF Conversion" table]
- Throughput: 25 pages/s projected on H100; time per page 0.18 s on H100 in chunk mode; 3.17 GB VRAM avg, 5 GB peak. [F, README "Throughput"]
- Marker `--use_llm` supports Gemini, Vertex, Ollama, Claude, OpenAI, Azure OpenAI. [F, README "LLM Services"]
- Self-host: yes. Code is GPL-3.0; weights have commercial restrictions. [F]

### Surya (Datalab)

- Repo: https://github.com/datalab-to/surya. License: Apache-2.0 (code); weights: modified AI Pubs Open Rail-M. [F, fetched 2026-06-14]
- "Surya is a 650M param OCR model with these features: Accuracy — scores 83.3% on olmOCR-bench (top under 3B params); Speed — throughput of 5 pages/s on an RTX 5090; Multilingual — scores 87.2% on an internal benchmark set of 91 languages; Layout analysis (table, image, header, etc.) with reading order; Table recognition (rows + columns)." [F, README]
- olmOCR-bench Pareto frontier (sizes from dataset card):
  - Infinity-Parser2-Pro 35.1B → 87.6
  - Chandra OCR 2 (Datalab) 5.3B → 85.9
  - dots.mocr 3.0B → 83.9
  - **Surya OCR 2 (Datalab) 0.65B → 83.3** (best under 3B)
  - LightOnOCR 2-1B 1.0B → 83.2
  - olmOCR (anchored) 8.3B → 77.4
  - GOT OCR 0.6B → 48.3
  [F, README "olmOCR-bench"]
- Surya 2 per-source pass rates (default preset, 8,413 tests): ArXiv 88.3, Base 99.7, Hdr/Ftr 92.5, TinyTxt 93.7, MultCol 82.4, OldScan 41.8, OldMath 81.4, Tables 86.6. [F, README]
- Multilingual: 87.2% pass rate across 91 languages; 38/91 ≥ 90%, 76/91 ≥ 80%. Top: it 93.0%, en 92.3%, es 90.7%, de 89.7%, fr 89.3%, ru 88.8%, ja 86.2%, zh 82.5%, hi 82.2%, ar 72.7%. [F, README "Multilingual"]
- Table recognition: detects rows/columns with bboxes; default returns row × column intersections; `predict_full` returns full HTML (spanning cells, multi-row headers). [F, README "Table Recognition"]
- Architecture: shared VLM for layout/OCR/table_rec (Qwen3.5-style, ~650M params); detection is a separate EfficientViT/Segformer torch model. Inference via vllm (GPU) or llama.cpp (CPU/Apple Silicon). [F, README "Training"]
- Self-host: yes. Surrogate server via vLLM (Docker) or llama.cpp binary. [F]

## Schema / Structured-Output Tooling

### OpenAI Structured Outputs

- Doc: https://platform.openai.com/docs/guides/structured-outputs. [F, fetched 2026-06-14]
- "Structured Outputs is a feature that ensures the model will always generate responses that adhere to your supplied JSON Schema, so you don't need to worry about the model omitting a required key, or hallucinating an invalid enum value." [F]
- Two forms: function-calling tool schema, or `text.format` / `response_format` with `type: json_schema` and `strict: true`. [F]
- "Structured Outputs with response_format: {type: 'json_schema', ...} is only supported with the gpt-4o-mini, gpt-4o-mini-2024-07-18, and gpt-4o-2024-08-06 model snapshots and later." [F, OpenAI docs]
- Python SDK supports Pydantic / Zod directly (`text_format=CalendarEvent` returns `event.parsed`). [F]
- License: OpenAI API (proprietary). The Pydantic / Zod models live in user code.

### Instructor

- Repo: https://github.com/567-labs/instructor. License: MIT. [F, fetched 2026-06-14]
- "Get reliable JSON from any LLM. Built on Pydantic for validation, type safety, and IDE support." [F, README]
- One unified API across OpenAI, Anthropic, Google, Ollama, Groq, etc. via `instructor.from_provider("openai/gpt-4o")`. [F, README "Works with every major provider"]
- Features: automatic retries on validation failure, `Partial[T]` streaming, nested Pydantic models, multi-language (Python, TypeScript, Ruby, Go, Elixir, Rust). [F, README]
- Notable users: OpenAI, Google, Microsoft, AWS (per README testimonial). [A — "used in production by" section]
- Multi-modal content (images, PDFs) supported via `response_model` + provider-specific upload. [A, per instructor docs]

### Pydantic / JSON Schema Draft 2020-12

- Pydantic v2 is the de-facto Python schema-construction tool; OpenAI Structured Outputs / Anthropic tool use / Gemini function calling all accept Pydantic-derived JSON Schema. [A]
- Pydantic model supports `model_json_schema()` → JSON Schema 2020-12. [F, Pydantic docs]
- Anthropic tool use: similar JSON Schema constraint on `input_schema`. [A]
- Gemini function calling: accepts JSON Schema via `response_schema` + `response_mime_type="application/json"`. [A]

### Outline / Outlines

- Outline: https://github.com/outlines-dev/outlines — guaranteed structured text generation using regex/JSON Schema/grammar-constrained sampling. [A, based on knowledge of library]
- Outlines: https://github.com/dottxt-ai/outlines — successor by dottxt, supports JSON Schema, regex, CFG, multiple backends (vLLM, TGI, llama.cpp, transformers). [A]

### docTR

- Repo: https://github.com/mindee/doctr — Mindee's OSS OCR (DBNet + CRNN). Focused on OCR + document classification, not table structure per se. [A, docTR is not a primary table extractor]

### Marker-PDF schema options

- Already covered under Marker. `ExtractionConverter` (beta) consumes a Pydantic schema and emits structured JSON. [F, https://github.com/datalab-to/marker]

## Benchmarks

### PubTabNet

- Zhong et al., CVPR 2020 — 516k+ tables with HTML structure labels from PubMed. Companion to TableNet. [A — established dataset; counts and methodology in paper]

### PubTables-1M

- Smock et al., CVPR 2022 (arXiv:2110.00061). 575,305 pages / 947,642 tables for detection+structure+functional analysis. [F, microsoft/table-transformer README; huggingface.co/datasets/bsmock/pubtables-1m]
- TATR-v1.0 metrics on this set quoted above. [F]

### TableBank

- Li et al., 2020 — large-scale table detection/recognition dataset based on Word/LaTeX documents. [A]

### FinTabNet

- Zheng et al., ICDAR 2021. Financial document tables from annual reports (10-K, 10-Q). [A]
- Marker's 0.816 / 0.907 / 0.829 (Gemini) FinTabNet test split. [F, https://github.com/datalab-to/marker, README "Table Conversion"]

### DocVQA

- Mathew et al., WACV 2021. Document Visual QA. [A]

### FUNSD

- Jaume et al., ICDAR 2019. Form Understanding in Noisy Scanned Documents. [A]

### CORD

- Park et al., 2019. Consolidated Receipt Dataset (post-OCR receipt). [A]

### Kleister-NDA / Kleister-Charity

- Stanislawek et al., ICDAR 2021. Long-form legal/NDA documents. [A]

### RoFuDa

- Deleted-recovery form understanding dataset. [A]

### ExtEval

- 2024 benchmark for extraction. [A]

### OmniTab

- 2023 (NAACL) — table extraction with pre-trained model (TableFormer-style). [A]

### OmniDocBench (v1.6 / v1.7)

- Repo: https://github.com/opendatalab/OmniDocBench. License: Apache-2.0. [F, fetched 2026-06-14]
- "OmniDocBench is a benchmark for evaluating diverse document parsing in real-world scenarios... includes 1651 PDF pages, covering 10 document types, 5 layout types, and 5 language types." [F, README]
- "Rich Annotation Information: 28 block-level (such as text paragraphs, headings, tables, etc.) and 4 span-level (such as text lines, inline formulas, subscripts, etc.) document elements." [F]
- Metrics: Edit distance, BLEU, METEOR, TEDS, COCODet (mAP, mAR). [F]
- v1.6 added 296 pages (complex nested tables, dense math, unconventional layouts) and the Multi-Granularity Adaptive Matching (MGAM) method. v1.7 added Qianfan-OCR leaderboard. [F, README "Updates"]

**OmniDocBench v1.6 leaderboard (key rows, raw numbers from README):**
| Model | Size | Overall ↑ | TextEdit ↓ | FormulaCDM ↑ | TableTEDS ↑ | TableTEDS-S ↑ | ReadOrderEdit ↓ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MinerU2.5-Pro | 1.2B | 95.75 | 0.036 | 97.45 | 93.42 | 95.92 | 0.120 |
| GLM-OCR | 0.9B | 95.22 | 0.044 | 97.18 | 92.83 | 95.39 | 0.133 |
| PaddleOCR-VL-1.5 | 0.9B | 94.93 | 0.038 | 96.89 | 91.67 | 94.37 | 0.130 |
| PaddleOCR-VL | 0.9B | 94.18 | 0.040 | 95.91 | 90.65 | 93.74 | 0.135 |
| Youtu-Parsing | 2.5B | 93.74 | 0.044 | 93.63 | 92.02 | 95.00 | 0.116 |
| MinerU-2.5 | 1.2B | 93.04 | 0.045 | 95.77 | 87.88 | 91.47 | 0.130 |
| Gemini 3 Pro | – | 92.91 | 0.064 | 95.99 | 89.15 | 92.96 | 0.165 |
| Gemini 3 Flash | – | 92.62 | 0.066 | 95.16 | 89.29 | 93.51 | 0.172 |
| dots.ocr | 3B | 90.77 | 0.048 | 89.95 | 87.18 | 90.58 | 0.138 |
| OpenDoc-0.1B | 0.1B | 90.67 | 0.049 | 93.02 | 83.88 | 87.45 | 0.140 |
| DeepSeek-OCR 2 | 3B | 90.25 | 0.050 | 91.84 | 83.89 | 87.75 | 0.144 |
| HunyuanOCR | 1B | 89.95 | 0.088 | 87.68 | 91.01 | 93.23 | 0.171 |
| Qwen3-VL-235B | 235B | 89.78 | 0.063 | 92.55 | 83.07 | 86.75 | 0.166 |
| MonkeyOCR-pro-3B | 3B | 88.57 | 0.074 | 88.74 | 84.35 | 88.62 | 0.189 |
| GPT-5.2 | – | 86.59 | 0.114 | 88.21 | 82.95 | 87.93 | 0.193 |
| Dolphin-1.5 | 0.3B | 86.52 | 0.094 | 87.49 | 81.43 | 84.82 | 0.167 |
| MinerU-Pipeline | – | 85.75 | 0.063 | 83.07 | 80.43 | 88.22 | 0.154 |
| olmOCR | 7B | 85.74 | 0.139 | 88.10 | 83.00 | 87.17 | 0.216 |
| Mistral OCR | – | 85.66 | 0.097 | 89.91 | 76.78 | 80.93 | 0.171 |
| Marker | – | 78.44 | 0.157 | 85.24 | 65.77 | 73.24 | 0.243 |

[F, https://github.com/opendatalab/OmniDocBench, fetched 2026-06-14]

**PaddleOCR-VL-1.6 (2026-06-11):** "Achieves over 96.3% on OmniDocBench v1.6, also sets new SOTA on OmniDocBench v1.5 and Real5-OmniDocBench, leading both open-source and proprietary solutions in text, formula, and table recognition." [F, PaddleOCR README, arXiv:2606.03264]

**olmOCR-bench (Surya 2 Pareto frontier quoted above).** [F, Surya README]

### Other emerging benchmarks (2024–2026)

- ClusterTabNet (arXiv:2402.07502, Feb 2024): transformer-encoder clustering for table detection + structure recognition on PubTables-1M, PubTabNet, FinTabNet. [F, arxiv.org/abs/2402.07502]
- Soric et al., "Benchmarking Table Extraction from Heterogeneous Scientific Extraction Documents" (arXiv:2511.16134, Nov 2025). [F, arxiv.org/abs/2511.16134]
- "Beyond String Matching: Semantic Evaluation of PDF Table Extraction" (arXiv:2603.18652). [F, arxiv.org/html/2603.18652]
- PulseBench-Tab: multilingual table extraction with graph-based eval (2025). [A, researchgate.net/publication/406465857]
- Infinity-Parser: layout-aware RL VLM, SOTA on OmniDocBench/olmOCR/PubTabNet/FinTabNet. [F, openreview.net/pdf?id=M3GgDDGYec]
- "Benchmarking Table Extraction: Multimodal LLMs vs Traditional OCR" (ACL 2025 XLLM workshop). [F, aclanthology.org/2025.xllm-1.2.pdf]

## Pipeline Patterns (observed across the literature)

- **PDF→JSON pipeline** (Azure DI v4.0): layout analysis + per-cell span + table JSON.
- **Image→HTML pipeline** (TATR): detection crop → structure recognition → cells_to_html with colspan/rowspan.
- **PDF→HTML pipeline** (Textract): block graph + child relationships + MERGED_CELL composition.
- **PDF→Markdown pipeline** (Marker): surya OCR + layout + LLM augmentation for cross-page table merge.
- **PDF→JSON-schema pipeline** (OpenAI Structured Outputs + Marker ExtractionConverter): page-by-page crop + VLM call constrained by JSON Schema.
- **Doc→DoclingDocument** (Docling): page layout + TableFormer for structure + DocTags/DocLang output.
