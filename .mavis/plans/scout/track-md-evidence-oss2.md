# OSS Anything-to-Markdown Landscape — Part 2 (Evidence)

> Subagent scout for LocalDeepL's Anything-to-Markdown landscape study.
> Second half of the OSS list: **Marker**, **PDFMiner**, **PyMuPDF4LLM**, **markitdown ecosystem / adjacent tools** (Zerox, LlamaParse, Docling, MinerU, Markitdown).
>
> All inline sources are cited as `[Author, URL, fetched YYYY-MM-DD]` or `[file_path:line_number]`. `[F]` = factual, `[A]` = analytical / my reading. Conflicts surfaced inline. Findings as of 2026-06-14.

---

## 1. Marker (datalab-to/marker) — the single closest competitor to LocalDeepL

### 1.1 Identity, vendor, license, output formats

| Field | Value | Source |
| --- | --- | --- |
| Current repo | **`datalab-to/marker`** (VikParuchuri/marker is a redirect alias) | [datalab-to/marker, GitHub, fetched 2026-06-14] |
| Vendor | Datalab (Vik Paruchuri's company) | [datalab-to/marker README, GitHub, fetched 2026-06-14] |
| Latest version | **v1.10.2**, released **2026-01-31** | [datalab-to/marker Releases, GitHub, fetched 2026-06-14] |
| PyPI package | `marker-pdf` (v1.10.2) | [pyproject.toml line 4, GitHub, fetched 2026-06-14] |
| Code license | **GPL-3.0-or-later** | [pyproject.toml line 6, GitHub, fetched 2026-06-14] |
| Model license | **Modified AI Pubs Open RAIL-M** (free for research / personal / startups under $2M revenue **OR** under $2M total funding) — see §1.7 for hard restrictions | [MODEL_LICENSE, GitHub, fetched 2026-06-14] |
| Output formats | **Markdown, JSON, HTML, chunks** (chunks is a flat list of top-level blocks with full HTML per block, designed for RAG) | [README "Output Formats", GitHub, fetched 2026-06-14] |
| Stars / forks | **36.1k stars / 2.5k forks** | [datalab-to/marker, GitHub, fetched 2026-06-14] |
| Releases | 71 total | [datalab-to/marker Releases, GitHub, fetched 2026-06-14] |

### 1.2 Input coverage (provider registry)

Marker dispatches by file type via `marker/providers/registry.py`:

| Extension family | Provider | Source |
| --- | --- | --- |
| Image (PNG/JPG/…) | `ImageProvider` (line 7) | [marker/providers/registry.py:7, GitHub, fetched 2026-06-14] |
| PDF | `PdfProvider` (line 8) | [marker/providers/registry.py:8, GitHub, fetched 2026-06-14] |
| DOCX | `DocumentProvider` (line 9) | [marker/providers/registry.py:9, GitHub, fetched 2026-06-14] |
| XLSX | `SpreadSheetProvider` (line 10) | [marker/providers/registry.py:10, GitHub, fetched 2026-06-14] |
| PPTX | `PowerPointProvider` (line 11) | [marker/providers/registry.py:11, GitHub, fetched 2026-06-14] |
| EPUB | `EpubProvider` (line 12) | [marker/providers/registry.py:12, GitHub, fetched 2026-06-14] |
| HTML | `HTMLProvider` (line 41, fallback if `.html` ext or any HTML tags detected by BeautifulSoup) | [marker/providers/registry.py:41, GitHub, fetched 2026-06-14] |

**Audio / video** — **not supported** by Marker's local providers. The `--disable_image_extraction` + `--use_llm` mode can replace images with LLM-generated descriptions but that is not the same as ASR for audio. `[A]` Inference from absence in `registry.py` + import list.

### 1.3 Quality claims

From README "Marker" section (claims only — benchmark numbers in §1.6):

- "Converts PDF, image, PPTX, DOCX, XLSX, HTML, EPUB files **in all languages**" — note: language coverage is bound to Surya OCR's language list; for non-OCR text extraction it works in any language. [datalab-to/marker README, GitHub, fetched 2026-06-14]
- "Formats tables, forms, equations, inline math, links, references, and code blocks" [datalab-to/marker README, GitHub, fetched 2026-06-14]
- "Extracts and saves images" [datalab-to/marker README, GitHub, fetched 2026-06-14]
- "Removes headers/footers/other artifacts" [datalab-to/marker README, GitHub, fetched 2026-06-14]
- Markdown output includes: image links, formatted tables, **embedded LaTeX equations fenced with `$$`**, code fenced with triple backticks, **superscripts for footnotes** [datalab-to/marker README "Markdown" section, GitHub, fetched 2026-06-14]
- HTML output mirrors markdown; images via `<img>`, equations via `<math>`, code in `<pre>` [datalab-to/marker README "HTML" section, GitHub, fetched 2026-06-14]
- Tables detection accuracy: **0.816 (marker) / 0.907 (marker w/ `--use_llm`)** on FinTabNet, vs gemini 2.0 flash 0.829. Source: README Table Conversion table. `[A]`
- JSON output: tree-structured with `block_type` enum values (28 types: Line, Span, Char, FigureGroup, TableGroup, ListGroup, PictureGroup, Page, Caption, Code, Figure, Footnote, Form, Equation, Handwriting, TextInlineMath, ListItem, PageFooter, PageHeader, Picture, SectionHeader, Table, Text, TableOfContents, Document, ComplexRegion, TableCell, Reference). [marker/schema/__init__.py:5-33, GitHub, fetched 2026-06-14]
- Chunks format: flat list with full HTML per block, designed for RAG. [datalab-to/marker README "Chunks" section, GitHub, fetched 2026-06-14]

CJK / RTL — `[A]` The README does not specifically call out CJK or RTL; surya-ocr's language list covers many languages and Marker says it works in "all languages" for non-OCR text. Surrogate tables in README benchmark list (book page, financial, letter, etc.) but no explicit multi-script claim.

### 1.4 Execution mode

- **Local CPU / GPU / MPS** — all three explicitly supported: "Works on GPU, CPU, or MPS" [datalab-to/marker README, GitHub, fetched 2026-06-14]
- **No-GPU / low-VRAM** — default deviceless: torch device auto-detected, override via `TORCH_DEVICE=cuda`. Throughput: 0.18 s/page, 3.17 GB VRAM, 43.42 s/document on Think Python book; projected **122 pages/s on H100** (README Throughput table).
- **Managed cloud (Datalab platform)** — yes, paid: "Our managed platform runs our latest open source model, **Chandra** — higher accuracy than Marker, with zero data retention by default, SOC 2 Type 2, and custom BAAs." "Get started with **$5 in free credits**" [datalab-to/marker README, GitHub, fetched 2026-06-14]
- **Self-host commercial** — requires a paid commercial license (see §1.7).
- **Optional LLM assistance** — `--use_llm` accepts Gemini / Vertex / Ollama / Claude / OpenAI / Azure OpenAI as the LLM provider. README: "By default, it uses `gemini-2.0-flash`." [datalab-to/marker README, GitHub, fetched 2026-06-14]
- **API server** — `marker_server --port 8001` exposes a FastAPI server. README: "Note that this is not a very robust API, and is only intended for small-scale use." [datalab-to/marker README, GitHub, fetched 2026-06-14]

### 1.5 Architecture / pipeline

The internals (README "Internals"):

> "The core units of marker are: Providers at `marker/providers` (extract info from a source), Builders at `marker/builders` (generate initial document blocks), Processors at `marker/processors` (process specific blocks, e.g. table formatter), Renderers at `marker/renderers` (render output), Schema at `marker/schema`, Converters at `marker/converters` (run the full pipeline)."

#### Entry point: `PdfConverter` (deep dive)

[marker/converters/pdf.py, GitHub, fetched 2026-06-14]

```python
# marker/converters/pdf.py
class PdfConverter(BaseConverter):
    use_llm: bool = False
    default_processors: Tuple[BaseProcessor, ...] = (
        OrderProcessor,
        BlockRelabelProcessor,
        LineMergeProcessor,
        BlockquoteProcessor,
        CodeProcessor,
        DocumentTOCProcessor,
        EquationProcessor,
        FootnoteProcessor,
        IgnoreTextProcessor,
        LineNumbersProcessor,
        ListProcessor,
        PageHeaderProcessor,
        SectionHeaderProcessor,
        TableProcessor,
        LLMTableProcessor,         # --use_llm
        LLMTableMergeProcessor,    # --use_llm
        LLMFormProcessor,          # --use_llm
        TextProcessor,
        LLMComplexRegionProcessor,  # --use_llm
        LLMImageDescriptionProcessor,  # --use_llm
        LLMEquationProcessor,       # --use_llm
        LLMHandwritingProcessor,    # --use_llm
        LLMMathBlockProcessor,      # --use_llm
        LLMSectionHeaderProcessor,  # --use_llm
        LLMPageCorrectionProcessor, # --use_llm
        ReferenceProcessor,
        BlankPageProcessor,
        DebugProcessor,
    )
    default_llm_service: BaseService = GoogleGeminiService
```

- **`__init__`** resolves LLM service and artifact_dict, initializes the processor list, picks `MarkdownRenderer` by default. [marker/converters/pdf.py:101-138, GitHub, fetched 2026-06-14]
- **`build_document`** uses four builders: `LayoutBuilder` → `LineBuilder` → `OcrBuilder` (surya) → `StructureBuilder`, then runs all processors. [marker/converters/pdf.py:163-176, GitHub, fetched 2026-06-14]
- The pipeline order is: layout detect → OCR (surya) → line/text build → structure → processors → render.
- The `__call__` method is the `provider → builders → processors → renderer` composition. [marker/converters/pdf.py:178-184, GitHub, fetched 2026-06-14]

#### Models used (`marker/models.py`)

[marker/models.py, GitHub, fetched 2026-06-14]

```python
from surya.foundation import FoundationPredictor
from surya.detection import DetectionPredictor
from surya.layout import LayoutPredictor
from surya.ocr_error import OCRErrorPredictor
from surya.recognition import RecognitionPredictor
from surya.table_rec import TableRecPredictor
```

Five surya models: **layout, recognition (text OCR), table_rec, detection (text-line detection), ocr_error**. These are loaded once via `create_model_dict()` and injected as `artifact_dict` into converters. `[A]` Note: this is essentially the same dependency stack that **LocalDeepL uses** (Surya for detection + OCR + layout, with a VLM post-processor).

#### Plugin points

README explicitly enumerates extension points:
- Override **processors** for custom formatting
- Add a new **renderer** for new output formats
- Add a new **provider** for new input formats
- "Processors and renderers can be directly passed into the base `PDFConverter`, so you can specify your own custom processing easily." [datalab-to/marker README "Internals", GitHub, fetched 2026-06-14]

#### Other converters

- `TableConverter` (table-only)
- `OCRConverter` (OCR-only)
- `ExtractionConverter` (structured extraction with Pydantic schema)
- `MarkerServer` (FastAPI)

[marker/converters/pdf.py imports, GitHub, fetched 2026-06-14]

#### `BaseConverter.resolve_dependencies` (DI pattern)

[marker/converters/__init__.py:13-39, GitHub, fetched 2026-06-14] — uses reflection to inject `artifact_dict` and `config` into each processor/renderer. This is a clean DI pattern that LocalDeepL's processor chain could mirror.

`BaseExtractor` at [marker/extractors/__init__.py:11-39, GitHub, fetched 2026-06-14] provides a concurrency-bounded base for LLM-backed structured extractors (`max_concurrency: int = 3`).

### 1.6 Documented strengths AND limitations

**Strengths (from README benchmarks):**
- Heuristic 95.67 / LLM-judge 4.24 (overall conversion, "marker" plain). vs. llamaparse 84.24/3.98, mathpix 86.43/4.16, docling 86.71/3.70. [README "Overall PDF Conversion" table, GitHub, fetched 2026-06-14]
- "Marker heuristic" outperforms all other tools on every per-document-type category in the table (scientific paper, book, presentation, financial, letter, engineering, legal, newspaper, magazine). Form is the weakest at 88.0/3.85.
- Throughput 0.18 s/page on H100 (projected 122 pages/s), 3.17 GB VRAM. [README "Throughput" table, GitHub, fetched 2026-06-14]
- GPU + CPU + MPS support.

**Documented limitations (from README "Limitations"):**

> "PDF is a tricky format, so marker will not always work perfectly. Here are some known limitations that are on the roadmap to address:
> - Very complex layouts, with nested tables and forms, may not work
> - Forms may not be rendered well
> Note: Passing the `--use_llm` and `--force_ocr` flags will mostly solve these issues."

[datalab-to/marker README "Limitations", GitHub, fetched 2026-06-14]

**Troubleshooting tips from README "Troubleshooting":**
- `--use_llm` to improve quality (Gemini by default).
- `--force_ocr` to re-OCR garbled digital text.
- `TORCH_DEVICE` to override device.
- Reduce worker count or split long PDFs if OOM.

`[A]` Note: Marker's stated limitation on "complex layouts with nested tables and forms" matches exactly the kind of input LocalDeepL is best at (per the existing `HybridEngine` and `GroundedEngine`). The fact that Marker punted to LLM is significant: LocalDeepL's deterministic + grounded approach is genuinely a different point in the design space.

### 1.7 Commercial / pricing reality

`pyproject.toml` declares code as GPL-3.0-or-later, but the README "Commercial usage" section is more nuanced:

> "Our model weights use a modified AI Pubs Open Rail-M license (free for research, personal use, and startups under $2M funding/revenue) and our code is GPL. For broader commercial licensing or to remove GPL requirements, visit our pricing page [here](https://www.datalab.to/pricing)."

[datalab-to/marker README, GitHub, fetched 2026-06-14]

The MODEL_LICENSE file Attachment A spells out the hard limits:

> "5(a) for any purpose if You (your employer, or the entity you are affiliated with) generated more than two million US Dollars ($2,000,000) in gross revenue in the prior year, except where Your Use is limited to personal use or research purposes; (b) ... has raised more than two million US dollars ... in total equity or debt funding ...; (c) for any purpose if You ... provides or otherwise makes available any product or service that competes with any product or service offered by or made available by Licensor or any of its affiliates."

[MODEL_LICENSE Attachment A, GitHub, fetched 2026-06-14]

**Critical for LocalDeepL positioning:** any commercial product using Marker weights above the $2M threshold must buy a commercial license from Datalab. Datalab also has a managed platform that competes directly (`Chandra` model, batch service, "200M+ pages per week"). `[A]` This is a meaningful competitive threat: a well-funded competitor that owns the same upstream models (Surya) AND sells a hosted alternative.

### 1.8 What this means for LocalDeepL

- **Direct architectural overlap**: both use Surya (detection + layout + recognition) as the primary layout pipeline, both have a per-page hybrid path (local heuristic + VLM), both output markdown + structured JSON. `[A]`
- **Marker's strong claims**: 95.67 heuristic on Common-Crawl-derived benchmark, 122 pages/s on H100, 28-element block schema with bbox. LocalDeepL's `DocumentResult` IR (§AGENTS.md `core/document.py`) has parallel coverage (`TableCell`, `Reference`, `TextInlineMath` etc.) but is not benchmarked against Marker's set.
- **Marker's weak spots (LocalDeepL's wedge)**: complex nested tables, forms, deterministic non-LLM OCR for production. LocalDeepL's `dense_mode="auto"` + DP alignment + Surya OCR is a different trade-off than Marker's "heuristic + LLM-fallback."
- **Licensing**: GPL code + Open RAIL-M weights with $2M cap → for any mid-market or enterprise customer, Marker is not a free lunch. LocalDeepL's permissive local-only story is a real differentiator.
- **Missing in Marker**: audio/video transcription, ASR pipeline, RTSP/multimodal — Marker is strictly text/visual document.

