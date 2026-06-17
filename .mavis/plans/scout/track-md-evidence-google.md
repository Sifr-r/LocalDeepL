# Evidence Inventory — Google Document AI, Gemini Document Understanding, NotebookLM (scout, track-md-evidence-google)

Fetched 2026-06-14. Methodology: web_search + webfetch against primary sources (cloud.google.com/document-ai, docs.cloud.google.com/gemini-enterprise-agent-platform, firebase.google.com/docs/ai-logic, blog.google, support.google.com/notebooklm, github.com/GoogleCloudPlatform, github.com/google-gemini, arxiv.org). For each subsystem, opened the canonical vendor doc and the public GitHub sample / cookbook repo. [F] = fact stated by source. [A] = synthesis / inference.

Cross-references: this evidence complements the schema/table track (`track-schema-evidence.md`, which already has Document AI row 1) and the OCR-vision track (`track-ocr-evidence.md`). It deliberately does NOT duplicate those — it goes deeper on Form Parser, Document OCR, Layout Parser, Custom Extractor, the Custom-Extractor Schema API, Gemini structured output / file input / PDF processing, and NotebookLM ingest.

---

## 1. Google Document AI — processors relevant to Anything-to-Markdown

### 1.1 Form Parser

- Vendor: Google Cloud. Service: Document AI. License: proprietary. [F, cloud.google.com/document-ai/docs/form-parser, fetched 2026-06-14]
- "Form Parser extracts key-value pairs (KVPs), tables, selection marks (like checkboxes), generic fields, and text to augment and automate document processing." [F, same]
- "Form Parser is pre-trained and cannot be up-trained." [F, same]
- Features (per vendor doc):
  - **KVP** — sets of two items within a document; can be used directly if keys are consistent, or with custom logic to normalize varied keys. [F]
  - **Generic entities** — out-of-the-box extraction of 11 fields: `email`, `phone`, `url`, `date_time`, `address`, `person`, `organization`, `quantity`, `price`, `id`, `page_number`. [F, same]
  - **Text and layout** — "use our latest OCR engine to extract text and layout information. This includes embedded text from digital PDFs (v2.1 only) or text from images." [F, same]
  - **Tables** — detect and extract tables from images and PDFs. [F, same]
  - **Checkboxes** — "high-quality selection mark detector, which extracts checkboxes from images and PDF output as KVP, using the text nearest the checkbox, with a `valueType` indicating whether it is filled or unfilled." [F, same]
- Language coverage: "Form Parser 2.0 supports over 200 languages." [F, same]
- Documented limitations:
  - "Prior JPEG compressions for TIFF are unsupported." [F, same]
  - "The checkbox model doesn't support parsing radio buttons. Some detected checkboxes might not have corresponding keys." [F, same]
  - "The model doesn't reliably parse a KVP with an unfilled value, such as a blank form." [F, same]
  - "The KVP parsing on documents in certain languages may have lower quality than Latin languages." [F, same]
