# Anything-to-Markdown / rich-text converter landscape — Track MD

> Scout deliverable for LocalDeepL product planning. Compiled 2026-06-14 from
> primary GitHub repos, vendor docs, arXiv papers, and verified secondary
> benchmarks. Companion files: [track-md-evidence.md](track-md-evidence.md) (consolidated
> evidence inventory) and the five per-vendor evidence files it indexes.
>
> Inline source format: `[Org, page, date]` or `[URL, fetched 2026-06-14]`. Where the
> source is a specific file in a GitHub repo, the citation is `[file_path:line_number]`.
> `[F]` = fact, `[A]` = analysis, `[C]` = conflict/caveat.
>
> Reads as: (1) Executive Summary, (2) Players by tier, (3) Feature Matrix,
> (4) Pipeline Patterns Common to Leaders, (5) Open-Source Quality Tier,
> (6) Gaps LocalDeepL Could Fill, (7) References.

---

## 1. Executive Summary

The 2026 "anything-to-Markdown" landscape is structurally fragmented along three
axes — input coverage, execution mode, and output schema — and **no single
product wins on all three**. The cloud majors (Microsoft, Google, Adobe) have
strong individual pieces but no first-party "anything→MD" service. The OSS
ecosystem has converged on three architectural patterns (A. local layout/ML
without LLM, B. local layout/ML with VLM post-processor / hybrid, C. VLM-only
/ pure-vision) with `Marker`, `Docling`, `MinerU`, and `LocalDeepL` all
occupying the B-mode center of gravity.

**For LocalDeepL specifically, the headline findings are:**

1. **The hybrid B-mode design is the right neighborhood** — the most active
   OSS tools (Marker, Docling, MinerU) are all converging on the same
   `surya-or-equivalent layout + VLM-fallback` pattern, with `LocalDeepL`'s
   `dense_mode="auto"` per-page routing and `grounded_backend` pluggability
   being the most defensible implementation. [A] [oss1 §4.3],
   [oss2 §1.5], [oss2 §4.4]
2. **License posture is a real B2B wedge** — `Marker` ships under
   **GPL-3.0 + RAIL-M** with a hard $2M revenue/funding cap
   ([MODEL_LICENSE, datalab-to/marker, fetched 2026-06-14]);
   `PyMuPDF4LLM` is **AGPL v3 OR paid commercial**; `Pandoc` is
   **GPL-2.0+**. `Docling`, `Markitdown`, `PDFMiner`, `Zerox`, `MinerU` are
   MIT / Apache-2.0 / Apache-2.0-based. Any mid-market or enterprise
   customer cannot freely ship Marker's weights. [F] [oss2 §1.7, §3.7, §5.3]
3. **No first-party cloud "anything→MD" service exists.** Microsoft Azure
   Document Intelligence's `prebuilt-layout` produces the strongest
   PDF→MD API output but the schema uses **HTML tables** (not GFM) plus
   LaTeX math and `<!--PageBreak-->` comments — friction for RAG pipelines
   expecting GFM. Google's Document AI has **no native Markdown output** —
   the `Document` JSON proto is the only structured surface. Adobe's
   PDF-to-Markdown is PDF-only with 400-page and 100 MB caps. [A] [ms §3],
   [google §1.3, §5], [adobe-apple §1.7]
4. **Markdown schema fragmentation is the #1 integration friction.** Every
   vendor's Markdown is subtly different. LocalDeepL can win on
   "predictable, configurable Markdown output" — but only if it explicitly
   documents its schema and provides an HTML-tables / GFM-tables toggle.
   [A] [ms §3], [adobe-apple §1.3], [oss2 §3.3]
5. **`Markitdown` (153k stars, MIT) is the de-facto OSS reference but
   explicitly positions itself as low-fidelity.** Its README:
   "meant to be consumed by text analysis tools — and may not be the best
   option for high-fidelity document conversions for human consumption."
   [F] [oss2 §4.1]. This is the *exact* positioning LocalDeepL rejects; it
   is also the *exact* positioning LocalDeepL can win against on PDF-heavy
   inputs.
6. **`Docling` (61.5k stars, IBM) and `Marker` (36.1k stars, Datalab) are the
   two most direct architectural analogs to LocalDeepL** — both use
   Surya-family layout detection; both have pluggable processors and a
   multi-format dispatch. LocalDeepL's wedge is the per-page sparse/dense
   routing combined with a Windows desktop one-click install story
   (`install.bat`/`start_app.vbs`) that no other OSS tool tells well. [A]
   [oss1 §4.6], [oss2 §1.8]
7. **`Pandoc` is the gold standard for non-PDF markup interchange** but has
   no native PDF reader. [F] [oss1 §1.2] For the **DOCX/PPTX/XLSX/HTML/EPUB**
   legs of a multi-format pipeline, `pandoc` shelling behind a license check
   is still the obvious answer. The GPL-2.0+ copyleft is a real adoption
   blocker for proprietary LocalDeepL distributions; for *use* via shell, it
   is fine.
8. **Microsoft 365 Copilot is closed and not a direct competitor.** The real
   Microsoft cloud competitors are Azure Document Intelligence (markdown via
   `prebuilt-layout`) and Azure Content Understanding (multimodal umbrella).
   No public "Microsoft Document Transformer" arXiv paper exists; the
   relevant Microsoft research lineage is `LayoutLMv3` (2022) and `UDOP`
   (CVPR 2023). [F] [ms §4]

The local product plan that follows is grounded in `LocalDeepL`'s existing
extension points (`grounded_backend`, `document_processors`, `aligner`,
`ocr_processor`, `page_preprocessor`, output writers). The "Gaps
LocalDeepL Could Fill" section lists concrete recommendations tied to those
slots.

---

## 2. Players (by tier)

### Tier 1 — Cloud incumbents (PDF→MD APIs, no full anything→MD)

#### 2.1.1 Microsoft — `microsoft/markitdown`, `Azure Document Intelligence`, Microsoft 365 Copilot

- **`Markitdown` core** ([github.com/microsoft/markitdown, fetched 2026-06-14]):
  MIT, **153k stars / 10.6k forks**, v0.1.6 (2026-05-26), 99.7% Python.
  Plugin-based converter registry: `MarkItDown` class instantiates a list of
  `ConverterRegistration(converter, priority)` and dispatches via
  `accepts()` → `convert()`. [F]
  [`packages/markitdown/src/markitdown/_markitdown.py:23-44`,
  fetched 2026-06-14]. Magic-type detection uses Google's `magika`
  (`_markitdown.py:105-109`).
- **Built-in converters** (read the import line at `_markitdown.py:23-44`):
  `PlainTextConverter`, `HtmlConverter`, `RssConverter`,
  `WikipediaConverter`, `YouTubeConverter`, `IpynbConverter`,
  `BingSerpConverter`, `PdfConverter`, `DocxConverter`, `XlsxConverter`,
  `XlsConverter`, `PptxConverter`, `ImageConverter`, `AudioConverter`,
  `OutlookMsgConverter`, `ZipConverter`, `EpubConverter`, `CsvConverter`,
  plus optional `DocumentIntelligenceConverter` and
  `ContentUnderstandingConverter` for Azure. [F]