---

## 2. PDFMiner (pdfminer.six)

### 2.1 Identity, vendor, license, output formats

| Field | Value | Source |
| --- | --- | --- |
| Repo | `pdfminer/pdfminer.six` | [pdfminer.six GitHub, fetched 2026-06-14] |
| Vendor | Community fork of the original PDFMiner; maintained by `pdfminer` org on GitHub | [pdfminer.six GitHub, fetched 2026-06-14] |
| License | **MIT** | [pdfminer.six GitHub repo nav, fetched 2026-06-14] |
| Latest release | **20260107** (Jan 7, 2026) | [pdfminer.six GitHub Releases, fetched 2026-06-14] |
| Stars | **7.0k** | [pdfminer.six GitHub, fetched 2026-06-14] |
| Primary output | **Pure text + coordinates**, with optional hOCR / HTML / XML / tagged-XML converters | [pdfminer/high_level.py docstring, GitHub, fetched 2026-06-14] |
| 1.0+ Python support | 3.10+ | [pdfminer.six README, GitHub, fetched 2026-06-14] |

### 2.2 Input coverage

**PDF only.** No DOCX/PPTX/XLSX/HTML/EPUB/images. PDF-1.7 spec ("well, almost"). [pdfminer.six README, GitHub, fetched 2026-06-14]

### 2.3 Quality claims (from README "Features")

- Written entirely in Python (pure-Python, no C extensions).
- "Parse, analyze, and convert PDF documents."
- "Extract content as text, images, html or hOCR."
- "Support for PDF-1.7 specification (well, almost)."
- "**Support for CJK languages and vertical writing.**" ← explicit
- "Support for various font types (Type1, TrueType, Type3, and CID) support."
- "Support for extracting embedded images (JPG, PNG, TIFF, JBIG2, bitmaps)."
- "Support for decoding various compressions (ASCIIHexDecode, ASCII85Decode, LZWDecode, FlateDecode, RunLengthDecode, CCITTFaxDecode)."
- "Support for RC4 and AES encryption."
- "Support for AcroForm interactive form extraction."
- "Table of contents extraction."
- "Tagged contents extraction."
- "**Automatic layout analysis.**"

[pdfminer.six README, GitHub, fetched 2026-06-14]

### 2.4 Execution mode

- **Pure-local CPU** only. No GPU. No cloud. No SaaS.
- `pdf2txt.py` CLI ships in `tools/`.
- `from pdfminer.high_level import extract_text` is the canonical API.
- No mention of Docker or hosted option.

### 2.5 Architecture / pipeline (deep dive)

[pdfminer/high_level.py, GitHub, fetched 2026-06-14]

The public API is just three functions:

- `extract_text_to_fp(...)` — main workhorse; opens PDF, builds `PDFResourceManager`, picks a converter (`TextConverter` / `HTMLConverter` / `XMLConverter` / `HOCRConverter` / `TagExtractor`) based on `output_type`, runs `PDFPageInterpreter.process_page(page)` per page, then `device.close()`. [pdfminer/high_level.py:32-137, GitHub, fetched 2026-06-14]
- `extract_text(...)` — string-returning convenience wrapper that internally uses `TextConverter` with a `StringIO` sink. [pdfminer/high_level.py:140-176, GitHub, fetched 2026-06-14]
- `extract_pages(...)` — yields `LTPage` layout objects via `PDFPageAggregator`. [pdfminer/high_level.py:179-211, GitHub, fetched 2026-06-14]