- Recommended over Custom/Layout parsers when (vendor's own guidance):
  - "Dealing with structured forms: It excels at extracting KVPs from well-defined forms that look like conventional forms with labeled blanks to fill in, such as `name: __`. Form Parser's pre-trained model offers high accuracy for common fields like names, dates, and addresses." [F, same]
  - "Flexible table extraction is needed: Form Parser extracts from simple (no cells that span rows or columns) tables that look like tables. No training is needed (nor possible). For trained table extraction, the custom extractor can be used with a parent field containing column (cell) child fields." [F, same]
  - "Need efficiency: Avoid building and maintaining extraction parsers, especially for high-volume and varied forms of extraction tasks." [F, same]
- Processor versions (per /document-ai/docs/processors-list, fetched 2026-06-14):
  - `pretrained-form-parser-v1.0-2020-09-23` (Stable, GA, Legacy)
  - `pretrained-form-parser-v2.0-2022-11-10` (Stable, GA, "Recommended version. Supports generic entities and includes upgraded table, KVP, and checkbox model, as well as more than 200 languages.")
  - `pretrained-form-parser-v2.1-2023-06-26` (Release Candidate, "Public Preview version. Same model as v2.0 with native text extraction from digital PDF files enabled.")
- Quotas/limits (per same processor-list page): Max pages online sync = 15, batch async = 100, imageless mode online = 30. [F]
- Input file types: PDF, GIF, TIFF, JPEG, PNG, BMP, WebP. (No DOCX/PPTX/XLSX/HTML for Form Parser — those are Layout Parser only.) [F, cloud.google.com/document-ai/docs/file-types, fetched 2026-06-14]
- Output format: the `Document` proto / JSON, with `pages`, `entities`, `formFields`, `tables`, etc. [F, /document-ai/docs/output, fetched 2026-06-14]
- Markdown output capability: **None** natively. Form Parser returns structured JSON, not Markdown. The same is true for the `Document` proto generally — there is no first-class Markdown export from Form Parser, Layout Parser, Custom Extractor, or Document OCR. [A, based on /document-ai/docs/output and the absence of any Markdown export in the docs; cross-checked with /document-ai/docs/processors-list which lists output as `Document` JSON for all processors]
- Strengths: pre-trained, fast, no schema work needed, 200+ languages, KVP + tables + checkboxes in one call. [F, vendor doc above]
- Limitations: no Markdown output, no training/uptraining, simple tables only (no row/col spans), KVP quality varies on non-Latin languages. [F, vendor doc above]

### 1.2 Enterprise Document OCR

- Vendor: Google Cloud. Service: Document AI. License: proprietary. [F, cloud.google.com/document-ai/docs/enterprise-document-ocr, fetched 2026-06-14]
- Description: "Specialized model for document use cases. Advanced features include image-quality score, language hints, and rotation correction." [F, same]
- Default features:
  - "Extract embedded or native text from digital PDFs: This feature extracts text and symbols exactly as they appear in the source documents, even for rotated texts, extreme font sizes or styles, and partially hidden text." [F, same]
  - "Rotation correction: Use Enterprise Document OCR to preprocess document images to correct rotation issues that can affect extraction quality or processing." [F, same]
  - "Image-quality score: Receive quality metrics that can help with document routing. Image-quality score provides you with page-level quality metrics in eight dimensions, including blurriness, the presence of smaller-than-usual fonts, and glare." [F, same]
  - "Language detection: Detects the languages used in the extracted texts." [F, same]
  - "Language and handwriting hints: Improve accuracy by providing the OCR model a language or handwriting hint based on the known characteristics of your dataset." [F, same]
  - "Specify page range: Specifies the range of the pages in an input document for OCR." [F, same]
- Layout detection attributes: printed text, handwriting, paragraph, block, line, word, symbol-level, page number. Configurable Enterprise Document OCR features are: `page_number` (default), `printed text`, `handwriting`, `paragraph`, `block`, `line`, `word`. [F, same]
- Optional OCR add-ons (must be enabled individually, v2.0+):
  - **Math OCR** — "Identify and extract formulas from documents in [LaTeX](https://www.latex-project.org/) format." Output appears in `Document.pages[].visualElements[]` with `"type": "math_formula"`. [F, same]
  - **Checkbox extraction** — "Detect checkboxes and extract their status (marked/unmarked) in Enterprise Document OCR response." Output type: `filled_checkbox` / `unfilled_checkbox`. [F, same]
  - **Font style detection** — word-level attributes: `handwriting detection`, `font style`, `font size`, `font type`, `font color`, `font weight`, `letter spacing`, `bold`, `italic`, `underlined`, `text color (RGBa)`, `background color (RGBa)`. [F, same]
  - "**Math OCR and selection mark detection are mutually exclusive add-ons. They can't be enabled at the same time.**" [F, same, explicit cross-restriction]
- Image-quality analysis (defect types returned when `enableImageQualityScores=true`): `quality/defect_blurry`, `quality/defect_noisy`, `quality/defect_dark`, `quality/defect_faint`, `quality/defect_text_too_small`, `quality/defect_document_cutoff`, `quality/defect_text_cutoff`, `quality/defect_glare`. Limitations: "It can return false positive detections with digital documents with no defects. The feature is best used on scanned or photographed documents." "Glare defects are local. Their presence might not hinder overall document readability." [F, same]
- Languages: 200+, exact list in /document-ai/docs/processors-list (the page enumerates 50+ languages from Afrikaans to Yiddish with their BCP-47 tags, scripts, and handwriting support flags). [F, same, fetched 2026-06-14]
- Processor versions:
  - `pretrained-ocr-v1.2-2022-11-10` (Stable, GA, frozen for 18 months)
  - `pretrained-ocr-v2.0-2023-06-02` (Stable, GA, "Production-ready model specialized for document use cases. Includes access to all OCR add-ons.")
  - `pretrained-ocr-v2.1-2024-08-07` (Stable, GA, "better printed text recognition, more precise checkbox detection and more accurate reading order.")
  - `pretrained-ocr-v2.1.1-2025-01-31` (Release Candidate, similar to v2.1, not in US/EU/asia-southeast1)
  [F, same]
- Supported file formats: PDF, GIF, TIFF, JPEG, PNG, BMP, WebP. "Enterprise Document OCR also supports DocX files up to 15 pages in sync and 30 pages in async. To make a quota increase request (QIR), follow the steps to request a quota adjustment. DocX support is in private preview. To request access, contact your Google account team." [F, same]
- Strengths: industry-leading 200+ languages, native-PDF fast path, Math OCR (LaTeX), font detection, quality scoring. [F, same]
- Limitations: Math OCR and checkbox extraction are mutually exclusive; image-quality analysis is "best used on scanned or photographed documents" and false-positives on digital docs; no Markdown output (only the `Document` JSON). [F, same + A]
- Pricing (US region, per 1,000 pages, fetched 2026-06-14 from cloud.google.com/generative-ai-app-builder/pricing "Document AI feature pricing" section):
  - Digitize text (OCR processor): $0 (first 1,000 pages/mo), then $1.50/1,000 (1,001–5,000,000), then $0.60/1,000 above 5,000,000. [F, same]
  - Layout Parser (includes initial chunking): $10.00 / 1,000 count. [F, same]
  - Page-size definitions for Layout Parser pricing:
    - "Images (JPEG/JPG, PNG, BMP, HEIF): Each image = 1 page"
    - "PDF: Each page in the PDF = 1 page"
    - "TIFF: Each image in the TIFF = 1 page"
    - "Word (DOCX): Up to 3,000 characters = 1 page"
    - "Excel (XLSX): Each tab = 1 page"
    - "Powerpoint (PPTX): Each slide = 1 page"
    - "HTML: Up to 3,000 characters = 1 page"
    - "Parsed Documents: Up to 3,000 characters = 1 page"
    [F, same]
  - Custom Extractor: $30 / 1,000 pages. Form Parser: $30 / 1,000 pages. Layout Parser: $10 / 1,000 pages. Custom Splitter: $5 / 1,000 pages. Custom Classifier: $5 / 1,000 pages. Summarizer: $25 / 1,000 pages. (These are also reflected in the older schema-evidence file, but the source is the same pricing page — cross-confirmed.) [F, same + cross-check vs /document-ai/pricing main page which redirected to /generative-ai-app-builder/pricing]

### 1.3 Layout Parser ("Gemini layout parser")

- Vendor: Google Cloud. Service: Document AI. License: proprietary. [F, cloud.google.com/document-ai/docs/layout-parse-chunk, fetched 2026-06-14]
- "The Document AI layout parser is an advanced text parsing and document understanding service that converts unstructured content from complex files into highly structured, precise and machine-readable information. It combines Google's specialized Object Character Recognition (OCR) models with the generative AI capabilities of Gemini." [F, same]
- "It understands the complete document structure, identifying elements like tables, figures, lists, and headers while preserving the contextual relationships between them, such as which paragraphs belong to which heading." [F, same]
- Use cases (per vendor):
  - "Document OCR: It can parse text and layout elements like heading, header, footer, table structure and figures from PDF documents."
  - "High-Fidelity Search & RAG: Its primary use is to prepare documents for Search and RAG pipelines. By creating context-aware chunks, it dramatically improves retrieval quality and the accuracy of generated answers."
  - "Structured Data Ingestion: It can parse complex documents (like 10-K filings or reports) and index structured content (like parsed tables or image descriptions) into databases."
  [F, same]
- Pipeline (vendor's own description, multi-stage):
  1. **Parse and Structure:** "The document is ingested. All elements are identified and organized into a tree format. This `DocumentLayout` proto field preserves the document's inherent hierarchy."
  2. **Annotate and Verbalize:** "Preview Gemini's generative capabilities are used to verbalize complex visual elements. Figures, charts, and tables are annotated with rich, textual descriptions."
  3. **Chunk and Augment:** "The parsed document and its annotations are used to create semantically coherent chunks. These chunks are augmented with contextual information, such as their ancestral headings, to ensure that the chunk's meaning is preserved even when retrieved in isolation."
  [F, same]
- Model versions (per same page):
  - `pretrained-layout-parser-v1.0-2024-06-03` (Stable, GA, default pre-trained processor version)
  - `pretrained-layout-parser-v1.5-2025-08-25` (Release Candidate, "powered by Gemini 2.5 Flash LLM for better layout analysis on PDF files. If used for non-PDF files, it will have the same behavior as the stable v1.0.")
  - `pretrained-layout-parser-v1.5-pro-2025-08-25` (Release Candidate, "powered by Gemini 2.5 Pro LLM. v1.5-pro has higher latency than v1.5.")
  - `pretrained-layout-parser-v1.6-pro-2025-12-01` (Release Candidate, Preview, "powered by Gemini 3.0 Pro LLM." Uses Vertex AI Gemini global endpoint, not DMZ-compliant — requests in US/EU may route globally.)
  - `pretrained-layout-parser-v1.6-2026-01-13` (Release Candidate, Preview, "powered by Gemini 3.0 Flash LLM." Same DMZ caveat.)
  [F, same]
- File type coverage (vendor's own table from the page):
  - **HTML** (`text/html`): paragraph, table, list, title, heading, page header, page footer. Limitation: "parsing relies heavily on HTML tags, so CSS-based formatting might not be captured." [F]
  - **PDF** (`application/pdf`): figure, paragraph, table, title, heading, page header, page footer. Limitation: "Tables spanning multiple pages might be split in two tables." [F]
  - **DOCX** (`application/vnd.openxmlformats-officedocument.wordprocessingml.document`): paragraph, tables across multiple pages, list, title, heading elements. Limitation: "Nested tables are not supported." [F]
  - **PPTX** (`application/vnd.openxmlformats-officedocument.presentationml.presentation`): paragraph, table, list, title, heading elements. Limitation: "For headings to be identified accurately, they should be marked as such within the PowerPoint file. Nested tables and hidden slides are not supported." [F]
  - **XLSX** (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`): tables within Excel spreadsheets, supporting `INT`, `FLOAT`, and `STRING` values. Limitation: "Multiple table detection is not supported. Hidden sheets, rows, or columns might also impact detection. Files with up to 5 million cells can be processed." [F]
  - **XLSM** (`application/vnd.ms-excel.sheet.macroenabled.12`): spreadsheet with macro enabled, supporting `INT`, `FLOAT`, and `STRING` values. Limitation: "Multiple table detection is not supported. Hidden sheets, rows, or columns might also impact detection." [F]
  [F, same]
- **Quotas/limits (Layout Parser, from the same page):**
  - Online processing: "Input file size maximum of 20 MB for all file types" + "Maximum of 15 pages per PDF file."
  - Batch processing: "Maximum single file size of 1 GB for PDF files" + "Maximum of 500 pages per PDF file."
  [F, same]
- Key capabilities (vendor):
  - "Advanced table parsing" — "Tables in financial reports or technical manuals are a common failure point for RAG. Gemini layout parser excels at extracting data from complex tables with merged cells and intricate headers." [F, same]
  - "Reduced hallucinations" — "Unlike pure LLM-based parsers that try to read text that isn't there, Gemini layout parser's foundation in advanced OCR grounds it in the document's actual content. This leads to significantly fewer hallucinations." [F, same]
  - "Layout-aware chunking" — "Gemini layout parser understands the document's hierarchy. It creates context-aware chunks that include content from ancestral headings and table headers." [F, same]
  - "Layout annotation" — "When processing a bank report, the parser doesn't just see an image. It generates a detailed description and extracts the data points from all three pie charts, making that data available for retrieval." [F, same, with worked LaTeX-style "diagram-to-prose" example for a BigQuery ARIMA model diagram]
- **Markdown output capability: None native.** Layout Parser outputs the `Document` JSON proto with `DocumentLayout`, chunks, and `visualElements`. There is no Markdown string in the response. [A, based on /document-ai/docs/output and the explicit pipeline description which says "context-aware chunks" — the chunk is structured, not Markdown]
- **Audio/video support: No.** Layout Parser is document-only (PDF/HTML/DOCX/PPTX/XLSX/XLSM). [F, file-types table]
- **EPUB support: No** (not in the Layout Parser supported file types table). [F, same]
- Strengths: best-in-class complex table extraction (merged cells, multirow headers), Gemini-grounded text reduces hallucinations, layout-aware chunking is the RAG use case the product was built for, multi-format coverage including HTML/DOCX/PPTX/XLSX. [F, vendor doc + A]
- Limitations: no Markdown output, no EPUB, no audio/video, no PPTX nested tables, no XLSX multi-table detection, DMZ-noncompliant global routing on the v1.6 Gemini-3 previews, tables spanning multiple PDF pages can be split into two. [F, same]

### 1.4 Custom Extractor

- Vendor: Google Cloud. Service: Document AI. License: proprietary. [F, cloud.google.com/document-ai/docs/processors-list, fetched 2026-06-14]
- "Extract fields from documents using generative AI or custom models; fine-tune models to accurately extract data from your documents." [F, same]
- Type: `CUSTOM_EXTRACTION_PROCESSOR`. [F, same]
- Foundation-model versions (per processor list, current as of fetched 2026-06-14):
  - `pretrained-foundation-model-v1.5-2025-05-05` — Stable, GA, "powered by Gemini 2.5 Flash LLM."
  - `pretrained-foundation-model-v1.5-pro-2025-06-20` — Stable, GA, "powered by the Gemini 2.5 Pro LLM. Supports a quota of up to 30 pages per minute for online process requests. This model has improved quality compared to v1.5, and may have a higher latency."
  - `pretrained-foundation-model-v1.5.1-2025-08-07` — Release Candidate, "powered by the Gemini 2.5 Flash LLM. This model has the same features as v1.5, and has improved adaptive few-shot learning."
  - `pretrained-foundation-model-v1.6-pro-2025-12-01` — Release Candidate, "powered by the Gemini 3 Pro LLM." Caveat: "uses the Vertex AI Gemini global endpoint and is not compliant with Data Residency (DMZ) standards. For example, requests in US and EU endpoints might route to anywhere globally."
  - `pretrained-foundation-model-v1.6-2026-01-13` — Release Candidate, "powered by the Gemini 3 Flash LLM." Same DMZ caveat.
  [F, same]
- Important restriction: "If using generative AI for extraction, then: Only the English language is officially supported. Region availability is in the `US`, `EU`, `northamerica-northeast1` and `asia-southeast1`." [F, same]
- Quotas/limits: Max pages online sync = 15, batch async = 200, imageless mode online = 30. [F, same]
- Normalized data types: `dateTime` (STRING), `currency` (STRING), `money` (`google.type.Money`), `number` (FLOAT or INTEGER). [F, same]
- Pricing: Custom Extractor $30 / 1,000 pages (per pricing page, fetched 2026-06-14). [F, cloud.google.com/generative-ai-app-builder/pricing]
- **Schema API (formally: "Automated schema generation" / `ce-schema-extraction`)** [F, cloud.google.com/document-ai/docs/ce-schema-extraction, fetched 2026-06-14]:
  - "Document AI's automated schema generation lets you automatically generate a document's schema from a test document you supply. Then, you can approve or decline the schema and edit it manually. This saves time and effort when defining the document schema for your custom processor and lets you focus on refining the schema." [F, same]
  - "Automated schema generation also has a wider knowledge base on creating high quality schemas. This can potentially improve document extraction quality." [F, same]
  - Status: **Preview** ("This product is subject to the 'Pre-GA Offerings Terms' … available 'as is' and might have limited support.") [F, same]
  - Workflow: (1) "On the Get started tab, select Generate schema from document" (2) "Use the input field to select a local file to generate the schema, or use the Browse option to upload a sample document" with an optional "Generate a schema prompt" (3) "Select Generate Schema" (4) "Review the generated schema preview. You can choose accept or reject the schema with Apply schema or Abort schema, to try again with a different sample document or prompt" (5) Optional: add a prompt "specifying the document type, stating the most important parts of the document, or suggesting a target number of entities." [F, same]
  - If processor is "snapshotted or fine-tuned", the "Generate schema from document" option is not displayed. [F, same]
- **Custom Extractor Schema API ≠ "REST endpoint that returns Markdown".** The schema output is a JSON schema for entity extraction, not a Markdown document. [A, based on /document-ai/docs/ce-schema-extraction and the absence of any Markdown output]
- Generative-AI fine-tuning claim: "achieve higher accuracy by providing as few as 10 documents to fine-tune the large model." (Per existing schema-evidence cross-reference.) [F, /document-ai/docs/custom-extractor-overview, as quoted in track-schema-evidence.md line 13]
- Failure mode cited in 3rd-party benchmarks (already in track-schema-evidence): "the UI and API batch mode apply schemas differently" — the Custom Extractor UI and batch API have historically diverged on how `additionalProperties` / extra fields are treated. [F, /discuss.google.dev thread cited in track-schema-evidence.md]
- 3rd-party benchmark: "Document AI's Custom Extractor requires 50-100 labeled documents before extraction works" — useful baseline for low-shot comparison. [F, docupipe.ai/vs/google-document-ai, fetched 2026-06-14, as quoted in track-schema-evidence.md line 20]
- Strengths: production-grade extraction with LLM-backed zero-shot, then uptrainable to 10 docs; supports complex entity types (date/currency/money/number with normalization). [F, vendor doc + A]
- Limitations: English-only when using the generative path; non-DMZ on v1.6 Gemini-3; no Markdown output; 50–100 docs typically needed for fine-tuning, 3rd-party benchmark. [F, vendor doc + 3rd party]

### 1.5 Schema API (Custom Extractor schema tooling, broader sense)

- This entry covers the *other* "Schema API" surfaces in Document AI: (a) the JSON-Schema-like `Document` proto itself, (b) Custom Extractor schema authoring, (c) the `ce-cel-validation` (CEL) and `ce-validation` tools.
- The `Document` proto is the universal response container for all Document AI processors. [F, /document-ai/docs/reference/rest/v1/Document, and /document-ai/docs/output, fetched 2026-06-14]
- Custom Extractor schema authoring surface (`Schema` is a subset of OpenAPI 3.0 — the same object Gemini uses for function calling). [F, cross-referenced with /document-ai/docs/ce-mechanisms, fetched 2026-06-14, sidebar nav confirmed]
- CEL dialect for document validation: documented at /document-ai/docs/ce-cel-validation (sidebar entry). This is a CEL (Common Expression Language) dialect for expressing field-level validation rules on extracted entities. [F, /document-ai/docs/ce-cel-validation confirmed in nav; content not fetched in this scout]
- "Derived field and signature detection" — Custom Extractor can compute derived fields and detect signatures on documents. [F, /document-ai/docs/ce-derived-signature, confirmed in nav; content not fetched]
- Take-away: there is **no `Markdown` field in the Document proto**. The closest thing to "Markdown output" is the third-party `document-json-explorer` React tool that the doc-ai-samples repo links to (https://github.com/GoogleCloudPlatform/document-ai-samples/tree/main/document-json-explorer) for visual exploration. [A, /document-ai/docs/output and the doc-ai-samples README confirm explorer is for visualization, not export]

### 1.6 Document AI — overall architecture (synthesis)

- **Hybrid pipeline (vendor's own description on /document-ai/docs/layout-parse-chunk):** Document OCR engine → layout detection (figures, paragraphs, tables, titles, headings, page headers, page footers) → `DocumentLayout` tree → Gemini-powered verbalization of figures/charts/tables into textual descriptions → context-aware chunking augmented with ancestral headings. [F, same]
- **Per-processor pipeline:** Form Parser and Custom Extractor use the OCR engine internally and add their own extraction layer; Layout Parser is the most complete pipeline (OCR + layout + LLM verbalization + chunking); Document OCR is the bare OCR + layout layer. [A, based on /document-ai/docs/processors-list "Functions" column: OCR/Form Parsing/Entity Extraction for Form Parser, Layout Parsing/Document Chunking for Layout Parser, OCR/Quality Analysis for Document OCR, OCR/Entity Extraction for Custom Extractor]
- **Output IR:** All processors emit a `Document` JSON. The IR exposes: `pages[].blocks/paragraphs/lines/words/tokens/symbols/visualElements/tables/formFields/entities`, with normalized bounding boxes (`x, y` in `0..1`) and `textAnchor` segments. FieldMask in `ProcessRequest` lets you limit fields returned. [F, /document-ai/docs/output and /document-ai/docs/reference/rest/v1/Document, fetched 2026-06-14]
- **No Markdown output in the IR.** To get Markdown from Document AI you have to: (1) call a processor, (2) walk the `Document` JSON yourself, (3) render to Markdown in your own code. Document AI does not provide a server-side Markdown render. [A, based on /document-ai/docs/output + the absence of any Markdown export in /document-ai/docs/processors-list]

---

## 2. Gemini structured output / Document Understanding

### 2.1 Models, file input, and quotas (Vertex AI / Gemini Enterprise Agent Platform)

- All Gemini multimodal models in this section are documented on https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/document-understanding, fetched 2026-06-14. [F]
- Document understanding is a Vertex AI / Gemini Enterprise Agent Platform capability. The "Developer API" counterpart (api.google.dev) is reachable via Firebase AI Logic. [F, firebase.google.com/docs/ai-logic/analyze-documents, fetched 2026-06-14]
- Supported document MIME types (across all Gemini multimodal models): `application/pdf`, `text/plain`. [F, same; cross-confirmed in firebase.google.com/docs/ai-logic/analyze-documents]
- Supported models and limits (from the Vertex AI document-understanding table; for PDF and text):
  - **Gemini 3.5 Flash, 3.1 Flash-Lite, 2.5 Pro, 2.5 Flash (preview), 2.5 Flash**: Max files/prompt = 3,000. Max pages/file = 3,000. Max file size = 50 MB (API/Cloud Storage) or 7 MB (text/plain or direct upload via console). [F]
  - **Gemini 3.1 Pro (preview), 3 Flash (preview)**: Same 3,000 files / 3,000 pages, 50 MB PDF or 7 MB text. Default resolution tokens 560. "OCR for scanned PDFs: Not used by default." [F]
  - **Gemini 3.1 Flash Image (preview)**: Files limited by 128k context window; pages by 65,536 token context window. 50 MB PDF / 7 MB text. [F]
  - **Gemini 3 Pro Image (preview)**: Files/pages bounded by 65,536 token context window. 50 MB / 7 MB. [F]
  - **Gemini 2.5 Flash-Lite**: 3,000 files / 1,000 pages / 50 MB / 7 MB. [F]
  - **Gemini 2.5 Flash Image**: 3 files / 3 pages / 50 MB / 7 MB. [F]
  [F, all from /gemini-enterprise-agent-platform/models/capabilities/document-understanding, table rows 1404–1480]
- **Inline (base64) request size limit for the Firebase AI Logic / Gemini API:** "The total request size limit is 20 MB. To send large files, review the options for providing files in multimodal requests." [F, firebase.google.com/docs/ai-logic/analyze-documents, fetched 2026-06-14]
- **Inline payload size was raised from 20 MB to 100 MB in January 2026 for the Gemini API (general), but the Document Processing Firebase AI Logic page still documents a 20 MB inline limit.** [F, blog.google/innovation-and-ai/technology/developers-tools/gemini-api-new-file-limits, fetched 2026-06-14, vs firebase.google.com/docs/ai-logic/analyze-documents, fetched 2026-06-14 — these are two different surfaces, see the conflict note in §2.5]
- Per-page tokenization: "Each document page is equivalent to 258 tokens" (per Google's general Gemini API documentation; surfaced in web search snippet from ai.google.dev/gemini-api/docs/document-processing). [F, Google search snippet, ai.google.dev/gemini-api/docs/document-processing, accessed via web_search 2026-06-14 — the page itself was not directly fetchable due to transport errors]
- **Media resolution for PDFs** (Vertex AI document understanding, fetched 2026-06-14, lines 2103–2106 of the truncated file):
  - `MEDIA_RESOLUTION_HIGH` — 1120 tokens per page.
  - `MEDIA_RESOLUTION_MEDIUM` — 560 tokens per page.
  - `MEDIA_RESOLUTION_LOW` — 280 tokens per page.
  - `MEDIA_RESOLUTION_UNSPECIFIED` — 560 tokens per page (default).
  [F, /gemini-enterprise-agent-platform/models/capabilities/document-understanding]
- PDF best practices documented by Vertex (same page, lines 2145–2154):
  - "If your prompt contains a single PDF, place the PDF before the text prompt in your request." [F]
  - "If you have a long document, consider splitting it into multiple PDFs to process it." [F]
  - "Use PDFs created with text rendered as text instead of using text in scanned images. This format ensures text is machine-readable so that it's easier for the model to edit, search, and manipulate compared to scanned image PDFs. This practice provides optimal results when working with text-heavy documents like contracts." [F]
  - **Spatial reasoning caveat:** "Spatial reasoning: The models aren't precise at locating text or objects in PDFs. They might only return the approximated counts of objects." [F]
  - **Hallucination caveat:** "Accuracy: The models might hallucinate when interpreting handwritten text in PDF documents." [F]
- **Discontinued / deprecation (Firebase AI Logic banner, fetched 2026-06-14):** "Gemini 2.0 Flash and Flash-Lite models were shut down on June 1, 2026. To avoid service disruption, update to a newer model like `gemini-3.1-flash-lite`." "All Imagen models will shut down on June 24, 2026. Learn about migrating your apps to use Nano Banana." [F, firebase.google.com/docs/ai-logic, fetched 2026-06-14]

### 2.2 Structured output (JSON mode / function calling)

- Vendor: Google. Service: Gemini API (Developer API + Vertex AI Gemini Enterprise Agent Platform). [F, firebase.google.com/docs/ai-logic/generate-structured-output, fetched 2026-06-14; cross-referenced with blog.google/innovation-and-ai/technology/developers-tools/gemini-api-structured-outputs, fetched 2026-06-14]
- "The Gemini API returns responses as unstructured text by default. However, some use cases require structured text, like JSON." [F, firebase.google.com/docs/ai-logic/generate-structured-output]
- **JSON mode** = "Using a response schema to generate structured output is sometimes called 'JSON mode' or 'controlled generation'." [F, same]
- **How to invoke:** set `responseMimeType` to `application/json` (or `text/x.enum` for classification) and provide a `responseSchema` in the generation config. [F, same]
- **Supported schema fields** (sub-document, subset of OpenAPI 3.0):
  - `enum`
  - `items`
  - `maxItems`
  - `nullable`
  - `properties`
  - `required`
  [F, same]
- **Note on optional fields (Firebase-specific):** "By default, for Firebase AI Logic SDKs, all fields are considered *required* unless you specify them as optional in an `optionalProperties` array. For these optional fields, the model can populate the fields or skip them. Note that this is opposite from the default behavior of the two Gemini API providers if you use their server SDKs or their API directly." [F, same]
- **JSON Schema support (broader):** As of the Nov 5 2025 blog post, "We've now added support for JSON Schema to all actively supported Gemini models. This enables libraries like Pydantic (Python) or Zod (JavaScript/TypeScript) to work out-of-the-box with the Gemini API. It builds upon the current support for the Gemini API's Schema object that is based on OpenAPI 3.0 for Structured Outputs and Function Calling." [F, blog.google/innovation-and-ai/technology/developers-tools/gemini-api-structured-outputs, fetched 2026-06-14]
- Newly added JSON Schema keywords: `anyOf` (unions), `$ref` (recursive schemas), `minimum` / `maximum` (numeric constraints), `additionalProperties` and `type: 'null'`, `prefixItems` (tuple-like arrays). [F, same]
- **Implicit property ordering:** "The API now preserves the same order as the ordering of keys in the schema. This is supported for all Gemini 2.5 models and beyond and also applies to our OpenAI compatibility API." [F, same]
- **Function calling** is the parallel "tools" surface (also uses `Schema` for parameter declarations). [F, same]
- **Multimodal structured output:** "This guide focuses on text-only input, but Gemini can also produce structured responses to multimodal requests that include images, videos, and audio as input." [F, firebase.google.com/docs/ai-logic/generate-structured-output]
- Strengths: Pydantic/Zod-native, broad JSON Schema coverage, deterministic (or as close as the model gets), property-ordering, supports multimodal inputs. [F, same + A]
- Limitations: schema fields are a subset of OpenAPI 3.0 (the full list of unsupported fields is not enumerated in the docs but the supported list is the exhaustive allowlist); the schema counts against the input token limit; Firebase vs raw Gemini API differ on default optional-fields semantics. [F, same]

### 2.3 File API and file input methods

- Vendor: Google. Service: Gemini API (Developer API) and Vertex AI. [F, blog.google/innovation-and-ai/technology/developers-tools/gemini-api-new-file-limits, fetched 2026-06-14]
- Three input methods (post Jan 12 2026 update):
  1. **Inline (base64) data** — was 20 MB, now "increasing the maximum payload size for inline data from 20MB to 100MB (base64 encoded, with varying limits based on data types)." [F, blog post, fetched 2026-06-14]
  2. **External URLs (public or signed)** — "We now support both files stored in public domains, as well as private storage (via signed URLs). You can pass any publicly accessible URL (like a PDF or image on the web) directly in your generation request. We support pre-signed URLs for accessing data from AWS S3, Azure Blob Storage or other cloud providers." [F, same]
  3. **GCS object registration** — "If your data is already in Google Cloud Storage (GCS), you no longer need to move bytes. You can now register your GCS files directly with the Files API. This requires authenticating with OAuth credentials as an IAM user or service with read access to the storage bucket." [F, same]
- The Files API previously had 48-hour persistence for uploaded files; the new methods are designed to make that ephemeral storage unnecessary for production. [F, same]
- **PDF / document input on the Gemini Developer API:** "Gemini supports PDF files up to 50MB or 1000 pages. This limit applies to both inline data and Files API uploads. Each document page is equivalent to 258 tokens." [F, Google search snippet from ai.google.dev/gemini-api/docs/document-processing, accessed 2026-06-14 — note this page is referenced in search but transport-blocked for direct fetch]
- **Conflict note (§2.5):** Vertex AI document understanding gives 50 MB PDF and up to 3,000 pages per file depending on the model. The Developer API page cited above is more conservative (1,000 pages). These are two different surfaces. [F vs F; A note that the Vertex tables above are the source of truth for production]
- Strengths: 100 MB inline (Gemini API), GCS / signed-URL ingest, no need to re-upload data, multimodal. [F, blog post]
- Limitations: max 50 MB PDF, max 1,000–3,000 pages depending on surface, "spatial reasoning is imprecise", "may hallucinate handwritten text in PDF". [F, same + Vertex doc-understanding best-practices]

### 2.4 Architecture / pipeline summary (synthesis)

- **Input → model → output pipeline for "Gemini as a markdown converter":**
  1. File is provided as inline base64, File API URI, public URL, or signed URL/GCS URI. [F, blog.google/.../gemini-api-new-file-limits]
  2. The model tokenizes the PDF (each page ≈ 258 tokens by default, tunable via `media_resolution` on Vertex). [F, Vertex doc-understanding + Google search snippet from ai.google.dev/gemini-api/docs/document-processing]
  3. The model returns either:
     - free-form text (default; not Markdown by contract)
     - structured JSON conforming to `responseSchema` (`application/json`)
     - an enum value (`text/x.enum`)
     - function-call arguments (function calling)
     [F, firebase.google.com/docs/ai-logic/generate-structured-output]
  4. **Crucially, Gemini is not a deterministic converter — the output is a model generation. The user has to prompt for Markdown (or for a JSON structure that maps to Markdown downstream).** [A, based on /ai-logic/generate-structured-output's explicit "unstructured text by default" line and the lack of a `Markdown` output mode in the API]
- **There is no first-class "convert to Markdown" endpoint on the Gemini API.** You can prompt "respond in Markdown" or define a `responseSchema` whose field is a `string` of Markdown — but the Markdown-ness is a property of the prompt, not of the API. [A]
- **Open-source example code:**
  - `GoogleCloudPlatform/generative-ai/gemini/use-cases/document-processing/document_processing.ipynb` is the official Vertex AI Colab showing "Document Processing with Gemini". [F, /gemini-enterprise-agent-platform/models/capabilities/document-understanding, line 1384, fetched 2026-06-14]
  - `google-gemini/cookbook` is the official Gemini API cookbook — Jupyter-Notebook heavy (99.9%), 17.4k stars, 2.7k forks as of 2026-06-14. [F, github.com/google-gemini/cookbook, fetched 2026-06-14]
  - Both repos are Apache-2.0 licensed. [F, same]

### 2.5 Source conflicts surfaced

- **Inline file size limit conflict:**
  - Firebase AI Logic doc says 20 MB for inline. [F, firebase.google.com/docs/ai-logic/analyze-documents, fetched 2026-06-14]
  - Gemini API blog post (Jan 12 2026) says inline is now 100 MB. [F, blog.google/.../gemini-api-new-file-limits, fetched 2026-06-14]
  - **Interpretation [A]:** Firebase AI Logic's `analyze-documents` page is a Firebase-specific surface that has its own 20 MB cap and has not been updated to reflect the API's general 100 MB increase. These are different products on top of the same model.
- **PDF max pages conflict:**
  - Google search snippet from ai.google.dev/gemini-api/docs/document-processing: "up to 1000 pages". [F, accessed 2026-06-14 via web search]
  - Vertex AI document understanding: 3,000 pages/file on Gemini 3.1 Pro / 3 Flash, 3,000 on Gemini 3.5 Flash / 3.1 Flash-Lite / 2.5 Pro / 2.5 Flash, 1,000 on 2.5 Flash-Lite, 3 on 2.5 Flash Image. [F, /gemini-enterprise-agent-platform/models/capabilities/document-understanding, fetched 2026-06-14]
  - **Interpretation [A]:** The 1,000-page figure is the older Developer-API default; the Vertex AI tables are the current source of truth per-model. The ai.google.dev page is the older generation.

---

## 3. NotebookLM — ingest pipeline (publicly documented)

### 3.1 What NotebookLM is and is not

- Product: NotebookLM (Google Labs). URL: https://notebooklm.google.com (gated behind Google sign-in; the sign-in page is what was fetched, the product UI is not accessible without an account). [F, fetched 2026-06-14]
- Marketed as: "a tool for understanding. When you upload your sources, it instantly becomes an expert, grounding its responses in your material with citations and relevant quotes." [F, blog.google/innovation-and-ai/products/notebooklm-audio-video-sources, fetched 2026-06-14]
- Underlying model family: Gemini. "Since launching, we've continued to add support for a wide range of source materials using the multimodal capabilities in Gemini 1.5." [F, same, Sep 26 2024 blog]
- Architecture (per arXiv 2504.09720v2, Tufino, July 2025): "NotebookLM is a versatile, RAG-based environment … At its core, the platform is powered by Google's Gemini family of models. Its interface is structured into three primary components: a Sources panel for uploading and managing materials, a Chat panel for dialogue, and a Studio panel for generating structured summaries and other aids." [F, arxiv.org/html/2504.09720v2, fetched 2026-06-14]
- Ingest pipeline (vendor's own description from the help center, fetched 2026-06-14):
  - "A source is a copy or auto-synced version of the source document you import or upload to the app. When you use NotebookLM, the model uses the sources you upload to answer your questions or complete your requests." [F, support.google.com/notebooklm/answer/16215270]
- **NotebookLM does NOT import footnotes or comments from Google files.** "NotebookLM does not import footnotes or comments from Google files." [F, same]
- **Multi-tab Google Docs/Sheets are flattened.** "While NotebookLM will pull in data from multiple tabs in Google Docs and Google Sheets as one source." [F, same]
- **Audio files from Drive are not supported.** "Importing audio files from Drive is not supported." [F, same]
- **Web URL ingest:** "Only the text content of the given HTML webpage is scraped for use as a source. Images, embedded videos, or nested webpages are not imported. Paywalled webpages aren't supported. PDFs uploaded through URLs are treated as PDF sources." [F, same]
- **YouTube URL ingest:** "Only public YouTube videos with captions, either user-uploaded or auto-generated, are supported. Only the text transcript of the video is imported as a source. Videos uploaded less than 72 hours prior may not be available to import. Videos without speech aren't supported. If a video is deleted or made private, sources are auto-deleted from your notebook within 30 days. There is no limit for the length of the video unless the caption file contains over 500,000 words." [F, same]

### 3.2 Supported source types (per NotebookLM help, fetched 2026-06-14)

- **Audio files**: "MP3 and WAV, among others." (Plus the supported-import list later in the page: 3g2, 3gp, aac, aif, aifc, aiff, amr, au, avi, cda, m4a, mid, mp3, mp4, mpeg, ogg, opus, ra, ram, snd, wav, wma.) Audios with no speech are not supported. [F, same]
- **Copy-and-pasted text** [F]
- **Google Drive files, including:**
  - Google Docs
  - Google Slides: up to 100 slides
  - Google Sheets: at this time, files are limited to 100k tokens
  [F]
- **Google Docs** (standalone) [F]
- **Google Slides** (standalone) [F]
- **Google Sheets** (standalone) [F]
- **Images:** "Supported file types: avif, bmp, gif, heic, heif, ico, jp2, jpe, jpeg, jpg, png, tif, tiff, webp. At this time, certain types of images may not work as well." [F]
- **Microsoft Word (docx), Text (txt), Markdown (md), PDF files (pdf), CSV (csv), and PowerPoint (pptx) files** [F]
- **Web URLs** [F]
- **ePub files** [F]
- **YouTube URLs of public videos** [F]
- **Gemini Chats** (paid feature, "Chat with your notebooks in Gemini to add them as context to your NotebookLM notebooks.") [F]

### 3.3 Source limits (per NotebookLM help, fetched 2026-06-14)

- **"Each source can contain up to 500,000 words or up to 200MB for uploaded files. You can include up to 50 sources (for Free users)."** [F, same]
- NotebookLM Plus tier expands this to 300 sources per notebook (per arXiv 2504.09720v2 footnote 4: "the Plus subscription also significantly increases the platform's capacity, for instance from 50 to 300 sources per notebook, making it suitable for handling extensive course materials.") [F, arxiv.org/html/2504.09720v2]

### 3.4 Audio import — language support

- Per the help page, audio import supports 60+ languages including: Afrikaans, Amharic, Albanian, Arabic, Armenian, Azerbaijani, Bangla, Basque, Belarusian, Bulgarian, Burmese, Catalan, Czech, Danish, Dutch, English, Estonian, Filipino, Finnish, French, Galician, Georgian, German, Greek, Gujarati, Hebrew, Hindi, Hungarian, Icelandic, Indonesian, Italian, Japanese, Javanese, Khmer, Kannada, Korean, Lao, Latvian, Lithuanian, Macedonian, Malay, Malayalam, Marathi, Mongolian, Norwegian, Nepali, Punjabi, Persian, Polish, Portuguese, Romanian, Russian, Serbian, Sinhalese, Slovak, Slovene, Spanish, Sundanese, Swedish, Swahili, Tamil, Telugu, Thai, Traditional Cantonese, Traditional Chinese, Turkish, Ukrainian, Urdu, Uzbek, Vietnamese, Zulu. [F, same]

### 3.5 Documented features / modes (per help-page sidebar and confirmed by blog posts)

- Chat (Q&A against sources) [F]
- Mind Maps (auto-generated) [F]
- Audio Overview (podcast-style synthesis of sources) [F, blog.google/innovation-and-ai/products/notebooklm-audio-video-sources, Sep 26 2024]
- Video Overviews [F, sidebar]
- Flashcards / Quizzes [F, sidebar]
- Infographic generation [F, sidebar]
- Slide Deck generation [F, sidebar]
- Public notebooks (featured and shared) [F, sidebar]
- **Fast Research** (web or Drive search for sources) [F, sidebar + help]
- **Deep Research** (Gemini Deep Research agent surfaces research into the notebook; "Over 18 users only"; usage-limited) [F, help page]
- **Auto-label & categorize** (5+ sources) [F, help]
- "**Source limits apply. Results may be partially imported if usage limits are exceeded.**" [F, help]

### 3.6 Internal RAG architecture (per arXiv 2504.09720v2)

- "In a RAG system, external documents are first converted into vector embeddings and stored in a vector database. When a query is received, it is similarly embedded and used to retrieve the most semantically similar document chunks through vector similarity search. These retrieved chunks, along with the original query, are then passed to the LLM as context, enabling it to generate factual and contextually appropriate answers grounded in the retrieved information." [F, arxiv.org/html/2504.09720v2, §1]
- "NotebookLM then indexes these documents to generate answers with explicit citations, ensuring that each answer is traceable to its source (though this mechanism is not perfect)." [F, same, §1]
- "Chat interactions have been powered by a succession of models, migrating from earlier versions to the recent integration of Gemini 2.5 Flash." [F, same, §2]
- **Citations are the defining UX feature** — inline citations link back to specific passages; Notebook Guide can convert to FAQs, briefing docs, study materials. [F, winbuzzer.com 2024-06-07 secondary citation + help-page sidebar]
- **Recent integration with Gemini (Dec 2025):** "NotebookLM is now available in Gemini … users will see a 'NotebookLM' option in the attachments panel. Selecting it allows attaching a notebook and instructing Gemini to use the information it contains to perform the corresponding operation." [F, ithome.com/0/905/058.htm, secondary, 2025-12-15]
- **Sharing/privacy:** "Your personal data is never used to train NotebookLM." [F, blog.google/innovation-and-ai/products/notebooklm-audio-video-sources, Sep 26 2024]
- **Deep Research integration:** "NotebookLM can now employ a Deep Research mode similar to what's available in Gemini, AI Mode, and Google Finance." [F, bgr.com/2025613/notebooklm-deep-research-file-uploads, fetched 2026-06-14]

### 3.7 Documented limitations (from help page, blog, arXiv paper)

- **NotebookLM does not import footnotes or comments from Google files.** [F, help page]
- **NotebookLM does not support importing audio files from Drive** (only direct upload). [F, help page]
- **Hidden slides, hidden rows/columns, and nested tables are NOT mentioned as supported for PPTX/XLSX in NotebookLM** (these restrictions are in Document AI Layout Parser, not NotebookLM). [A — the NotebookLM help page does not enumerate these; the Layout Parser limits from §1.3 are a *different* product]
- **Multimodal PDF limitations (third-party evaluation, arXiv 2504.09720v2 §3):** "NotebookLM's performance in interpreting graphs from PDF sources was less accurate and reliable compared to its performance with the same graphs presented within Google Documents. This limitation was observed even considering the enhancements to NotebookLM's multimodal PDF capabilities announced on April 2, 2025." [F, arxiv.org/html/2504.09720v2]
- **LaTeX/math limitation:** "NotebookLM currently does not render LaTeX mathematics, thereby reducing its effectiveness in handling problems that require complex mathematical derivations." [F, same, §3]
- **3rd-party report (Toutiao, low-confidence) reports Chinese PDF / Google Doc / Chinese-input limitations, but this is a non-official Chinese-language source and is not corroborated by Google's help page. Treat as `[A]` and uncertain.** [A, m.toutiao.com/w/1784999166478348 — NOT official source]
- **"hallucinations也不少"** (hallucinations are not rare) — third-party Chinese-language report, not official. [A]
- **Backend is Gemini, which has the same hallucination risks as the base model.** "The system inherits the intrinsic statistical nature of the underlying AI models; this means responses, particularly for problems without curated guidance, may occasionally contain inaccuracies, necessitating critical evaluation by users and potential oversight from educators." [F, arxiv.org/html/2504.09720v2, §5]
- **Output modes are Socratic/chat/studio (no Markdown export).** The arXiv paper describes chat, study guides, mind maps, podcast-style audio summaries, "automated resources … that can range from targeted study questions and alternative explanations to visual aids like mind maps or podcast-style audio summaries." [F, arxiv.org/html/2504.09720v2, §2]

### 3.8 NotebookLM in the Anything-to-Markdown context

- **NotebookLM is a hosted RAG research product, not a document-to-Markdown converter.** It does not export Markdown from sources. Its outputs are chat answers with inline citations, mind maps, Audio Overviews, Video Overviews, flashcards/quizzes, infographics, slide decks. [A, synthesis of /support.google.com/notebooklm/answer/16215270 sidebar, blog.google posts, and arXiv 2504.09720v2 §2]
- **Strengths:** rich ingest (12+ source types incl. ePub, YouTube transcripts, audio), generous free tier (50 sources × 500k words × 200 MB), RAG with inline citations, multimodal (Gemini 1.5/2.5 Flash), no training on user data. [F, multiple sources above]
- **Limitations:** no Markdown export, footnotes/comments dropped, multi-tab flattened, audio-from-Drive unsupported, PDF graph understanding lags Google Docs graph understanding, no LaTeX math rendering, arXiv-evaluated accuracy issues on graph interpretation. [F, help + arXiv paper]
- **Self-host: No.** NotebookLM is a Google-hosted consumer/edu/enterprise product. There is no on-prem or open-source distribution. [F, blog + help]
- **Output format: chat text + audio (podcast) + mind map + study guide + flashcards + infographic + slide deck. Not Markdown.** [F, sidebar + arXiv]
- **Architecture / pipeline summary (synthesis):** User uploads source (Drive/URL/local) → NotebookLM ingests and **indexes** the document (vector embeddings + retrieval index, per arXiv 2504.09720v2) → user's query is embedded and used to retrieve semantically similar chunks → chunks + query go to Gemini 2.5 Flash (current per arXiv §2) → Gemini generates a chat answer with inline citations → optional Studio outputs (audio/mind map/flashcards/infographic/slide deck). [A, built from F, arXiv 2504.09720v2 §1–§3 + help + blog posts]

---

## 4. GitHub repos relevant to Google document/text→Markdown landscape

### 4.1 GoogleCloudPlatform/document-ai-samples
- URL: https://github.com/GoogleCloudPlatform/document-ai-samples
- Stars / forks / watchers (fetched 2026-06-14): **323 stars, 115 forks, 29 watchers, 1,592 commits, 17 open issues, 59 open PRs.** [F, same]
- License: Apache-2.0. [F, same]
- Description (vendor README): "The repository contains samples and Community Samples that demonstrate how to analyze, classify and search documents using Google Cloud Document AI." [F, same]
- Language mix: Jupyter Notebook 72.8%, Python 18.8%, JavaScript 2.5%, TypeScript 1.7%, Shell 1.6%, HTML 0.8%. [F, same]
- Notable sample folders (from repo root):
  - `bq-connector` — uses Document AI → BigQuery ingestion. [F]
  - `classify-split-extract-workflow` — multi-stage processor pipeline. [F]
  - `cx-content-moderation` — Content Moderation processor + Dialogflow CX. [F]
  - `document-json-explorer` — React tool to explore `Document` JSON responses. (No Markdown export — visualization only.) [F]
  - `document-processing-workflows` [F]
  - `document_ai_warehouse` — Document AI Warehouse (now App Builder) ingestion scripts. [F]
  - `ekg-demo`, `extract-languages`, `extract-tables`, `filter-hitl-language` [F]
  - `form-parser-to-cde` — bridges Form Parser output into Custom Document Extractor. [F]
  - `fraud-detection-python` — Invoice Parser + Google Maps + BigQuery. [F]
  - `hitl-custom-review` — Human-in-the-loop review UI. [F]
  - `incubator-tools` [F]
  - `paper_summarization` — "uses the Document AI API to summarize scientific articles." [F, relevant for A2MD]
  - `pdf-embedded-text` — demonstrates the native-PDF parsing feature of the OCR processor. [F]
  - `pdf-splitter-python` (DEPRECATED, replaced by Document AI Toolbox). [F]
  - `sql-pdf-python` — "shows how to run a BigQuery SQL and extract information from documents." (LLM+SQL-over-PDF, not a general Markdown converter.) [F]
  - `tax-processing-pipeline-python` — classify/parse/calculate tax forms. [F]
  - `toolbox-batch-processing` [F]
  - `uptraining_docai_processor_using_python` [F]
  - `watermark-remover` [F]
  - `web-app-demo` — "full-stack application that uses Document AI to process different types of documents. This application currently supports Form, Invoice and OCR processors." [F]
  - `web-app-pix2info-python` [F]
  - `community/pdf-annotator-python` — community sample for PDF annotation with Document AI. [F]
- Deprecated / replaced by Document AI Toolbox: `pdf-splitter-python`, `extract-tables`. [F, same]
- Disclaimer: "This is not an officially supported Google product. The code in this repository is for demonstrative purposes only." [F, same]

### 4.2 GoogleCloudPlatform/generative-ai
- Referenced from `/gemini-enterprise-agent-platform/models/capabilities/document-understanding` line 1384 as the source of `gemini/use-cases/document-processing/document_processing.ipynb` (the official Vertex AI "Document Processing with Gemini" Colab). [F, fetched 2026-06-14]
- Not separately fetched for stats in this scout. [A, NOT FETCHED]

### 4.3 google-gemini/cookbook
- URL: https://github.com/google-gemini/cookbook
- Stars / forks / watchers (fetched 2026-06-14): **17.4k stars, 2.7k forks, 201 watchers, 670 commits, 32 open issues, 37 open PRs.** [F, same]
- License: Apache-2.0. [F, same]
- Description (vendor README): "This cookbook provides a structured learning path for using the Gemini API, focusing on hands-on tutorials and practical examples." [F, same]
- Language mix: Jupyter Notebook 99.9%. [F, same]
- Relevant recent additions (per README):
  - "**Gemini 3.5 Flash**: Gemini 3.5 Flash is generally available." [F, same]
  - "**Agents API**: Create and run agents using the Antigravity agent." [F, same]
  - "**File Search:** Discover how to ground generations in your own data in a hosted RAG system with the File Search quickstart." [F, same]
  - "**Grounding with Google Maps**" [F, same]
  - "**Inference tiers**: Learn how to use the Priority and Flex tiers" [F, same]
  - "**Webhooks**: Get real-time notifications for async operations like batch jobs and video generation" [F, same]
  - "**Veo 3.1** video generation" [F, same]
  - "**Gemini Robotics-ER 1.5** spatial reasoning" [F, same]
  - "**🍌 Nano-Banana 2 & Pro** image generation" [F, same]
- Official SDKs (per README):
  - Python: github.com/googleapis/python-genai [F]
  - Go: github.com/googleapis/go-genai [F]
  - Node.js: github.com/googleapis/js-genai [F]
  - Java: github.com/googleapis/java-genai [F]
  - C#: github.com/googleapis/dotnet-genai/ [F]
- None of these are "convert to Markdown" tools; they are SDKs + a Colab-based cookbook. [A]

### 4.4 Repos NOT fetched / out of scope
- `github.com/google-gemini/gemini-cli` — referenced from the cookbook README as "Open-source AI agent that brings the power of Gemini directly into your terminal." Stats not fetched. [A, NOT FETCHED]
- `github.com/google-gemini/gemini-api-quickstart` — "Python Flask App running with the Google AI Gemini API." Stats not fetched. [A, NOT FETCHED]
- `github.com/google-gemini/multimodal-live-api-web-console` — "React-based starter app for using the Multimodal Live API over a websocket." Stats not fetched. [A, NOT FETCHED]
- `github.com/google-gemini/gemini-fullstack-langgraph-quickstart` — "fullstack application using a React frontend and a LangGraph-powered backend agent." Stats not fetched. [A, NOT FETCHED]
- `github.com/google-gemini/starter-applets` — "small apps that demonstrate how Gemini can be used to create interactive experiences." Stats not fetched. [A, NOT FETCHED]
- `github.com/googleapis/java-document-ai` and `github.com/googleapis/nodejs-document-ai` — official client libraries. Stats not fetched. [A, NOT FETCHED]
- `github.com/google-gemini/cookbook/pull/86` "BeyondLLM" PR — community RAG implementation, not merged as a primary example. [A, NOT FETCHED]
- `github.com/GoogleCloudPlatform/documentai-sheets-plugin` — Document AI Sheets plugin (referenced from doc-ai-samples README). [A, NOT FETCHED]
- `github.com/GoogleCloudPlatform/document-intake-accelerator` — "Document AI Intake Accelerator." [A, NOT FETCHED]

---

## 5. Cross-cutting facts (Markdown-output capability, overall)

- **None of Document AI's processors (Form Parser, Document OCR, Custom Extractor, Layout Parser) emit Markdown as a built-in output.** All four return the `Document` JSON proto. To get Markdown, callers must walk the JSON themselves. [A, based on /document-ai/docs/output and the absence of any Markdown export in /document-ai/docs/processors-list]
- **The Gemini API does not have a "Markdown mode".** It has structured-output modes (`application/json`, `text/x.enum`) and free-form text. The Markdown-ness of the output is a property of the prompt, not the API. [A, based on /firebase/google.com/docs/ai-logic/generate-structured-output and the Nov 5 2025 structured-outputs blog post]
- **NotebookLM does not export Markdown from sources.** Its outputs are chat, audio, mind map, study guide, infographic, slide deck. [A, based on the NotebookLM help-page sidebar and the Studio panel]
- **None of the three Google products in this scout are a drop-in "anything → Markdown" service.** They are building blocks (OCR + layout, structured JSON, RAG) that a user can compose into an A2MD pipeline. [A, this is the headline finding for the LocalDeepL scout]

---

## 6. Blockers and gaps

- **ai.google.dev/gemini-api/docs/structured-output** and **ai.google.dev/gemini-api/docs/document-processing** and **ai.google.dev/gemini-api/docs/file-api** were all transport-blocked for direct fetch (3 consecutive attempts each returned "Transport error"). The information from these pages is sourced from: (a) the Google search snippets that surfaced the page titles and key facts (one sentence each), (b) the firebase.google.com mirror docs which are API-equivalent in content, (c) the Vertex AI / Gemini Enterprise Agent Platform equivalents at docs.cloud.google.com which were directly fetched. This is a partial gap; if direct verification is needed, retry those URLs from a different network or via the search cache. [B, blocker noted]
- **The `/document-ai/docs/processors-list` page is 2,679 lines; the portion beyond the Form Parser, Custom Extractor, Layout Parser, and Document OCR sections was truncated to 2,679 lines and saved to disk but not parsed in full** — only the four primary processors were inspected. Other processors (Summarizer, Custom Classifier, Custom Splitter, Bank Statement Parser, W2 Parser, US Passport Parser, Utility Parser, ID Proofing Parser, US Driver License Parser, Expense Parser, Invoice Parser) are listed in the truncated file but not deep-dived here. [B]
- **Document AI's "Schema API" is ambiguous terminology.** The vendor doc exposes three things that could be called that: (a) the `Document` proto JSON schema (the output IR), (b) the Custom Extractor schema authoring surface (`Schema` subset of OpenAPI 3.0), (c) the "Automated schema generation" Preview tool at /document-ai/docs/ce-schema-extraction. This scout treats all three. There is **no** REST endpoint called "Schema API" with a Markdown export. [A, this is the cleanest reading of the docs]
- **No first-party "Document AI → Markdown" sample** in the doc-ai-samples repo. The repo's Markdown-adjacent sample is `paper_summarization`, but that uses the Summarizer processor (which itself returns `Document` JSON, not Markdown). [A]
- **No NotebookLM public API** for ingesting or exporting sources as Markdown. The product is web/UI only and gated behind Google sign-in. [A]

---

## 7. Cross-references and follow-ups

- This evidence is complementary to:
  - `track-schema-evidence.md` — already has Document AI row (row 1) for schema/table extraction; my findings are consistent with that row and add processor-version detail, the Schema API preview, the "Automated schema generation" workflow, and the Gemini-3 Custom Extractor versions.
  - `track-ocr-vision.md` — track-ocr-vision covers the OCR-vision landscape broadly; Document AI's Enterprise Document OCR is also a sub-entry there (row 1, the schema track). I focused here on the *full* Document AI processor catalog and the Layout Parser / Custom Extractor v1.5/v1.6 Gemini-3 details, which were not in the OCR track.
- The most decision-relevant findings for LocalDeepL are in §5 (no first-class Markdown from any of the three Google products) and §1.3 (Layout Parser's RAG-chunked output is the closest "structured" Document AI surface, and it has explicit table-merging + figure-verbalization that LocalDeepL's "structure_analysis" / "layout_enrichment" processors would have to replicate).
- Open follow-ups: (a) retry ai.google.dev pages; (b) try the Document AI REST endpoint `documentai.googleapis.com/v1/...:process` to confirm empirically that no Markdown field appears; (c) check the python-genai SDK for any "convert to Markdown" helper class — current public evidence suggests there is none.