- **`PdfConverter` (built-in)** uses `pdfplumber` for form/table detection
  with adaptive column tolerance `[25, 50]` pixels and 70th-percentile gap
  analysis ([`packages/markitdown/src/markitdown/converters/_pdf_converter.py:101-130`,
  fetched 2026-06-14]), `pdfminer.six` as prose fallback
  ([`_pdf_converter.py:400-405`](_pdf_converter.py)). **No layout detection,
  no OCR for scanned PDFs** — confirmed by issues
  [#296](https://github.com/microsoft/markitdown/issues/296),
  [#1361](https://github.com/microsoft/markitdown/discussions/1361),
  [#1845](https://github.com/microsoft/microsoft/markitdown/issues/1845).
  Maintainer comment on #1361: "for scanned PDFs (images of pages), there
  is no embedded text, so markitdown will return empty or minimal output -
  this is a pdfminer limitation, not a [markitdown] one." [F]
- **`DocumentIntelligenceConverter`** is a thin wrapper that calls Azure
  Document Intelligence `prebuilt-layout` with
  `output_content_format="markdown"` and strips `<!--…-->` comments
  ([`_doc_intel_converter.py:201-209`](_doc_intel_converter.py)).
  **Hardcoded** model id `prebuilt-layout` (line 198) and `api_version`
  `"2024-07-31-preview"` (line 104). [F]
- **`ContentUnderstandingConverter`** routes documents to
  `prebuilt-documentSearch`, images to `prebuilt-documentSearch`, audio to
  `prebuilt-audioSearch`, video to `prebuilt-videoSearch`, and emits **YAML
  front matter + Markdown** ([`_cu_converter.py:280-313`,
  fetched 2026-06-14](_cu_converter.py)). [F] This is the only Microsoft
  converter with **native video support** and is the more future-proof
  integration path (Azure is "now part of Azure Content Understanding"
  per [azure.microsoft.com/en-us/products/ai-foundry/tools/document-intelligence](https://azure.microsoft.com/en-us/products/ai-foundry/tools/document-intelligence),
  fetched 2026-06-14).
- **Extras** (11 pip extras): `pptx`, `docx`, `xlsx`, `xls`, `pdf`, `outlook`,
  `az-doc-intel`, `az-content-understanding`, `audio-transcription`,
  `youtube-transcription`, `all`. Plus a `markitdown-ocr` plugin that uses
  an LLM-vision endpoint to OCR images embedded in PDF/DOCX/PPTX/XLSX
  ([`packages/markitdown-ocr/README.md`, fetched 2026-06-14](packages/markitdown-ocr/README.md)).
- **Azure Document Intelligence `prebuilt-layout`** — current GA v4.0
  (2024-11-30). Output Markdown schema is well-defined
  ([learn.microsoft.com/.../concept/markdown-elements, fetched 2026-06-14](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept/markdown-elements)):
  paragraphs, headings (H1-H6), **HTML `<table>` (not GFM)**, `<figure>`,
  Unicode `☒`/`☐` selection marks, LaTeX math (inline `$…$`, block
  `$$…$$`), barcodes, page header/footer/number as `<!--…-->` HTML
  comments, `<!-- PageBreak -->` delimiter. KVP/Language/Style go into
  the JSON `analyzeResult`, **not** into the Markdown. [F]
- **`prebuilt-read` v4.0 (2024-11-30) added searchable PDF output at no
  extra cost** — the only Doc Intel model that returns a PDF binary output
  ([learn.microsoft.com/.../prebuilt/read, fetched 2026-06-14](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read?view=doc-intel-4.0.0)). [F]
- **Language support** (v4.0): CJK added to Read for images; full list at
  [learn.microsoft.com/.../language-support/ocr](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr).
  [F]
- **Documented limitations** ([ms §3](../track-md-evidence-ms.md#3-azure-document-intelligence-formerly-form-recognizer)):
  tables in XLSX are not analyzed; embedded images in Office files
  (DOCX/XLSX/PPTX) are not processed by Read or Layout; F0 free tier only
  processes 2 pages; HTML tables (not GFM) downstream friction; LiteLLM
  proxy bug [#25687](https://github.com/BerriAI/litellm/issues/25687)
  flattens response (LiteLLM bug, not Azure).
- **Pricing** ([azure.microsoft.com/en-us/pricing/details/document-intelligence/](https://azure.microsoft.com/en-us/pricing/details/document-intelligence/),
  page renders `$-` placeholders; concrete numbers from secondary
  trackers): Read ~$1.50/1k pages, Prebuilt (incl. Layout) ~$10/1k pages,
  Custom Extraction ~$30/1k pages. F0 free tier: 500 pages/month. [F]
- **Microsoft 365 Copilot parsing pipeline**: closed-source. Privacy doc
  describes orchestration = "Large language models (LLMs)" + "Content in
  Microsoft Graph" + "Microsoft 365 productivity apps" + **Semantic
  Index** ([learn.microsoft.com/en-us/copilot/microsoft-365/microsoft-365-copilot-privacy,
  fetched 2026-06-14](https://learn.microsoft.com/en-us/copilot/microsoft-365/microsoft-365-copilot-privacy)).
  Default LLM is GPT-4/4o/5-class via Azure OpenAI; Anthropic Claude
  and xAI Grok also used. **No user-facing Markdown export of parsed
  documents** — outputs are grounded chat responses. [A]
- **No public "Microsoft Document Transformer" arXiv paper exists.** The
  closest Microsoft research lineage is `LayoutLMv3` (2022) and `UDOP`
  (CVPR 2023) — both pre-training papers, not the production Copilot
  pipeline. KOSMOS-2.5 is a 2023 multimodal that was not deep-read in this
  scout. [F] [ms §4]

#### 2.1.2 Google — `Document AI`, `Gemini structured output`, `NotebookLM`

- **Document AI Form Parser** ([cloud.google.com/document-ai/docs/form-parser, fetched 2026-06-14](https://cloud.google.com/document-ai/docs/form-parser)):
  pre-trained (no up-training), KVP + 11 generic entities
  (`email`, `phone`, `url`, `date_time`, `address`, `person`,
  `organization`, `quantity`, `price`, `id`, `page_number`) + tables +
  checkboxes. v2.0+ supports 200+ languages. Quotas: 15 pages sync, 100
  pages batch, 30 pages imageless. **No Markdown output** — returns the
  `Document` JSON proto. [F]
- **Document AI Enterprise OCR** ([cloud.google.com/document-ai/docs/enterprise-document-ocr, fetched 2026-06-14](https://cloud.google.com/document-ai/docs/enterprise-document-ocr)):
  200+ languages, image-quality scoring (8 dimensions: blurriness,
  noise, dark, faint, text_too_small, document_cutoff, text_cutoff,
  glare), rotation correction, language hints, handwriting hints.
  Optional add-ons:
  - **Math OCR** (LaTeX) — output in `Document.pages[].visualElements[]` with
    `"type": "math_formula"`.
  - **Checkbox extraction** — `filled_checkbox` / `unfilled_checkbox`.
  - **Font style detection** — word-level font/style/colour/weight.
  - **Hard restriction:** "Math OCR and selection mark detection are
    mutually exclusive add-ons. They can't be enabled at the same time."
    [F]
- **Document AI Layout Parser** ("Gemini layout parser")
  ([cloud.google.com/document-ai/docs/layout-parse-chunk, fetched 2026-06-14](https://cloud.google.com/document-ai/docs/layout-parse-chunk)):
  hybrid pipeline = Document OCR + layout detection + Gemini-grounded
  text. Pipeline per vendor: "Parse and Structure" → "Annotate and
  Verbalize" (Gemini describes figures/charts/tables in text) → "Chunk
  and Augment" (semantic chunks with ancestral headings). [F]
  - Versions: `v1.0-2024-06-03` (default), `v1.5-2025-08-25` (Gemini 2.5
    Flash), `v1.5-pro-2025-08-25` (Gemini 2.5 Pro), `v1.6-pro-2025-12-01`
    (Gemini 3 Pro, DMZ-noncompliant global routing), `v1.6-2026-01-13`
    (Gemini 3 Flash, same DMZ caveat). [F]
  - File coverage: PDF, HTML, DOCX, PPTX, XLSX, XLSM. Limitations:
    HTML "relies heavily on HTML tags, so CSS-based formatting might
    not be captured"; PDF "tables spanning multiple pages might be
    split in two tables"; DOCX "nested tables are not supported";
    PPTX "nested tables and hidden slides are not supported"; XLSX
    "multiple table detection is not supported". [F]
  - Quotas: 20 MB online / 1 GB batch, 15 pages online / 500 pages batch.
    [F]
  - **No Markdown output** — outputs the `Document` JSON proto. [A]
- **Document AI Custom Extractor**
  ([cloud.google.com/document-ai/docs/processors-list, fetched 2026-06-14](https://cloud.google.com/document-ai/docs/processors-list)):
  generative-AI extraction (Gemini 2.5/3) + fine-tuning. Generative
  path is **English-only**. Fine-tuning "achieve higher accuracy by
  providing as few as 10 documents". Normalized data types
  `dateTime`, `currency`, `money`, `number`. Quotas 15 pages sync,
  200 pages batch. Pricing $30/1k pages. [F]
- **Document AI Schema API** — actually three things: (a) the `Document`
  proto JSON schema, (b) Custom Extractor schema authoring (subset of
  OpenAPI 3.0), (c) the "Automated schema generation" Preview tool at
  [/document-ai/docs/ce-schema-extraction](https://cloud.google.com/document-ai/docs/ce-schema-extraction).
  **There is no REST endpoint called "Schema API" with a Markdown
  export.** [A]
- **Gemini structured output** ([firebase.google.com/docs/ai-logic/generate-structured-output, fetched 2026-06-14](https://firebase.google.com/docs/ai-logic/generate-structured-output)):
  `responseMimeType: application/json` + `responseSchema` (subset of
  OpenAPI 3.0). Per Nov 5 2025 blog, JSON Schema support expanded to
  `anyOf`, `$ref`, `minimum/maximum`, `additionalProperties`,
  `type:'null'`, `prefixItems`. Pydantic/Zod-native. **No Markdown
  mode** — Markdown-ness is a property of the prompt, not the API. [F]
- **Gemini file input** ([blog.google/.../gemini-api-new-file-limits, fetched 2026-06-14](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-api-new-file-limits)):
  inline base64 raised from 20 MB to 100 MB on Jan 12 2026; public URLs
  and signed URLs (S3, Azure Blob) now supported; GCS objects can be
  registered with the Files API. [F]
- **Source conflict surfaced** [google §2.5](../track-md-evidence-google.md#25-source-conflicts-surfaced):
  Firebase AI Logic's `analyze-documents` still says **20 MB** inline; the
  Jan 12 2026 Gemini API blog says **100 MB**. These are different
  products on top of the same model. PDF max pages: 1,000 (Developer API)
  vs 3,000 (Vertex AI doc-understanding). [C]
- **NotebookLM** ([support.google.com/notebooklm/answer/16215270, fetched 2026-06-14](https://support.google.com/notebooklm/answer/16215270),
  + [arXiv 2504.09720v2, Tufino, July 2025](https://arxiv.org/html/2504.09720v2)):
  - Sources: 12+ types including ePub, YouTube transcripts, audio
    (3g2/3gp/aac/aif/…/wav/wma), Google Docs/Sheets/Slides, **MD/TXT/CSV
    uploads**, web URLs, **PDF**, **docx**, **pptx**, Gemini Chats
    (paid). 500k words / 200 MB per source. Free 50 sources/Notebook;
    Plus 300. [F]
  - "**NotebookLM does not import footnotes or comments from Google
    files.**" [F]
  - Architecture: RAG (vector embeddings + retrieval + Gemini 2.5 Flash)
    per arXiv 2504.09720v2. [F]
  - Outputs: chat + inline citations, mind maps, audio overview
    (podcast-style), video overview, flashcards/quizzes, infographic,
    slide deck. **No Markdown export.** [A]

#### 2.1.3 Adobe — `Acrobat Extract API`, `PDF Services API`, `Sensei` rebrand

- **Adobe PDF Extract API** ([developer.adobe.com/document-services/apis/pdf-extract/, fetched 2026-06-14](https://developer.adobe.com/document-services/apis/pdf-extract/)):
  - Two endpoints: **Extract PDF (JSON)** → `structuredData.json` + ZIP
    with `tables/` and `figures/` (PNG/CSV/XLSX); **PDF to Markdown** →
    `.md` with base64-embedded images. [F]
  - Element types: headings `H1, H2, H3…`, lists `L, Li, Lbl, Lbody`,
    paragraphs `P, ParagraphSpan`, footnotes, sections `Sect`,
    references/links, tables (`Table, TD, TH, TR`), figures, asides,
    styles (`StyleSpan`). [F]
    [developer.adobe.com/.../howtos/pdf-to-markdown-api/, fetched 2026-06-14](https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/howtos/pdf-to-markdown-api/)
  - JSON Schema is **open-sourced** ([opensource.adobe.com/pdftools-sdk-docs/release/shared/extractJSONOutputSchema.json, fetched 2026-06-14](https://opensource.adobe.com/pdftools-sdk-docs/release/shared/extractJSONOutputSchema.json))
    — a rare transparency move.
  - Limitations
    ([adobe-apple §1.7](../track-md-evidence-adobe-apple.md#17-documented-limitations--known-issues)):
    **PDF only**; no support for hidden objects, XFA/fillable forms,
    complex annotations, CAD drawings, password-protected content; 400
    pages max (150 for scanned); 100 MB max; 25 RPM; community-reported
    reading-order issues on simple pages. [F]
  - Pricing: 500 free Document Transactions/month, no credit card;
    paid plans via sales. 1 DT per 5 pages for Extract / PDF-to-Markdown.
    [F]
- **Adobe Sensei** is a **marketing brand layer**, not a product — the
  structured-extraction product is the PDF Extract API. Re-branded
  toward "Adobe AI" / "Adobe AI Platform" at Adobe Summit 2025. There
  is **no `adobe/sensei-sdk` repo**. [F]
  [adobe-apple §2](../track-md-evidence-adobe-apple.md#2-adobe-sensei-structured-extraction)
- **Adobe PDF Services API** ([developer.adobe.com/document-services/docs/overview/pdf-services-api/, fetched 2026-06-14](https://developer.adobe.com/document-services/docs/overview/pdf-services-api/)):
  umbrella for Create / Export / OCR / Accessibility Auto-Tag /
  Document Generation / Sign / PDF Embed. **No docx/pptx/xlsx → MD
  path**; Markdown export is only via PDF-to-Markdown (PDF input).
  Server-only SDKs. [F]
- **GitHub repos** actually fetched: `adobe/pdfservices-python-sdk-samples`
  (MIT, 163★, v4.2.0 / 2025-07-11),
  `adobe/pdfservices-node-sdk-samples` (MIT, 109★, v4.1.0 / 2025-01-02),
  `adobe/PDFServices.NET.SDK.Samples` (MIT, 47★). The runtime SDKs and
  server engine are closed. [F]

#### 2.1.4 Apple — `Vision`, `Shortcuts`, `Notes`, `Intelligence`

- **Apple Vision `VNRecognizeTextRequest`** (closed-source, on-device
  CPU/GPU/Neural Engine, iOS 11+ / macOS 10.13+). Output: flat list of
  `VNRecognizedTextObservation` with bounding boxes (`topLeft`, `topRight`,
  `bottomRight`, `bottomLeft`) and per-region confidence. **No semantic
  structure** (no headings/lists/tables classification). [F]
  [developer.apple.com/documentation/vision, fetched 2026-06-14]
  - Works on images only; PDFs require a PDFKit → CGImage rendering
    pass first. [A] [MacScripter "OCR Script" thread, 2023, fetched 2026-06-14](https://www.macscripter.net/t/optical-character-recognition-ocr-script/74498/21)
  - Apple added `VNRecognizeDocumentsRequest` at WWDC21 for forms/tables
    (referenced in "Extract document data using Vision" session 10041). [F]
  - CJK + RTL covered via per-language support; per-character info not
    returned. [A]
- **Apple Shortcuts "Extract Text from PDF" / "Make Rich Text from
  Markdown" / "Make Markdown from Rich Text"** — confirmed via third-party
  blogs only (cnblogs, MacScripter, IT之家, AppleInsider). Apple
  documentation is JS-gated. [A] [adobe-apple §4.2](../track-md-evidence-adobe-apple.md#42-apple-shortcuts--extract-from-pdf--make-rich-text-from-markdown--markdown-to-html)
  - iOS 26 / macOS Tahoe 26 added **Apple Intelligence** Summarize PDF
    via Shortcuts; 3 backends: on-device, Private Cloud Compute, ChatGPT.
    [A] [IT之家, 2025-06-12, fetched 2026-06-14](https://next.ithome.com/archiver/860/180.htm)
  - "Make Rich Text from Markdown" produces the Shortcuts rich-text
    internal representation, not GitHub-flavored markdown round-trip
    fidelity. [A]
- **Apple Notes Markdown (iOS 26 / macOS Tahoe 26, shipped 2025+)**
  ([support.apple.com/en-us/102223, published 2026-04-02, fetched 2026-06-14](https://support.apple.com/en-us/102223)):
  first-party MD I/O. "On Mac: File → Import Markdown → select `.md`
  files." On iPhone/iPad: open `.md` in Files, Share → Notes → Import.
  Export: Share → Export as Markdown. **Editor does not render Markdown
  live.** "Apple Notes only supports the most basic of Markdown features."
  [A] [AppleInsider, 2026-01-12, fetched 2026-06-14](https://appleinsider.com/inside/ios-26/tips/how-to-import-and-export-markdown-with-apple-notes-in-ios-26)
- **Apple Intelligence Writing Tools** can summarize a read-only PDF, but
  the output is prose, not structured Markdown. [F]
  [support.apple.com/guide/iphone/find-the-right-words-with-writing-tools-iph6f08da1d2/ios, fetched 2026-06-14](https://support.apple.com/guide/iphone/find-the-right-words-with-writing-tools-iph6f08da1d2/ios)
- **macOS 27 "Golden Gate" preview** ([apple.com/os/?version=no-hero, fetched 2026-06-14](https://www.apple.com/os/?version=no-hero))
  is heavy on Siri AI / Visual Intelligence but **does not announce a
  new "Apple Extract" API**. [F]

#### 2.1.5 Other cloud adjacents

- **Box `ai/extract`** ([developer.box.com/guides/representations/text, fetched 2026-06-14](https://developer.box.com/guides/representations/text)):
  text representations on upload, includes code files but **not images**
  ("image files as these do not have a text layer"). 500 MB max. Box AI
  Extract is LLM-driven freeform metadata. [F]
- **Dropbox Sign / DocSend** — not in the same product category as Adobe
  Extract; e-signature and document-analytics products respectively.
  [A] [adobe-apple §5.2](../track-md-evidence-adobe-apple.md#52-dropbox--docsend--hellosign-dropbox-sign)

### Tier 2 — Serious open-source converters (the direct competitive set)

The OSS landscape has converged on three architectural patterns (A / B / C
above) with the most direct LocalDeepL competitors in the B-mode hybrid
center.

#### 2.2.1 `Marker` (`datalab-to/marker`) — the single closest competitor

- **Identity** ([github.com/datalab-to/marker, fetched 2026-06-14](https://github.com/datalab-to/marker)):
  Datalab (Vik Paruchuri's company). v1.10.2 / 2026-01-31. PyPI
  `marker-pdf`. **36.1k stars / 2.5k forks**. **Code: GPL-3.0+. Models:
  modified AI Pubs Open RAIL-M (free for research/personal/startups under
  $2M revenue OR under $2M total funding).** [F]
  [oss2 §1.1](../track-md-evidence-oss2.md#11-identity-vendor-license-output-formats)
- **Input coverage** (provider registry
  [`marker/providers/registry.py:7-12, 41`, fetched 2026-06-14](marker/providers/registry.py)):
  Image, **PDF, DOCX, XLSX, PPTX, EPUB, HTML** (BeautifulSoup-detected
  fallback). **No audio/video** in the local providers. [F]
- **Quality**: 95.67 heuristic / 4.24 LLM-judge on its own benchmark,
  beats llamaparse (84.24/3.98), mathpix (86.43/4.16), and docling
  (86.71/3.70). Tables: 0.816 (marker) / 0.907 (marker `--use_llm`).
  Throughput 0.18 s/page, 3.17 GB VRAM, 122 pages/s on H100. [F]
  [oss2 §1.3](../track-md-evidence-oss2.md#13-quality-claims)
- **Execution mode**: **local CPU / GPU / MPS** (all three); "Works on
  GPU, CPU, or MPS". Optional `--use_llm` accepts Gemini / Vertex /
  Ollama / Claude / OpenAI / Azure OpenAI (default `gemini-2.0-flash`).
  Managed platform ("Chandra", $5 free credits) is paid SaaS. [F]
  [oss2 §1.4](../track-md-evidence-oss2.md#14-execution-mode)
- **Architecture (deep dive)**
  [`marker/converters/pdf.py:101-138`, fetched 2026-06-14](marker/converters/pdf.py):
  `PdfConverter(BaseConverter)` with a long `default_processors` tuple
  (`OrderProcessor, BlockRelabelProcessor, LineMergeProcessor,
  BlockquoteProcessor, CodeProcessor, DocumentTOCProcessor,
  EquationProcessor, FootnoteProcessor, IgnoreTextProcessor,
  LineNumbersProcessor, ListProcessor, PageHeaderProcessor,
  SectionHeaderProcessor, TableProcessor, LLMTableProcessor,
  LLMTableMergeProcessor, LLMFormProcessor, TextProcessor,
  LLMComplexRegionProcessor, LLMImageDescriptionProcessor,
  LLMEquationProcessor, LLMHandwritingProcessor, LLMMathBlockProcessor,
  LLMSectionHeaderProcessor, LLMPageCorrectionProcessor,
  ReferenceProcessor, BlankPageProcessor, DebugProcessor`). Default
  LLM service is `GoogleGeminiService`. [F]
- **`build_document`** uses four builders: `LayoutBuilder` →
  `LineBuilder` → `OcrBuilder (surya)` → `StructureBuilder`. Pipeline
  order: layout detect → OCR (surya) → line/text build → structure →
  processors → render. [F]
  [`marker/converters/pdf.py:163-176`, fetched 2026-06-14](marker/converters/pdf.py)
- **Models** ([`marker/models.py`, fetched 2026-06-14](marker/models.py)):
  five Surya models: layout, recognition (OCR), table_rec, detection,
  ocr_error. **Same dependency stack LocalDeepL uses** for its hybrid
  path. [A]
- **DI pattern**: `BaseConverter.resolve_dependencies` uses reflection
  to inject `artifact_dict` and `config` into each processor/renderer
  [`marker/converters/__init__.py:13-39`, fetched 2026-06-14](marker/converters/__init__.py).
  `BaseExtractor` has `max_concurrency: int = 3` for LLM-backed
  extractors
  [`marker/extractors/__init__.py:11-39`, fetched 2026-06-14](marker/extractors/__init__.py).
  Clean pattern that LocalDeepL's processor chain could mirror. [A]
- **Output formats**: Markdown, JSON (28-element block schema:
  `Line, Span, Char, FigureGroup, TableGroup, ListGroup, PictureGroup,
  Page, Caption, Code, Figure, Footnote, Form, Equation, Handwriting,
  TextInlineMath, ListItem, PageFooter, PageHeader, Picture,
  SectionHeader, Table, Text, TableOfContents, Document, ComplexRegion,
  TableCell, Reference`), HTML, chunks (flat list with full HTML per
  block, designed for RAG). [F]
  [`marker/schema/__init__.py:5-33`, fetched 2026-06-14](marker/schema/__init__.py)
- **Documented limitations** ([oss2 §1.6](../track-md-evidence-oss2.md#16-documented-strengths-and-limitations)):
  "Very complex layouts, with nested tables and forms, may not work";
  "Forms may not be rendered well". `--use_llm` and `--force_ocr`
  mostly solve. [F]
- **Commercial reality** ([oss2 §1.7](../track-md-evidence-oss2.md#17-commercial--pricing-reality)):
  the MODEL_LICENSE Attachment A hard limits:
  "5(a) for any purpose if You (your employer, or the entity you are
  affiliated with) generated more than two million US Dollars ($2,000,000)
  in gross revenue in the prior year, except where Your Use is limited
  to personal use or research purposes; (b) ... has raised more than
  two million US dollars ... in total equity or debt funding ...; (c)
  for any purpose if You ... provides or otherwise makes available any
  product or service that competes with any product or service offered
  by or made available by Licensor or any of its affiliates." [F]
  Datalab also operates a managed platform that competes directly
  ("Chandra" + batch service, "200M+ pages per week"). [A]

#### 2.2.2 `Docling` (`docling-project/docling`) — IBM Research + LF AI & Data

- **Identity** ([github.com/docling-project/docling, fetched 2026-06-14](https://github.com/docling-project/docling)):
  originally IBM Research Zurich ("AI for knowledge team"), now LF AI
  & Data. v2.102.1 / 2026-06-12. **61.5k stars / 4.3k forks / 183
  releases / 1,103 commits**. **MIT (code), per-model licenses for
  bundled ML models**. [F]
- **Input coverage**: **broadest in the survey.** PDF, DOCX, PPTX, XLSX,
  HTML, **EPUB**, WAV, MP3, **WebVTT**, email (EML, MSG), images
  (PNG/TIFF/JPEG), LaTeX, **DocLang**, plain text, QMD, RMD, CSV, XML,
  application-specific XML schemas (USPTO patents, JATS, XBRL, METS/GBS).
  OCR engines pluggable: RapidOCR, EasyOCR, Tesseract, macOCR. VLM
  pipeline (`--pipeline vlm --vlm-model granite_docling`). [F]
  [oss1 §4.2](../track-md-evidence-oss1.md#42-input--output-coverage)
- **Architecture (deep dive)**: two-axis `Backend × Pipeline`
  [`docling/document_converter.py:53-89`, fetched 2026-06-14](docling/document_converter.py).
  `FormatOption` table covers 18 input formats mapped to 3 pipelines
  (`SimplePipeline`, `StandardPdfPipeline`, `AsrPipeline`). [F]
- **`StandardPdfPipeline`**: **multi-threaded, production-grade 5-stage
  pipeline** — Preprocess → OCR → Layout → Table-structure → Assemble
  — with bounded `ThreadedQueue`, per-run-id isolation,
  document-timeout, explicit back-pressure. **Failed pages are
  preserved as empty `PageItem` entries** so page-break markers stay
  correct. Status enums `SUCCESS / PARTIAL_SUCCESS / FAILURE`.
  Models: `PagePreprocessingModel`, OCR, layout, `TableStructureModel`,
  `PageAssembleModel`, `ReadingOrderModel`, optional
  `CodeFormulaVlmModel`. Confidence aggregation: `layout_score`,
  `parse_score` (10th percentile), `table_score`, `ocr_score`. [F]
  [`docling/pipeline/standard_pdf_pipeline.py:393-435, 740-823, fetched 2026-06-14`](docling/pipeline/standard_pdf_pipeline.py)
- **Caching**: `DocumentConverter.initialized_pipelines: dict[(pipeline_class, options_md5_hash), pipeline_instance]`
  re-uses heavy models across documents with the same options
  [`docling/document_converter.py:355-378`, fetched 2026-06-14](docling/document_converter.py). [F]
- **Concurrency**: `convert_all` uses
  `ThreadPoolExecutor(max_workers=settings.perf.doc_batch_concurrency)`
  across documents [`docling/document_converter.py:518-547`,
  fetched 2026-06-14](docling/document_converter.py). [F]
- **Lossless IR**: `DoclingDocument` (in `docling-core`) — `PageItem`,
  `PictureItem`, `TableItem`, `DocItem`, `ImageRef`, `BoundingBox`.
  Exports Markdown, HTML, **DocTags** (lossless, arXiv 2503.11576), JSON,
  WebVTT, DocLang. [F]
- **Quality** ([oss1 §4.4](../track-md-evidence-oss1.md#44-quality--layout-fidelity)):
  "Advanced PDF understanding incl. page layout, reading order, table
  structure, code, formulas, image classification, and more"; "Chart
  understanding (Barchart, Piechart, LinePlot): converting them into
  tables, code or adding detailed descriptions". [F]
- **Limitations** ([oss1 §4.6](../track-md-evidence-oss1.md#46-strengths--limitations-summary-marked)):
  heavy ML dep stack (PyTorch, docling-ibm-models, transformers,
  accelerate); first-run model downloads; rapid release cadence
  (v2.102.1 in 2 days, 183 total releases → pinning mandatory);
  Python 3.10+ (3.9 dropped in v2.70.0); per-model licenses need
  separate audit. [F]
- **Per Marker's own benchmark**: docling scores 86.71 heuristic / 3.70
  LLM-judge overall, 92.1/3.72 on scientific paper, 90.0/3.65 on
  books, **68.4/3.40 on forms** (vs Marker 88.0/3.85). [F]
  [datalab-to/marker README, fetched 2026-06-14](https://github.com/datalab-to/marker)
- **Pricing**: OSS MIT free, no quota. No first-party SaaS; IBM and
  Apify operate third-party managed services. [F]
  [oss1 §4.7](../track-md-evidence-oss1.md#47-pricing--quota)

#### 2.2.3 `MinerU` (`opendatalab/MinerU`) — OpenDataLab / Shanghai AI Lab

- **Identity** ([github.com/opendatalab/MinerU, fetched 2026-06-14](https://github.com/opendatalab/MinerU)):
  v3.3 / 2026-06-11. **67.5k stars / 5.7k forks**. **Custom
  "MinerU Open Source License" (Apache-2.0-based)** since v3.1.0
  (2026-04-18); prior versions were AGPLv3. [F]
- **Input coverage**: PDF, DOCX (native, v3.0.0), PPTX / XLSX (native,
  v3.1.0), images, web pages. **109-language OCR.** [F]
  [oss2 §4.4](../track-md-evidence-oss2.md#44-mineru-opendatalabminerU)
- **Three backends** with explicit tradeoff matrix: `pipeline` (fast,
  no hallucination, CPU/GPU), `vlm-engine` (high accuracy, vLLM /
  LMDeploy / mlx), `hybrid-engine` (high accuracy, native text +
  VLM). v3.3 (2026-06-11) adds `effort` parameter (medium/high) for
  hybrid. Reported gains: "Linux: ~80% faster for text PDF scenarios
  and ~35% faster for OCR scenarios; Windows: ~90% faster / 45%;
  macOS: ~220% faster / 50%". [F]
- **Deployment surface (deepest in survey)**: CLI / FastAPI / Gradio
  WebUI / Python+Go+TypeScript SDK / Docker / REST API; `mineru-router`
  for multi-service multi-GPU; **10+ domestic AI chip support**
  (Ascend, Cambricon, Enflame, MetaX, Moore Threads, Kunlunxin,
  Iluvatar, Hygon, Biren, T-Head); **MCP server**; LangChain,
  LlamaIndex, RAGFlow, RAG-Anything, Flowise, Dify, FastGPT
  integrations. [F]
- **Architecture (deep dive)** [`mineru/cli/client.py:570-650, 404-451, 526-559, 128-227, 330-364, fetched 2026-06-14](mineru/cli/client.py):
  - **Task binning**: `plan_pipeline_tasks` sorts documents by
    descending page count, packs into bins up to
    `processing_window_size` total pages, each bin becomes one batch
    submitted to the API.
  - **Asynchronous task submission** with concurrency limit via
    `asyncio.Queue` worker pool.
  - **Live progress renderer** (TTY only) with frame-step animation,
    integrated with `loguru` via custom `LiveAwareStderrSink`.
  - **Sliding-window memory** for long documents (v3.0.0).
  - **Streaming writes to disk** during batch inference (v3.0.0).
    [F]
- **Strengths / limits** ([oss2 §4.4](../track-md-evidence-oss2.md#44-mineru-opendatalabminerU)):
  most production-mature deployment surface; "the strongest direct
  competitor on the PDF+image axis" outside of Marker. Limitations:
  v3.0.0 still has "scenarios where the parsing results may fall
  short of expectations" for complex layouts; default `medium` effort
  disables image/chart analysis. [F]

#### 2.2.4 `Markitdown` — see Tier 1 / Microsoft above (the OSS bellwether)

Cross-referenced here as the **de-facto OSS "anything to markdown"
reference** with 153k stars. LocalDeepL's positioning is **explicitly
higher-fidelity** than Markitdown's deliberate LLM-feed positioning. [A]
[oss2 §4.1](../track-md-evidence-oss2.md#41-microsoftmarkitdown-the-oss-bellwether)

#### 2.2.5 `PyMuPDF4LLM` (`pymupdf/PyMuPDF4LLM`)

- **Identity** ([github.com/pymupdf/PyMuPDF4LLM, fetched 2026-06-14](https://github.com/pymupdf/PyMuPDF4LLM)):
  Artifex Software (MuPDF maintainer). v0.3.4 / 2026-02-14. **1.8k
  stars / 226 forks**. License: **AGPL v3 OR commercial**. [F]
- **Input coverage**: PDF, XPS/OXPS, EPUB/MOBI/FB2, images; **Office
  formats (DOCX, XLSX, PPTX, HWP) require paid PyMuPDF Pro**. [F]
  [oss2 §3.2](../track-md-evidence-oss2.md#32-input-coverage-from-readme-supported-document-formats)
- **Hybrid OCR strategy** (a documented differentiator):
  "PyMuPDF4LLM applies OCR selectively — only where it is actually
  needed… This selective approach typically reduces OCR processing
  time by around 50%." Four conditions: too many illegible chars,
  vector graphics that simulate text, previous OCR text layer,
  images containing text. [F]
  [github.com/pymupdf/PyMuPDF4LLM README, fetched 2026-06-14](https://github.com/pymupdf/PyMuPDF4LLM)
- **Output**: GFM Markdown with `#` – `######` headings from font
  size, `**bold**`, `*italic*`, fenced code, **GFM pipe tables**,
  `![alt](path)` images, lists. JSON and plain text also available. [F]
- **Performance**: "**10× faster** on standard cloud instances"
  (vs. vision-LLM extraction); "**Up to 250× lower** infrastructure
  cost"; "Matches or exceeds vision-LLM accuracy on table detection".
  [F]
- **Architecture (deep dive)** [`pymupdf4llm/src/__init__.py:7-184, fetched 2026-06-14](pymupdf4llm/src/__init__.py):
  `to_markdown(doc, ...)` dispatcher; Layout mode requires the
  **closed-source `pymupdf_layout`** package with its own license.
  `OCRMode` enum ([`pymupdf4llm/src/ocr/__init__.py`, fetched 2026-06-14](pymupdf4llm/src/ocr/__init__.py))
  has 5 modes: NEVER, SELECT_REMOVING_OLD, SELECT_PRESERVING_OLD,
  ALWAYS_REMOVING_OLD, ALWAYS_PRESERVING_OLD. [F]
- **Limitations** ([oss2 §3.6](../track-md-evidence-oss2.md#36-documented-strengths-and-limitations)):
  Office formats require paid Pro; advanced Layout Mode requires
  closed-source `pymupdf_layout`; no LLM/VLM hookup; no public
  benchmarks vs Marker or Docling on the same harness. [F]
- **Significance for LocalDeepL**: the **single biggest threat to
  LocalDeepL's "structured OCR without LLM" pitch** for pure-PDF
  cases. Direct correspondence: PyMuPDF4LLM's hybrid OCR pattern is
  exactly what LocalDeepL's `dense_mode="auto"` does. [A]
  [oss2 §3.8](../track-md-evidence-oss2.md#38-what-this-means-for-localdeepl)

#### 2.2.6 `PDFMiner.six`

- **Identity** ([github.com/pdfminer/pdfminer.six, fetched 2026-06-14](https://github.com/pdfminer/pdfminer.six)):
  MIT, 7.0k stars, 20260107 / 2026-01-07. Pure-Python, no GPU. [F]
- **Output**: text + coordinates; hOCR / HTML / XML / tagged-XML via
  converters in `pdfminer.high_level`. **PDF only.** [F]
  [oss2 §2](../track-md-evidence-oss2.md#2-pdfminer-pdfminersix)
- **Strengths**: "**Support for CJK languages and vertical writing**"
  (README); "Automatic layout analysis"; AcroForm + RC4/AES + Tagged
  PDF + TOC + various font types + image extraction. [F]
- **Architecture** [`pdfminer/high_level.py:32-211, fetched 2026-06-14](pdfminer/high_level.py):
  three public functions `extract_text_to_fp`, `extract_text`,
  `extract_pages`. `LAParams` (line 52-92 of
  [`pdfminer/layout.py`](pdfminer/layout.py)) is the layout
  parameter object. `LTItem`/`LTComponent`/`LTCurve`/`LTLine`/`LTChar`
  /`LTTextContainer`/`LTTextLine`/`LTTextBox`/`LTTextGroup` object
  hierarchy. `LTTextLineVertical`/`LTTextBoxVertical` for CJK
  vertical writing. **Reading-order reconstruction** uses a
  heap-based `group_textboxes` (lines 472-535). [F]
- **Significance**: a **dependency, not a competitor** for modern
  anything-to-MD products. PyMuPDF is usually a better choice in
  the digital-text fallback path (faster, more accurate C engine
  vs. pure-Python). [A] [oss2 §2.8](../track-md-evidence-oss2.md#28-what-this-means-for-localdeepl)

#### 2.2.7 `Unstructured` (`Unstructured-IO/unstructured`)

- **Identity** ([github.com/Unstructured-IO/unstructured, fetched 2026-06-14](https://github.com/Unstructured-IO/unstructured)):
  14.9k stars, v0.23.1 / 2026-06-11, **Apache-2.0**, "Development
  Status :: 4 - Beta". Python 3.11-3.13. [F]
  [oss1 §5](../track-md-evidence-oss1.md#5-unstructured--unstructured-iounstructured)
- **Inputs** (broadest): CSV, DOC, DOCX, EPUB, image (PNG/JPG/HEIC/TIFF),
  MD, ODT, ORG, PDF, PPT, PPTX, RTF, RST, TSV, XLSX, **email, audio
  (wav/mp3 via OpenAI Whisper)**, JSON, NDJSON, XML, plain text.
  Plus a separate `unstructured-ingest` package with 40+ source
  connectors (S3, Azure, GCS, OneDrive, Notion, Slack, Salesforce…).
  [F] [`pyproject.toml:60-128, 140-142, fetched 2026-06-14`](pyproject.toml)
- **Architecture** ([oss1 §5.3](../track-md-evidence-oss1.md#53-architecture-from-the-source)):
  `unstructured.partition.auto.partition()` does file-type detection
  via libmagic and routes to per-format partitioner
  ([`unstructured/partition/auto.py:34-95, 114-219, 283-307, fetched 2026-06-14`](unstructured/partition/auto.py)).
  **Three PDF strategies** dispatched at runtime:
  1. `PartitionStrategy.HI_RES` — `unstructured-inference` (Detectron2
     layout) + pdfminer + Tesseract.
  2. `PartitionStrategy.FAST` — pdfminer text only.
  3. `PartitionStrategy.OCR_ONLY` — render + Tesseract.
  4. `PartitionStrategy.AUTO` (default) — tries `fast`, falls back
     to `hi_res`. [F]
     [`unstructured/partition/pdf.py:74-77, 399-450, 633-740, fetched 2026-06-14`](unstructured/partition/pdf.py)
  - A heuristic (`is_pdf_too_complex`) regex-counts graphics vs
    text operators in the decoded content stream; falls back to
    `hi_res` if ratio > 20:1.
- **Output**: `list[Element]` (typed: `Text`, `Title`, `NarrativeText`,
  `ListItem`, `Image`, `Table`, `PageBreak`, …) with
  `ElementMetadata` (coordinates, page number, languages, links,
  last_modified). **Markdown export is not a first-class feature**
  — the library is partitioned-element-first, Markdown-second. [F]
  [oss1 §5.2](../track-md-evidence-oss1.md#52-input--output-coverage)
- **System deps**: `libmagic-dev`, `poppler-utils`, `tesseract-ocr`
  (+ `tesseract-lang` for languages), `libreoffice`. [F]
- **Limits** ([oss1 §5.6](../track-md-evidence-oss1.md#56-strengths--limitations-summary-marked)):
  Beta status; first-run model downloads; regex-based "complex PDF"
  heuristic may misclassify; `pdf_infer_table_structure` kwarg
  **deprecated** in favour of `skip_infer_table_types`
  [`unstructured/partition/auto.py:111-115, fetched 2026-06-14`](unstructured/partition/auto.py);
  Windows Python 3.13 not fully supported; SaaS push (Unstructured
  Platform). [F]

#### 2.2.8 `Pandoc` (`jgm/pandoc`)

- **Identity** ([github.com/jgm/pandoc, fetched 2026-06-14](https://github.com/jgm/pandoc)):
  44.8k stars, v3.10 / 2026-06-04, **GPL-2.0-or-later** (copyleft).
  Haskell. [F] [oss1 §1.1](../track-md-evidence-oss1.md#11-identity)
- **Inputs**: 40+ readers (DOCX, PPTX, XLSX, ODT, HTML, EPUB, LaTeX,
  RST, Org, MediaWiki, IPYNB, BibTeX/BibLaTeX, CSV, TSV, TWiki,
  Jira, JATS, Man/Mdoc, Djot, Typst, FB2, RIS, EndNoteXML, etc.).
  [F] [oss1 §1.2](../track-md-evidence-oss1.md#12-input--output-coverage)
- **PDF is an OUTPUT, not a meaningful INPUT.** The brief said
  `src/Text/Pandoc/Readers/PDF.hs` exists — that path does not
  exist. [F] [api.github.com/repos/jgm/pandoc/contents/src/Text/Pandoc/Readers, fetched 2026-06-14]
- **Architecture**: modular reader → AST → writer pattern
  [`src/Text/Pandoc.hs:42-69, fetched 2026-06-14](src/Text/Pandoc.hs).
  Native AST in `Text.Pandoc.Definition`. Filters can transform the
  AST (Haskell, JSON, or Lua). [F]
- **Documented lossiness** (README): "Because pandoc's intermediate
  representation of a document is less expressive than many of the
  formats it converts between, one should not expect perfect
  conversions between every format and every other. Pandoc attempts
  to preserve the structural elements of a document, but not
  formatting details such as margin size. And some document
  elements, such as complex tables, may not fit into pandoc's simple
  document model." [F]
- **Significance for LocalDeepL**: gold standard for non-PDF
  interchange; not directly applicable to the PDF mission but is
  the obvious choice for **DOCX/PPTX/XLSX/HTML/EPUB/ODT** legs.
  **GPL-2.0+ copyleft is a real friction point for proprietary
  distributions.** [A] [oss1 §1.8](../track-md-evidence-oss1.md#18-architecture-summary-for-localdeepl-decision)

#### 2.2.9 `Mammoth` (`mwilliamson/python-mammoth`)

- **Identity** ([github.com/mwilliamson/python-mammoth, fetched 2026-06-14](https://github.com/mwilliamson/python-mammoth)):
  1.1k stars, 3.1k dependents. **BSD-2-Clause** (permissive). [F]
- **Single purpose**: `.docx` → `HTML`. **Markdown is deprecated:**
  "Markdown support is deprecated. Generating HTML and using a
  separate library to convert the HTML to Markdown is recommended,
  and is likely to produce better results." [F]
  [oss1 §2.2](../track-md-evidence-oss1.md#22-input--output-coverage)
- **Architecture** [`mammoth/__init__.py:1-42, fetched 2026-06-14](mammoth/__init__.py):
  `convert_to_html` chain: `docx.read(fileobj)` → `transform_document`
  → `convert.convert_document_element_to_html`. Monadic I/O via
  Maybe/Result. Style-map DSL is the killer feature
  (`p[style-name='Aside Heading'] => div.aside > h2:fresh`). [F]
- **Documented limitations** ([oss1 §2.6](../track-md-evidence-oss1.md#26-strengths--limitations-documented)):
  **No HTML sanitisation** — "Source documents can contain links
  with `javascript:` targets" → unsafe for untrusted uploads.
  External file access disabled by default. Pathological
  performance on certain documents (DoS risk). WMF images not
  handled. Underline default ignored. [F]
- **Significance**: specialist tool; useful alternative to pandoc's
  DOCX reader when style-map semantics are wanted. [A]
  [oss1 §2.8](../track-md-evidence-oss1.md#28-architecture-summary-for-localdeepl-decision)

#### 2.2.10 `Marko` (`frostming/marko`) — note scope mismatch

- The brief said "Marko (H2OAI/marko or whatever the canonical repo
  is — verify)". Verification: **there is no `H2OAI/marko`**; the
  H2O.ai GitHub org has `h2o-3`, `h2o-llmstudio`, `h2ogpt`, `wave`.
  The canonical `marko` matching the name and PyPI package is
  `frostming/marko` — a pure-Python **CommonMark Markdown parser**
  (MD → HTML/AST), **not a converter**. The brief most likely meant
  `microsoft/markitdown` (153k stars) — added to the OSS bucket. [A]
  [oss1 §0](../track-md-evidence-oss1.md#0-top-line-re-classifying-marko)
- **`frostming/marko`** ([github.com/frostming/marko, fetched 2026-06-14](https://github.com/frostming/marko)):
  MIT, 458 stars, v2.2.3 / 2026-05-28, CommonMark 0.31.2. Architecture
  [`marko/__init__.py:67-156`, fetched 2026-06-14](marko/__init__.py):
  `Markdown` class wraps `Parser` + `Renderer`; mixin-based
  extension system via `_setup_extensions` that builds a dynamic
  subclass `type("_Parser", tuple(parser_mixins) + (base_parser,), {})()`.
  [F] Built-in extensions: `footnote`, `toc`, `pangu`, `codehilite`,
  plus `marko.ext.gfm.gfm`. **Not thread-safe per instance.** [F]
- **Cross-link worth noting**: `docling`'s `pyproject.toml` declares
  `marko>=2.1.2,<3.0.0` as the markdown parser for its
  `format-markdown` extra
  [`docling/pyproject.toml, fetched 2026-06-14`](docling/pyproject.toml).
  [F]

#### 2.2.11 `Zerox` (`getomni-ai/zerox`) — vision-LLM-only

- **Identity** ([github.com/getomni-ai/zerox, fetched 2026-06-14](https://github.com/getomni-ai/zerox)):
  MIT, 12.2k stars, v0.1.06 / 2024-12-18. **TS 67.6% / Python
  27.2%**. [F]
- **Cloud-only for the heavy lifting** — requires an
  OpenAI / Azure OpenAI / Anthropic / AWS Bedrock / Google Gemini /
  Vertex API key. **No GPU needed, no model download.** Local
  preprocessing uses `libreoffice` (non-PDF → PDF → image), then
  `graphicsmagick` (Node) or `poppler` (Python) to rasterize. [F]
  [oss2 §4.2](../track-md-evidence-oss2.md#42-zerox-getomni-aizerox)
- **Architecture (deep dive)**
  [`node-zerox/src/index.ts`, fetched 2026-06-14](node-zerox/src/index.ts):
  per-page loop, `maintainFormat` mode passes prior page's
  markdown as context; per-page concurrency via `pLimit(10)` (Node)
  / asyncio (Python). **Tesseract is used for orientation
  correction** (cheap local OCR to find page rotation) before
  sending to the vision LLM. [F]
- **Limitations**: cost (every page = one vision-LLM call); no
  offline mode; latest release Dec 2024 → not heavily maintained. [F]
- **Significance for LocalDeepL**: a **positioning reference for
  "vision-LLM-only"**, not a direct competitor for the hybrid
  local-first story. The `maintainFormat` pattern is worth
  selectively adopting for the `GroundedEngine` VLM post-processor.
  [A] [oss2 §4.2](../track-md-evidence-oss2.md#42-zerox-getomni-aizerox)

#### 2.2.12 `LlamaParse` (`run-llama/llama_cloud_services`) — **deprecated SDK**

- **Identity** ([github.com/run-llama/llama_cloud_services, fetched 2026-06-14](https://github.com/run-llama/llama_cloud_services)):
  4.3k stars, v0.6.94 / 2026-02-13, MIT (SDK). **Repo is
  DEPRECATED**, EOL **May 1, 2026** — migrate to `llama-cloud>=1.0`.
  [F]
- **Cloud-only**, pay-per-page. Gold-standard cloud reference for
  LlamaIndex ecosystem users. [A]
  [oss2 §4.5](../track-md-evidence-oss2.md#45-llamaparse--run-llamallama_cloud_services)

---

## 3. Feature Matrix

### 3.1 Input coverage matrix (synthesized from §2)

| Format | Marker | PDFMiner | PyMuPDF4LLM | Markitdown | Docling | MinerU | Unstructured | Pandoc | Mammoth | Zerox | LlamaParse | **LocalDeepL** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PDF | ✅ | ✅ | ✅ | ✅ (pdfplumber, no OCR) | ✅ | ✅ | ✅ | ❌ no reader | ❌ | ✅ | ✅ | ✅ (Surya+VLM) |
| DOCX | ✅ | ❌ | 🔒 Pro | ✅ (mammoth) | ✅ | ✅ (v3.0) | ✅ | ✅ | ✅ | ✅ (libreoffice) | ✅ | (via pandoc) |
| XLSX | ✅ | ❌ | 🔒 Pro | ✅ (openpyxl) | ✅ | ✅ (v3.1) | ✅ | ✅ | ❌ | ✅ (libreoffice) | ❌ | (via pandoc) |
| PPTX | ✅ | ❌ | 🔒 Pro | ✅ (python-pptx) | ✅ | ✅ (v3.1) | ✅ | ✅ | ❌ | ✅ (libreoffice) | ✅ | (via pandoc) |
| HTML | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ (web pages) | ✅ | ✅ | ❌ | ✅ | ❌ | (via pandoc) |
| EPUB | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | (via pandoc) |
| Images | ✅ | ❌ | ✅ (single-page) | ✅ (EXIF + OCR) | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ✅ (HybridEngine) |
| Audio | ❌ | ❌ | ❌ | ✅ (EXIF + ASR) | ✅ (AsrPipeline) | ❌ | ✅ (Whisper) | ❌ | ❌ | ❌ | ❌ | ❌ (VLM audio possible) |
| Email (EML/MSG) | ❌ | ❌ | ❌ | ❌ (MSG) | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| LaTeX | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| WebVTT (captions) | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| YouTube URLs | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Patents / JATS / XBRL | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| ZIP (iterate) | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Apple Vision (on-device) | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | (could integrate) |

(Sources: §2 entries + [oss2 §5.4](../track-md-evidence-oss2.md#54-format-coverage-matrix-synthesized)
+ [ms §1](../track-md-evidence-ms.md#1-markitdown-core-repo). [F] except where noted
as inferred from absence.) [A] Docling has the broadest; Marker is PDF-centric;
PyMuPDF4LLM is PDF+EPUB+image; **the audio + email + LaTeX + WebVTT niche is
uncontested by Marker/PyMuPDF4LLM/PDFMiner and only Docling serves it locally**.

### 3.2 Quality claims (synthesized from §2)

| Player | Layout fidelity | CJK / RTL | Footnotes | Code | LaTeX/math | Markdown schema |
|---|---|---|---|---|---|---|
| Markitdown (PDF) | No layout detection; pdfplumber only | "passable UTF-8" | ❌ | ❌ | ❌ | GFM |
| Markitdown (docx via mammoth) | Headings/lists/hyperlinks; no table formatting | UTF-8 | endnotes | n/a | n/a | GFM via html2md |
| Azure DI prebuilt-layout | HTML tables, LaTeX, `<!--PageBreak-->` | 200+ langs | KVP→JSON | n/a | `$$…$$` | **HTML-tables + comments** |
| Azure DI prebuilt-read | OCR + searchable PDF | 200+ langs, CJK on images (v4.0) | n/a | n/a | n/a | text + structure |
| Google Form Parser | KVP + tables + checkboxes | 200+ langs | n/a | n/a | n/a | n/a (JSON only) |
| Google Layout Parser | "Layout-aware chunking" w/ merged cells | n/a | n/a | n/a | n/a | n/a (no MD) |
| Google Custom Extractor | Up-trains with 10 docs (gen path) | English-only on gen path | n/a | n/a | n/a | n/a (no MD) |
| Adobe PDF→MD | Path-style element classification (H1, L, Li, P, Table) | "broad range" | n/a | n/a | n/a | GFM + base64-embedded images |
| Pandoc | Lossy; structural not visual | format-agnostic | ✅ | ✅ | ✅ (TeX/KaTeX/MathML/OMML) | native + GFM + CommonMark + others |
| Mammoth | Semantic clean HTML | n/a | footnotes/endnotes | n/a | n/a | HTML (MD deprecated) |
| Docling | Full PDF: layout + reading order + table + code + formula + chart | multilingual layout + OCR packs | ✅ | ✅ | LaTeX | MD, HTML, JSON, **DocTags** (lossless) |
| Unstructured | Element-level IR; Markdown is secondary | per-element lang detection | n/a | n/a | n/a | not first-class |
| Marker | 95.67 heuristic / 4.24 LLM-judge | "all languages" (Surya) | superscript | fenced | `$$…$$` | GFM + 28-element block JSON |
| PDFMiner | Layout analysis + reading order + CJK vertical | explicit CJK + vertical | n/a | n/a | n/a | text/hOCR/HTML/XML |
| PyMuPDF4LLM | GFM with bold/italic/code; pipe tables; headings from font hierarchy | CJK fonts via MuPDF | n/a (inferred) | fenced | n/a | GFM |
| Zerox | LLM-only; no own OCR | model-dep | model-dep | model-dep | model-dep | GFM |
| MinerU | 109-lang OCR; cross-page table merge; seal text; vertical text | explicit 109 langs | ✅ | ✅ | interline formula numbering | GFM + JSON |
| **LocalDeepL (current)** | Surya layout + VLM fallback + DP align | (Surya multilingual + VLM lang) | (post-process configurable) | (configurable) | (configurable) | (configurable; see gaps §6) |

(Sources: §2 + [ms §3](../track-md-evidence-ms.md#3-azure-document-intelligence-formerly-form-recognizer)
+ [google §1](../track-md-evidence-google.md#1-google-document-ai--processors-relevant-to-anything-to-markdown)
+ [adobe-apple §1.3](../track-md-evidence-adobe-apple.md#13-quality--layout-fidelity)
+ [oss1 §1.4, §2.4, §4.4, §5.4](../track-md-evidence-oss1.md)
+ [oss2 §1.3, §2.3, §3.3, §4.2, §4.3, §4.4](../track-md-evidence-oss2.md))

### 3.3 Pricing (cloud services only)

| Service | Free tier | Pay-as-you-go |
|---|---|---|
| Azure Document Intelligence Read | 500 pages/mo F0 | ~$1.50 / 1k pages |
| Azure Document Intelligence Prebuilt (incl. Layout) | 500 pages/mo F0 | ~$10 / 1k pages |
| Azure Document Intelligence Custom Extraction | (none) | ~$30 / 1k pages |
| Google Document AI Form Parser | 1k pages/mo free | $30 / 1k pages |
| Google Document AI Enterprise OCR (digitize) | 1k pages/mo free | $1.50 / 1k pages |
| Google Document AI Layout Parser | (no free tier called out) | $10 / 1k pages |
| Google Document AI Custom Extractor | (no free tier called out) | $30 / 1k pages |
| Adobe PDF Services / Extract / PDF-to-Markdown | 500 Document Transactions/mo | 1 DT per 5 pages |
| Microsoft 365 Copilot | n/a (per-user) | $30/user/month (US list, secondary) |
| NotebookLM | 50 sources × 500k words × 200 MB | Plus: 300 sources |
| LlamaParse | $5 free credits (per Omni / Datalab) | pay per page |
| Marker (managed Chandra) | $5 free credits (per Datalab) | pay per page |

(Sources: §2 entries + [ms §3](../track-md-evidence-ms.md#3-azure-document-intelligence-formerly-form-recognizer)
+ [google §1.2 pricing](../track-md-evidence-google.md#12-enterprise-document-ocr)
+ [adobe-apple §1.8](../track-md-evidence-adobe-apple.md#18-pricing--quota)
+ [oss2 §1.4](../track-md-evidence-oss2.md#14-execution-mode)
+ [oss2 §4.5](../track-md-evidence-oss2.md#45-llamaparse--run-llamallama_cloud_services))

### 3.4 License matrix (synthesized from §2)

| Project | License | Commercial-use note |
|---|---|---|
| Markitdown | MIT | No restrictions |
| Pandoc | **GPL-2.0-or-later** | Copyleft — ok to *use* via shell, dangerous to *link/distribute* |
| Mammoth | BSD-2-Clause | No restrictions |
| Marko (frostming) | MIT | No restrictions |
| Docling | MIT (code) | Permissive code, per-model licenses separate |
| Unstructured | Apache-2.0 | No restrictions |
| Marker | **GPL-3.0 + RAIL-M** (models) | **$2M revenue/funding cap**; commercial license required above |
| PDFMiner | MIT | No restrictions |
| PyMuPDF4LLM | **AGPL v3 OR commercial** | AGPL viral; commercial license for proprietary SaaS |
| PyMuPDF Layout | **Closed-source, separate license** | Required for advanced mode |
| Zerox | MIT | No restrictions (vision-LLM cost on user) |
| MinerU | **Apache-2.0-based (custom)** | Apache-style, permissive |
| LlamaParse SDK | MIT (cloud) | Cloud usage pay-per-page |
| Adobe PDF Services SDK samples | MIT (samples only) | Runtime SDKs closed |
| Azure / Google / Apple services | Cloud SaaS | Pay-per-use |

(Sources: §2 entries + [oss2 §5.3](../track-md-evidence-oss2.md#53-licenses-decision-relevant-for-localdeepls-vendor-picks).)

**Key insight** [A]: any LocalDeepL user with >$2M revenue cannot freely ship
Marker's model weights. PyMuPDF4LLM is risky under AGPL. The MIT-licensed
options (Docling, Markitdown, PDFMiner, Zerox, frostming/marko) are the
safest substrate; MinerU is also safe. Marker is the most popular but most
license-encumbered.

### 3.5 Execution mode matrix

| Player | Pure-local CPU | Local GPU | Cloud-only | Hybrid local+VLM | Self-host commercial |
|---|---|---|---|---|---|
| Markitdown (built-in) | ✅ | ❌ | ❌ | (via `markitdown-ocr` plugin or az extras) | n/a |
| Markitdown az extras | (via `azure-ai-documentintelligence`) | (via LLM extras) | ✅ (Azure) | ✅ | n/a |
| Azure Document Intelligence | (Connected/Disconnected Container, $$$$) | n/a | ✅ | n/a | ✅ (Disconnected Container) |
| Google Document AI | ❌ | ❌ | ✅ | n/a | ❌ |
| Google Gemini | (Vertex AI) | (Vertex AI) | ✅ | ✅ | ❌ |
| NotebookLM | ❌ | ❌ | ✅ (UI only) | n/a | ❌ |
| Adobe Extract / PDF Services | ❌ | ❌ | ✅ | n/a | ❌ |
| Apple Vision | ✅ (on-device) | (Apple Neural Engine) | ❌ | n/a | n/a |
| Apple Shortcuts / Notes | ✅ (on-device) | (ANE) | n/a | n/a | n/a |
| Pandoc | ✅ | ❌ | ❌ | n/a | ✅ |
| Mammoth | ✅ | ❌ | ❌ | n/a | ✅ |
| Marko | ✅ | ❌ | ❌ | n/a | ✅ |
| Docling | ✅ | ✅ | ❌ | ✅ (GraniteDocling VLM, 258M) | ✅ |
| Unstructured | ✅ | ✅ (Detectron2) | ❌ | ❌ (LLM via SaaS Platform) | ✅ |
| Marker | ✅ | ✅ (incl. MPS) | (Chandra paid SaaS) | ✅ (`--use_llm`) | ✅ (paid commercial license) |
| PDFMiner | ✅ | ❌ | ❌ | n/a | ✅ |
| PyMuPDF4LLM | ✅ | ❌ | ❌ | ❌ (Layout mode is closed-source) | ✅ (paid) |
| Zerox | ✅ (preprocessing) | n/a | ✅ (vision LLM) | n/a | n/a |
| MinerU | ✅ | ✅ (incl. vLLM/LMDeploy/mlx) | (mineru.net paid) | ✅ (hybrid-engine) | ✅ |
| LlamaParse | ❌ | ❌ | ✅ | n/a | n/a |
| **LocalDeepL (current)** | ✅ (default) | ✅ (VLM backend) | (via VLM) | ✅ (HybridEngine + GroundedEngine + grounded_backend) | ✅ |

(Sources: §2 entries + [AGENTS.md](../../AGENTS.md). [F] where the cell is
verified by source, [A] otherwise.)

---

## 4. Pipeline Patterns Common to Leaders

The OSS leaders converge on a small set of architectural primitives. Each
pattern is cited with a primary source.

### 4.1 Format-keyed dispatch table

Mapping `InputFormat → (backend, pipeline)`. Used by:

- **Docling** — `_get_default_option` dict in
  [`docling/document_converter.py:190-237, fetched 2026-06-14`](docling/document_converter.py)
  covers 18 input formats mapped to 3 pipelines. [F]
- **Markitdown** — `MarkItDown` priority-ordered
  `ConverterRegistration(converter, priority)` list in
  [`packages/markitdown/src/markitdown/_markitdown.py:23-44, 34-39, fetched 2026-06-14`](packages/markitdown/src/markitdown/_markitdown.py). [F]
- **Unstructured** — `unstructured.partition.auto.partition()` with
  libmagic-driven routing in
  [`unstructured/partition/auto.py:34-219, fetched 2026-06-14`](unstructured/partition/auto.py). [F]
- **Marker** — `marker/providers/registry.py` for file extension dispatch,
  `BaseConverter` for per-converter composition. [F]

LocalDeepL can grow this pattern in `core/routing.py` + the new
`document_processors` extension point (see §6 below).

### 4.2 Multi-stage threaded pipeline with bounded queues, back-pressure, partial-success

The single most important production pattern. **Docling's
`StandardPdfPipeline`** is the reference implementation:

- 5 stages (Preprocess → OCR → Layout → Table → Assemble) with
  `ThreadedPipelineStage(batch_size, batch_timeout, queue_max_size)`.
  [`docling/pipeline/standard_pdf_pipeline.py:393-435, 572-606, 763-784, fetched 2026-06-14`](docling/pipeline/standard_pdf_pipeline.py). [F]
- Per-run-id isolation, document-timeout, `SUCCESS / PARTIAL_SUCCESS / FAILURE`
  status. **Failed pages preserved as empty `PageItem` entries** so
  page-break markers stay correct.
- Heavy model init once per pipeline instance, thread-safe read-only
  in workers.

LocalDeepL's current `HybridEngine` runs sequentially per page (per
AGENTS.md). [A] Borrow this pattern if/when batch throughput becomes a
bottleneck.

### 4.3 Content-sniff dispatcher

Using `magika` (Google) or `libmagic` to pick the right converter without
relying on file extensions:

- **Markitdown** — `self._magika = magika.Magika()`
  [`_markitdown.py:105-109, fetched 2026-06-14`](packages/markitdown/src/markitdown/_markitdown.py). [F]
- **Unstructured** — `libmagic` content sniffing. [F]

### 4.4 Hybrid OCR with page-level decision

The pattern LocalDeepL's `dense_mode="auto"` embodies:

- **PyMuPDF4LLM** — `OCRMode` enum (5 modes:
  `NEVER, SELECT_REMOVING_OLD, SELECT_PRESERVING_OLD, ALWAYS_REMOVING_OLD, ALWAYS_PRESERVING_OLD`).
  Selective OCR reduces processing time by ~50%. [F]
  [`pymupdf4llm/src/ocr/__init__.py, fetched 2026-06-14`](pymupdf4llm/src/ocr/__init__.py)
- **Marker** — `OrderProcessor → TextProcessor` chain; `--force_ocr` for
  re-OCR of garbled digital text. [F]
- **Docling** — `PreprocessThreadedStage` → OCR stage with `batch_size`/
  `batch_timeout`/`queue_max_size`. [F]
- **MinerU** — explicit `method` (`"auto" | "txt" | "ocr"`) and
  `backend` (`"pipeline" | "vlm-engine" | "vlm-http-client" | "hybrid-engine" | "hybrid-http-client"`). [F]
  [`mineru/cli/client.py:570-650, fetched 2026-06-14`](mineru/cli/client.py)

### 4.5 Plugin entry-points

For extensibility without forking:

- **Markitdown** — `markitdown.plugin` entry-point
  [`_markitdown.py:42-62, fetched 2026-06-14`](packages/markitdown/src/markitdown/_markitdown.py). [F]
- **Docling** — `pipeline_cls` factory + extras
  (`format-pdf-docling`, `feat-ocr-rapidocr`, `models-vlm-inline`,
  `format-audio`, etc.). [F]

### 4.6 Lossless structured IR with multiple output renderers

- **Docling `DoclingDocument`** — Markdown, HTML, WebVTT, DocLang, **DocTags**
  (lossless, arXiv 2503.11576), JSON. [F]
- **Marker `Schema`** — 28 block types; Markdown, JSON, HTML, chunks
  (flat list with full HTML per block, designed for RAG). [F]

This is the **gold standard for anything-to-MD** — a lossless structured IR
that can be re-rendered to MD, JSON, HTML, or chunks without losing
information. LocalDeepL's `DocumentResult` IR is closer in spirit to
Unstructured's `list[Element]` than to a true lossless IR. [A] See §6.

### 4.7 Heavy model caching keyed by options-hash

- **Docling** — `DocumentConverter.initialized_pipelines: dict[(pipeline_class, options_md5_hash), pipeline_instance]`
  [`docling/document_converter.py:355-378, fetched 2026-06-14`](docling/document_converter.py). [F]

The right pattern for any VLM-backed pipeline that loads multi-GB models.

### 4.8 DI via reflection to wire `artifact_dict` and `config`

- **Marker** `BaseConverter.resolve_dependencies` injects dependencies
  into each processor/renderer via reflection
  [`marker/converters/__init__.py:13-39, fetched 2026-06-14`](marker/converters/__init__.py). [F]
- **`BaseExtractor.max_concurrency: int = 3`** for LLM-backed extractors
  [`marker/extractors/__init__.py:11-39, fetched 2026-06-14`](marker/extractors/__init__.py). [F]

### 4.9 Sliding-window memory + streaming writes for long documents

- **MinerU v3.0.0** — sliding-window memory optimization + streaming
  writes to disk during batch inference. [F]
- **Docling** — `document_timeout` + per-page partial success. [F]

### 4.10 Async orchestration with task binning + bounded concurrency

- **MinerU CLI** [`mineru/cli/client.py:570-650, 404-451, 526-559, 128-227, 330-364, fetched 2026-06-14`](mineru/cli/client.py):
  `plan_pipeline_tasks` sorts docs by descending page count, packs
  into bins up to `processing_window_size` total pages. `asyncio.Queue`
  worker pool. Custom `LiveAwareStderrSink` for live progress. [F]

### 4.11 Per-page context threading (VLM maintainFormat)

- **Zerox** `maintainFormat` mode passes prior page's markdown as
  context to keep formatting consistent across pages. [F]

This is a clever pattern LocalDeepL could selectively adopt for the
`GroundedEngine` VLM post-processor — see §6.

### 4.12 License-as-feature

- Marker, PyMuPDF4LLM, Pandoc have copyleft/viral/cap clauses; Docling,
  Markitdown, PDFMiner, Zerox, MinerU do not. **A permissive license is
  a real B2B feature.** [A] [oss2 §5.3](../track-md-evidence-oss2.md#53-licenses-decision-relevant-for-localdeepls-vendor-picks)

---

## 5. Open-Source Quality Tier

The OSS quality tier forms three concentric rings around LocalDeepL.

### 5.1 Direct architectural analogs (most relevant for LocalDeepL strategy)

| Project | Why it's a direct analog | Key differentiator vs LocalDeepL |
|---|---|---|
| **Marker** | Same Surya stack (layout + recognition + table_rec + detection + ocr_error); same VLM post-processor idea (`--use_llm`); same markdown + JSON outputs; 28-element block schema | GPL-3.0 + RAIL-M **$2M cap**; `forms` benchmark worst in class; `--use_llm` defaults to cloud Gemini |
| **Docling** | Same broad-format coverage idea; lossless `DoclingDocument` IR; multi-stage threaded pipeline; GraniteDocling VLM embedded | Heavy ML dep stack (torch, docling-ibm-models); 183 releases = pinning mandatory; no per-page dense/sparse routing |
| **MinerU** | Hybrid backend = same idea (pipeline + vlm); 109-language OCR; cross-page table merge; deepest deployment surface | Docker-first; Chinese AI chip support is irrelevant to LocalDeepL's typical Windows customer; no Windows quick-start |

The shared architectural fingerprint across Marker, Docling, and MinerU is
**Surya-family layout detection + VLM fallback**. LocalDeepL already has
this; the wedge is *the triggering logic* (per-page dense/sparse routing
controlled by `dense_mode="auto"`) and *the deployment story*
(`install.bat`/`start_app.vbs` Windows one-click). [A]
[oss1 §4.6](../track-md-evidence-oss1.md#46-strengths--limitations-summary-marked),
[oss2 §1.8](../track-md-evidence-oss2.md#18-what-this-means-for-localdeepl),
[oss2 §4.4](../track-md-evidence-oss2.md#44-mineru-opendatalabminerU)

### 5.2 Performance reference (LocalDeepL must beat for pure-PDF)

| Project | Why it sets the floor |
|---|---|
| **PyMuPDF4LLM** | "10× faster" / "250× lower cost" claims; hybrid OCR pattern; GFM output; MIT-compatible BUT Office formats paywalled; Layout mode is closed-source `pymupdf_layout`; no LLM fallback |
| **PDFMiner** | Pure-Python reference; explicit CJK + vertical writing; AcroForm + Tagged PDF support; "dependency, not competitor" |

For customers who are happy with PyMuPDF4LLM's fidelity on pure-PDF
inputs, LocalDeepL must win on **broader input coverage (image, audio
transcripts via VLM) and grounded VLM fallback for hard pages**. [A]
[oss2 §3.8](../track-md-evidence-oss2.md#38-what-this-means-for-localdeepl)

### 5.3 Format-coverage leaders (where LocalDeepL should NOT compete)

| Project | Where it wins | Why LocalDeepL should not chase |
|---|---|---|
| **Markitdown** | 153k stars; broadest cloud-Azure bridge; plugin ecosystem | Low-fidelity positioning; LocalDeepL explicitly higher-fidelity |
| **Unstructured** | 40+ ingest connectors; SaaS Platform for enterprise | Element-list primary output, not MD; Beta status; heavy system deps |
| **Pandoc** | Gold standard for non-PDF interchange | GPL-2.0+; no PDF reader; lossy round-trips by design |
| **Zerox** | "Dead simple" VLM-only; multi-provider LLM | Cloud-only; no offline; Dec 2024 last release |
| **LlamaParse** | Gold-standard cloud for LlamaIndex ecosystem | Cloud-only; **SDK deprecated, EOL 2026-05-01** |

[A] The local product plan should not try to be a better Markitdown
(LLM-feed positioning) or a better Pandoc (universal format
interchange). The defensive moat is **local-first, higher-fidelity
PDF + image + audio transcripts, with VLM as escape hatch** — narrower
than Docling/MinerU on input coverage but better-tuned.

### 5.4 Quality tiering summary

```
Tier 1 (local-first, broad coverage, VLM-ready)
  Docling, MinerU, Marker, LocalDeepL
Tier 2 (specialist or performance reference)
  PyMuPDF4LLM, PDFMiner, Mammoth, Pandoc
Tier 3 (cloud-only or positioning-specific)
  Markitdown, Unstructured, Zerox, LlamaParse, Adobe Extract,
  Azure Doc Intel, Google Document AI, NotebookLM
```

[oss2 §5.1](../track-md-evidence-oss2.md#51-three-architectural-patterns-for-anything-to-markdown),
[oss2 §5.6](../track-md-evidence-oss2.md#56-what-localdeepls-wedge-should-be)

---

## 6. Gaps LocalDeepL Could Fill

The brief requires that gaps be specific to LocalDeepL's existing extension
points (`grounded_backend`, `document_processors`, `aligner`, `ocr_processor`,
`page_preprocessor`, output writers — see
[AGENTS.md](../../AGENTS.md)). The gaps below are mapped to those slots.

### 6.1 Anything-to-MD richness (heading / list / table / code / math fidelity)

| Gap | Evidence | Recommendation (extension point) | Effort |
|---|---|---|---|
| **Markdown schema is implicit, not documented.** Azure uses HTML tables + `<!--PageBreak-->`; Adobe uses base64-embedded images; Marker uses GFM; Docling ships DocTags. LocalDeepL's output is configurable but not enumerated. | [ms §3](../track-md-evidence-ms.md#3-azure-document-intelligence-formerly-form-recognizer), [adobe-apple §1.3](../track-md-evidence-adobe-apple.md#13-quality--layout-fidelity), [oss1 §4.2](../track-md-evidence-oss1.md#42-input--output-coverage) | **Document and add a schema config** to the markdown writer. Expose a `markdown_flavor` enum: `gfm` (default) / `gfm_html_tables` / `docling_like` / `markdown_only`. Add to `ProcessSettings`. | S |
| **No Markitdown-style plugin registry.** Markitdown's `markitdown.plugin` entry-point system lets users add a new `DocumentConverter` subclass and have it auto-registered. | [ms §1](../track-md-evidence-ms.md#1-markitdown-core-repo), [oss1 §5.3](../track-md-evidence-oss1.md#53-architecture-from-the-source) | **Add a `localdeepl.plugin` entry-point** so third parties can ship a `DocumentConverter` and have it auto-discovered by the pipeline. Maps to the existing extension point; new code is a small loader. | S |
| **No `magika`/libmagic-style content-sniff dispatcher.** Markitdown uses `magika` to dispatch even without extensions. | [ms §1](../track-md-evidence-ms.md#1-markitdown-core-repo), [oss1 §5.3](../track-md-evidence-oss1.md#53-architecture-from-the-source) | **Add a `core/routing.py` extension that sniffs the file with `magika` before deciding the path.** Falls back to extension-based dispatch if not installed. | S |
| **No lossless structured IR.** Docling's `DoclingDocument` exports MD/HTML/DocTags/JSON; Marker's `Schema` has 28 block types. LocalDeepL's `DocumentResult` (`core/document.py`) is closer to Unstructured's `list[Element]`. | [oss1 §4.2](../track-md-evidence-oss1.md#42-input--output-coverage), [oss2 §1.3](../track-md-evidence-oss2.md#13-quality-claims) | **Round-trip test for the `DocumentResult` IR**: ensure every field is preserved through Markdown → parser → `DocumentResult` for at least one parser. Add `chunk_format` to the output writer (like Marker's chunks). | M |
| **Mammoth-style style-map DSL for DOCX → MD.** Mammoth's `p[style-name='Aside Heading'] => div.aside > h2:fresh` is a clean declarative mapping tool. | [oss1 §2.4](../track-md-evidence-oss1.md#24-quality--layout-fidelity) | **Adopt Mammoth's style-map DSL** for the `docx → markdown` leg (or for the existing `core/docx_writer.py` reversed). | M |
| **Per-page `maintainFormat` for the `GroundedEngine`.** Zerox passes the prior page's markdown as context to keep formatting consistent across pages. | [oss2 §4.2](../track-md-evidence-oss2.md#42-zerox-getomni-aizerox) | **Add a `grounded_backend` option `maintain_format: bool`** that threads prior-page Markdown into the VLM prompt. Maps to the existing `grounded_backend` extension point. | S |
| **No `effort` parameter.** MinerU's v3.3 added an `effort: "medium" | "high"` parameter to the hybrid backend (medium disables image/chart analysis). | [oss2 §4.4](../track-md-evidence-oss2.md#44-mineru-opendatalabminerU) | **Add an `effort` knob to `ProcessSettings`**: `low` (Surya-only), `medium` (default, no image/chart analysis), `high` (image/chart analysis + VLM if available). | M |

### 6.2 `document_processors` (table_extraction, layout_enrichment, new ones)

| Gap | Evidence | Recommendation (extension point) | Effort |
|---|---|---|---|
| **Cross-page table merge.** Marker has `LLMTableMergeProcessor`; MinerU v3.0 explicitly adds cross-page table merge. LocalDeepL has `table_extraction` but cross-page merge is unclear. | [oss2 §1.5](../track-md-evidence-oss2.md#15-architecture--pipeline), [oss2 §4.4](../track-md-evidence-oss2.md#44-mineru-opendatalabminerU) | **Add a `cross_page_table_merge: bool` to `table_extraction`** (or as a new processor). Use heuristics: same column count + similar row heights + adjacent page-break marker. | M |
| **Form extraction.** Every OSS tool admits weakness on forms. Marker's README: "Forms may not be rendered well". Docling 68.4/3.40 on forms. | [oss2 §1.6](../track-md-evidence-oss2.md#16-documented-strengths-and-limitations) | **Add a `form_extraction` processor** (use AcroForm text + VLM for non-AcroForm). Maps to existing `document_processors` extension point. | L |
| **No native audio / video transcript leg.** Docling has `AsrPipeline`; Markitdown has `audio-transcription` and `az-content-understanding` (video). LocalDeepL has none. | [oss1 §4.2](../track-md-evidence-oss1.md#42-input--output-coverage), [ms §1](../track-md-evidence-ms.md#1-markitdown-core-repo) | **Add an `audio_transcription` processor** (Whisper ONNX for local) and a `video_caption_extraction` processor (VLM on key frames). Maps to `document_processors`. | L |
| **Long-document memory.** Only MinerU (sliding window + streaming writes) and Docling (document_timeout + per-page partial success) handle this in their core. | [oss2 §4.4](../track-md-evidence-oss2.md#44-mineru-opendatalabminerU), [oss1 §4.3](../track-md-evidence-oss1.md#43-architecture-from-the-source) | **Add a `long_document_strategy` to `ProcessSettings`**: `eager` (current), `sliding_window` (page-batch with explicit GC), `streaming` (write to disk per page). | L |

### 6.3 `aligner` / detector swap (layout)

| Gap | Evidence | Recommendation (extension point) | Effort |
|---|---|---|---|
| **No `pymupdf_layout` integration.** PyMuPDF4LLM's advanced Layout Mode uses the closed-source `pymupdf_layout` package. If a customer is happy with that fidelity, it's a strong local-only option. | [oss2 §3.5](../track-md-evidence-oss2.md#35-architecture--pipeline) | **Make the `aligner` slot pluggable with `PyMuPDFLayoutBackend`** as an alternative to Surya. License: `pymupdf_layout` is closed-source with separate license; **do not enable by default** and gate behind an opt-in extra. | M |
| **Docling-parse as an alternative PDF text backend.** `docling-parse` (v6.x) is the text-extraction layer Docling uses; faster and more accurate than pdfminer for many cases. | [oss1 §4.3](../track-md-evidence-oss1.md#43-architecture-from-the-source) | **Add `docling_parse` as a `aligner` backend option** alongside `pypdfium2` and `pdfminer.six`. | M |
| **GraniteDocling 258M as a local VLM fallback.** Docling ships its own 258M VLM for `--pipeline vlm`. | [oss1 §4.2](../track-md-evidence-oss1.md#42-input--output-coverage) | **Add `granite_docling` as a `grounded_backend` option** for users who want a local VLM that doesn't require a separate inference server. | M |

### 6.4 `ocr_processor` (provider selection, fallback chain)

| Gap | Evidence | Recommendation (extension point) | Effort |
|---|---|---|---|
| **No OCR engine selection.** Markitdown, Docling, Unstructured all let the user pick (Tesseract / RapidOCR / EasyOCR / macOCR). LocalDeepL's `ocr_processor` is locked to Surya. | [oss1 §4.2](../track-md-evidence-oss1.md#42-input--output-coverage), [oss1 §5.2](../track-md-evidence-oss1.md#52-input--output-coverage) | **Allow the `ocr_processor` slot to be a list** with fallback chain. Default: `[SuryaOCRProcessor, TesseractOCRProcessor]`. User can override. | M |
| **No OCR engine for Microsoft / Google cloud fallback.** For users who want the highest accuracy on a specific page, routing to Azure `prebuilt-read` (searchable PDF) or Google Enterprise OCR (Math OCR, font detection) is a real option. | [ms §3](../track-md-evidence-ms.md#3-azure-document-intelligence-formerly-form-recognizer), [google §1.2](../track-md-evidence-google.md#12-enterprise-document-ocr) | **Add an `ocr_processor: "az-read" | "google-ocr" | "surya"` option** to `ProcessSettings`. These become opt-in cloud backends. | L |

### 6.5 `page_preprocessor` (orientation / deskew / denoise / contrast / crop)

| Gap | Evidence | Recommendation (extension point) | Effort |
|---|---|---|---|
| **No image-quality scoring before preprocessing.** Google Enterprise OCR exposes an 8-dimension image-quality score that is the basis for routing decisions. | [google §1.2](../track-md-evidence-google.md#12-enterprise-document-ocr) | **Add a `quality_routing` decision** that uses the existing `core/routing.py` + a per-page quality score. Score thresholds drive `dense_mode` and VLM fallback. | M |
| **No MIME dispatch (image / audio / video).** LocalDeepL's `page_preprocessor` is currently a single class; the inputs include images, audio, video that need different preprocessing chains. | [oss1 §4.2](../track-md-evidence-oss1.md#42-input--output-coverage) | **Make `page_preprocessor` format-keyed** (per §4.1 above). Image, audio, video each get their own preprocessor. | M |

### 6.6 Output writers (docx_writer, new ones: xlsx, html, jats-xml)

| Gap | Evidence | Recommendation (extension point) | Effort |
|---|---|---|---|
| **No xlsx / html / jats-xml export.** Docling exports Markdown, HTML, WebVTT, DocLang, DocTags, lossless JSON. Markitdown exports Markdown only. LocalDeepL's docx export route is the only second format. | [oss1 §4.2](../track-md-evidence-oss1.md#42-input--output-coverage), [ms §1](../track-md-evidence-ms.md#1-markitdown-core-repo) | **Add three more output writers**: `xlsx_writer` (tables only; `openpyxl`), `html_writer` (Docling-like semantic HTML), `jats_xml_writer` (JATS for scientific publishing). Maps to existing output writer extension. | L |
| **No chunks output (RAG-friendly).** Marker ships a `chunks` output (flat list of top-level blocks with full HTML per block, designed for RAG). | [oss2 §1.3](../track-md-evidence-oss2.md#13-quality-claims) | **Add a `chunks_writer`** to the output writer chain. RAG chunkers downstream should be able to consume this without re-parsing Markdown. | M |
| **No docx style map DSL.** Mammoth's killer feature is the `p[style-name='Aside Heading'] => div.aside > h2:fresh` style-map DSL. | [oss1 §2.4](../track-md-evidence-oss1.md#24-quality-fidelity) | **Expose a `style_map` option** in the `docx_writer` for the docx export route. | S |

### 6.7 Schema / structured extraction (Pydantic, JSON Schema round-trip)

| Gap | Evidence | Recommendation (extension point) | Effort |
|---|---|---|---|
| **No first-class structured extraction beyond `table_extraction` and `layout_enrichment`.** Marker has `ExtractionConverter` (Pydantic schema). LlamaParse has structured output. Google has `Custom Extractor`. | [oss2 §1.5](../track-md-evidence-oss2.md#15-architecture--pipeline), [google §1.4](../track-md-evidence-google.md#14-custom-extractor) | **Add a `structured_extraction` processor** that takes a Pydantic model (or JSON Schema), runs Gemini Structured Output (`responseSchema`) or equivalent, and emits typed results. Cross-cuts to track-schema. | L |
| **No JSON Schema round-trip on the input side.** | [google §2.2](../track-md-evidence-google.md#22-structured-output-json-mode--function-calling) | **Mirror Gemini's `responseSchema` (OpenAPI 3.0 subset) and the broader JSON Schema keywords** (`anyOf`, `$ref`, `minimum/maximum`, `additionalProperties`, `type:'null'`, `prefixItems`) in the public API. | M |

### 6.8 Routing / quality scoring

| Gap | Evidence | Recommendation (extension point) | Effort |
|---|---|---|---|
| **No first-party quality / routing metadata exposed.** Google's image-quality score is 8 dimensions; LocalDeepL's `core/routing.py` is mentioned in AGENTS.md but not deep. | [google §1.2](../track-md-evidence-google.md#12-enterprise-document-ocr), [oss1 §4.3](../track-md-evidence-oss1.md#43-architecture-from-the-source) | **Expose per-page quality scores** as part of the public API (currently `core/routing.py` exists per AGENTS.md but is not documented in the public API). 8 dimensions from Google's quality scoring are a sensible default. | M |
| **No fallback chain in `dense_mode`.** `dense_mode="auto"` switches when box count exceeds `dense_threshold`; no per-page *fallback* (try dense, then fall back to grounded VLM if low confidence). | [oss2 §1.6](../track-md-evidence-oss2.md#16-documented-strengths-and-limitations) | **Add a `fallback_to_grounded: bool` option** to `ProcessSettings`. When a dense-mode page's confidence is below threshold, automatically re-run with `grounded_backend`. | M |

### 6.9 Eval / regression harness

| Gap | Evidence | Recommendation (extension point) | Effort |
|---|---|---|---|
| **No public benchmark on common harnesses.** Marker's own benchmark table shows LocalDeepL is not there. The cross-track sister task `track-ocr-vision` is more about model choice; this gap is about a *harness* to measure end-to-end quality. | [oss2 §1.6](../track-md-evidence-oss2.md#16-documented-strengths-and-limitations), [`scripts/confidence_eval.py` and `scripts/confidence_image.py`](../../scripts/) | **Run Marker's own benchmark on LocalDeepL's outputs** for at least the `examples/dense.pdf` fixture. Add the harness to `scripts/`. | M |
| **No public Markitdown-vs-LocalDeepL comparison.** | [ms §1](../track-md-evidence-ms.md#1-markitdown-core-repo) | **Add a `scripts/markitdown_compare.py`** that runs Markitdown (with and without `az-doc-intel` extra) on the same fixtures and outputs a side-by-side diff. | S |

### 6.10 Schema of gaps (mapped to LocalDeepL extension points)

| Extension point | Gap | Recommendation | Effort |
|---|---|---|---|
| `document_processors` | Cross-page table merge, form extraction, audio/video transcription, long-document strategy | Add 4 new processor classes | M-L each |
| `aligner` | Add `pymupdf_layout` and `docling_parse` as alternatives to Surya | 2 new backends, one opt-in | M |
| `grounded_backend` | `maintain_format` per-page context threading (Zerox); `granite_docling` as a local VLM | 2 new options | S-M |
| `ocr_processor` | Fallback chain; cloud backends (Azure Read, Google OCR) | Pluggable list | M-L |
| `page_preprocessor` | Format-keyed dispatch; image-quality scoring | Refactor + extension | M |
| Output writers | `xlsx_writer`, `html_writer`, `jats_xml_writer`, `chunks_writer`; docx style-map DSL | 4 new writer classes | M-L |
| Public API (`ProcessSettings`) | `markdown_flavor`, `effort`, `cross_page_table_merge`, `fallback_to_grounded`, `long_document_strategy`, `style_map` | 6 new fields | S each |
| Pipeline orchestration | `localdeepl.plugin` entry-point, multi-stage threaded pipeline pattern from Docling | Larger refactor | L |
| IR | Round-trip test for `DocumentResult`; consider lossless variant | Test + feature | M |

---

## 7. References

All URLs were fetched 2026-06-14 unless otherwise noted. Companion files for
raw evidence: [track-md-evidence.md](track-md-evidence.md) and the five
per-vendor files in the same directory.

### 7.1 Microsoft

- [github.com/microsoft/markitdown](https://github.com/microsoft/markitdown) — README + `_markitdown.py` + `_pdf_converter.py` + `_doc_intel_converter.py` + `_cu_converter.py` + `packages/markitdown-ocr/README.md`
- [pypi.org/project/markitdown](https://pypi.org/project/markitdown/) — v0.1.6 / 2026-05-26
- [learn.microsoft.com/en-us/azure/ai-services/document-intelligence/](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/) — Doc Intel v4.0 GA
- [learn.microsoft.com/.../prebuilt/layout](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0) — `prebuilt-layout` reference
- [learn.microsoft.com/.../concept/markdown-elements](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept/markdown-elements?view=doc-intel-4.0.0) — Markdown schema
- [learn.microsoft.com/.../prebuilt/read](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read?view=doc-intel-4.0.0) — `prebuilt-read` + searchable PDF
- [azure.microsoft.com/en-us/pricing/details/document-intelligence/](https://azure.microsoft.com/en-us/pricing/details/document-intelligence/) — pricing
- [learn.microsoft.com/en-us/copilot/microsoft-365/microsoft-365-copilot-privacy](https://learn.microsoft.com/en-us/copilot/microsoft-365/microsoft-365-copilot-privacy) — Copilot privacy / architecture
- [github.com/microsoft/autogen](https://github.com/microsoft/autogen) — AutoGen team attribution
- [github.com/microsoft/markitdown/issues/296](https://github.com/microsoft/markitdown/issues/296), [/discussions/1361](https://github.com/microsoft/markitdown/discussions/1361), [/issues/1845](https://github.com/microsoft/microsoft/markitdown/issues/1845) — PDF limitations
- [github.com/BerriAI/litellm/issues/25687](https://github.com/BerriAI/litellm/issues/25687) — LiteLLM proxy flattening bug (surfaced as source conflict)

### 7.2 Google

- [cloud.google.com/document-ai/docs/form-parser](https://cloud.google.com/document-ai/docs/form-parser) — Form Parser
- [cloud.google.com/document-ai/docs/enterprise-document-ocr](https://cloud.google.com/document-ai/docs/enterprise-document-ocr) — Enterprise OCR
- [cloud.google.com/document-ai/docs/layout-parse-chunk](https://cloud.google.com/document-ai/docs/layout-parse-chunk) — Layout Parser / Gemini
- [cloud.google.com/document-ai/docs/processors-list](https://cloud.google.com/document-ai/docs/processors-list) — processor catalog
- [cloud.google.com/document-ai/docs/ce-schema-extraction](https://cloud.google.com/document-ai/docs/ce-schema-extraction) — Schema API / automated schema gen
- [cloud.google.com/document-ai/docs/output](https://cloud.google.com/document-ai/docs/output) — Document proto output
- [cloud.google.com/document-ai/docs/file-types](https://cloud.google.com/document-ai/docs/file-types) — supported file types
- [cloud.google.com/generative-ai-app-builder/pricing](https://cloud.google.com/generative-ai-app-builder/pricing) — pricing (Document AI)
- [firebase.google.com/docs/ai-logic/generate-structured-output](https://firebase.google.com/docs/ai-logic/generate-structured-output) — JSON mode / responseSchema
- [firebase.google.com/docs/ai-logic/analyze-documents](https://firebase.google.com/docs/ai-logic/analyze-documents) — Document Processing
- [blog.google/innovation-and-ai/technology/developers-tools/gemini-api-structured-outputs](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-api-structured-outputs) — Nov 5 2025 JSON Schema expansion
- [blog.google/innovation-and-ai/technology/developers-tools/gemini-api-new-file-limits](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-api-new-file-limits) — Jan 12 2026 file-limits update
- [docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/document-understanding](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/document-understanding) — Vertex AI doc understanding
- [support.google.com/notebooklm/answer/16215270](https://support.google.com/notebooklm/answer/16215270) — NotebookLM sources
- [blog.google/innovation-and-ai/products/notebooklm-audio-video-sources](https://blog.google/innovation-and-ai/products/notebooklm-audio-video-sources) — Sep 26 2024 NotebookLM blog
- [arxiv.org/html/2504.09720v2](https://arxiv.org/html/2504.09720v2) — Tufino, NotebookLM RAG architecture, July 2025
- [github.com/GoogleCloudPlatform/document-ai-samples](https://github.com/GoogleCloudPlatform/document-ai-samples) — 323★, Apache-2.0
- [github.com/google-gemini/cookbook](https://github.com/google-gemini/cookbook) — 17.4k★, Apache-2.0
- [arxiv.org/abs/2410.21169](https://arxiv.org/abs/2410.21169) — "Document Parsing Unveiled" survey

### 7.3 Adobe + Apple + other cloud adjacents

- [developer.adobe.com/document-services/apis/pdf-extract/](https://developer.adobe.com/document-services/apis/pdf-extract/) — PDF Extract API
- [developer.adobe.com/document-services/docs/overview/pdf-extract-api/howtos/pdf-to-markdown-api/](https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/howtos/pdf-to-markdown-api/) — PDF-to-Markdown
- [developer.adobe.com/document-services/docs/overview/pdf-services-api/](https://developer.adobe.com/document-services/docs/overview/pdf-services-api/) — PDF Services API
- [developer.adobe.com/document-services/pricing/main/](https://developer.adobe.com/document-services/pricing/main/) — pricing
- [developer.adobe.com/document-services/docs/overview/pdf-extract-api/dcserviceslicensing/](https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/dcserviceslicensing/) — DT metering
- [opensource.adobe.com/pdftools-sdk-docs/release/shared/extractJSONOutputSchema.json](https://opensource.adobe.com/pdftools-sdk-docs/release/shared/extractJSONOutputSchema.json) — open-sourced JSON Schema
- [github.com/adobe/pdfservices-python-sdk-samples](https://github.com/adobe/pdfservices-python-sdk-samples) — 163★, MIT
- [github.com/adobe/pdfservices-node-sdk-samples](https://github.com/adobe/pdfservices-node-sdk-samples) — 109★, MIT
- [github.com/adobe/PDFServices.NET.SDK.Samples](https://github.com/adobe/PDFServices.NET.SDK.Samples) — 47★, MIT
- [medium.com/adobetech/adobe-pdf-extract-api-output-demystified-ff69841c4ed3](https://medium.com/adobetech/adobe-pdf-extract-api-output-demystified-ff69841c4ed3) — Joel Geraci, 2021-06-18
- [developer.apple.com/documentation/vision/recognizing-text-in-images](https://developer.apple.com/documentation/vision/recognizing-text-in-images) — Vision `VNRecognizeTextRequest`
- [support.apple.com/en-gb/guide/shortcuts/welcome/9.0/ios/26](https://support.apple.com/en-gb/guide/shortcuts/welcome/9.0/ios/26) — Shortcuts User Guide (iOS 26)
- [support.apple.com/en-us/102223](https://support.apple.com/en-us/102223) — Apple Notes Markdown I/O, 2026-04-02
- [appleinsider.com/inside/ios-26/tips/how-to-import-and-export-markdown-with-apple-notes-in-ios-26](https://appleinsider.com/inside/ios-26/tips/how-to-import-and-export-markdown-with-apple-notes-in-ios-26) — AppleInsider, 2026-01-12
- [support.apple.com/guide/iphone/find-the-right-words-with-writing-tools-iph6f08da1d2/ios](https://support.apple.com/guide/iphone/find-the-right-words-with-writing-tools-iph6f08da1d2/ios) — Writing Tools
- [apple.com/os/?version=no-hero](https://www.apple.com/os/?version=no-hero) — macOS 27 "Golden Gate" preview
- [developer.box.com/guides/representations/text](https://developer.box.com/guides/representations/text) — Box text representations
- [next.ithome.com/archiver/860/180.htm](https://next.ithome.com/archiver/860/180.htm) — IT之家 iOS 26 Shortcuts + Apple Intelligence, 2025-06-12
- [www.macscripter.net/t/optical-character-recognition-ocr-script/74498/21](https://www.macscripter.net/t/optical-character-recognition-ocr-script/74498/21) — MacScripter OCR script, 2023

### 7.4 Open-source converters

- [github.com/jgm/pandoc](https://github.com/jgm/pandoc) — 44.8k★, GPL-2.0+, v3.10 / 2026-06-04
  - [`src/Text/Pandoc.hs:42-69`](src/Text/Pandoc.hs)
  - [`src/Text/Pandoc/Readers/`](src/Text/Pandoc/Readers/) (no PDF reader)
- [github.com/mwilliamson/python-mammoth](https://github.com/mwilliamson/python-mammoth) — 1.1k★, BSD-2-Clause
  - [`mammoth/__init__.py:1-42`](mammoth/__init__.py)
- [github.com/frostming/marko](https://github.com/frostming/marko) — 458★, MIT, v2.2.3 / 2026-05-28
  - [`marko/__init__.py:67-156`](marko/__init__.py)
  - [`marko/parser.py:13-95`](marko/parser.py)
- [github.com/docling-project/docling](https://github.com/docling-project/docling) — 61.5k★, MIT, v2.102.1 / 2026-06-12
  - [`docling/document_converter.py:53-89, 190-237, 355-378, 518-547`](docling/document_converter.py)
  - [`docling/backend/docling_parse_backend.py:1-37, 213-265`](docling/backend/docling_parse_backend.py)
  - [`docling/pipeline/standard_pdf_pipeline.py:393-435, 572-606, 763-823`](docling/pipeline/standard_pdf_pipeline.py)
  - [`pyproject.toml`](pyproject.toml)
- [github.com/Unstructured-IO/unstructured](https://github.com/Unstructured-IO/unstructured) — 14.9k★, Apache-2.0, v0.23.1 / 2026-06-11
  - [`unstructured/partition/auto.py:34-307`](unstructured/partition/auto.py)
  - [`unstructured/partition/pdf.py:74-740`](unstructured/partition/pdf.py)
  - [`pyproject.toml:5-176`](pyproject.toml)
- [github.com/datalab-to/marker](https://github.com/datalab-to/marker) — 36.1k★, GPL-3.0 + RAIL-M, v1.10.2 / 2026-01-31
  - [`marker/converters/pdf.py:101-184`](marker/converters/pdf.py)
  - [`marker/converters/__init__.py:13-39`](marker/converters/__init__.py)
  - [`marker/models.py`](marker/models.py)
  - [`marker/providers/registry.py:7-12, 41`](marker/providers/registry.py)
  - [`marker/schema/__init__.py:5-33`](marker/schema/__init__.py)
  - [`marker/extractors/__init__.py:11-39`](marker/extractors/__init__.py)
  - `MODEL_LICENSE` (Attachment A — $2M cap clause)
  - `pyproject.toml`
- [github.com/pdfminer/pdfminer.six](https://github.com/pdfminer/pdfminer.six) — 7.0k★, MIT, 20260107 / 2026-01-07
  - [`pdfminer/high_level.py:32-211`](pdfminer/high_level.py)
  - [`pdfminer/layout.py:52-535`](pdfminer/layout.py)
- [github.com/pymupdf/PyMuPDF4LLM](https://github.com/pymupdf/PyMuPDF4LLM) — 1.8k★, AGPL v3 OR commercial, v0.3.4 / 2026-02-14
  - [`pymupdf4llm/src/__init__.py:7-184`](pymupdf4llm/src/__init__.py)
  - [`pymupdf4llm/src/ocr/__init__.py`](pymupdf4llm/src/ocr/__init__.py)
  - `CHANGES.md` v0.2.0 (closed-source `pymupdf_layout` caveat)
- [github.com/microsoft/markitdown](https://github.com/microsoft/markitdown) — 153k★, MIT, v0.1.6 / 2026-05-26
  - [`packages/markitdown/src/markitdown/_markitdown.py:23-456`](packages/markitdown/src/markitdown/_markitdown.py)
  - [`packages/markitdown/src/markitdown/converters/_pdf_converter.py:101-405`](packages/markitdown/src/markitdown/converters/_pdf_converter.py)
  - [`packages/markitdown/src/markitdown/converters/_doc_intel_converter.py:104, 163-209`](packages/markitdown/src/markitdown/converters/_doc_intel_converter.py)
  - [`packages/markitdown/src/markitdown/converters/_cu_converter.py:280-332`](packages/markitdown/src/markitdown/converters/_cu_converter.py)
  - [`packages/markitdown-ocr/README.md`](packages/markitdown-ocr/README.md)
- [github.com/getomni-ai/zerox](https://github.com/getomni-ai/zerox) — 12.2k★, MIT, v0.1.06 / 2024-12-18
  - [`node-zerox/src/index.ts`](node-zerox/src/index.ts)
- [github.com/opendatalab/MinerU](https://github.com/opendatalab/MinerU) — 67.5k★, Apache-2.0-based, v3.3 / 2026-06-11
  - [`mineru/cli/client.py:128-227, 330-364, 404-451, 526-559, 570-650`](mineru/cli/client.py)
- [github.com/run-llama/llama_cloud_services](https://github.com/run-llama/llama_cloud_services) — 4.3k★, MIT (SDK), **DEPRECATED EOL 2026-05-01**
- [github.com/adobe/pdfservices-python-sdk-samples](https://github.com/adobe/pdfservices-python-sdk-samples) — 163★, MIT, v4.2.0 / 2025-07-11
- [github.com/adobe/pdfservices-node-sdk-samples](https://github.com/adobe/pdfservices-node-sdk-samples) — 109★, MIT, v4.1.0 / 2025-01-02
- [github.com/adobe/PDFServices.NET.SDK.Samples](https://github.com/adobe/PDFServices.NET.SDK.Samples) — 47★, MIT

### 7.5 LocalDeepL (the project this scout informs)

- [AGENTS.md](../../AGENTS.md) — top-level project map and extension points
- [`src/local_deepl/pipeline.py`](../../src/local_deepl/pipeline.py) — `OCRPipeline` facade
- [`src/local_deepl/core/workflows/hybrid.py`](../../src/local_deepl/core/workflows/hybrid.py) — `HybridEngine` (Surya + VLM + DP align)
- [`src/local_deepl/core/workflows/grounded.py`](../../src/local_deepl/core/workflows/grounded.py) — `GroundedEngine` (bbox-native VLM)
- [`src/local_deepl/core/aligner.py`](../../src/local_deepl/core/aligner.py) — `tqdm_patch.apply()` + `DetectionPredictor`
- [`src/local_deepl/core/ocr.py`](../../src/local_deepl/core/ocr.py) — LiteLLM OCR calls
- [`src/local_deepl/core/grounded.py`](../../src/local_deepl/core/grounded.py) — grounded backends
- [`src/local_deepl/core/processors.py`](../../src/local_deepl/core/processors.py) — `document_processors`
- [`src/local_deepl/core/preprocessing.py`](../../src/local_deepl/core/preprocessing.py) — `page_preprocessor`
- [`src/local_deepl/core/document.py`](../../src/local_deepl/core/document.py) — `DocumentResult` IR
- [`src/local_deepl/api/schemas/requests.py`](../../src/local_deepl/api/schemas/requests.py) — `ProcessSettings` + enums
- [`src/local_deepl/core/routing.py`](../../src/local_deepl/core/routing.py) — quality routing
- [`src/local_deepl/core/docx_writer.py`](../../src/local_deepl/core/docx_writer.py) — Markdown → docx
- [`scripts/confidence_eval.py`](../../scripts/confidence_eval.py) + [`scripts/confidence_image.py`](../../scripts/confidence_image.py) — eval harness

### 7.6 Companion evidence files (raw)

- [track-md-evidence.md](track-md-evidence.md) — consolidated evidence inventory
- [track-md-evidence-ms.md](track-md-evidence-ms.md) — Microsoft
- [track-md-evidence-google.md](track-md-evidence-google.md) — Google
- [track-md-evidence-adobe-apple.md](track-md-evidence-adobe-apple.md) — Adobe + Apple
- [track-md-evidence-oss1.md](track-md-evidence-oss1.md) — OSS first half
- [track-md-evidence-oss2.md](track-md-evidence-oss2.md) — OSS second half