`LAParams` is the layout-analysis parameter object with `line_overlap`, `char_margin`, `word_margin`, `line_margin`, `boxes_flow`, `detect_vertical`, `all_texts`. `boxes_flow` ranges from `-1.0` (horizontal only) to `+1.0` (vertical only); `None` disables advanced layout analysis and falls back to bottom-left position. [pdfminer/layout.py:52-92, GitHub, fetched 2026-06-14]

The layout object hierarchy in `pdfminer/layout.py`:

- `LTItem` (root) → `LTComponent` (with bbox) → `LTCurve` (Bezier), `LTLine`, `LTRect`, `LTImage`, `LTAnno` (virtual char for spacing), `LTChar` (real char with matrix/fontname/adv).
- `LTContainer` → `LTTextContainer` (collects text) → `LTTextLine` → `LTTextLineHorizontal` / `LTTextLineVertical` (CJK vertical writing), `LTTextBox` → `LTTextBoxHorizontal` / `LTTextBoxVertical`.
- `LTTextGroup` (multi-column merge via heap-merge of nearby boxes — interesting algorithm) → `LTTextGroupLRTB` / `LTTextGroupTBRL`.
- `LTFigure` (PDF Form XObjects — recursive), `LTPage` (top-level per-page container).

[pdfminer/layout.py:115-535, GitHub, fetched 2026-06-14]

**Reading-order reconstruction** uses a heap-based `group_textboxes` (lines 472-535) that pair-wise merges the closest text boxes into a hierarchical group. CJK vertical writing supported via separate `LTTextLineVertical`/`LTTextBoxVertical` classes (`detect_vertical=True`). [pdfminer/layout.py:342-389, GitHub, fetched 2026-06-14]

### 2.6 Documented strengths AND limitations

**Strengths:**
- Pure-Python, MIT, no GPU required. Very low barrier to install.
- Best-in-class font + encoding + CJK + RTL support — has been the reference implementation for 10+ years.
- Lossless extraction with coordinates; can be the layout backbone for any higher-level converter.
- AcroForm + encrypted PDF + Tagged PDF support.

**Limitations (implicit / `[A]`):**
- Text-only. No images beyond `ImageWriter` extraction. No "smart" table detection, no math, no code fences, no semantic structure.
- The output is plain text or hOCR/HTML/XML with positions — the consumer has to build a markdown formatter on top.
- No audio/video/image inputs.
- `output_type` is `text` in practice: `converters.HTMLConverter` etc. are available but the docstring notes "Only 'text' works properly" for some legacy paths (line 47). [pdfminer/high_level.py:47, GitHub, fetched 2026-06-14]
- No LLM integration.
- Maintenance: "limited maintainer availability" per `CONTRIBUTING.md` quote. [pdfminer.six README, GitHub, fetched 2026-06-14]

### 2.7 Pricing

Free. MIT. No SaaS.

### 2.8 What this means for LocalDeepL

`[A]` PDFMiner is a **dependency, not a competitor**, for any modern anything-to-markdown product. It is often used as the digital-text layer (e.g. Marker's `pdftext` dep, PyMuPDF4LLM's digital-text branch). LocalDeepL could route digital-text pages through pdfminer.six instead of `pdftext` to gain MIT-licensed, conservative fallback text — but PyMuPDF is already a better choice in most cases (faster, more accurate C engine vs. pure-Python). `[A]`

---

## 3. PyMuPDF4LLM (pymupdf/PyMuPDF4LLM)

### 3.1 Identity, vendor, license, output formats

| Field | Value | Source |
| --- | --- | --- |
| Repo | `pymupdf/PyMuPDF4LLM` | [pymupdf4llm GitHub, fetched 2026-06-14] |
| Vendor | Artifex Software, Inc. (maintainer of MuPDF) | [pymupdf4llm GitHub README, fetched 2026-06-14] |
| License | **Dual: AGPL v3 OR commercial** | [pymupdf4llm GitHub README, fetched 2026-06-14; setup.py LICENSE, GitHub, fetched 2026-06-14] |
| Latest release | **v0.3.4** on 2026-02-14 (note: also published as 1.27.2.x "PyMuPDF family" version) | [pymupdf4llm GitHub Releases, fetched 2026-06-14; CHANGES.md, GitHub, fetched 2026-06-14] |
| Stars / forks | **1.8k / 226** | [pymupdf4llm GitHub, fetched 2026-06-14] |
| Output formats | **Markdown, JSON, plain text** (with `page_chunks=True`, per-page dicts) | [pymupdf4llm README, fetched 2026-06-14] |

### 3.2 Input coverage (from README "Supported document formats")

| Format | Notes |
| --- | --- |
| **PDF** | Full support, scanned pages via OCR |
| **XPS / OXPS** | Text + image extraction |
| **EPUB / MOBI / FB2** | Chapter-aware |
| **Images** (PNG, JPG, TIFF…) | Single-page with optional OCR |
| **Office** (DOCX, XLSX, PPTX, HWP) | Requires **PyMuPDF Pro** (paid) |

[pymupdf4llm README, GitHub, fetched 2026-06-14]

> "This automatically installs or upgrades [PyMuPDF](https://pypi.org/project/PyMuPDF/) & [PyMuPDF Layout](https://pypi.org/project/pymupdf-layout/) as a dependency."

[pymupdf4llm README, GitHub, fetched 2026-06-14]

**Office formats are gated behind a paid PyMuPDF Pro** — the OSS module is PDF + EPUB + image-centric.

### 3.3 Quality claims

README "Markdown" output spec:
- "GitHub-compatible Markdown with: `#` – `######` headings derived from font size hierarchy"
- "`**bold**`, `*italic*`, `` `monospace` `` inline formatting"
- "Fenced code blocks for detected code spans"
- "GFM pipe tables for detected table regions"
- "`![alt](path)` image references for extracted images"
- "Ordered and unordered lists"

[pymupdf4llm README "Output format reference", GitHub, fetched 2026-06-14]

**Hybrid OCR strategy** is a documented differentiator:

> "PyMuPDF4LLM applies OCR selectively — only where it is actually needed. Rather than blindly sending every page through an OCR engine (slow and counterproductive on clean text), or naively skipping OCR on mixed documents (leaving scanned regions unreadable), it analyses each page first and makes a targeted decision. This selective approach typically reduces OCR processing time by around 50%."

> "Four conditions that can lead to OCR the page: 1) Too many illegible characters (�) 2) Presence of (many) vector graphics that simulate text 3) Presence of a previous OCR text layer 4) Presence of images containing text."

[pymupdf4llm README "Hybrid OCR Strategy", GitHub, fetched 2026-06-14]

This is **directly analogous to LocalDeepL's sparse vs dense per-page mode** (with `dense_mode="auto"`). `[A]`

**Languages**: CJK fonts are supported via MuPDF, but no specific RTL claim in the README. Default OCR language is `eng`; configurable to `eng+fra` style. [pymupdf4llm README, GitHub, fetched 2026-06-14]

**Footnotes, hyperlinks, code**: code fences are detected, but no explicit footnote-preservation claim. Hyperlinks are not specifically called out in the markdown output (no `[text](url)` is shown in the example). `[A]`

### 3.4 Execution mode

- **Pure-local CPU/GPU**. "No GPU, no Cloud, no Tokens required." [pymupdf4llm README, GitHub, fetched 2026-06-14]
- **No LLM integration**. The library deliberately does not call any VLM/LLM.
- **C engine** under the hood (MuPDF is C; PyMuPDF is the Python binding).
- Both Layout Mode and legacy mode available. Layout Mode is the new default since v0.2.0 (2025-era): "Greatly improved table detection; Support of list item hierachy levels; Detection of page headers and footers; Improved detection of text paragraphs, titles and section headers." [CHANGES.md, GitHub, fetched 2026-06-14]
- No hosted SaaS, no API server shipped.

### 3.5 Architecture / pipeline

[pymupdf4llm/src/__init__.py, GitHub, fetched 2026-06-14]

```python
# pymupdf4llm/src/__init__.py (top of file)
import pathlib
import pymupdf
from .versions_file import VERSION, VERSION_TUPLE
import pymupdf4llm.helpers.pymupdf_rag
import pymupdf4llm.helpers.document_layout
_pvt = tuple(map(int, pymupdf.__version__.split(".")))
if _pvt != VERSION_TUPLE:
    raise ImportError(...)  # hard version lock

def use_layout(yes): ...  # toggle legacy vs layout

def to_markdown(doc, *, ...):  # dispatcher
    if _use_layout:
        return _layout_to_markdown(*args, **kwargs)
    else:
        return pymupdf4llm.helpers.pymupdf_rag.to_markdown(*args, **kwargs)
```

[pymupdf4llm/src/__init__.py:7-184, GitHub, fetched 2026-06-14]

The layout mode signature is rich (excerpted):

```python
def _layout_to_markdown(
    doc,
    *,
    dpi=150,
    embed_images=False,
    filename="",
    footer=True,
    force_ocr=False,
    force_text=True,
    header=True,
    ignore_code=False,
    image_format="png",
    image_path="",
    ocr_dpi=300,
    ocr_function=None,
    ocr_language="eng",
    page_chunks=False,
    page_height=None,
    page_separators=False,
    pages=None,
    page_width=612,
    show_progress=False,
    use_ocr=True,
    write_images=False,
    **kwargs,
):
    parsed_doc = pymupdf4llm.helpers.document_layout.parse_document(
        doc, ...,
    )
    return parsed_doc.to_markdown(...)
```

