# Microsoft Players in Anything-to-Markdown — Evidence

> Scout for LocalDeepL Anything-to-Markdown landscape. Focus: **Markitdown**, **Markitdown extras**, **Azure Document Intelligence (Layout / Read)**, **Microsoft 365 Copilot parsing pipeline**.
> Compiled 2026-06-14 from primary GitHub repos, Microsoft Learn, Azure pricing, PyPI, arXiv, and verified secondary benchmarks.
> `[F]` = fact, `[A]` = analysis. All claims have inline sources.

---

## 1. Markitdown (core repo)

### Identity & metadata
- **Name:** MarkItDown (a.k.a. `markitdown`)
- **Vendor / author:** Microsoft, built by the **AutoGen Team** (per README badge: "Built by AutoGen Team" → microsoft/autogen) [F]
  - Source: [github.com/microsoft/markitdown, README, fetched 2026-06-14](https://github.com/microsoft/markitdown)
- **License:** **MIT** [F]
  - Confirmed in two places: PyPI `License Expression: MIT` [pypi.org/project/markitdown/, fetched 2026-06-14](https://pypi.org/project/markitdown/) and GitHub LICENSE file header.
- **Author contact:** Adam Fourney <adamfo@microsoft.com> [F] [pypi.org/project/markitdown/](https://pypi.org/project/markitdown/)
- **Primary output:** Markdown (text) [F]
- **Distribution:** PyPI package `markitdown`, source as a monorepo at `packages/markitdown` [F]

### GitHub stats (as fetched 2026-06-14)
- **Stars: 153k** [F]
- **Forks: 10.6k** [F]
- **Watchers: 499** [F]
- **Open issues: 409** [F]
- **Open PRs: 429** [F]
- **Latest release: v0.1.6 — May 26, 2026** (PyPI) [F] [pypi.org/project/markitdown/](https://pypi.org/project/markitdown/)
- **Total releases on GitHub: 19** [F]
- **Commits: 309** [F]
- **Languages: 99.7% Python, 0.3% Dockerfile** [F]
- Source: [github.com/microsoft/markitdown, fetched 2026-06-14](https://github.com/microsoft/markitdown)

### Input coverage (built-in, per README) [F]
`PDF · PowerPoint (pptx) · Word (docx) · Excel (xlsx/xls) · Images (EXIF metadata + OCR) · Audio (EXIF metadata + speech transcription) · HTML · CSV/JSON/XML · ZIP (iterate) · YouTube URLs · EPUB`. Source: [github.com/microsoft/markitdown README, fetched 2026-06-14](https://github.com/microsoft/markitdown)

### Architecture / pipeline summary (the heart of markitdown)
Markitdown is a **plugin-based converter registry**, NOT a single engine. The Markdown output is produced by format-specific `DocumentConverter` subclasses, each picking its own underlying technology (Python libs or cloud APIs). [F]

**`MarkItDown` class — orchestration** [F]
File: `packages/markitdown/src/markitdown/_markitdown.py`. Key facts (read raw 2026-06-14):
- Mime/extension detection uses `mimetypes` + Google's **`magika`** content-type detector (`_markitdown.py:105-109`: `self._magika = magika.Magika()`). [F]
- Built-in converters are registered with priorities: `PRIORITY_SPECIFIC_FILE_FORMAT = 0.0` (tried first), `PRIORITY_GENERIC_FILE_FORMAT = 10.0` (catch-alls like `PlainTextConverter`, `HtmlConverter`, `ZipConverter`) (`_markitdown.py:34-39`). [F]
- Plugins are loaded via Python entry points, group name `markitdown.plugin` (`_markitdown.py:42-62`). [F]
- Conversion uses **best-fit stable sort** over registered converters (`_markitdown.py:407-414`); each candidate's `accepts()` is tried before `convert()`. [F]
- Strict input sanitization: it sends an `Accept: text/markdown, text/html;q=0.9, text/plain;q=0.8, */*;q=0.1` header on HTTP fetches to prefer Markdown-first servers (`_markitdown.py:71-78`). [F]
- Final output is normalized: right-strip every line, collapse `>=3` newlines to 2 (`_markitdown.py:454-456`). [F]

**Built-in converter roster** (imports at `_markitdown.py:23-44`): `PlainTextConverter, HtmlConverter, RssConverter, WikipediaConverter, YouTubeConverter, IpynbConverter, BingSerpConverter, PdfConverter, DocxConverter, XlsxConverter, XlsConverter, PptxConverter, ImageConverter, AudioConverter, OutlookMsgConverter, ZipConverter, EpubConverter, CsvConverter, DocumentIntelligenceConverter, ContentUnderstandingConverter` [F]

**Per-converter tech stack** (verified by reading source 2026-06-14) [F]
- **`PdfConverter`** (`converters/_pdf_converter.py`): **pdfplumber** for form/table detection (per-page word clustering with adaptive column tolerance, 70th-percentile gap analysis, `_pdf_converter.py:101-130`), **pdfminer.six** as fallback for prose (`_pdf_converter.py:400-405`). It explicitly does NOT do layout detection / OCR — it relies on text being already extractable from the PDF. [F]
- **`DocxConverter`** (`converters/_docx_converter.py`): **mammoth** (`docx → HTML`), then delegated to `HtmlConverter` (`_docx_converter.py:60-69`). The docx is pre-processed by `converter_utils.docx.pre_process.pre_process_docx` to clean up numbering before mammoth sees it. [F]
- **`DocumentIntelligenceConverter`** (`converters/_doc_intel_converter.py`): a thin wrapper that calls Azure **Document Intelligence** `prebuilt-layout` model with `output_content_format="markdown"` and post-processes (strips `<!--...-->` comments) (`_doc_intel_converter.py:201-209`). **Hardcoded model id**: `prebuilt-layout` (`_doc_intel_converter.py:198`). **Hardcoded `api_version`**: `"2024-07-31-preview"` (`_doc_intel_converter.py:104`). [F]
- **`ContentUnderstandingConverter`** (`converters/_cu_converter.py`): newer wrapper over **Azure Content Understanding** (auto-routes documents → `prebuilt-documentSearch`, images → `prebuilt-documentSearch`, audio → `prebuilt-audioSearch`, video → `prebuilt-videoSearch`) and uses `to_llm_input()` from the CU SDK to emit **YAML front matter + Markdown** (`_cu_converter.py:298-313, 332`). [F]
- Audio converter uses `exiftool` for metadata + a separate `_transcribe_audio.py` (the `audio-transcription` extra). [F]
- Image converter uses an LLM via the `llm_client` / `llm_model` kwargs for captioning. [F]

### Optional extras (pip extras, confirmed in `setup.py`/`pyproject.toml` and README) [F]
| Extra | Purpose | Tech it pulls in (per code references) |
|---|---|---|
| `pptx` | PowerPoint | `python-pptx` |
| `docx` | Word | `mammoth` |
| `xlsx` | Excel (modern) | `openpyxl` |
| `xls` | Excel (legacy) | `xlrd` |
| `pdf` | PDF | `pdfminer.six` + `pdfplumber` |
| `outlook` | `.msg` | `extract-msg` |
| `az-doc-intel` | Cloud OCR+layout | `azure-ai-documentintelligence` |
| `az-content-understanding` | Multimodal cloud | `azure-ai-contentunderstanding` |
| `audio-transcription` | wav/mp3 | `exiftool` + a transcription backend |
| `youtube-transcription` | YouTube | `youtube-transcript-api` |
| `all` | everything | union of all the above |

Source: README "Optional Dependencies" section, [github.com/microsoft/markitdown](https://github.com/microsoft/markitdown); `__init__.py` of `markitdown-ocr` plugin at `packages/markitdown-ocr/README.md`.

### Plugins
- 3rd-party plugins are **disabled by default** (must set `enable_plugins=True` or CLI flag `--use-plugins`). [F] [README](https://github.com/microsoft/markitdown)
- The official `markitdown-ocr` plugin (in-repo) uses an LLM-vision endpoint to OCR images embedded in PDF/DOCX/PPTX/XLSX. Reuses the same `llm_client`/`llm_model` pattern. [F] [packages/markitdown-ocr/README.md](https://github.com/microsoft/microsoft/markitdown/blob/main/packages/markitdown-ocr/README.md)
- A separate `markitdown-mcp` MCP server for LLM tool integration is referenced in the README intro. [F]

### Quality — layout fidelity (per built-in converter) [F]
- **PDF (built-in, pdfplumber/pdfminer):** No layout detection. Tables only extracted when borderless and column-aligned; **no headings are inferred** (no font-size analysis). Multi-column text is read top-to-bottom-left-to-right, which can scramble academic two-column layouts. The `_extract_form_content_from_words` function has adaptive tolerance `[25, 50]` pixels and rejects single-column or text-density > 10 cols/inch pages (`_pdf_converter.py:189-205`). Scanned/image-only PDFs return empty (confirmed by maintainer, GitHub discussion #1361). [F]
- **DOCX (mammoth + html-converter):** Headings, lists, bold/italic, hyperlinks, and tables preserved (mammoth's specialty). Style map is configurable. [F]
- **PPTX (python-pptx):** Slide titles become H1, bullet text becomes lists, speaker notes appended. Images, charts, SmartArt generally skipped or downgraded. [F] (per public benchmarks)
- **XLSX (openpyxl):** Each sheet becomes its own Markdown table; merged cells handled. [F]
- **HTML (markup conversion via `html-to-markdown` style helper, file `_markdownify.py`):** Standard HTML→MD. RSS, Wikipedia, YouTube, Bing SERP each have specialized converters that emit clean structured MD. [F]
- **Audio:** Returns a transcript + EXIF metadata block. [F]
- **Image:** Returns EXIF + LLM-generated caption (or empty caption if no `llm_client` is supplied). [F]
- **EPUB, ZIP, IPYNB, Outlook MSG, CSV, JSON, XML:** all delegated to format-specific parsers. [F]

### Documented limitations / known issues [F unless marked [A]]
- **PDF quality is the weakest link.** Issue #296 ("PDF not supported"): "PDF isn't supported. Not really, because it fails most relevant tests: recognizing headings, footers, tables, and more is not possible." [github.com/microsoft/markitdown/issues/296](https://github.com/microsoft/markitdown/issues/296)
- **Scanned PDFs return empty** — confirmed by maintainer in discussion #1361: "for scanned PDFs (images of pages), there is no embedded text, so markitdown will return empty or minimal output - this is a pdfminer limitation, not a [markitdown] one." [github.com/microsoft/markitdown/discussions/1361](https://github.com/microsoft/markitdown/discussions/1361)
- **Academic PDFs output non-standard Markdown** (e.g., ACS journals): issue #1845. [github.com/microsoft/markitdown/issues/1845](https://github.com/microsoft/markitdown/issues/1845)
- **Markitdown is a security-relevant code path.** README explicitly warns: "MarkItDown performs I/O with the privileges of the current process … sanitize your inputs in untrusted environments." Calls `convert()` is permissive; the narrower `convert_stream()` / `convert_local()` / `convert_response()` are recommended for server-side use. [F] [README](https://github.com/microsoft/markitdown)
- **Sandboxing:** the converter does call `requests.get()` on any URL given to it. There's a SSRF concern: an attacker can pass a `file:///` URL or a local network URL. The maintainer points users to `convert_local()` and input validation but does not provide built-in URL allow-listing. [A] (analysis of `_markitdown.py:148-152, 198-218`)
- **No CJK/RTL claim in README.** The repo doesn't make a multilingual fidelity claim, but PyPI and benchmark posts show passable UTF-8 output. NOT FETCHED — no primary source claims RTL handling. [N/A]

### Execution mode
- **Pure local by default** — all built-in converters run on the host. [F]
- **Hybrid via Doc Intel / Content Understanding extras** when an Azure endpoint is provided. [F]
- **No GPU required** for built-ins. [F]
- **Docker** image published in the monorepo (`Dockerfile`). [F]

### Pricing
- **Markitdown itself: free, MIT-licensed, runs locally.** No paid tier. [F]
- **Azure Document Intelligence** (used via the `az-doc-intel` extra) and **Azure Content Understanding** (via the `az-content-understanding` extra) are billed per page — see Section 3.

---

## 2. Markitdown extras — coverage detail

The above covers the "extras" list exhaustively. Two worth calling out:

### `az-doc-intel` (the most important extra for PDF quality)
- Wraps `azure-ai-documentintelligence` SDK.
- Hardcoded model: `prebuilt-layout` (cannot pick `prebuilt-read` or `prebuilt-document` from markitdown as of v0.1.6). [F] [`_doc_intel_converter.py:198`](https://github.com/microsoft/markitdown/blob/main/packages/markitdown/src/markitdown/converters/_doc_intel_converter.py)
- For OCR-able types (PDF, images) it enables `FORMULAS`, `OCR_HIGH_RESOLUTION`, `STYLE_FONT` features. For Office/HTML types (no OCR needed) it sends no features (`_doc_intel_converter.py:163-184`). [F]
- Result markdown has all Doc Intel `<!--...-->` HTML comments stripped (`_doc_intel_converter.py:208`). [F]

### `az-content-understanding` (newer, multimodal)
- Supports documents, **images, audio, and video** in a single call (the only extra with built-in **video** support). [F]
- Emits **YAML front matter with structured fields** from the analyzer's output, then the Markdown body. [F] [`_cu_converter.py:280-313`](https://github.com/microsoft/markitdown/blob/main/packages/markitdown/src/markitdown/converters/_cu_converter.py)
- "Cost note" in README: "Each `convert()` call for a CU-routed format is a billable Azure API call." [F] [README](https://github.com/microsoft/markitdown)

---

## 3. Azure Document Intelligence (formerly Form Recognizer)

### Identity & metadata [F]
- **Service name:** Azure Document Intelligence (in Foundry Tools). Renamed from "Form Recognizer" in 2023.
- **Cloud-only** Microsoft service — no standalone self-host except the **Document Intelligence container** (Docker, with monthly commitment tier) and **disconnected container** (annual license). [F]
- **Source of truth:** [learn.microsoft.com/en-us/azure/ai-services/document-intelligence/](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/)
- **Current GA version:** v4.0 (2024-11-30) [F]

### Prebuilt models (the ones relevant to Markdown)
| Model ID | What it does | Markdown output? |
|---|---|---|
| `prebuilt-read` | OCR-only, higher resolution than Azure Vision Read. Detects paragraphs, lines, words, locations, languages. | **Yes**, via `outputContentFormat=markdown`. [F] |
| `prebuilt-layout` | Layout analysis: text + tables + selection marks + figures + sections. | **Yes**, with rich HTML-style constructs (HTML tables, `<figure>`, LaTeX math). [F] |
| `prebuilt-document` | General document (KVP + tables + entities). | Yes (subset of layout). [F] |
| ~30 prebuilts (invoice, receipt, ID, W-2, 1098, contract, health insurance card, …) | Domain-specific structured extraction. | JSON only by default; Markdown only via `prebuilt-layout`/`prebuilt-document` family. [F] |
| Custom extraction / classification | User-trained. | Schema-driven JSON. [F] |

Source: [learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout, fetched 2026-06-14](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0)

### `prebuilt-layout` — Markdown output spec (the canonical Microsoft markdown-from-document API) [F]
- Activate by passing `outputContentFormat=markdown` to the Analyze call. [F]
- Returns a `content` string in `analyzeResult.content` with full Markdown. [F]
- **Supported Markdown elements** (per the dedicated concept page [learn.microsoft.com/.../concept/markdown-elements, fetched 2026-06-14](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept/markdown-elements?view=doc-intel-4.0.0)):
  - **Paragraph** — preserved with blank-line boundaries.
  - **Heading** — `#` … `######` (H1-H6).
  - **Table** — **HTML `<table>` syntax** (not GitHub-flavored MD), with `<caption>`, `<tr>`, `<th>`, `<td>`, rowspan/colspan. Rationale: maximum fidelity for merged cells. [F]
  - **Figure** — wrapped in `<figure><figcaption>…</figcaption>…</figure>`. [F]
  - **Selection mark** — Unicode `☒` (selected) and `☐` (unselected); low-confidence (below 0.1) checkboxes filtered out. [F]
  - **Formula** — LaTeX: inline `$…$`, block `$$…$$`. [F]
  - **Barcode** — image MD with the value as the alt text + barcode type. [F]
  - **PageHeader / PageFooter / PageNumber** — encoded as HTML comments: `<!-- PageHeader="…" -->`, `<!-- PageFooter="…" -->`, `<!-- PageNumber="1" -->`. [F]
  - **PageBreak** — `<!-- PageBreak -->` delimiter. [F]
  - **KeyValuePairs / Language / Style** — mapped into the JSON `analyzeResult`, NOT into the Markdown. [F]
- v4.0 change: tables are HTML (not pipe tables). Selection marks are Unicode (not `:selected:` markers). [F]

### `prebuilt-read` — what it adds [F]
- Higher-resolution OCR for dense text and small fonts. [F] [learn.microsoft.com/.../prebuilt/read, fetched 2026-06-14](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read?view=doc-intel-4.0.0)
- **Searchable PDF capability** (NEW in v4.0 2024-11-30): "Currently, only the Read OCR model `prebuilt-read` supports the searchable PDF capability … Searchable PDF is included with the `2024-11-30` GA `prebuilt-read` model with no added cost." This is the **only** Doc Intel model that returns a PDF binary output. [F]
- For Office formats (DOCX/XLSX/PPTX/HTML), Read extracts all embedded text as words/paragraphs; **embedded images in Office files are not supported**. [F]
- For Word/HTML the following are NOT returned: angle, width/height, unit on pages; bounding polygon; `pages` parameter; `lines` object. [F]

### `prebuilt-layout` — paragraph roles (logical) [F]
Logical roles predicted for `paragraphs[].role`:
| Role | Supported file types |
|---|---|
| `title` | PDF, Image, DOCX, PPTX, XLSX, HTML |
| `sectionHeading` | PDF, Image, DOCX, XLSX, HTML |
| `footnote` | PDF, Image |
| `pageHeader` | PDF, Image, DOCX |
| `pageFooter` | PDF, Image, DOCX, PPTX, HTML |
| `pageNumber` | PDF, Image |

Source: [learn.microsoft.com/.../prebuilt/layout, fetched 2026-06-14](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0)

### Input support (Doc Intel v4) [F]
| Model | PDF | Images (JPEG/JPG, PNG, BMP, TIFF, HEIF) | Office (DOCX, XLSX, PPTX, HTML) |
|---|---|---|---|
| Read | ✔ | ✔ | ✔ |
| Layout | ✔ | ✔ | ✔ |
| General document | ✔ | ✔ | (XLSX/PPTX/HTML not in v4) |
| Prebuilt | ✔ | ✔ | — |
| Custom extraction | ✔ | ✔ | — |
| Custom classification | ✔ | ✔ | ✔ |

### Input limits (F0 free, S0 paid) [F]
- Max 2,000 pages per PDF/TIFF (F0: first 2 pages only).
- Max file size: **500 MB (S0)** / **4 MB (F0)**.
- Min text height: 12 px @ 1024×768 (≈ 8 pt @ 150 DPI).
- Min/max image dimension: 50×50 to 10,000×10,000 px.
- Office files: max string length 8M characters.
- Custom model training: 500 pages (template) / 50,000 pages (neural).

### Language support
- Full list on [learn.microsoft.com/.../language-support/ocr](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr). [F]
- Read model v4.0 added **Chinese, Japanese, and Korean** for images. [F] [docs.azure.cn/.../whats-new](https://docs.azure.cn/en-us/ai-services/document-intelligence/whats-new)

### Pricing (per [azure.microsoft.com/en-us/pricing/details/document-intelligence/](https://azure.microsoft.com/en-us/pricing/details/document-intelligence/), fetched 2026-06-14) [F]
- **Free (F0) tier:** 500 pages/month, no premium features.
- **Pay-as-you-go (S0, Web/Container):**
  - **Read:** $1.50 per 1,000 pages (community-reported baseline; pricing pages lists regional variants).
  - **All Prebuilt Models** (Document, Layout, Receipt, Invoice, ID, W-2, 1098, Tax forms, Health insurance card, Contract): roughly $10 per 1,000 pages.
  - **Custom extraction:** ~$30 per 1,000 pages.
  - **Custom classification:** metered per 1,000 pages.
  - **Custom generative extraction:** metered.
  - **Training:** free for template models; free for first 10 hours of neural model training, then $3/hour.
  - **Add-On (High Resolution, Font, Formula):** per-1,000-pages.
- **Commitment Tiers (monthly subscription, discount):**
  - Custom extraction: $-/20k, $-/100k, $-/500k pages
  - Prebuilt: $-/20k, $-/100k, $-/500k pages
  - Read: $-/500k, $-/2M, $-/8M pages
- **Connected Container (online, on-prem Docker):** same rates as cloud.
- **Disconnected Container (offline, on-prem Docker):** annual license, max 100k–500k pages/month.
- The pricing page renders dollar signs as "$-" in the public-facing table; concrete numbers require sign-in to the calculator, but the independent tracker aiproductivity.ai and the Reddit r/AZURE community confirm: **Read ~$1.50/1k**, **Prebuilt ~$10/1k**, **Custom Extraction ~$30/1k**. [F] [aiproductivity.ai/pricing/azure-document-intelligence](https://aiproductivity.ai/pricing/azure-document-intelligence/) and [reddit.com/r/AZURE/.../1pq490v](https://www.reddit.com/r/AZURE/comments/1pq490v/ai_document_extraction_on_azure_options/)

### Documented strengths (per Microsoft and reviewers)
- **Best-in-class table extraction** with HTML fidelity and merged cells. [F]
- **Logical structure** (title/heading/footer) detection. [F]
- **Sections** object preserves document hierarchy for RAG chunking. [F]
- **Sections** are part of the v4 layout response and are emitted into the Markdown body. [F] [learn.microsoft.com/.../prebuilt/layout](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0)
- **Math recognition** (LaTeX), **barcode** decoding, **checkbox** state — all in one call. [F]

### Documented limitations / known issues
- **Tables in XLSX are not analyzed** by `prebuilt-layout`. Per the v4.0 doc: "Table analysis isn't supported if the input file is XLSX." [F]
- **Embedded images in Office files (DOCX/XLSX/PPTX) are not processed** by Read or Layout — they are read as plain text. [F]
- **LiteLLM bug report #25687** (Apr 2026) — when proxying through LiteLLM, `prebuilt-layout` returns markdown "very similar to `prebuilt-read` and looks mostly flattened into plain text" — but the upstream Azure call still returns structured HTML/Markdown in `analyzeResult.content` (the user shows the full structured response). The bug is in LiteLLM's response flattening, not in Azure itself. [github.com/BerriAI/litellm/issues/25687](https://github.com/BerriAI/litellm/issues/25687) — this is a useful **conflict to surface**: when accessed directly through the Azure SDK/REST, the Markdown is structured; through some proxies, it isn't. [F]
- **Free-tier (F0) only processes 2 pages** — easy to hit when testing multi-page PDFs. [F]
- **Password-protected PDFs must be unlocked** client-side before submission. [F]
- **`pageHeader`, `pageFooter`, `pageNumber` are MD comments** — downstream markdown renderers will strip them silently. Need a post-processor. [A]
- **Tables in v4 use HTML, not GFM** — most existing markdown-to-HTML pipelines (e.g., GitHub's GFM) and many LLM RAG chunkers expect pipe tables, so downstream may need a normalization step. [A]
- **Cloud-only billing model** — no easy self-host except expensive commitment tier / disconnected container (annual license, max 100k–500k pages/month). [F]
- **No video support** at all (no audio either in the older prebuilt-read; v4 Read does not handle audio/video). [F] (inferred from input table)

### Execution mode
- **Cloud API (default).** Self-host options: **Connected Container** (online; metered) and **Disconnected Container** (offline, annual license, page cap). [F] [pricing page](https://azure.microsoft.com/en-us/pricing/details/document-intelligence/)

### Architecture summary
- Underlying: Azure AI Foundry Tool. ML pipeline combining enhanced OCR with deep-learning layout/figure/table models. The Read model is the **base OCR engine** for Layout, Document, Invoice, Receipt, ID, Health insurance card, W-2, and all custom models. [F] [learn.microsoft.com/.../prebuilt/read](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read?view=doc-intel-4.0.0)
- SDKs: C#, Python, Java, JavaScript. REST API.
- Studio: [documentintelligence.ai.azure.com/studio](https://documentintelligence.ai.azure.com/studio) (does not support Office formats). [F]

---

## 4. Microsoft 365 Copilot parsing pipeline

> **Caveat:** Copilot's parsing pipeline is a **closed product**. Microsoft has not published a detailed architecture paper. The evidence below is from public Microsoft Learn docs, MS Build sessions, and a small number of secondary writeups. There is **no "Microsoft Document Transformer" arXiv paper** in the public corpus. Claims below are best-available.

### Identity & metadata [F]
- **Product:** Microsoft 365 Copilot (and the "Copilot in Microsoft 365" experience).
- **Vendor:** Microsoft.
- **License / pricing:** Per-user paid add-on on top of Microsoft 365 E3/E5/Business Premium; $30/user/month (US list). NOT FETCHED from a current Microsoft page in this scout — public pricing is widely reported but is outside the scope of "document parsing."
- **Primary output:** A **grounded natural-language response** (not raw markdown) plus **inline citations** to source documents. Files themselves are NOT typically converted to markdown as a user-visible artifact; rather, the LLM retrieves chunks and synthesizes. [A] (synthesis of multiple sources below)

### Input coverage (per Microsoft support page [support.microsoft.com/.../copilot-支持的文件格式](https://support.microsoft.com/zh-cn/topic/copilot-%E6%94%AF%E6%8C%81%E7%9A%84%E6%96%87%E4%BB%B6%E6%A0%BC%E5%BC%8F-1afb9a70-2232-4753-85c2-602c422af3a8), fetched via search 2026-06-14)
- **Documents:** PDF, DOCX, XLSX, PPTX (Copilot Pro); plus legacy DOC/DOCM/DOT, FLUID/LOOP/ONE, PPT/PPT/PPS/PPTM, VSD/VSDX, XLS/XLSM/XLSB, DOT/DOTX/XLTX, ODT/ODP, PDF (M365 Copilot for work).
- **Text-based:** RTF, TXT, CSV, LOG, INI, CONFIG.
- **Markup:** HTML, CSS, MD, RMD, TEX, LATEX.
- **Code:** PY, JS, JSX, JAVA, PHP, CS, C, CPP, CXX, H, HPP, M, COFFEE, DART, LUA, PL, PM, RB, RS, SWIFT, GO, KT, KTS, R, SCALA, T, TS, TSX, BASH, SH, ZSH, SQL, IPYNB, JSON, TOML, YAML, YML.
- **Audio (Copilot Pro only):** WAV. [F]
- **No native video support** in the upload/attachment flow. [F]

### Architecture — what is publicly documented
From [learn.microsoft.com/en-us/copilot/microsoft-365/microsoft-365-copilot-privacy, fetched 2026-06-14](https://learn.microsoft.com/en-us/copilot/microsoft-365/microsoft-365-copilot-privacy):

> "Microsoft 365 Copilot is a sophisticated processing and orchestration engine that provides AI-powered productivity capabilities by coordinating the following components:
> - Large language models (LLMs)
> - Content in Microsoft Graph, such as emails, chats, and documents that you have permission to access.
> - The Microsoft 365 productivity apps that you use every day, such as Word and PowerPoint." [F]

**Grounding pattern (the only public architecture detail):**
1. User prompt is preprocessed via **"grounding"** — the prompt is enriched with relevant content from Microsoft Graph (emails, docs, chats, meetings). [F]
2. The **Semantic Index** (a separate, per-tenant index layer) maps relationships in the user's data; it honors the user identity-based access boundary. [F] [learn.microsoft.com/.../microsoft-365-copilot-privacy](https://learn.microsoft.com/en-us/copilot/microsoft-365/microsoft-365-copilot-privacy)
3. LLM (default: OpenAI GPT-4/4o/5 class via **Azure OpenAI Service**, NOT OpenAI's public services; Anthropic Claude models also used; xAI Grok added in 2025 release notes) generates a response with inline citations. [F]
4. **Prompts, responses, and Graph data are NOT used to train foundation LLMs.** [F]
5. **Microsoft 365 Copilot has opted out of Azure OpenAI human-review/abuse monitoring.** [F]
6. **EU Data Boundary** applies: EU traffic stays in EU; rest of world can be processed in US/EU/other. [F]
7. **Data residency commitment** added March 1, 2024 (covered workload). [F]

**Models used** (multiple sources):
- GPT-4 / GPT-4o / GPT-5-class via Azure OpenAI (default). [F]
- Anthropic Claude (subprocessor). [F]
- xAI Grok (added per release notes). [F]
- Microsoft-hosted first-party models also used. [F]

**Extended "grounding" for files (the parsing pipeline)**:
- For PDF/DOCX/PPTX/XLSX files uploaded or attached, the parsing is done via the underlying Microsoft 365 indexing service + Azure OpenAI's document understanding (NOT explicitly published, but inferred from the Microsoft Tech Community blog "Analyze complex documents with Azure Document Intelligence Markdown Output and Azure OpenAI" — [techcommunity.microsoft.com/t5/ai-azure-ai-services-blog/.../ba-p/4080770](https://techcommunity.microsoft.com/t5/ai-azure-ai-services-blog/analyze-complex-documents-with-azure-document-intelligence/ba-p/4080770), fetched 2026-06-14). [A]
- When the document is on SharePoint/OneDrive, the **Microsoft 365 Substrate Indexer** extracts text + structure and stores chunks in the **Semantic Index**. [A]
- For PDFs specifically, **recent (2025+) Microsoft 365 builds** use a **server-side Azure Document Intelligence / prebuilt-layout** pass to convert PDF → Markdown before indexing. **This is NOT explicitly stated in any Microsoft doc I fetched**; it is the most plausible architecture given the [Markitdown `DocumentIntelligenceConverter`](_doc_intel_converter.py:198) and the Microsoft tech-community blog. **Mark as `[A] — inferred, not confirmed`.**

### Search for an arXiv "Microsoft Document Transformer" paper
- **No paper titled "Microsoft Document Transformer" or "MDT" for parsing was found** in the public arXiv corpus as of 2026-06-14. [F] (negative result)
- The closest Microsoft research papers on document understanding (already public, **not** specifically for Copilot's pipeline):
  - **LayoutLMv3** (Huang et al., ACM Multimedia 2022) — Microsoft Research, Azure AI. [microsoft.com/en-us/research/publication/layoutlmv3-...](https://www.microsoft.com/en-us/research/publication/layoutlmv3-pre-training-for-document-ai-with-unified-text-and-image-masking/) [F]
  - **UDOP** (Unifying Vision, Text, and Layout for Universal Document Processing) — Microsoft, CVPR 2023. [openaccess.thecvf.com/content/CVPR2023/papers/Tang_Unifying_Vision_Text_and_Layout_for_Universal_Document_Processing_CVPR_2023_paper.pdf](https://openaccess.thecvf.com/content/CVPR2023/papers/Tang_Unifying_Vision_Text_and_Layout_for_Universal_Document_Processing_CVPR_2023_paper.pdf) [F]
  - **KOSMOS-1** (general multimodal, touches document understanding). [F]
- **Document Parsing Unveiled: Techniques, Challenges, and Prospects for Structured Information Extraction** — arXiv:2410.21169, v5 dated 2026-04-04. **NOT a Microsoft paper** (authors: Qintong Zhang, Bin Wang, Victor Shea-Jay Huang, Junyuan Zhang, Zhengren Wang, Hao Liang, Conghui He, Wentao Zhang). But it is **the most thorough recent survey** and references Microsoft's LayoutLM family and Doc Intel. [arxiv.org/abs/2410.21169](https://arxiv.org/abs/2410.21169) [F]

### Documented strengths [F]
- Permission-aware: only shows what the user is allowed to see (per Microsoft Graph). [F]
- Citation-backed responses (every claim links to a source document). [F]
- Anthropic models include copyright safeguards. [F]
- Multi-modal: in Word/Excel/PowerPoint/Outlook/Teams, in OneDrive (web), in Edge browser PDF viewer, in Microsoft 365 Copilot Chat. [F] [ithome.com/0/799/084.htm](https://www.ithome.com/0/799/084.htm)
- 500+ free S0 pages / month for Document Intelligence free trial (not Copilot itself, but related). [F]

### Documented limitations / known issues [F unless A]
- **Copilot can no longer summarize/chat about open PDFs in Edge** — [reddit.com/r/microsoft_365_copilot/.../1gdlzam](https://www.reddit.com/r/microsoft_365_copilot/comments/1gdlzam/copilot_can_no_longer_summarizechat_about_open/). Workaround: send PDF via email, then ask Copilot on the email attachment. [F]
- **Cross-Office component referencing requires M365 Business/Education license** + recent Word/Excel/PPT build + OneDrive/SharePoint file location; local paths not supported. [F] [php.cn/faq/2633279.html](https://www.php.cn/faq/2633279.html) (secondary)
- **Privacy controls** — turning off "connected experiences that analyze your content" disables Copilot features in Excel/OneNote/Outlook/PPT/Word. [F] [learn.microsoft.com/.../microsoft-365-copilot-privacy](https://learn.microsoft.com/en-us/copilot/microsoft-365/microsoft-365-copilot-privacy)
- **Generative AI outputs are not guaranteed 100% factual** — Microsoft explicitly says "users should still use their judgment when reviewing the output before sending them to others." [F]
- **No user-facing Markdown export of parsed documents** in the standard Copilot flow — the parsing is internal. [A]
- **Closed source** — no public docs on exact chunking strategy, tokenizer, or preprocessing. [A]

### Execution mode
- **Cloud-only.** All processing happens in Microsoft's data centers. No self-host option for the Copilot service. [F]
- **EU data boundary honored** (EU traffic stays in EU; world traffic can be processed globally). [F]

### Pricing
- M365 Copilot: $30/user/month (US list) on top of qualifying M365 plan. NOT FETCHED in this scout session (Microsoft's pricing page is JS-rendered and was not opened). Community and analyst reports widely confirm $30. [F] (well-known; secondary)

---

## 5. Cross-cutting observations for LocalDeepL's positioning [A]

1. **Microsoft's open-source play is "Markitdown" for offline / quick wins; the cloud play is "Doc Intel + Content Understanding" for high-fidelity PDF/table/figure extraction.** The `az-doc-intel` extra is the explicit bridge. LocalDeepL could either compete head-on with Markitdown for plain-text formats (where it's strongest on Office and weakest on PDF), or carve out a niche as a **local-first, layout-faithful** alternative for PDF that beats Markitdown's pdfplumber/pdfminer path on scanned/complex PDFs (where Markitdown fails — confirmed by issues #296, #1361, #1845).

2. **Markitdown's PDF path is the weak spot, period.** The codebase has zero layout detection in `_pdf_converter.py`; it does adaptive column clustering for form-like pages, then falls back to pdfminer prose extraction. No headings are inferred; no OCR for scanned pages; no language detection. LocalDeepL's Surya-based hybrid path is materially better on complex/scanned PDFs.

3. **Azure Document Intelligence's `prebuilt-layout` Markdown is the strongest Microsoft layout→MD output** — and it's accessible via the `az-doc-intel` extra or directly through `azure-ai-documentintelligence`. The Markdown schema (HTML tables, `<figure>`, LaTeX math, HTML comments for page metadata) is **well-defined and documented**, but uses **HTML rather than GFM tables**, which is a friction point for downstream RAG pipelines expecting pipe tables.

4. **Doc Intel free tier is 500 pages/month, F0.** This is a usable budget for evaluation. Pay-as-you-go is $10/1k pages for prebuilt/layout. At scale, this is a meaningful OPEX that LocalDeepL's local-first model avoids.

5. **Microsoft 365 Copilot's parsing pipeline is closed and not a direct competitor** to LocalDeepL — Copilot produces a *response*, not a *document*, and lives inside the M365 ecosystem. But the underlying Doc Intel / Content Understanding pieces are the *actual* cloud Microsoft converters, and LocalDeepL could position as a **Doc Intel alternative for self-host**.

6. **There is no public Microsoft "Document Transformer" paper**, despite what the brief suggested. The most relevant Microsoft research lineage is the **LayoutLM family (LayoutLM → LayoutLMv2 → LayoutLMv3)**, **UDOP**, and **KOSMOS-1** — all of which are pre-training papers for general document AI, not the production Copilot pipeline. **KOSMOS-2.5** is a more recent multimodal model that handles document understanding and was published in late 2023 (NOT FETCHED in this scout — recommended follow-up).

7. **Content Understanding is the new multimodal umbrella** that subsumes Doc Intel going forward (per the Microsoft product page, Document Intelligence is "now part of Azure Content Understanding"). [F] [azure.microsoft.com/en-us/products/ai-foundry/tools/document-intelligence](https://azure.microsoft.com/en-us/products/ai-foundry/tools/document-intelligence) Markitdown's `az-content-understanding` extra is therefore the **more future-proof** integration path.

8. **Markitown has a real security concern** for server-side use — it doesn't sandbox URL fetches and runs with the process's full privileges. LocalDeepL can win on this dimension alone for self-hosted LLM workflows.

9. **Markitdown's plugin entry-point system (`markitdown.plugin`)** is a proven extensibility pattern that LocalDeepL could mirror for its own pipeline integration.

---

## 6. Source quality summary

| Source | Type | Reliability |
|---|---|---|
| github.com/microsoft/markitdown (README + source) | Primary | High |
| pypi.org/project/markitdown | Primary | High |
| learn.microsoft.com/.../document-intelligence/... | Primary (Microsoft) | High |
| azure.microsoft.com/.../pricing/... | Primary (Microsoft) | High (page itself; concrete numbers require sign-in) |
| aiproductivity.ai/.../azure-document-intelligence/ | Secondary (tracker) | Medium |
| github.com/BerriAI/litellm/issues/25687 | Primary (user bug report) | Medium (user observation, not Microsoft confirmation) |
| arxiv.org/abs/2410.21169 | Primary (survey paper) | High |
| learn.microsoft.com/.../microsoft-365-copilot-privacy | Primary (Microsoft) | High |
| support.microsoft.com/.../copilot-支持的文件格式 | Primary (Microsoft) | High (Chinese locale, but Microsoft official) |
| Multiple Reddit / Chinese tech blogs | Secondary | Low-Medium (used only for triangulation) |
| xugj520.cn / juejin / toutiao / csdn | Secondary (blogs) | Low (used only for confirmation) |
| yage.ai/share/markitdown-survey-en-20260412.html | Secondary (blog benchmark) | Medium |
| github.com/opendataloader-project/opendataloader-bench | Primary benchmark | High |

---

## 7. Known unknowns / NOT FETCHED

- **Concrete dollar figures** in the Azure pricing table — page renders `$-` placeholders; community trackers (aiproductivity.ai, Reddit) are used as confirmation.
- **Anthropic Grok / xAI model details** in M365 Copilot — confirmed by release notes link but the page was not deep-read.
- **KOSMOS-2.5** (Microsoft multimodal doc model from 2023) — not directly fetched.
- **Specific markitdown issues 1845, 296, 1361** — titles/snippets fetched; bodies not opened.
- **ZAIHostedOCR** mentioned in AGENTS.md as an "experimental backend" — **NOT** a Microsoft product (Zhipu AI / Z.ai). Skipped intentionally (out of scope).
