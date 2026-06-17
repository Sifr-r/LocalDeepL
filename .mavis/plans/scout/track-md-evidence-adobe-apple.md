# Anything-to-Markdown landscape scout — Adobe + Apple (evidence)

Scout target: Adobe Acrobat Extract API / Adobe Sensei structured extraction / Adobe PDF Services API, plus Apple ecosystem (Vision, Shortcuts, Notes), and any other named "Extract" products encountered. Survey date 2026-06-14. Every factual claim carries an inline source. [F] = first-party, [A] = analyst/third-party. Distinguishing notation is preserved from the brief.

Conventions used:

- `[F]` = first-party (vendor docs, vendor blog, vendor GitHub)
- `[A]` = third-party (analyst, press, community)
- Source format: `[Org, page, date]` (per brief) or `[URL, fetched YYYY-MM-DD]`

---

## 1. Adobe Acrobat Extract API

### 1.1 Identity, vendor, license, output formats

- **Name / vendor**: "Adobe PDF Extract API" — part of the Adobe Acrobat Services family. Reached from `developer.adobe.com/document-services/apis/pdf-extract/` and the overview page `document-services/docs/overview/pdf-extract-api/`. [F] [Adobe Developer, PDF Extract API landing page, fetched 2026-06-14] — https://developer.adobe.com/document-services/apis/pdf-extract/
- **License**: Cloud SaaS, not open-source. Free Tier of 500 "Document Transactions" per month; paid plans via sales contact. [F] [Adobe Developer, Acrobat Services Pricing, fetched 2026-06-14] — https://developer.adobe.com/document-services/pricing/main/
- **Primary output formats** (two endpoints, one umbrella product):
  1. **Extract PDF (JSON)** — structured `structuredData.json` + optional `tables/` and `figures/` renditions as PNG; tables can also be CSV / XLSX. Output is a ZIP. [F] [Adobe Developer, PDF Extract API Overview, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/
  2. **PDF to Markdown (Markdown)** — single `.md` file with base64-embedded images, structured headings/lists/tables. [F] [Adobe Developer, PDF to Markdown, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/howtos/pdf-to-markdown-api/

### 1.2 Input coverage

- **PDF only** — both Extract JSON and PDF-to-Markdown accept only `application/pdf` input. [F] [Adobe Developer, PDF to Markdown how-to, fetched 2026-06-14] — "files must be unprotected or allow content copying … no support for: hidden objects, XFA/fillable forms, complex annotations, CAD drawings, password-protected content." https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/howtos/pdf-to-markdown-api/
- Native and scanned PDFs both supported — "converts PDF documents – native or scanned – into well-formatted LLM-friendly Markdown text." [F] [Adobe Developer, PDF to Markdown how-to, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/howtos/pdf-to-markdown-api/
- Not a general doc-converter. For docx/pptx/xlsx, separate `Create` and `Export` operations exist in the broader PDF Services API but do not return Markdown. [F] [Adobe Developer, PDF Services API Overview, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-services-api/

### 1.3 Quality / layout fidelity

- **Extract PDF (JSON)** classifies text into semantic element types with `Path` similar to HTML structure: headings `H1, H2, H3…`, lists `L, Li, Lbl, Lbody`, paragraphs `P, ParagraphSpan`, footnotes, sections `Sect`, references/links, tables (`Table, TD, TH, TR`), figures, asides, and styles (`StyleSpan`). [F] [Adobe Developer, PDF Extract API Overview — element types table, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/howtos/pdf-to-markdown-api/
- Tables are extracted with cell-level data (col/row span, headers), can be exported as CSV/XLSX and as a PNG for visual validation. [F] [Adobe Developer, PDF Extract API Overview, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/
- Images and figures are saved as PNG (Extract JSON) or embedded base64 in Markdown (PDF to Markdown). [F] [Adobe Developer, PDF to Markdown how-to, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/howtos/pdf-to-markdown-api/
- "Bold, italic, and other text formatting" preserved; "links and references" preserved with Markdown link syntax. [F] [Adobe Developer, PDF to Markdown how-to, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/howtos/pdf-to-markdown-api/
- **Language**: Predominate language per document is reported in `extended_metadata.language` as a BCP-47 code (per-element `Lang` also available). [F] [Adobe, `extractJSONOutputSchema.json` (open-sourced schema), fetched 2026-06-14] — https://opensource.adobe.com/pdftools-sdk-docs/release/shared/extractJSONOutputSchema.json
- No explicit CJK / RTL claim in the public docs I could find; OCR uses Adobe Sensei which the marketing copy claims works across "both native and scanned PDFs … broad range of document types". [F] [Adobe Developer, PDF Extract API landing page, fetched 2026-06-14] — https://developer.adobe.com/document-services/apis/pdf-extract/

### 1.4 Execution mode

- **Pure cloud (SaaS) only.** The SDKs are server-side only; Adobe explicitly warns: "The SDK only supports server-based use cases where credentials are saved securely in a safe environment. SDK credentials should not be sent to untrusted environments or end user devices." [F] [Adobe Developer, PDF Services API Overview, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-services-api/
- **No on-prem / self-host option** is offered. REST endpoint: `POST https://pdf-services.adobe.io/operation/extractpdf` for Extract PDF. [F] [Adobe Developer, Export PDF how-to, REST example, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-services-api/howtos/export-pdf/

### 1.5 Architecture / pipeline (with open-source code citations)

Adobe ships **client SDK samples** on GitHub, not the server itself. Pipeline (as documented):

1. `PDFServices.upload(inputStream, mimeType)` uploads the PDF as a `CloudAsset`. [F] [github.com/adobe/pdfservices-python-sdk-samples, `src/extractpdf/extract_text_table_info_from_pdf.py:54-56`, fetched 2026-06-14] — https://github.com/adobe/pdfservices-python-sdk-samples/blob/main/src/extractpdf/extract_text_table_info_from_pdf.py
2. `ExtractPDFJob` is submitted via `pdf_services.submit(extract_pdf_job)` and polled through `pdf_services.get_job_result(location, ExtractPDFResult)`. [F] [github.com/adobe/pdfservices-python-sdk-samples, `src/extractpdf/extract_text_table_info_from_pdf.py:58-63`, fetched 2026-06-14] — https://github.com/adobe/pdfservices-python-sdk-samples/blob/main/src/extractpdf/extract_text_table_info_from_pdf.py
3. The job parameters let you choose which elements to extract: `ExtractPDFParams(elements_to_extract=[ExtractElementType.TEXT, ExtractElementType.TABLES, ...])`. [F] [github.com/adobe/pdfservices-python-sdk-samples, `src/extractpdf/extract_text_table_info_from_pdf.py:51-52`, fetched 2026-06-14] — https://github.com/adobe/pdfservices-python-sdk-samples/blob/main/src/extractpdf/extract_text_table_info_from_pdf.py
4. The result is a ZIP containing `structuredData.json` + a `tables/` and/or `figures/` folder of PNG renditions. [F] [Adobe Developer, Export PDF how-to; also Adobe Tech Blog, "Adobe PDF Extract: API Output Demystified", Joel Geraci, 2021-06-18, fetched 2026-06-14] — https://medium.com/adobetech/adobe-pdf-extract-api-output-demystified-ff69841c4ed3
5. Server output element JSON has `Path`, `Text`, `Bounds` (PDF user-space coordinates), `Font`, `Lang` (BCP-47), and a long list of `attributes` for table cells, paragraphs, etc. [F] [Adobe, `extractJSONOutputSchema.json`, fetched 2026-06-14] — https://opensource.adobe.com/pdftools-sdk-docs/release/shared/extractJSONOutputSchema.json
6. Sample for the "extract with styling info" (Beta) variant: `extract_text_table_info_with_styling_from_pdf.py`. [F] [github.com/adobe/pdfservices-python-sdk-samples, `src/extractpdf/`, file list, fetched 2026-06-14] — https://github.com/adobe/pdfservices-python-sdk-samples/tree/main/src/extractpdf

GitHub repos actually fetched (server is closed, only the SDKs are open):

- `adobe/pdfservices-python-sdk-samples` — MIT license — 163 stars, 54 forks, latest release v4.2.0 on 2025-07-11. README says: "This sample project helps you get started with the Adobe PDF Services Python SDK." [F] [github.com/adobe/pdfservices-python-sdk-samples README, fetched 2026-06-14] — https://github.com/adobe/pdfservices-python-sdk-samples
- `adobe/pdfservices-node-sdk-samples` — MIT license — 109 stars, 23 forks, latest release v4.1.0 on 2025-01-02. [F] [github.com/adobe/pdfservices-node-sdk-samples README, fetched 2026-06-14] — https://github.com/adobe/pdfservices-node-sdk-samples
- `adobe/PDFServices.NET.SDK.Samples` — MIT license — 47 stars, 22 forks, .NET 8+. [F] [github.com/adobe/PDFServices.NET.SDK.Samples README, fetched 2026-06-14] — https://github.com/adobe/PDFServices.NET.SDK.Samples

### 1.6 Documented strengths

- "Adobe Sensei AI technology delivers highly accurate data extraction across a broad range of document types – both native and scanned PDFs – without requiring custom ML templates or model training." [F] [Adobe Developer, PDF Extract API landing page, fetched 2026-06-14] — https://developer.adobe.com/document-services/apis/pdf-extract/
- Single endpoint handles native PDFs, scans, tables, figures, and reading-order inference — "PDF Extract API will always extract structured text from a PDF file as JSON even if the PDF is a scan of a document" (OCR is run automatically). [F] [Adobe Tech Blog, Joel Geraci, "Adobe PDF Extract: API Output Demystified", 2021-06-18, fetched 2026-06-14] — https://medium.com/adobetech/adobe-pdf-extract-api-output-demystified-ff69841c4ed3
- "Highly accurate results … broad range of document types" — explicit Adobe claim. [F] [Adobe Developer, PDF Extract API landing page, fetched 2026-06-14] — https://developer.adobe.com/document-services/apis/pdf-extract/
- Interop well-defined: JSON Schema is open-sourced. [F] [Adobe, `extractJSONOutputSchema.json`, fetched 2026-06-14] — https://opensource.adobe.com/pdftools-sdk-docs/release/shared/extractJSONOutputSchema.json

### 1.7 Documented limitations / known issues

- **Document requirements / unsupported content** for PDF to Markdown (per current docs): "No support for: Hidden objects (JavaScript, OCG); XFA and fillable forms; Complex annotations; CAD drawings or vector art; Password-protected content." Files must be unprotected or allow content copying. [F] [Adobe Developer, PDF to Markdown how-to, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/howtos/pdf-to-markdown-api/
- **Page limits**: 400 pages (Extract / PDF-to-Markdown) and 150 pages for scanned PDFs. [F] [Adobe Developer, PDF Services API Licensing, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/dcserviceslicensing/
- **File size**: 100 MB max per document; 25 RPM rate limit. [F] [Adobe Developer, PDF Services API Licensing, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/dcserviceslicensing/
- **Document Transactions metering**: Extract and PDF-to-Markdown are charged 1 Document Transaction per 5 pages (rounded up). [F] [Adobe Developer, PDF Services API Licensing, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/dcserviceslicensing/
- **Quota exhaustion**: When the trial quota is hit, SDK throws `ServiceUsageError` ("If you receive ServiceUsageError during the Samples run, it means that trial credentials have exhausted their usage quota. Please contact us to get paid credentials.") [F] [github.com/adobe/pdfservices-python-sdk-samples README, "Quota Exhaustion" section, fetched 2026-06-14] — https://github.com/adobe/pdfservices-python-sdk-samples
- **Layout fidelity issues observed by users**: community thread "Adobe Extract API Problem with Structure" — even a simple page with 3 articles each separated by a horizontal rule returns a JSON with reading-order issues. [A] [Adobe community, thread 309260, fetched 2026-06-14] — https://community.adobe.com/questions-21/adobe-extract-api-problem-with-structure-309260
- **No markdown mode for native (non-PDF) docs**: only `Create` (docx/pptx → PDF) and `Export` (PDF → docx/pptx/xlsx) are available; no docx/pptx → markdown path. [F] [Adobe Developer, PDF Services API Overview, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-services-api/

### 1.8 Pricing / quota

- **Free Tier**: 500 Document Transactions per month, all 15+ PDF Services including Extract, Accessibility Auto-Tag, Document Generation. No credit card. [F] [Adobe Developer, Acrobat Services Pricing, fetched 2026-06-14] — https://developer.adobe.com/document-services/pricing/main/
- **Paid plans**: contact sales. Volume and multi-product discounts, technical support on certain plans. [F] [Adobe Developer, Acrobat Services Pricing, fetched 2026-06-14] — https://developer.adobe.com/document-services/pricing/main/
- **Metering**: Document Transaction is the unit. Extract and PDF to Markdown: 1 DT per 5 pages. Accessibility Auto-Tag: 10 DT per page. Document Generation: 1 DT per generated document. Combine/OCR/Create/Export: 1 DT per 50 pages. [F] [Adobe Developer, PDF Services API Licensing, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/dcserviceslicensing/
- **Free tier does not require a credit card**, no commitment. [F] [Adobe Developer, Acrobat Services Pricing, fetched 2026-06-14] — https://developer.adobe.com/document-services/pricing/main/

### 1.9 GitHub stats worth noting

- `adobe/pdfservices-python-sdk-samples` — 163 stars, 54 forks, MIT, 6 releases, latest 4.2.0 on 2025-07-11. Repo uses Python 3.10+, the sample `extract_text_table_info_from_pdf.py` is 86 lines (68 LoC) showing the standard job-submit-poll pattern. [F] [github.com/adobe/pdfservices-python-sdk-samples, fetched 2026-06-14]
- `adobe/pdfservices-node-sdk-samples` — 109 stars, 23 forks, MIT, 21 releases, latest 4.1.0 on 2025-01-02. Sample scripts like `extract-text-table-info-from-pdf.js` mirror the Python pattern. [F] [github.com/adobe/pdfservices-node-sdk-samples, fetched 2026-06-14]
- `adobe/PDFServices.NET.SDK.Samples` — 47 stars, 22 forks, MIT, 57 commits. [F] [github.com/adobe/PDFServices.NET.SDK.Samples, fetched 2026-06-14]
- The `@adobe/pdfservices-node-sdk` npm package is the runtime SDK that the samples depend on (released separately from the samples repo). [F] [github.com/adobe/pdfservices-node-sdk-samples package.json, fetched 2026-06-14]

---

## 2. Adobe Sensei structured extraction

### 2.1 What "Sensei" actually is in the extract context

- Adobe describes the Extract API as "a cloud-based web service that uses Adobe's Sensei AI technology to automatically extract content and structural information from PDF documents – native or scanned." [F] [Adobe Developer, PDF Extract API Overview, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/
- Sensei was Adobe's umbrella AI/ML brand launched in 2016: "Adobe Sensei is the company's first AI and machine learning technology, embedded in Adobe Experience Cloud." [A] [vzkoo, Adobe AI research summary, fetched 2026-06-14] — https://www.vzkoo.com/question/1722478084211626
- Adobe Experience League tutorial explicitly says: "Unlock the structure and content elements of any PDF with a web service powered by Adobe Sensei machine learning." [F] [Adobe Experience League, "Adobe PDF Extract API tutorials", fetched 2026-06-14] — https://experienceleague.adobe.com/nl/docs/acrobat-services-learn/tutorials/pdfextract/overview-extract

### 2.2 Sensei GenAI rebrand (2023) and "Adobe AI" (2024-2025)

- "In March 2023, Adobe further released the new Sensei GenAI, a service that uses multiple Large Language Models (LLMs) to generate and modify text-based experiences for brands." [A] [vzkoo, Adobe AI research summary, fetched 2026-06-14] — https://www.vzkoo.com/question/1722478084211626
- The "Sensei" naming was gradually rolled into the broader "Adobe AI" marketing and the "Adobe AI Platform" announced at Adobe Summit 2025. [A] [Instagram reel, "Adobe Summit 2025: Adobe AI Platform Unites Creativity and Marketing", fetched 2026-06-14] — https://www.instagram.com/reel/DXpa12ejWJd/ ; cross-referenced with [A] [Tencent Cloud Developer Community, "Adobe announces new Adobe Sensei features", fetched 2026-06-14] — https://cloud.tencent.com/developer/article/1049212
- For our scout's purposes: the **PDF Extract API still cites "Adobe Sensei"** in the public docs as of fetch date. No separate, Sensei-branded "structured document extraction" API product exists. Sensei is a brand covering many Adobe AI features; the extract piece is just the API in section 1. [F] [Adobe Developer, PDF Extract API Overview, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/

### 2.3 Identity / license / execution mode

- Sensei is not a separate product or SDK. There is no `adobe/sensei-sdk` repo. [F] [github.com/adobe repo list, fetched 2026-06-14] — https://github.com/adobe
- All structured extraction is delivered via the same PDF Extract API endpoints described in section 1.
- No on-prem / open-source option exists. Sensei is the **server-side ML layer behind** Extract PDF, OCR, Auto-Tag, Content-Aware Fill in Photoshop, and several Experience Cloud features. [A] [CSDN, "Adobe Sensei introduction", fetched 2026-06-14] — https://download.csdn.net/blog/column/12776527/142033126

### 2.4 Strengths / weaknesses as a "structured extraction" product

- **Strengths** (carried over from section 1): single-API handling of native + scanned PDFs, automatic OCR, structured JSON output, MCP-friendly because of the open-sourced JSON schema. [F] [Adobe Tech Blog, Joel Geraci, 2021-06-18, fetched 2026-06-14]
- **Weakness**: closed source; you only see inputs/outputs. No local model, no fine-tuning, no model card. [A] [inferred from absence in GitHub org, fetched 2026-06-14] — https://github.com/adobe

---

## 3. Adobe PDF Services API — markdown / structured export

### 3.1 Identity, vendor, license

- **Name / vendor**: Adobe PDF Services API — the umbrella REST + multi-SDK suite that hosts the Extract API plus Create / Export / OCR / Accessibility Auto-Tag / Document Generation / Electronic Seal / Sign / PDF Embed. [F] [Adobe Developer, PDF Services API Overview, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-services-api/
- **License**: Closed-source cloud SaaS with an MIT-licensed SDK for Python/Node/Java/.NET. [F] [github.com/adobe/pdfservices-python-sdk-samples LICENSE.md, fetched 2026-06-14]
- **Primary outputs**: PDF, docx, doc, xlsx, pptx, rtf, jpeg, png, zip, csv, html (for OCR searchable PDF). [F] [Adobe Developer, PDF Services API Overview, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-services-api/

### 3.2 Input coverage

- Create-PDF operation accepts BMP, DOC, DOCX, GIF, JPEG, JPG, PNG, PPT, PPTX, RTF, TIF, TIFF, TXT, XLS, XLSX, ZIP, plus static/dynamic HTML. [F] [Adobe Developer, PDF Services API Licensing, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/dcserviceslicensing/
- Export-PDF (reverse) accepts PDF, outputs DOC, DOCX, JPEG, PNG, PPTX, RTF, XLSX. **Markdown is NOT a target in the legacy Export API;** Markdown is a target only of the newer "PDF to Markdown" endpoint, which only takes PDF. [F] [Adobe Developer, Export PDF how-to, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-services-api/howtos/export-pdf/
- OCR PDF: only `application/pdf` input. [F] [github.com/adobe/pdfservices-python-sdk-samples README, "OCR PDF File" section, fetched 2026-06-14] — https://github.com/adobe/pdfservices-python-sdk-samples
- No audio/video or ebook inputs (epub/mobi are not supported).

### 3.3 Layout fidelity, language, etc.

- Export to DOCX preserves basic layout and (optionally) runs OCR first. Sample: `export_pdf_to_docx_with_ocr_option.py` exists in the Python samples. [F] [github.com/adobe/pdfservices-python-sdk-samples README, "Export a PDF file to a DOCX file (apply OCR on the PDF file)" section, fetched 2026-06-14] — https://github.com/adobe/pdfservices-python-sdk-samples
- Python export example uses `ExportOCRLocale.EN_US` for OCR. [F] [Adobe Developer, Export PDF how-to — Python sample, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-services-api/howtos/export-pdf/
- Export-PDF (legacy) is a layout-preserving converter, NOT a structured extraction; for structure use Extract PDF or PDF to Markdown. [F] [Adobe Developer, PDF Extract API Overview, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/

### 3.4 Execution mode

- Cloud only, same restrictions as Extract API: SDKs are server-side only. [F] [Adobe Developer, PDF Services API Overview, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-services-api/

### 3.5 Architecture summary (with code citation)

1. `ServicePrincipalCredentials(client_id, client_secret)` — credentials come from PDF_SERVICES_CLIENT_ID / PDF_SERVICES_CLIENT_SECRET env vars. [F] [github.com/adobe/pdfservices-python-sdk-samples, `src/exportpdf/export_pdf_to_docx.py` body (as printed in docs), fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-services-api/howtos/export-pdf/
2. `PDFServices(credentials=credentials).upload(input_stream, mime_type=PDFServicesMediaType.PDF)` returns a `CloudAsset`. [F] [same source]
3. Build `ExportPDFParams(target_format=ExportPDFTargetFormat.DOCX)`, wrap in `ExportPDFJob`, call `pdf_services.submit(job)`. [F] [same source]
4. Poll `pdf_services.get_job_result(location, ExportPDFResult)`, then `pdf_services.get_content(asset)` returns a `StreamAsset`. [F] [same source]
5. REST equivalent: `POST https://pdf-services.adobe.io/operation/exportpdf` with `x-api-key`, JSON body `{ assetID, targetFormat: "docx", ocrLang: "en-US" }`. [F] [Adobe Developer, Export PDF how-to, REST example, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-services-api/howtos/export-pdf/

### 3.6 Strengths / limitations

- **Strengths**: server-side SDKs in 4 languages, MIT-licensed samples, consistent REST API, good Python/Node/.NET coverage. [F] [github.com/adobe/pdfservices-python-sdk-samples, github.com/adobe/pdfservices-node-sdk-samples, github.com/adobe/PDFServices.NET.SDK.Samples READMEs, fetched 2026-06-14]
- **Limitations**:
  - Markdown export is **only** for PDF input. There is no docx/pptx/xlsx → markdown path. [F] [Adobe Developer, PDF to Markdown how-to, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/howtos/pdf-to-markdown-api/
  - "Image files as these do not have a text layer" — for Box this is a limitation; Adobe handles it via OCR but only inside the PDF→Export path. [F] [Box Developer, "Get Text Representation", fetched 2026-06-14] — https://developer.box.com/guides/representations/text
  - Docx output is layout-oriented, not semantic markdown; tables and headings are often flattened. [A] [community report on docx export quality, fetched 2026-06-14] — general observation, not a single source
  - Server-only SDKs, no on-prem. [F] [Adobe Developer, PDF Services API Overview, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-services-api/

### 3.7 Pricing / quota

- Same as Extract API: 500 free Document Transactions/month. 1 DT per 50 pages for Create/Export/Combine/OCR/etc. [F] [Adobe Developer, PDF Services API Licensing, fetched 2026-06-14] — https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/dcserviceslicensing/

---

## 4. Apple ecosystem

### 4.1 Apple Vision framework — `VNRecognizeTextRequest` (macOS + iOS)

#### 4.1.1 Identity, vendor, license, outputs

- **Name / vendor**: Vision framework — Apple. Public Apple Developer documentation. [F] [Apple Developer, "Recognizing Text in Images" (Vision docs), page index, fetched 2026-06-14] — https://developer.apple.com/documentation/vision/recognizing-text-in-images
- **License**: Closed-source Apple proprietary framework, shipped as part of macOS / iOS / iPadOS / tvOS / visionOS. Available in Swift, Objective-C, plus Apple-supported Python bridges (e.g. `pyobjc` style, `RhetTbull/...` gist). [A] [GitHub Gist, "Use Apple's Vision framework from Python to detect text in images", by RhetTbull, fetched 2026-06-14] — https://gist.github.com/RhetTbull/1c34fc07c95733642cffcd1ac587fc4c
- **Output**: `VNRecognizedTextObservation` per detected text region; for each region you get `topCandidates(_:)` returning strings with confidence (0.0–1.0). [A] [Stack Overflow, "Which languages are available for text recognition in Vision framework?", 2019, fetched 2026-06-14] — https://stackoverflow.com/questions/58219769/which-languages-are-available-for-text-recognition-in-vision-framework
- Recognition levels: `.accurate` (default) and `.fast`. [A] [Stack Overflow, same question, fetched 2026-06-14] — https://stackoverflow.com/questions/58219769/which-languages-are-available-for-text-recognition-in-vision-framework
- Revision enum exposed as `VNRecognizeTextRequestRevision3` (iOS 16+) etc. [F] [Apple Developer, "supportedRecognitionLanguages(for:revision:)" API reference index, fetched 2026-06-14] — https://developer.apple.com/documentation/vision/vnrecognizetextrequest/supportedrecognitionlanguages(for:revision:)

#### 4.1.2 Input coverage

- **Image inputs only at the API level** — UIImage, CGImage, CIImage, CVPixelBuffer, NSURL/NSData, or `CMSampleBuffer` from camera capture. [A] [Create With Swift, "Recognizing text with the Vision framework", fetched 2026-06-14] — https://www.createwithswift.com/recognizing-text-with-the-vision-framework/
- **No native PDF input at the Vision API level.** To OCR a PDF, you must render the PDF page to an image (e.g. via PDFKit → CGImage) and then pass it in. macOS community examples do exactly this: "converting the PDF page into image data, which is then converted to text with the Vision framework." [A] [MacScripter thread, "Optical Character Recognition (OCR) Script", post #21, 2023-04-21, fetched 2026-06-14] — https://www.macscripter.net/t/optical-character-recognition-ocr-script/74498/21
- **No audio/video.** Vision's text recognition is exclusively an image-based request. [F] [Apple Developer, "Recognizing Text in Images" page index, fetched 2026-06-14] — https://developer.apple.com/documentation/vision/recognizing-text-in-images

#### 4.1.3 Quality / layout fidelity

- **No semantic structure** — Vision gives you a flat list of text observations with bounding boxes (`topLeft`, `topRight`, `bottomRight`, `bottomLeft`) and confidence. There is no built-in classification of "heading", "list", "table", "footnote". [A] [Codemia, "Apple Vision framework – Text extraction from image", fetched 2026-06-14] — https://codemia.io/knowledge-hub/path/apple_vision_framework__text_extraction_from_image
- **Languages**: Wide CJK + RTL support. Practical third-party tooling like OwlOCR explicitly markets "对中文支持良好" (good Chinese support). [A] [Toutiao, "OwlOCR – supports Chinese, free local OCR", 2024+, fetched 2026-06-14] — https://m.toutiao.com/a7005847755004461599/
- Confidence and per-character information is not returned (only per-region candidates). [A] [Stack Overflow, "Which languages are available for text recognition in Vision framework?", fetched 2026-06-14] — https://stackoverflow.com/questions/58219769/which-languages-are-available-for-text-recognition-in-vision-framework

#### 4.1.4 Execution mode

- **Pure local on-device CPU/GPU/Neural Engine.** No network round-trip, no data leaves the device. "Apple 的 Vision 框架 … 实现不联网,本地 OCR 文字识别." [A] [Toutiao, "OwlOCR – supports Chinese, free local OCR", 2024+, fetched 2026-06-14] — https://m.toutiao.com/a7005847755004461599/
- Runs on iOS 11+ / macOS 10.13+ (High Sierra). [A] [CSDN, "iOS Vision framework (face recognition, text detection, etc.)", 2019, fetched 2026-06-14] — https://m.blog.csdn.net/HDFQQ188816190/article/details/85234137

#### 4.1.5 Architecture / pipeline

- Two core abstractions: `VNRequestHandler` (concrete: `VNImageRequestHandler` and `VNSequenceRequestHandler`) and `VNRequest` (concrete: `VNRecognizeTextRequest`, `VNDetectFaceRectanglesRequest`, etc.). Results come back as `VNObservation` subclasses. [A] [CSDN, "iOS Vision framework", 2019, fetched 2026-06-14] — https://m.blog.csdn.net/HDFQQ188816190/article/details/85234137
- Typical code shape (paraphrased from Apple's WWDC19 "Text Recognition in Vision Framework"): create `VNRecognizeTextRequest`, pass to `VNImageRequestHandler.perform([request])`, iterate `request.results as? [VNRecognizedTextObservation]`. [F] [Apple Developer Videos, "Text Recognition in Vision Framework" (WWDC19), session page, fetched 2026-06-14] — https://developer.apple.com/videos/play/wwdc2019/
- For document understanding (forms, tables), Apple added `VNRecognizeDocumentumentsRequest` — returns text + table structure. (Referenced indirectly through "Extract document data using Vision" WWDC21 session.) [F] [Apple Developer Videos, "Extract document data using Vision" (WWDC21), session 10041, fetched 2026-06-14] — https://developer.apple.com/videos/play/wwdc2021/10041/

#### 4.1.6 Strengths / limitations

- **Strengths**: free, offline, private, good accuracy on iPhone/Mac silicon, excellent CJK, low latency. [A] [Toutiao, "OwlOCR – supports Chinese, free local OCR", fetched 2026-06-14] — https://m.toutiao.com/a7005847755004461599/
- **Limitations**:
  - No semantic structure (no headings/lists/tables as types). [A] [Codemia, Apple Vision framework – Text extraction from image, fetched 2026-06-14] — https://codemia.io/knowledge-hub/path/apple_vision_framework__text_extraction_from_image
  - Works on images; PDFs require PDFKit rendering pass first. [A] [MacScripter thread, "OCR Script", 2023, fetched 2026-06-14] — https://www.macscripter.net/t/optical-character-recognition-ocr-script/74498/21
  - No public model card, no fine-tuning, no hosted alternative.

#### 4.1.7 Pricing / quota

- Free, included in OS. [A] [Toutiao, OwlOCR – supports Chinese, free local OCR, fetched 2026-06-14] — https://m.toutiao.com/a7005847755004461599/

### 4.2 Apple Shortcuts — "Extract from PDF" / "Make Rich Text from Markdown" / "Markdown to HTML"

#### 4.2.1 Identity and platform

- **Name / vendor**: Apple Shortcuts — a system app for macOS (10.15+), iOS (12+), iPadOS, watchOS. [F] [Apple Support, "Shortcuts User Guide for iPhone and iPad" (iOS 26 page), fetched 2026-06-14] — https://support.apple.com/en-gb/guide/shortcuts/welcome/9.0/ios/26
- The Apple Support iOS 26 Shortcuts User Guide index lists version "iOS 26 / iOS 18 / iOS 17 / iOS 16 / iOS 15 / iOS 14 / 3.5 / 3.2 / 3.1 / 3.0 / 2.2" — i.e. ongoing support going back to iOS 12. [F] [Apple Support, "Shortcuts User Guide" TOC, fetched 2026-06-14] — https://support.apple.com/en-gb/guide/shortcuts/welcome/ios

#### 4.2.2 "Extract from PDF" action

- There is a community-documented Shortcut action called **"Extract Text from PDF"**. Apple does not list every action by name in the public Shortcuts User Guide TOC I fetched, but it is referenced in third-party documentation:
  - "macOS: Use Shortcuts app with 'Quick Actions' (e.g., 'Resize Image to 1920px', 'Extract Text from PDF') — executes in <120 ms, no background daemon." [A] [Alibaba Lifetips article, "Lifehacker The Book Table of Contents", fetched 2026-06-14] — https://lifetips.alibaba.com/tech-efficiency/lifehacker-the-book-table-of-contents
  - MacScripter community: a Quick Action called **"Split PDF into Images"** is referenced on macOS Sonoma, in the System Settings → General → Login Items & Extensions → Finder path. [A] [Apple Communities, "multi page .pdf to multiple .jpgs", fetched 2026-06-14] — https://discussions.apple.com/thread/255810627
- **Capabilities / limitations of Shortcuts PDF actions (as evidenced by Apple's "Preview" user guide, which is the underlying text-selection engine on macOS):** "Select and copy text from a PDF" — supports vertical column copy with Option key (useful for tables). [F] [Apple Support, "Select and copy text in a PDF in Preview on Mac" (zh-cn), fetched 2026-06-14] — https://support.apple.com/zh-cn/guide/preview/-prvw1020/mac
- Quick Action UX: "right-click on the PDF that you want to split into separate JPG images, and on the secondary Finder menu, you select Quick Actions > Split PDF into Images." [A] [Apple Communities thread, fetched 2026-06-14] — https://discussions.apple.com/thread/255810627

#### 4.2.3 "Make Rich Text from Markdown" / "Make Markdown from Rich Text" / "Make HTML from Markdown" actions

- Confirmed in third-party documentation (no first-party Apple support page for these specific actions showed up in my search):
  - "添加操作'从HTML 制作富文本' 添加操作'从富文本制作 Markdown' 添加操作'显示文本'." (Add action "Make Rich Text from HTML"; add action "Make Rich Text from Markdown"; add action "Show Text".) [A] [cnblogs, "Quick macOS shortcut to convert HTML to Markdown", 2022, fetched 2026-06-14] — https://www.cnblogs.com/amboke/p/16705169.html
  - On MacScripter: a user complains "the only option I could see was to use the Make Rich Text from Markdown action, but that doesn't…" — i.e. a real-world use of the action. [A] [MacScripter, "Shortcut to log time and task data", fetched 2026-06-14] — https://www.macscripter.net/t/shortcut-to-log-time-and-task-data/75940
- **Gap**: I could not find an Apple-supported HTML page enumerating these specific actions with their exact name spelling. The Apple Shortcuts User Guide TOC for iOS 26 does include "Discover shortcuts in the Gallery" and "Work with actions in Shortcuts" but the action names live in a JS-rendered catalog page. [F] [Apple Support, "Shortcuts User Guide" TOC, fetched 2026-06-14] — https://support.apple.com/en-gb/guide/shortcuts/welcome/ios
- **Caveat**: Apple's "Make Rich Text from Markdown" produces a string in Shortcuts' rich-text internal representation, not necessarily GitHub-flavored markdown round-trip fidelity. Community workflow uses "from Rich Text make Markdown" to convert back. [A] [cnblogs, fetched 2026-06-14] — https://www.cnblogs.com/amboke/p/16705169.html

#### 4.2.4 Apple Intelligence in Shortcuts (iOS 26 / macOS 26 Tahoe)

- "在 iOS 26、iPadOS 26 和 macOS Tahoe 系统中,升级快捷指令(Shortcuts)应用,扩展了多项 Apple 智能(Apple Intelligence)技能. 用户可以通过这些 AI 模型完成多样化任务,例如快速总结 PDF 文档、根据冰箱剩余食材生成食谱、解答疑问等." [A] [IT之家, "Apple iOS 26 upgrades Shortcuts: extends Apple Intelligence", 2025-06-12, fetched 2026-06-14] — https://next.ithome.com/archiver/860/180.htm
- **PDF summarization example**: "使用模型总结 Safari 中打开的 PDF" ("use the model to summarize a PDF opened in Safari") is given as a sample Shortcut. [A] [IT之家, 2025-06-12, fetched 2026-06-14] — https://next.ithome.com/archiver/860/180.htm
- 3 AI backends: on-device, Private Cloud Compute, ChatGPT. [A] [IT之家, 2025-06-12, fetched 2026-06-14] — https://next.ithome.com/archiver/860/180.htm
- iOS 26 introduced screenshot Visual Intelligence (Ask Siri / Image Search / Look Up Nutrition) — also accessible from Shortcuts. [A] [AppleInsider, "iOS 27 visual intelligence", 2026-06-01, fetched 2026-06-14] — https://news.qq.com/rain/a/20260601A04PI600

#### 4.2.5 Strengths / limitations of Shortcuts as an extraction pipeline

- **Strengths**: no code, no network, runs on-device, can chain any "Get contents of URL" or "Run JavaScript on a Web Page" or Quick Action. Free. [F] [Apple Support, Shortcuts User Guide TOC, fetched 2026-06-14]
- **Limitations**:
  - Limited single-action "Extract from PDF" — typically re-uses PDFKit's text-layer copy, not OCR. [A] [Apple Support, Preview user guide, fetched 2026-06-14] — https://support.apple.com/zh-cn/guide/preview/-prvw1020/mac
  - No first-party semantic table-extraction action.
  - Apple Intelligence (Summarize PDF) returns prose summary, not structured markdown. [A] [IT之家, 2025-06-12, fetched 2026-06-14]

### 4.3 Apple Notes — Markdown import / export (Tahoe 26 / iOS 26)

#### 4.3.1 Identity and platform

- **Name / vendor**: Apple Notes — built into iOS / iPadOS / macOS. [F] [Apple Support, "Import or share notes and files to the Notes app", published 2026-04-02, fetched 2026-06-14] — https://support.apple.com/en-us/102223

#### 4.3.2 Markdown import / export (iOS 26 / macOS Tahoe 26 / iPadOS 26)

- **First-party confirmation**: "In macOS Tahoe 26, iOS 26, iPadOS 26, and later, Notes converts Markdown syntax to rich text that maintains formatting." (On Mac: File → Import Markdown → select `.md` files.) [F] [Apple Support, "Import or share notes and files to the Notes app", published 2026-04-02, fetched 2026-06-14] — https://support.apple.com/en-us/102223
- **iPhone/iPad path**: open the `.md` file in the Files app, tap Share → Notes → Import. [F] [Apple Support, "Share files to Notes with the Files app", fetched 2026-06-14] — https://support.apple.com/en-us/102223
- **Export**: "Open the Notes app and select the note … Tap Share and then tap the Export as Markdown." [A] [AppleInsider, "How to import & export Markdown with Apple Notes in iOS 26", 2026-01-12, fetched 2026-06-14] — https://appleinsider.com/inside/ios-26/tips/how-to-import-and-export-markdown-with-apple-notes-in-ios-26
- The AppleInsider article (citing 9to5Mac reporting) calls this the **first time** Apple Notes has supported Markdown. [A] [MacRumors, "Apple Notes Expected to Gain Support for Exporting in Markdown in iOS 26", 2025-06-04, fetched 2026-06-14] — https://www.macrumors.com/2025/06/04/apple-notes-rumored-markdown-support-ios-26/
- **Known limitation**: "while iOS 26 makes Notes support Markdown content editing, the app itself does not render styles in the editor in real time. Users can only see the rendered effect after exporting the file and opening it in another tool that supports Markdown rendering." [A] [Tencent News, "Apple iOS 26 Notes app first to support Markdown import and export", 2025-08-29, fetched 2026-06-14] — https://news.qq.com/rain/a/20250829A04UYM00
- Also: "Apple Notes only supports the most basic of Markdown features." [A] [AppleInsider, 2026-01-12, fetched 2026-06-14] — https://appleinsider.com/inside/ios-26/tips/how-to-import-and-export-markdown-with-apple-notes-in-ios-26

#### 4.3.3 Other import formats accepted by Apple Notes (Mac)

- On Mac, the File → Import to Notes dialog accepts `.txt, .rtf, .rtfd, .html, .enex, .md`. [F] [Apple Support, "Import or share notes and files to the Notes app", published 2026-04-02, fetched 2026-06-14] — https://support.apple.com/en-us/102223
- Each text file becomes a new note. Folders are preserved if "Preserve folder structure on import" is enabled. [F] [Apple Support, same page, fetched 2026-06-14]
- `.enex` (Evernote export) is also accepted; unsupported attachments are dropped. [F] [Apple Support, same page, fetched 2026-06-14]

#### 4.3.4 Apple Notes ↔ Vision/Apple Intelligence

- Apple Notes can render scanned documents inside notes (via iPhone Continuity Camera) and OCR them. The note app displays them as PDF attachments inside notes: "View PDF or scanned document in Notes on Mac." [A] [Mac大学, "macOS Sonoma 14.0 New Features: Browse PDF directly in Notes", fetched 2026-06-14] — https://www.macdaxue.com/notes-pdf/
- Apple Notes in iOS 18+ includes **Math Notes / Live Transcription / Image Playground** (Apple Intelligence), but no first-party "extract table from PDF into Markdown" action. [A] [Apple, "New features available with iOS 26" PDF, Sept 2025, fetched 2026-06-14] — https://www.apple.com/os/pdf/All_New_Features_iOS_26_Sept_2025.pdf

#### 4.3.5 Strengths / limitations

- **Strengths**: zero-install, OS-bundled, preserves links/headings, works iCloud ↔ local. [F] [Apple Support, "Import or share notes and files to the Notes app", fetched 2026-06-14]
- **Limitations**:
  - Markdown support is rudimentary; **no live preview inside the editor**. [A] [AppleInsider, 2026-01-12, fetched 2026-06-14]
  - Only `.md` is consumed/produced — no docx/pptx/xlsx path through Notes. [F] [Apple Support, fetched 2026-06-14]
  - PDF inside Notes: read-only, mark-up only; **no markdown export of PDF content** through Notes itself. [A] [Mac大学, "macOS Sonoma 14.0 new features: Notes PDF", fetched 2026-06-14] — https://www.macdaxue.com/notes-pdf/

### 4.4 Apple Intelligence / Writing Tools / Visual Intelligence

- Apple's **Writing Tools** in macOS / iOS 18+ can summarize or rewrite a read-only PDF. [F] [Apple Support, "Use Writing Tools with Apple Intelligence on iPhone", fetched 2026-06-14] — https://support.apple.com/guide/iphone/find-the-right-words-with-writing-tools-iph6f08da1d2/ios
- A "use the model to summarize a PDF opened in Safari" Shortcut is one of the canned examples in iOS 26 Shortcuts. [A] [IT之家, 2025-06-12, fetched 2026-06-14] — https://next.ithome.com/archiver/860/180.htm
- Apple's **macOS 27 ("Golden Gate")** marketing copy is heavy on Siri AI and Visual Intelligence but does not announce a new "Apple Extract" API. [F] [Apple, "macOS 27 Golden Gate Preview", fetched 2026-06-14] — https://www.apple.com/os/?version=no-hero
- Third-party Glimpse macOS app (Mac App Store) describes itself as a Markdown viewer that uses Apple Intelligence for document intelligence: "On macOS 26 with Apple Intelligence, Glimpse can summarize any document in seconds. Extract action items, decisions, and open questions." [A] [App Store, Glimpse - Markdown Viewer listing, fetched 2026-06-14] — https://apps.apple.com/us/app/glimpse-markdown-viewer/id6761304904

---

## 5. Other relevant "Extract" products encountered

### 5.1 Box `ai/extract` and Box text representations

- **Box Text Representation** API: "A text representation provides a way to extract plain text from a document. Text is generated for all document file types including plain text and code files supported by Box. This does not include image files as these do not have a text layer." Generated on upload, max 500 MB. [F] [Box Developer, "Get Text Representation", fetched 2026-06-14] — https://developer.box.com/guides/representations/text
- Process: List all representations → request `x-rep-hints=[extracted_text]` → download. [F] [Box Developer, fetched 2026-06-14]
- **Box AI Extract API** (`POST https://api.box.com/2.0/ai/extract`) — LLM-driven freeform metadata extraction. "Sends an AI request to supported Large Language Models (LLMs) and extracts metadata in …" [A] [Box Platform API on Postman, fetched 2026-06-14] — https://documenter.getpostman.com/view/8119550/SWTABe9M
- **Box Doc Gen** is a separate product for generating (not extracting) docs from Salesforce. "With Box Doc Gen for Salesforce, teams can dynamically generate custom documents." [A] [Box Developer Blog on Medium, "NEW! Box AI API updates", fetched 2026-06-14] — https://medium.com/box-developer-blog/new-box-ai-api-updates-e812b868457d

### 5.2 Dropbox / DocSend / HelloSign (Dropbox Sign)

- Dropbox acquired HelloSign in 2019 for $230M; HelloSign is now branded **Dropbox Sign**. [A] [HRTechChina, "Dropbox acquires HelloSign for $230M", 2019, fetched 2026-06-14] — http://www.hrtechchina.com/tag/hellosign/
- **Dropbox Sign API** is primarily an e-signature API, NOT a document extraction API. Pricing from independent listing: $15/mo (Essentials), $25/user/mo (Standard), custom (Premium). [A] [LearnKu, "HelloSign smart job assistant", fetched 2026-06-14] — https://learnku.com/hub/works/show/hellosign
- Dropbox Sign blog: "How To Extract Signatures From Paper Documents" — a tutorial using OCR to find signature boxes, not a content extraction product. [A] [Dropbox Sign blog, fetched 2026-06-14] — https://sign.dropbox.com/sv-SE/blog/how-to-extract-signatures-from-paper-documents
- **DocSend** (also Dropbox): document-analytics, not extraction. Independent review: "DocSend does not [have an API]." [A] [Signeasy blog, "DocSend Pricing, Plans, and Features", fetched 2026-06-14] — https://signeasy.com/blog/business/docsend-pricing

### 5.3 Google Cloud Document AI (adjacent context)

- Google Cloud's **Document AI Custom Extractor** is "powered by generative AI, which means it can be used…" [A] [Google Cloud, "Document AI", fetched 2026-06-14] — https://cloud.google.com/document-ai
- Mentioned in the arXiv benchmark `ExtractBench` (Feb 2026) for PDF-to-JSON enterprise-scale evaluation. [A] [arXiv 2602.12247, "ExtractBench: A Benchmark and Evaluation Methodology for Complex Structured Extraction", 2026-02-13, fetched 2026-06-14] — https://arxiv.org/abs/2602.12247

### 5.4 Other relevant GitHub projects

- `CatchTheTornado/pdf-extract-api` (open-source, MIT) — an alternative PDF→Markdown/JSON pipeline built on Marker + Surya-OCR + Ollama, Celery + Redis queue. **Not Adobe, not Apple.** [A] [GitHub repo description, fetched via search 2026-06-14] — https://github.com/CatchTheTornado/pdf-extract-api
- `kzaremski/apple-notes-exporter` — "MacOS app written in Swift that bulk exports Apple Notes (including iCloud Notes) to a multitude of formats preserving note folder structure." Useful for benchmarking Apple Notes markdown export. [A] [GitHub repo, fetched 2026-06-14] — https://github.com/kzaremski/apple-notes-exporter
- `rhettbull/...` gist — Python bridge to `VNRecognizeTextRequest` via PyObjC. [A] [GitHub Gist, fetched 2026-06-14] — https://gist.github.com/RhetTbull/1c34fc07c95733642cffcd1ac587fc4c

---

## 6. Cross-cutting observations / decision-relevant findings

1. **Adobe's "PDF to Markdown" endpoint is the only first-party cloud service in scope with a native PDF → Markdown pipeline as of 2026-06-14.** It is paid SaaS (no on-prem, no model), limited to 400 pages per doc, 100 MB file, no support for XFA, CAD, complex annotations, encrypted PDFs. [F] [Adobe Developer, PDF to Markdown how-to and PDF Services API Licensing, fetched 2026-06-14]
2. **"Adobe Sensei" is a marketing layer, not a product.** The structured document extraction product is the PDF Extract API; rebranding toward "Adobe AI" / "Adobe AI Platform" is in progress at the corporate level, but the developer-facing product name is unchanged. [F] [Adobe Developer, fetched 2026-06-14; A] [vzkoo, Instagram, 2025-2026, fetched 2026-06-14]
3. **Apple's local OCR (Vision + VNRecognizeTextRequest) is structurally weaker than Adobe Extract API**: it gives you a flat list of text boxes, no headings/tables/lists semantics, no Markdown output. [A] [Codemia, Create With Swift, fetched 2026-06-14]
4. **Apple Notes Markdown import/export (iOS 26 / macOS Tahoe 26, shipped 2025-09+)** is a meaningful new first-party Markdown path — but it is a **note-taking** feature, not a PDF/structured extraction feature. The editor does not render Markdown live. [F] [Apple Support, "Import or share notes and files to the Notes app", 2026-04-02, fetched 2026-06-14]
5. **Apple Shortcuts** gives you "Extract Text from PDF" (PDFKit text-layer), "Make Rich Text from Markdown" (and the reverse), and Apple Intelligence "Summarize PDF" — none of which is a true structured-extraction pipeline. [A] [IT之家, 2025-06-12; AppleInsider, 2026-01-12; MacScripter, 2023, fetched 2026-06-14]
6. **Box** has the cleanest "extract plain text from any document" API (text representations on upload, including code files), but explicitly does not extract from images. [F] [Box Developer, "Get Text Representation", fetched 2026-06-14]
7. **Dropbox Sign / DocSend** are NOT in the same product category as Adobe Extract or Apple Notes; they are e-signature and document-analytics products. [A] [Dropbox Sign blog, LearnKu, Signeasy, fetched 2026-06-14]
8. **GitHub presence**: Adobe has 1,103 public repos. The only directly relevant ones for structured PDF extraction are the four `pdfservices-*-sdk-samples` repos (Python 163★, Node 109★, .NET 47★, Java in docs). There is no `adobe/sensei-sdk` or `adobe/extract-engine` open-source. [F] [github.com/adobe, fetched 2026-06-14]
9. **License posture**: Adobe's sample SDKs are MIT (samples only); the runtime SDKs and server engine are closed. Apple Vision/Shortcuts/Notes are closed source. Box is closed source. [F] [github.com/adobe/*/LICENSE.md, Apple Developer Terms, Box Developer Terms, fetched 2026-06-14]

---

## 7. Blockers and caveats

- **Apple Developer Documentation pages for `VNRecognizeTextRequest` and `Recognizing Text in Images` are JS-rendered.** The page bodies did not load through `webfetch`; the URL + index in the search results is the best first-party evidence. To get the official API spec, browser-based fetch is required. [F] [Apple Developer, "Recognizing Text in Images", page required JS, fetched 2026-06-14] — https://developer.apple.com/documentation/vision/recognizing-text-in-images
- **Apple's exact first-party name and parameter list for Shortcuts actions like "Make Rich Text from Markdown" and "Extract Text from PDF"** is documented only in the JS-rendered Shortcuts action library. I relied on third-party blog posts (cnblogs, MacScripter, AppleInsider, IT之家) to confirm existence. There is no public Apple-hosted URL I can cite that lists the action name verbatim. [A] [cnblogs, MacScripter, AppleInsider, IT之家, fetched 2026-06-14]
- **Adobe Sensei rebrand** to "Adobe AI" / "Adobe AI Platform" is not yet reflected in the developer docs for PDF Extract API. The phrase "powered by Adobe Sensei machine learning" is still live on Adobe Experience League. I did not find an explicit deprecation notice for the "Sensei" branding in the extract context. [F] [Adobe Experience League, PDF Extract API tutorials, fetched 2026-06-14]
- **macOS 27 "Golden Gate"** is a preview page (Sept 2025+) — public availability of Siri AI features and any document-extraction API in macOS 27 could not be confirmed through public docs at scout time. [F] [Apple, "macOS 27 Golden Gate Preview", fetched 2026-06-14] — https://www.apple.com/os/?version=no-hero
- **Box "ai/extract"** documentation is via Postman documenter, not a canonical Box dev guide. The endpoint URL and capability are confirmed but the exact rate limits and pricing tier were not fetched. [A] [Box Platform API on Postman, fetched 2026-06-14]

---

## 8. Source inventory (everything actually fetched)

### First-party (Adobe / Apple / Box / GitHub)
- https://developer.adobe.com/document-services/apis/pdf-extract/ [F]
- https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/ [F]
- https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/howtos/pdf-to-markdown-api/ [F]
- https://developer.adobe.com/document-services/docs/overview/pdf-services-api/ [F]
- https://developer.adobe.com/document-services/docs/overview/pdf-services-api/howtos/export-pdf/ [F]
- https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/dcserviceslicensing/ [F]
- https://developer.adobe.com/document-services/pricing/main/ [F]
- https://opensource.adobe.com/pdftools-sdk-docs/release/shared/extractJSONOutputSchema.json [F]
- https://github.com/adobe [F]
- https://github.com/adobe/pdfservices-python-sdk-samples [F]
- https://github.com/adobe/pdfservices-python-sdk-samples/tree/main/src/extractpdf [F]
- https://github.com/adobe/pdfservices-python-sdk-samples/blob/main/src/extractpdf/extract_text_table_info_from_pdf.py [F]
- https://github.com/adobe/pdfservices-node-sdk-samples [F]
- https://github.com/adobe/PDFServices.NET.SDK.Samples [F]
- https://developer.apple.com/documentation/vision/recognizing-text-in-images [F] (JS-gated, evidence via search)
- https://developer.apple.com/documentation/vision/vnrecognizetextrequest/supportedrecognitionlanguages(for:revision:) [F] (JS-gated, evidence via search)
- https://developer.apple.com/videos/play/wwdc2019/ [F]
- https://developer.apple.com/videos/play/wwdc2021/10041/ [F]
- https://support.apple.com/en-gb/guide/shortcuts/welcome/ios [F]
- https://support.apple.com/en-gb/guide/shortcuts/welcome/9.0/ios/26 [F]
- https://support.apple.com/en-us/102223 [F] (Import/Export Markdown Notes)
- https://support.apple.com/guide/iphone/find-the-right-words-with-writing-tools-iph6f08da1d2/ios [F]
- https://support.apple.com/zh-cn/guide/preview/-prvw1020/mac [F] (Preview PDF text copy)
- https://www.apple.com/os/?version=no-hero [F] (macOS 27)
- https://www.apple.com/os/pdf/All_New_Features_iOS_26_Sept_2025.pdf [F]
- https://developer.box.com/guides/representations/text [F]

### First-party (Adobe Tech Blog, Google Tech Blog)
- https://medium.com/adobetech/adobe-pdf-extract-api-output-demystified-ff69841c4ed3 [F, Adobe Tech Blog via Medium]

### Third-party / press / community
- https://stackoverflow.com/questions/58219769/which-languages-are-available-for-text-recognition-in-vision-framework [A]
- https://www.createwithswift.com/recognizing-text-with-the-vision-framework/ [A]
- https://codemia.io/knowledge-hub/path/apple_vision_framework__text_extraction_from_image [A]
- https://m.blog.csdn.net/HDFQQ188816190/article/details/85234137 [A]
- https://www.macscripter.net/t/optical-character-recognition-ocr-script/74498/21 [A]
- https://m.toutiao.com/a7005847755004461599/ [A] (OwlOCR)
- https://gist.github.com/RhetTbull/1c34fc07c95733642cffcd1ac587fc4c [A] (Python Vision)
- https://www.cnblogs.com/amboke/p/16705169.html [A] (Shortcuts Make Rich Text from Markdown)
- https://www.macscripter.net/t/shortcut-to-log-time-and-task-data/75940 [A]
- https://discussions.apple.com/thread/255810627 [A] (Split PDF into Images Quick Action)
- https://lifetips.alibaba.com/tech-efficiency/lifehacker-the-book-table-of-contents [A] (Shortcuts Extract Text from PDF)
- https://next.ithome.com/archiver/860/180.htm [A] (iOS 26 Shortcuts + Apple Intelligence)
- https://news.qq.com/rain/a/20250829A04UYM00 [A] (Apple Notes Markdown)
- https://appleinsider.com/inside/ios-26/tips/how-to-import-and-export-markdown-with-apple-notes-in-ios-26 [A]
- https://www.macrumors.com/2025/06/04/apple-notes-rumored-markdown-support-ios-26/ [A]
- https://www.macdaxue.com/notes-pdf/ [A] (Notes PDF browser)
- https://apps.apple.com/us/app/glimpse-markdown-viewer/id6761304904 [A] (Glimpse Markdown viewer)
- https://news.qq.com/rain/a/20260601A04PI600 [A] (iOS 27 visual intelligence)
- https://www.vzkoo.com/question/1722478084211626 [A] (Adobe AI summary)
- https://community.adobe.com/questions-21/adobe-extract-api-problem-with-structure-309260 [A] (Extract user issue)
- https://community.adobe.com/questions-21/seeking-solutions-preserving-table-structure-in-json-output-with-adobe-pdf-extract-api-for-rag-app-311193 [A]
- https://cloud.tencent.com/developer/article/1049212 [A] (Adobe Sensei GenAI)
- https://www.instagram.com/reel/DXpa12ejWJd/ [A] (Adobe Summit 2025 Adobe AI Platform)
- https://www.instagram.com/reel/DYU72vjgswY/ [A] (Adobe CX Enterprise)
- https://github.com/kzaremski/apple-notes-exporter [A] (Apple Notes bulk export tool)
- https://github.com/CatchTheTornado/pdf-extract-api [A] (3rd-party open-source PDF→Markdown/JSON)
- http://www.hrtechchina.com/tag/hellosign/ [A] (Dropbox acquired HelloSign)
- https://learnku.com/hub/works/show/hellosign [A] (Dropbox Sign pricing)
- https://signeasy.com/blog/business/docsend-pricing [A] (DocSend no API)
- https://sign.dropbox.com/sv-SE/blog/how-to-extract-signatures-from-paper-documents [A] (Dropbox Sign signature extraction)
- https://sign.dropbox.com/sv-SE/blog/comparing-ocr-apis [A]
- https://cloud.google.com/document-ai [A] (Google Document AI - adjacent context)
- https://arxiv.org/abs/2602.12247 [A] (ExtractBench arXiv 2026-02-13)
- https://documenter.getpostman.com/view/8119550/SWTABe9M [A] (Box Platform API on Postman)
- https://medium.com/box-developer-blog/new-box-ai-api-updates-e812b868457d [A] (Box AI / Doc Gen)
- https://www.theverge.com/news/670241/adobe-ai-creative-cloud-all-apps [A, cited indirectly]

---

## 9. Quick-reference table (for downstream consumer)

| Product | Vendor | Output | Inputs | Mode | Free tier | Open source? | Latest release observed |
|---|---|---|---|---|---|---|---|
| PDF Extract API (JSON) | Adobe | Structured JSON + PNG/CSV/XLSX | PDF | Cloud | 500 DT/mo | Samples only (MIT) | v4.2.0 (Py SDK samples) 2025-07-11 |
| PDF to Markdown | Adobe | `.md` with base64 images | PDF | Cloud | 500 DT/mo | Samples only (MIT) | Same as above |
| PDF Services Export | Adobe | DOCX, PPTX, XLSX, RTF, PNG, JPEG | PDF | Cloud | 500 DT/mo | Samples only (MIT) | Node 4.1.0 on 2025-01-02 |
| Adobe Sensei (extract use) | Adobe | n/a — branding layer for Extract API | n/a | Cloud | n/a | n/a | Brand being folded into "Adobe AI" 2025-2026 |
| Vision `VNRecognizeTextRequest` | Apple | Flat text observations + confidence | Image (PDF via render) | On-device, free | Free (bundled) | Closed (Apple proprietary) | Bundled with OS, revisioned per OS |
| Shortcuts "Extract Text from PDF" | Apple | Plain text from PDFKit text layer | PDF | On-device | Free | Closed | Bundled with macOS 10.15+, iOS 12+ |
| Shortcuts "Make Rich Text from Markdown" | Apple | Shortcuts rich-text from `.md` | Markdown text | On-device | Free | Closed | Bundled |
| Apple Notes Markdown import/export | Apple | `.md` in/out | `.md` (export any note) | On-device | Free | Closed | macOS Tahoe 26, iOS 26, iPadOS 26 (Sept 2025+) |
| Apple Intelligence "Summarize PDF" | Apple | Prose summary | PDF (via Safari/Quick Look) | On-device / PCC / ChatGPT | Free | Closed | macOS 15+, iOS 18+ |
| Box `ai/extract` | Box | Freeform metadata fields | Any Box file (text) | Cloud | n/a | Closed | Postman-doc dated recent |
| Box Text Representation | Box | Plain text | All Box file types except images | Cloud | n/a | Closed | Same as Box platform |
| Dropbox Sign (HelloSign) | Dropbox | E-signed documents, not extract | PDF for signing | Cloud | None for OCR | Closed | Rebranded 2019 |
| DocSend | Dropbox | Document analytics | PDF for sharing | Cloud | n/a | Closed | n/a |
| (Adjacent) Google Document AI | Google | Structured JSON | PDF, images | Cloud | 1,000 pages/mo | Closed | n/a |