[pymupdf4llm/src/__init__.py:73-119, GitHub, fetched 2026-06-14]

The flow is: `pymupdf.open(file)` → `document_layout.parse_document(...)` → `parsed_doc.to_markdown() | to_text() | to_json()`.

Layout mode requires the proprietary **`pymupdf_layout`** package (closed-source, not AGPL — see CHANGES.md line 0.2.0):

> "The PyMuPDF-Layout package is not open-source and has its own license, which is different from PyMuPDF4LLM. It also is dependent on a number of other, fairly large packages like onnxruntime, numpy, sympy and OpenCV... We therefore keep the use of the layout feature optional. To activate PyMuPDF-Layout support the following import statement must be included before importing PyMuPDF4LLM itself..."

[CHANGES.md v0.2.0, GitHub, fetched 2026-06-14]

OCR engine selection (from CHANGES.md v1.27.2.2):
- Tesseract (built-in via PyMuPDF)
- RapidOCR (`rapidocr_onnxruntime`)
- Whichever is installed is picked automatically; both can be combined for higher accuracy.

[pymupdf4llm CHANGES.md, GitHub, fetched 2026-06-14]

`LlamaMarkdownReader` integration: a thin wrapper that converts `to_markdown()` output into LlamaIndex `Document` objects. [pymupdf4llm/src/__init__.py:178-184, GitHub, fetched 2026-06-14]

OCRMode enum ([pymupdf4llm/src/ocr/__init__.py, GitHub, fetched 2026-06-14]): 5 modes — NEVER, SELECT_REMOVING_OLD, SELECT_PRESERVING_OLD, ALWAYS_REMOVING_OLD, ALWAYS_PRESERVING_OLD. This is a well-thought-out model of the OCR-decision space.

### 3.6 Documented strengths AND limitations

**Strengths (README quotes):**
- "**10× faster** on standard cloud instances" (vs. vision-LLM extraction)
- "**Up to 250× lower** infrastructure cost"
- "Matches or exceeds vision-LLM accuracy on table detection"
- "Smart OCR processes only the regions that need it, reducing OCR time by ~50%"

[pymupdf4llm README "Performance", GitHub, fetched 2026-06-14]

**Limitations:**
- Office formats (DOCX/XLSX/PPTX) **require paid PyMuPDF Pro** — not in the OSS path. [pymupdf4llm README, GitHub, fetched 2026-06-14]
- The advanced Layout Mode requires the closed-source `pymupdf_layout` package (extra dep, separate license). [pymupdf4llm CHANGES.md v0.2.0, GitHub, fetched 2026-06-14]
- No LLM/VLM hookup; table merging across pages and complex-form recovery are out of scope.
- The README "When to use" of the layout mode shows it's not bulletproof: "1) No text at all — image-covered pages 2) Garbled text" are the only auto-OCR triggers; "Hybrid OCR Strategy" lists the four conditions above.
- `[A]` Issue: no public benchmarks vs Marker or Docling on the same harness.

### 3.7 Pricing

- **AGPL v3** (free for OSS) OR paid commercial license from Artifex. [pymupdf4llm README, GitHub, fetched 2026-06-14]
- **PyMuPDF Pro** (paid) needed for Office + HWP formats. [pymupdf4llm README, GitHub, fetched 2026-06-14]
- **PyMuPDF Layout** (closed-source, separate license) for advanced table/header detection. [pymupdf4llm CHANGES.md, GitHub, fetched 2026-06-14]
- Demo hosted at `demo.pymupdf.io`.

### 3.8 What this means for LocalDeepL

- PyMuPDF4LLM is the **performance reference** for "no-LLM, CPU-only, fast markdown." If a customer is happy with that fidelity, it's hard to beat on cost.
- Its hybrid OCR pattern is exactly what LocalDeepL should articulate; PyMuPDF4LLM's README is a great explainer source.
- `[A]` PyMuPDF4LLM is the **single biggest threat to LocalDeepL's "structured OCR without LLM" pitch** for pure-PDF cases, because it's actively maintained by a commercial PDF vendor, has 250× cost claims, and is already on LlamaIndex.
- **However**: it does not handle DOCX/XLSX/PPTX/audio/video without paid Pro, and it has no LLM fallback for hard cases. LocalDeepL's broader input coverage (image, audio transcripts via VLM) and grounded VLM fallback are genuine differentiators.

---

## 4. Markitdown Ecosystem & Adjacent Tools

The "anything to markdown" space has a clear topology: each tool is either a **broad-format dispatcher** (Markitdown, Docling, MinerU), a **specialized engine** (Marker, PyMuPDF4LLM, PDFMiner, Zerox), or a **cloud API** (LlamaParse). LocalDeepL is in the second bucket with broad inputs.

### 4.1 microsoft/markitdown (the OSS bellwether)

#### Identity

| Field | Value | Source |
| --- | --- | --- |
| Repo | `microsoft/markitdown` | [markitdown GitHub, fetched 2026-06-14] |
| Vendor | Microsoft (AutoGen team) | [markitdown GitHub, fetched 2026-06-14] |
| License | **MIT** | [markitdown GitHub repo nav, fetched 2026-06-14] |
| Latest release | **v0.1.6** on 2026-05-26 | [markitdown GitHub Releases, fetched 2026-06-14] |
| Stars / forks | **153k / 10.6k** | [markitdown GitHub, fetched 2026-06-14] |
| Built by | AutoGen Team | [markitdown GitHub, fetched 2026-06-14] |

#### Input coverage (README "MarkItDown currently supports")

- PDF, PowerPoint, Word, Excel
- **Images (EXIF metadata and OCR)**
- **Audio (EXIF metadata and speech transcription)**
- HTML, CSV, JSON, XML
- **ZIP files (iterates over contents)**
- **YouTube URLs**
- **EPubs**
- "... and more!"

[markitdown GitHub README, GitHub, fetched 2026-06-14]

#### Architecture

[markitdown/_markitdown.py, GitHub, fetched 2026-06-14]

Built on a **priority-ordered converter registry**. The `MarkItDown` class instantiates a list of `ConverterRegistration(converter, priority)` objects and dispatches via `accepts(file_stream, stream_info) -> convert(file_stream, stream_info)`. Built-in converters include: `PlainTextConverter`, `HtmlConverter`, `RssConverter`, `WikipediaConverter`, `YouTubeConverter`, `IpynbConverter`, `BingSerpConverter`, `PdfConverter`, `DocxConverter`, `XlsxConverter`, `XlsConverter`, `PptxConverter`, `ImageConverter`, `AudioConverter`, `OutlookMsgConverter`, `ZipConverter`, `EpubConverter`, `CsvConverter`, plus optional `DocumentIntelligenceConverter` and `ContentUnderstandingConverter` for Azure. [markitdown/_markitdown.py:24-30, GitHub, fetched 2026-06-14]

`magika` (Google's content-type sniffer) is used to identify file types from stream content, so Markitdown can dispatch correctly even without an extension. [markitdown/_markitdown.py:152-160 + `_get_stream_info_guesses`, GitHub, fetched 2026-06-14]

**Plugin system** — entry-points based: any pip package exposing a `markitdown.plugin` entry-point is auto-loaded. Markitdown explicitly advertises the `#markitdown-plugin` hashtag for discoverability. [markitdown README "Plugins", GitHub, fetched 2026-06-14]

A new **markitdown-ocr** plugin uses LLM vision to OCR images inside PDF/DOCX/PPTX/XLSX: "The `markitdown-ocr` plugin adds OCR support to PDF, DOCX, PPTX, and XLSX converters, extracting text from embedded images using LLM Vision — the same `llm_client` / `llm_model` pattern that MarkItDown already uses for image descriptions. No new ML libraries or binary dependencies required." [markitdown README "markitdown-ocr Plugin", GitHub, fetched 2026-06-14]

A **Azure Content Understanding** integration supports audio + video with structured YAML front matter fields. [markitdown README "Azure Content Understanding", GitHub, fetched 2026-06-14]

#### Quality

The README is explicit that the output is "meant to be consumed by text analysis tools — and may not be the best option for high-fidelity document conversions for human consumption." [markitdown README "MarkItDown", GitHub, fetched 2026-06-14]

This is a **deliberate positioning**: lightweight, format-agnostic, LLM-friendly. Not a layout-fidelity leader.

#### Execution mode

- **Pure-local**, no GPU. Optional cloud backends: Azure Document Intelligence, Azure Content Understanding.
- `pip install 'markitdown[all]'` for all formats; otherwise opt-in per-format extras.
- 3rd-party plugin system.

#### Pricing

Free. MIT. No quota. Cloud backends are pay-per-use Azure SKUs.

#### What this means for LocalDeepL

- Markitdown is the **de-facto OSS "anything to markdown" reference**. 153k stars. Heavy AutoGen integration.
- Markitdown's design (priority converter registry + magika content sniffing + plugin entry-points) is a clean pattern LocalDeepL could borrow for its `OCRPipeline.choose_processor_for(...)` style dispatch.
- Markitdown's *deliberate* acceptance of lower layout fidelity is the *exact* positioning LocalDeepL rejects; LocalDeepL's hybrid Surya+grounded path is a **higher-fidelity alternative** for users who care.
- Markitdown is also a *channel*: it can route to markitdown-ocr (LLM-OCR) or to Document Intelligence for higher quality, so its local-only path is the floor, not the ceiling.

---

### 4.2 Zerox (`getomni-ai/zerox`)

#### Identity

| Field | Value | Source |
| --- | --- | --- |
| Repo | `getomni-ai/zerox` | [zerox GitHub, fetched 2026-06-14] |
| Vendor | Omni (getomni.ai) | [zerox GitHub README, fetched 2026-06-14] |
| License | **MIT** | [zerox GitHub, fetched 2026-06-14] |
| Latest release | v0.1.06 (Dec 18, 2024) | [zerox GitHub Releases, fetched 2026-06-14] |
| Stars / forks | **12.2k / 847** | [zerox GitHub, fetched 2026-06-14] |
| Languages | TS 67.6% / Python 27.2% | [zerox GitHub, fetched 2026-06-14] |
| Hosted demo | `getomni.ai/ocr-demo` | [zerox GitHub README, fetched 2026-06-14] |

#### Input coverage

```
PDF, doc, docx, odt, ott, rtf, txt, html, htm, xml, wps, wpd,
xls, xlsx, ods, ots, csv, tsv,
ppt, pptx, odp, otp
```

[zerox README "Supported File Types", GitHub, fetched 2026-06-14]

For non-PDF/non-image, Zerox uses `libreoffice` → PDF → image. For PDF, it uses `graphicsmagick` (Node) or `poppler` (Python) to rasterize.

#### Quality claims

Zerox is **vision-LLM-only by design**: it does not have its own OCR. The README's tagline:

> "Documents are meant to be a visual representation after all. With weird layouts, tables, charts, etc. The vision models just make sense!"

[zerox GitHub README, GitHub, fetched 2026-06-14]

#### Execution mode

- **Cloud-only for the heavy lifting**: requires an OpenAI / Azure OpenAI / Anthropic / AWS Bedrock / Google Gemini / Vertex API key. [zerox README "Supported Models", GitHub, fetched 2026-06-14]
- **Local preprocessing** (libreoffice/poppler/graphicsmagick) — pure local.
- **No GPU needed**, no model download.

#### Architecture / pipeline

[zerox node-zerox/src/index.ts, GitHub, fetched 2026-06-14]

```ts
// Per-page loop (paraphrased from node-zerox/src/index.ts)
for each imagePath in imagePaths:
  if maintainFormat: pass priorPage + image to LLM
  if extractOnly:    pass image directly
  else:              pass image only
```

Key design points:
- **Maintain-format** mode is sequential (slower) and threads the previous page's markdown as context to keep formatting consistent across pages. [zerox README, GitHub, fetched 2026-06-14]
- **Per-page concurrency** via `pLimit(concurrency=10)` (Node) / asyncio (Python). [zerox node-zerox/src/index.ts ~line 200, GitHub, fetched 2026-06-14]
- **Tesseract** is used for *orientation correction* (cheap local OCR to find page rotation) before sending to the vision LLM. [zerox node-zerox/src/index.ts, GitHub, fetched 2026-06-14]
- Structured extraction via **JSON Schema** (Node side has it; Python side doesn't per README feature matrix). [zerox README "Data Extraction", GitHub, fetched 2026-06-14]

#### Documented strengths / limitations

**Strengths:**
- Trivially simple: `zerox({filePath, model, modelProvider})` → markdown.
- "Dead simple" tagline; very low integration effort.
- Multi-provider LLM support out of the box (OpenAI/Azure/Anthropic/Bedrock/Gemini/Vertex).
- Hosted demo for non-developers.

**Limitations:**
- **Cost**: every page = one vision-LLM call. At scale, this is the most expensive option in the landscape.
- **No offline mode** (always requires a cloud LLM).
- **No table-formula-aware math**: tables are reconstructed by the LLM, not by a table structure model, so accuracy depends on model choice.
- Latest release is **Dec 2024** — not heavily maintained. `[A]` Inference from release date.

#### Pricing

- **OSS**: free.
- **Hosted demo**: $5 free credits, then pay per use (Omni).

#### What this means for LocalDeepL

- Zerox is a **positioning reference for "vision-LLM-only"**, not a direct competitor for LocalDeepL's hybrid local-first story.
- However, Zerox's `maintainFormat` (passing prior page context) is a clever pattern LocalDeepL could selectively adopt for the **VLM post-processor** in the `GroundedEngine`. `[A]`
- A user who is happy paying per page for high accuracy will pick Zerox + GPT-4o; a user who cares about offline / cost / privacy picks LocalDeepL.

---

### 4.3 Docling (`docling-project/docling`)

#### Identity

| Field | Value | Source |
| --- | --- | --- |
| Repo | `docling-project/docling` (moved from `DS4SD/docling`) | [docling GitHub, fetched 2026-06-14] |
| Vendor | **IBM Research Zurich** (Deep Search team); LF AI & Data Foundation hosted | [docling GitHub README, fetched 2026-06-14] |
| License | **MIT** (codebase); individual model licenses per package | [docling GitHub, fetched 2026-06-14] |
| Latest release | **v2.102.1** on 2026-06-12 | [docling GitHub Releases, fetched 2026-06-14] |
| Stars / forks | **61.5k / 4.3k** | [docling GitHub, fetched 2026-06-14] |
| Tech report | arXiv:2408.09869 | [docling GitHub README, fetched 2026-06-14] |
| Releases | 183 total | [docling GitHub, fetched 2026-06-14] |

#### Input coverage (README "Features")

> "🗂️ Parsing of multiple document formats incl. **PDF, DOCX, PPTX, XLSX, HTML, EPUB, WAV, MP3, WebVTT, email formats (EML, MSG), images (PNG, TIFF, JPEG, ...), LaTeX, DocLang, plain text**, and more"

[docling GitHub README, GitHub, fetched 2026-06-14]

This is the **broadest input coverage of any OSS converter we surveyed** (Marker + PDF + image, plus audio (WAV/MP3), video captions (WebVTT), email, LaTeX, DocLang, etc.). LocalDeepL's audio coverage is via VLM transcription; Docling has a dedicated `AsrPipeline` for native ASR.

#### Architecture / pipeline (deep dive)

[docling/document_converter.py, GitHub, fetched 2026-06-14]

The core entry point is `DocumentConverter`, which is a **format-keyed dispatch table**:

```python
class DocumentConverter:
    def __init__(self, allowed_formats=None, format_options=None):
        self.format_to_options = {
            format: (
                _get_default_option(format=format)
                if (custom_option := normalized_format_options.get(format)) is None
                else custom_option
            )
            for format in self.allowed_formats
        }
        self.initialized_pipelines = {}
```

[docling/document_converter.py:331-348, GitHub, fetched 2026-06-14]

The default-options table (`_get_default_option`) is a textbook example of backend-per-format dispatch:

```python
format_to_default_options = {
    InputFormat.CSV: CsvFormatOption(),               # SimplePipeline + CsvDocumentBackend
    InputFormat.XLSX: ExcelFormatOption(),             # SimplePipeline + MsExcelDocumentBackend
    InputFormat.DOCX: WordFormatOption(),              # SimplePipeline + MsWordDocumentBackend
    InputFormat.PPTX: PowerpointFormatOption(),        # SimplePipeline + MsPowerpointDocumentBackend
    InputFormat.MD: MarkdownFormatOption(),
    InputFormat.ASCIIDOC: AsciiDocFormatOption(),
    InputFormat.HTML: HTMLFormatOption(),
    InputFormat.XML_USPTO: PatentUsptoFormatOption(),
    InputFormat.XML_JATS: XMLJatsFormatOption(),
    InputFormat.XML_DOCLANG: XMLDocLangFormatOption(),
    InputFormat.XML_XBRL: XBRLFormatOption(),
    InputFormat.METS_GBS: FormatOption(pipeline_cls=StandardPdfPipeline, backend=MetsGbsDocumentBackend),
    InputFormat.IMAGE: ImageFormatOption(),            # StandardPdfPipeline + ImageDocumentBackend
    InputFormat.PDF: PdfFormatOption(),                # StandardPdfPipeline + DoclingParseDocumentBackend
    InputFormat.JSON_DOCLING: ...,
    InputFormat.AUDIO: AudioFormatOption(),            # AsrPipeline + NoOpBackend
    InputFormat.VTT: FormatOption(pipeline_cls=SimplePipeline, backend=WebVTTDocumentBackend),
    InputFormat.LATEX: LatexFormatOption(),
    InputFormat.EMAIL: EmailFormatOption(),
    InputFormat.EPUB: EpubFormatOption(),
}
```

[docling/document_converter.py:213-281, GitHub, fetched 2026-06-14]

A `FormatOption` ties a **backend** (format-specific extraction) to a **pipeline** (page-level AI processing):

- **SimplePipeline** for non-PDF formats (DOCX, XLSX, PPTX, MD, HTML, EPUB, CSV, etc.) — fast, no AI.
- **StandardPdfPipeline** for PDF and images — full multi-stage ML pipeline.
- **AsrPipeline** for audio — automatic speech recognition.

The **StandardPdfPipeline** is a sophisticated 5-stage threaded pipeline:

[docling/pipeline/standard_pdf_pipeline.py, GitHub, fetched 2026-06-14]

```python
class StandardPdfPipeline(ConvertPipeline):
    def _create_run_ctx(self) -> RunContext:
        preprocess = PreprocessThreadedStage(...)  # PagePreprocessingModel
        ocr = ThreadedPipelineStage(name="ocr", model=self.ocr_model, batch_size=opts.ocr_batch_size, ...)
        layout = ThreadedPipelineStage(name="layout", model=self.layout_model, batch_size=opts.layout_batch_size, ...)
        table = ThreadedPipelineStage(name="table", model=self.table_model, batch_size=opts.table_batch_size, ...)
        assemble = ThreadedPipelineStage(name="assemble", model=self.assemble_model, ...)

        # wire stages
        output_q = ThreadedQueue(opts.queue_max_size)
        preprocess.add_output_queue(ocr.input_queue)
        ocr.add_output_queue(layout.input_queue)
        layout.add_output_queue(table.input_queue)
        table.add_output_queue(assemble.input_queue)
        assemble.add_output_queue(output_q)
```

[docling/pipeline/standard_pdf_pipeline.py:572-606, GitHub, fetched 2026-06-14]

Key engineering choices:

- **Bounded queues** with `ThreadedQueue` (custom `Queue.put` with `not_full`/`not_empty` conditions, explicit `close()`).
- **Per-run deterministic run-id** to avoid `id()` collisions after GC.
- **Bounded back-pressure**: producers block on full queues; downstream close propagates so stages terminate deterministically.
- **Timeout enforcement** via `document_timeout` (each page beyond timeout is marked `is_failed=True` with `RuntimeError("document timeout exceeded")`).
- **Per-page partial success**: status becomes `PARTIAL_SUCCESS` if any page was attempted, `FAILURE` if none, `SUCCESS` otherwise. [docling/pipeline/standard_pdf_pipeline.py:763-784, GitHub, fetched 2026-06-14]
- **Heavy model init once per pipeline instance**, then thread-safe read-only access in workers.

This pipeline design is **directly relevant to LocalDeepL** — LocalDeepL's `HybridEngine` runs sequentially per page; Docling's design shows that bounded, multi-stage, threaded pipelines with back-pressure are a known, robust pattern for production. `[A]`

The pipeline enrichments include: `CodeFormulaVlmModel` (code + formula), `ReadingOrderModel`, `PageAssembleModel`, `PagePreprocessingModel`. [docling/pipeline/standard_pdf_pipeline.py:486-498, GitHub, fetched 2026-06-14]

#### Quality claims

README "Features" highlights:
- "Advanced PDF understanding incl. **page layout, reading order, table structure, code, formulas, image classification**, and more"
- "Unified, expressive `DoclingDocument` representation format"
- "Various export formats and options, including **Markdown, HTML, WebVTT, DocLang, DocTags and lossless JSON**"
- "Support of several application-specific XML schemas incl. DocLang, USPTO patents, JATS articles, and XBRL financial reports"
- "Plug-and-play integrations incl. LangChain, LlamaIndex, Crew AI & Haystack"
- "Extensive OCR support for scanned PDFs and images"
- "Support of several Visual Language Models (**GraniteDocling**)"
- "Audio support with Automatic Speech Recognition (ASR) models"
- "Connect to any agent using the **MCP server**"

[docling GitHub README, GitHub, fetched 2026-06-14]

Docling ships its own **VLM** (GraniteDocling 258M), positioning it to compete on VLM-fronted document understanding with Marker+LLM and LlamaParse. `[A]`

#### Execution mode

- **Local CPU / GPU** ("🔒 Local execution capabilities for sensitive data and air-gapped environments" — README)
- **Multiple pipelines**: `simple` (CPU-only), `standard` (GPU-accelerated ML), `vlm` (GraniteDocling)
- CLI + Python API + LangChain/LlamaIndex/Crew AI/Haystack + MCP server
- **"10+ domestic AI chip support"** for vlm-engine (Ascend, Cambricon, Enflame, MetaX, Moore Threads, Kunlunxin, Iluvatar, Hygon, Biren, T-Head) — see MinerU §4.4 below; this is part of a trend in the Chinese OSS ecosystem.

#### Documented strengths / limitations

**Strengths (from Marker's own benchmark table, quoted in Marker's README):**
- "docling" scores 86.71 heuristic / 3.70 LLM-judge overall — **lower than Marker (95.67 / 4.24)** but similar to llamaparse and mathpix.
- Per-doc table: docling is 92.1/3.72 on scientific paper, 90.0/3.65 on books (vs. Marker 96.7/4.35, 97.2/4.16).
- On forms: docling 68.4/3.40 (vs. Marker 88.0/3.85) — significantly worse.
- [datalab-to/marker README, GitHub, fetched 2026-06-14]

**Limitations (implicit):**
- IBM backing → big-org review cadence, 183 releases, conservative API changes. `[A]`
- Heavy stack: integrates a dozen model backends, factory pattern for plugins, threaded pipeline — first-time install is large.
- VLM mode (GraniteDocling) is small (258M params) so it may not match Marker's gemini-2.0-flash or GPT-4o on hard cases.

#### Pricing

- **OSS**: free, MIT.
- No SaaS / managed offering from docling-project.

#### What this means for LocalDeepL

- Docling is the **most direct architectural analog**: format-keyed backend dispatch + pipeline-based processing + per-page threaded queues + per-stage batching + explicit partial-success semantics.
- LocalDeepL's existing `OCRPipeline` + `BaseConverter`-style design (per AGENTS.md) is a subset of Docling's surface area. The **threaded multi-stage pipeline** is a known production pattern LocalDeepL should consider if it wants to scale throughput. `[A]`
- Docling's broader format coverage (XBRL, METS/GBS, JATS, USPTO, ASR, WebVTT, email) is a long tail that LocalDeepL can safely ignore unless a customer asks.
- The MCP-server integration is becoming table-stakes for AI-first products.

---

### 4.4 MinerU (`opendatalab/MinerU`)

#### Identity

| Field | Value | Source |
| --- | --- | --- |
| Repo | `opendatalab/MinerU` | [MinerU GitHub, fetched 2026-06-14] |
| Vendor | **OpenDataLab** (Shanghai AI Lab ecosystem; InternLM pre-training origin) | [MinerU GitHub README, fetched 2026-06-14] |
| License | **Custom "MinerU Open Source License" (Apache 2.0-based)** since v3.1.0 (2026-04-18); prior versions were AGPLv3 | [MinerU GitHub README changelog, GitHub, fetched 2026-06-14] |
| Stars / forks | **67.5k / 5.7k** | [MinerU GitHub, fetched 2026-06-14] |
| Tech reports | arXiv:2409.18839, 2509.22186, 2604.04771 | [MinerU GitHub, fetched 2026-06-14] |
| Latest release | "3.3" (2026-06-11) per README changelog | [MinerU GitHub README, GitHub, fetched 2026-06-14] |

#### Input coverage

> "Converts PDF · DOCX · PPTX · XLSX · Images · Web pages into structured Markdown / JSON · VLM+OCR dual engine · 109 languages"

[MinerU GitHub README header, GitHub, fetched 2026-06-14]

Native (not via libreoffice roundtrip): **PDF, image, DOCX, PPTX, XLSX**. v3.0.0 (2026-03-29) added native DOCX; v3.1.0 (2026-04-18) added native PPTX and XLSX. [MinerU GitHub README changelog, GitHub, fetched 2026-06-14]

#### Quality claims

> "109-language OCR recognition. Automatic detection of scanned PDFs and garbled PDFs. Cross-page table merging, image/chart analysis (vlm-engine), seal text recognition, vertical text support, interline formula numbering recognition."

[MinerU GitHub README, GitHub, fetched 2026-06-14]

Hybrid engine: "pipeline" (fast, no hallucination, runs on CPU or GPU) + "vlm-engine" (high accuracy, supports vLLM / LMDeploy / mlx) + "hybrid-engine" (high accuracy, native text extraction, low hallucination). [MinerU GitHub README, GitHub, fetched 2026-06-14]

v3.3 (2026-06-11) introduces a new **`effort` parsing-strength parameter** for the Hybrid backend with two levels: `medium` (default, faster) and `high` (image/chart analysis enabled). Reported gains: "Linux: about 80% faster for text PDF scenarios and about 35% faster for OCR scenarios; Windows: about 90% faster / 45%; macOS: about 220% faster / 50%". [MinerU GitHub README changelog 2026/06/11, GitHub, fetched 2026-06-14]

#### Execution mode

- **Local CPU / GPU** (multiple backends)
- **VLM acceleration via vLLM / LMDeploy / mlx** for the vlm-engine
- **GPU vendor support**: "10+ domestic AI chip support" (Ascend, Cambricon, Enflame, MetaX, Moore Threads, Kunlunxin, Iluvatar, Hygon, Biren, T-Head) — Chinese AI silicon coverage is a distinctive feature
- **CLI / FastAPI / Gradio WebUI / Python+Go+TypeScript SDK / Docker / REST API** — full deployment surface
- **mineru-router** for unified multi-service, multi-GPU load balancing
- **mineru.net** hosted offering (no data retention claim; commercial)
- **MCP server** for AI-coding-tool integration (Cursor, Claude Desktop, Windsurf)
- Integrations: LangChain, LlamaIndex, RAGFlow, RAG-Anything, Flowise, Dify, FastGPT

[MinerU GitHub README, GitHub, fetched 2026-06-14]

#### Architecture / pipeline (deep dive)

[mineru/cli/client.py, GitHub, fetched 2026-06-14]

The CLI is an **async orchestration client** that talks to a local-or-remote `mineru-api` FastAPI service:

```python
async def run_orchestrated_cli(
    input_path: Path,
    output_dir: Path,
    method: str,    # "auto" | "txt" | "ocr"
    backend: str,   # "pipeline" | "vlm-engine" | "vlm-http-client" | "hybrid-engine" | "hybrid-http-client"
    effort: str,    # "medium" | "high"  (hybrid only)
    lang: str,
    ...
):
    if api_url is None:
        local_server = LocalAPIServer(extra_cli_args=extra_cli_args)
        base_url = local_server.start()
        server_health = await wait_for_local_api_ready(http_client, local_server)
    ...
    planned_tasks = plan_tasks(documents, backend, processing_window_size=...)
    progress = build_task_execution_progress(planned_tasks)
    concurrency = resolve_submit_concurrency(...)
    failures = await execute_planned_tasks(
        planned_tasks, concurrency,
        task_runner=lambda task: run_planned_task(...)
    )
```

[mineru/cli/client.py:570-650, GitHub, fetched 2026-06-14]

Key design:

- **Task binning** (`plan_pipeline_tasks`): documents are sorted by descending page count and packed into bins up to `processing_window_size` total pages. Each bin becomes one batch submitted to the API. [mineru/cli/client.py:404-451, GitHub, fetched 2026-06-14]
- **Asynchronous task submission with concurrency limit** via `asyncio.Queue` worker pool. [mineru/cli/client.py:526-559, GitHub, fetched 2026-06-14]
- **Live progress renderer** (TTY only) — `[====>     ]` progress bar with frame-step animation, integrated with `loguru` via a custom `LiveAwareStderrSink`. [mineru/cli/client.py:128-227, GitHub, fetched 2026-06-14]
- **Visualization context** is a separate `ProcessPoolExecutor` for layout-span drawing post-processing. [mineru/cli/client.py:330-364, GitHub, fetched 2026-06-14]
- **Sliding-window memory optimization** for long documents (v3.0.0 changelog claim: "ultra-long document parsing has moved from 'requiring manual splitting' to 'stable, scalable, and ready for production'"). [MinerU GitHub README changelog 2026/03/29, GitHub, fetched 2026-06-14]
- **Streaming writes to disk** during batch inference (v3.0.0).

#### Documented strengths / limitations

**Strengths:**
- Three backends (pipeline / vlm / hybrid) with explicit tradeoff matrix.
- 109-language OCR; long-document memory handling.
- The most production-grade deployment surface in this set (router, multi-GPU, MCP, Chinese AI chip support, multi-language SDK).
- License change to Apache-2.0-based in v3.1.0 → lowers adoption friction vs. Marker's RAIL-M + GPL combo.

**Limitations (from changelog caveats + README):**
- v3.0.0 still has "scenarios where the parsing results may fall short of expectations" for complex layouts — recommended to try the online demo first. [MinerU GitHub README, GitHub, fetched 2026-06-14]
- Removed two AGPLv3 models (`doclayoutyolo`, `mfd_yolov8`) and one CC-BY-NC-SA 4.0 model (`layoutreader`) — meaning some prior integrations may not be available. [MinerU GitHub README changelog 2026/03/29, GitHub, fetched 2026-06-14]
- The default `medium` effort disables image/chart analysis. [MinerU GitHub README changelog 2026/06/11, GitHub, fetched 2026-06-14]

#### Pricing

- **OSS**: free, custom license (Apache-2.0-based).
- **mineru.net**: hosted (pay per page, no data retention claim).

#### What this means for LocalDeepL

- MinerU is the **most production-mature OSS anything-to-markdown tool in the survey**, with the deepest deployment story. The async orchestration + binning + sliding-window memory pattern is worth borrowing if LocalDeepL ever offers a long-document API. `[A]`
- MinerU is also the **strongest direct competitor on the PDF+image axis** outside of Marker; its hybrid backend is the same architectural choice LocalDeepL has made.
- The "10+ domestic AI chip support" is unique and irrelevant to LocalDeepL's typical Windows/desktop customer. `[A]`
- MinerU's license is **more permissive than Marker's** (Apache-2.0-ish vs RAIL-M with $2M cap) — important for any vendor considering OSS derivatives.

---

### 4.5 LlamaParse / `run-llama/llama_cloud_services`

#### Identity

| Field | Value | Source |
| --- | --- | --- |
| Repo | `run-llama/llama_cloud_services` | [llama_cloud_services GitHub, fetched 2026-06-14] |
| Vendor | **LlamaIndex / Run Llama** | [llama_cloud_services GitHub, fetched 2026-06-14] |
| License | MIT | [llama_cloud_services GitHub, fetched 2026-06-14] |
| Stars / forks | **4.3k / 471** | [llama_cloud_services GitHub, fetched 2026-06-14] |
| Latest release | `llama-cloud-services-py@0.6.94` on 2026-02-13 | [llama_cloud_services GitHub Releases, fetched 2026-06-14] |

#### Critical note — deprecated

The repo's README has a deprecation banner at the top:

> "**⚠️ DEPRECATION NOTICE**
> This repository and its packages are deprecated and will be maintained until **May 1, 2026**.
> Please migrate to the new packages:
> - **Python**: `pip install llama-cloud>=1.0` ([GitHub](https://github.com/run-llama/llama-cloud-py))
> - **TypeScript**: `npm install @llamaindex/llama-cloud` ([GitHub](https://github.com/run-llama/llama-cloud-ts))
> The new packages provide the same functionality with improved performance, better support, and active development."

[llama_cloud_services GitHub README, GitHub, fetched 2026-06-14]

So the old SDK is EOL by **May 1, 2026** (i.e. ~6 weeks from this report's date). Any LocalDeepL integration pointing at `llama_cloud_services` needs to be on the new `llama-cloud` packages or to a direct API call. `[A]`

#### Execution mode

- **Cloud-only**. LlamaParse is a hosted API at `cloud.llamaindex.ai`; the OSS repo is just a thin SDK wrapper.
- Required because the parsing engine runs proprietary vision-LLM + table models on LlamaIndex's infrastructure.

#### Input coverage

From topics: `pdf, parsing, document, pptx, structured-data, pdf-to-text, pdf-to-excel, tables, docx-to-markdown, document-parser, pdf-document-processor, pdf-to-json, document-parsing, ppt-to-json, pdf-to-markdown, ppt-to-markdown`. [llama_cloud_services GitHub, fetched 2026-06-14]

PDF, DOCX, PPTX. No native XLSX/EPUB/image/audio.

#### Pricing

- **Cloud**: pay per page. Marker's own benchmark table shows it as 23.3s/page at 84.2 heuristic, implying non-trivial cost.
- SDK is MIT.

#### What this means for LocalDeepL

- LlamaParse is the **gold-standard cloud reference**. Any user who is already in the LlamaIndex ecosystem uses it; otherwise they pick a cheaper option.
- The deprecation is a signal that the SDK is churning; LocalDeepL should not invest in tight coupling with this SDK. A direct `requests`/HTTP client to the cloud.llamaindex.ai API is more durable. `[A]`
- LlamaParse is **not a LocalDeepL competitor for offline / private use cases** — it's a complement in the cloud.

---

## 5. Cross-cutting observations (OSS landscape second half)

`[A]` All observations below are mine; not directly fetched but synthesized from the evidence above.

### 5.1 Three architectural patterns for "anything to markdown"

After surveying Marker, PyMuPDF4LLM, Docling, MinerU, Markitdown, Zerox, LlamaParse, the field splits into three:

| Pattern | Who does it | Strength | Weakness |
| --- | --- | --- | --- |
| **A. Local layout/ML pipeline, no LLM** | **PyMuPDF4LLM**, **PDFMiner**, Marker's "plain" mode | Fastest, cheapest, no data exfiltration | Hard on forms / complex layouts / handwriting |
| **B. Local layout/ML + VLM post-processor (hybrid)** | **Marker (--use_llm)**, **LocalDeepL (HybridEngine / GroundedEngine)**, **Docling (vlm pipeline)**, **MinerU (hybrid-engine)** | High accuracy, offline-capable when VLM is local | Cost (if VLM is cloud) or hardware (if VLM is local) |
| **C. VLM-only / pure-vision** | **Zerox**, **LlamaParse** | Trivial integration, best on hard/handwritten/scanned | Highest cost per page, no offline |

**LocalDeepL's choice of A-with-B-fallback (surya + grounded VLM only on hard pages, controlled by `dense_mode="auto"` and `grounded_backend=`)** is the most differentiated of the OSS tools. PyMuPDF4LLM is A-only, Marker defaults to A but encourages B via `--use_llm` (which is a cloud VLM), Docling is mostly A with a small local VLM (GraniteDocling 258M), MinerU has both pipeline and vlm backends.

### 5.2 Common pitfalls in this space (from documented limitations)

- **Forms**: every OSS tool admits weakness on forms. Marker's README: "Forms may not be rendered well." Docling: 68.4/3.40 on forms (vs 88.0/3.85 for Marker). No tool surveyed has a dedicated forms pipeline.
- **Nested tables**: Marker explicitly says "Very complex layouts, with nested tables and forms, may not work." Docling/MinerU are better but still imperfect.
- **Cross-page table merging**: Marker's `LLMTableMergeProcessor` and MinerU v3.0 explicitly call this out; others don't.
- **Long-document memory**: only MinerU (sliding window + streaming writes) and Docling (`document_timeout` + per-page partial success) handle this in their core. LocalDeepL doesn't have a published strategy here. `[A]`

### 5.3 Licenses (decision-relevant for LocalDeepL's vendor picks)

| Project | License | Commercial use note |
| --- | --- | --- |
| Marker | **GPL-3.0 + RAIL-M (models) with $2M cap** | Paid commercial license required for >$2M revenue/funding |
| pdfminer.six | MIT | No restrictions |
| PyMuPDF4LLM | **AGPL v3 OR commercial** | AGPL is viral; commercial license for proprietary SaaS |
| PyMuPDF Layout | **Closed-source, separate license** | Required for advanced mode; bundled with PyMuPDF4LLM |
| markitdown | MIT | No restrictions |
| Zerox | MIT | No restrictions (vision-LLM cost is on the user) |
| Docling | MIT | No restrictions (model licenses separate) |
| MinerU | **MinerU Open Source License (Apache-2.0-based)** | Apache-style, permissive |
| LlamaParse SDK | MIT (cloud) | Cloud usage pay-per-page |

`[A]` Recommendation: any LocalDeepL user with >$2M revenue cannot freely ship Marker's model weights. PyMuPDF4LLM is also risky under AGPL. The MIT-licensed options (Docling, Markitdown, PDFMiner, Zerox) are the safest substrate; MinerU is also safe. Marker is the most popular but most license-encumbered.

### 5.4 Format coverage matrix (synthesized)

| Format | Marker | PDFMiner | PyMuPDF4LLM | Markitdown | Docling | MinerU | Zerox |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PDF | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| DOCX | ✅ | ✗ | 🔒 Pro | ✅ | ✅ | ✅ (v3.0) | ✅ (via libreoffice) |
| XLSX | ✅ | ✗ | 🔒 Pro | ✅ | ✅ | ✅ (v3.1) | ✅ (via libreoffice) |
| PPTX | ✅ | ✗ | 🔒 Pro | ✅ | ✅ | ✅ (v3.1) | ✅ (via libreoffice) |
| HTML | ✅ | ✗ | ✗ | ✅ | ✅ | (web pages) | ✅ |
| EPUB | ✅ | ✗ | ✅ | ✅ | ✅ | ✗ | ✗ |
| Images | ✅ | ✗ | ✅ (single-page) | ✅ (EXIF + OCR) | ✅ | ✅ | ✅ |
| Audio | ✗ | ✗ | ✗ | ✅ (EXIF + ASR) | ✅ (AsrPipeline) | ✗ | ✗ |
| Email (EML/MSG) | ✗ | ✗ | ✗ | ✗ (MSG) | ✅ | ✗ | ✗ |
| LaTeX | ✗ | ✗ | ✗ | ✗ | ✅ | ✗ | ✗ |
| Video captions (WebVTT) | ✗ | ✗ | ✗ | ✗ | ✅ | ✗ | ✗ |
| YouTube URLs | ✗ | ✗ | ✗ | ✅ | ✗ | ✗ | ✗ |
| Patents / JATS / XBRL | ✗ | ✗ | ✗ | ✗ | ✅ | ✗ | ✗ |
| ZIP (iterate) | ✗ | ✗ | ✗ | ✅ | ✗ | ✗ | ✗ |

(Sources: §1.2, §2.2, §3.2, §4.1 input list, §4.3 README, §4.4 header, §4.2 supported list above.)

`[A]` Docling has the broadest; Marker is PDF-centric; PyMuPDF4LLM is PDF+EPUB+image; LocalDeepL's current scope is PDF + image (per `HybridEngine` / `GroundedEngine`); the **audio + email + LaTeX + WebVTT niche is uncontested by Marker/PyMuPDF4LLM/PDFMiner and only Docling serves it locally**.

### 5.5 What LocalDeepL should NOT compete on

- Pure PDF table structure for clean digital PDFs (PyMuPDF4LLM and `pymupdf_layout` are already excellent and free).
- Generic 100+ format dispatcher (Markitdown / Docling have done the integration work; LocalDeepL would be a worse second).
- Cloud-only vision-LLM (Zerox / LlamaParse are entrenched).

### 5.6 What LocalDeepL's wedge should be

`[A]` Synthesizing all evidence above:

1. **Hybrid local-first pipeline with VLM as escape hatch, not as default** — Marker, Docling, and MinerU all do this; LocalDeepL's `dense_mode="auto"` + grounded VLM is the right pattern. The defensible claim is the *triggering* logic.
2. **Free of the GPL/RAIL-M/AGPL encumbrances** — explicitly MIT/Apache-permissive for any company above the $2M cap. This is a real B2B wedge.
3. **Local PDF + image, with optional VLM only for hard pages** — narrower than Docling/MinerU on input coverage but better-tuned. LocalDeepL's `document_processors` in AGENTS.md already lets users selectively turn on extra features.
4. **Per-page dense vs sparse routing** — explicitly LocalDeepL's pattern (per AGENTS.md: `sparse: full-page OCR -> DP alignment` vs `dense: per-box OCR`). This is a uniquely tunable knob that most competitors hard-code.
5. **Windows desktop one-click install** — `install.bat` / `start_app.vbs` is a story no other OSS tool tells well; MinerU has Docker, Docling has Python pip, but neither has a packaged Windows experience. `[A]` Reinforces the user-facing positioning.

### 5.7 Blockers / open questions for the strategy team

1. **`pymupdf_layout` license terms** are not fully public. CHANGES.md says "not open-source and has its own license" — but the link to those terms wasn't fetched. If PyMuPDF4LLM's "advanced mode" is forbidden in commercial use, that strengthens LocalDeepL. **Need to fetch** `https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/` or the `pymupdf-layout` PyPI page.
2. **Marker's $2M cap** — does it apply per entity, per product, or per use? MODEL_LICENSE says "you, your employer, or the entity you are affiliated with." Worth checking with a lawyer.
3. **Docling vs MinerU quality benchmarks** — we have Marker's own benchmark showing docling at 86.71, but no head-to-head Docling-vs-MinerU on a neutral test set. If the strategy team needs to position vs either, this is missing evidence.
4. **Marker "Chandra" model** is the next-generation Datalab model. The README claims it's "higher accuracy than Marker" but the GitHub repo `datalab-to/chandra` returned 404 on the README fetch — meaning either private or the path is different. Worth investigating.

---

## 6. Sources index

| # | Project | URL | Fetched |
| --- | --- | --- | --- |
| 1 | datalab-to/marker README | https://github.com/datalab-to/marker | 2026-06-14 |
| 2 | marker/converters/pdf.py | https://raw.githubusercontent.com/datalab-to/marker/master/marker/converters/pdf.py | 2026-06-14 |
| 3 | marker/models.py | https://raw.githubusercontent.com/datalab-to/marker/master/marker/models.py | 2026-06-14 |
| 4 | marker/converters/__init__.py | https://raw.githubusercontent.com/datalab-to/marker/master/marker/converters/__init__.py | 2026-06-14 |
| 5 | marker/providers/registry.py | https://raw.githubusercontent.com/datalab-to/marker/master/marker/providers/registry.py | 2026-06-14 |
| 6 | marker/schema/__init__.py | https://raw.githubusercontent.com/datalab-to/marker/master/marker/schema/__init__.py | 2026-06-14 |
| 7 | marker/extractors/__init__.py | https://raw.githubusercontent.com/datalab-to/marker/master/marker/extractors/__init__.py | 2026-06-14 |
| 8 | Marker MODEL_LICENSE | https://raw.githubusercontent.com/datalab-to/marker/master/MODEL_LICENSE | 2026-06-14 |
| 9 | Marker pyproject.toml | https://raw.githubusercontent.com/datalab-to/marker/master/pyproject.toml | 2026-06-14 |
| 10 | pdfminer/pdfminer.six | https://github.com/pdfminer/pdfminer.six | 2026-06-14 |
| 11 | pdfminer/high_level.py | https://raw.githubusercontent.com/pdfminer/pdfminer.six/master/pdfminer/high_level.py | 2026-06-14 |
| 12 | pdfminer/layout.py | https://raw.githubusercontent.com/pdfminer/pdfminer.six/master/pdfminer/layout.py | 2026-06-14 |
| 13 | pymupdf/PyMuPDF4LLM | https://github.com/pymupdf/PyMuPDF4LLM | 2026-06-14 |
| 14 | pymupdf4llm/src/__init__.py | https://raw.githubusercontent.com/pymupdf/PyMuPDF4LLM/main/src/__init__.py | 2026-06-14 |
| 15 | pymupdf4llm/src/ocr/__init__.py | https://raw.githubusercontent.com/pymupdf/PyMuPDF4LLM/main/src/ocr/__init__.py | 2026-06-14 |
| 16 | pymupdf4llm setup.py | https://raw.githubusercontent.com/pymupdf/PyMuPDF4LLM/main/setup.py | 2026-06-14 |
| 17 | pymupdf4llm CHANGES.md | https://raw.githubusercontent.com/pymupdf/PyMuPDF4LLM/main/CHANGES.md | 2026-06-14 |
| 18 | microsoft/markitdown | https://github.com/microsoft/markitdown | 2026-06-14 |
| 19 | markitdown _markitdown.py | https://raw.githubusercontent.com/microsoft/markitdown/main/packages/markitdown/src/markitdown/_markitdown.py | 2026-06-14 |
| 20 | getomni-ai/zerox | https://github.com/getomni-ai/zerox | 2026-06-14 |
| 21 | zerox node-zerox/src/index.ts | https://raw.githubusercontent.com/getomni-ai/zerox/main/node-zerox/src/index.ts | 2026-06-14 |
| 22 | docling-project/docling | https://github.com/docling-project/docling | 2026-06-14 |
| 23 | docling/document_converter.py | https://raw.githubusercontent.com/docling-project/docling/main/docling/document_converter.py | 2026-06-14 |
| 24 | docling/pipeline/standard_pdf_pipeline.py | https://raw.githubusercontent.com/docling-project/docling/main/docling/pipeline/standard_pdf_pipeline.py | 2026-06-14 |
| 25 | opendatalab/MinerU | https://github.com/opendatalab/MinerU | 2026-06-14 |
| 26 | mineru/cli/client.py | https://raw.githubusercontent.com/opendatalab/MinerU/master/mineru/cli/client.py | 2026-06-14 |
| 27 | run-llama/llama_cloud_services | https://github.com/run-llama/llama_cloud_services | 2026-06-14 |

---

*End of evidence file. Factual claims are inline-cited; analytical conclusions are marked `[A]`.*
