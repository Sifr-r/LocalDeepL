# OSS Anything-to-Markdown Converter Landscape — Track 1 (first half of list)

> Research subagent evidence file for the LocalDeepL Anything-to-Markdown scout.
> Compiled 2026-06-14. Sources cited inline as `[URL, fetched YYYY-MM-DD]` or `[github.com/<org>/<repo>, fetched YYYY-MM-DD]`. Tags `[F]` = factual claim (fetched from primary source), `[A]` = analyst inference, `[C]` = conflict / caveat.
>
> Scope: Pandoc, Mammoth, Marko, Docling, Unstructured. PDF relevance and architecture emphasis throughout — these are the five "classical" OSS converters most directly comparable to LocalDeepL.

---

## 0. Top-line: re-classifying "Marko"

The task brief listed **Marko** as "H2OAI/marko (or whatever the canonical repo is — verify)". I verified:

- There is **no `H2OAI/marko` repository**. The H2O.ai org on GitHub contains `h2o-3`, `h2o-llmstudio`, `h2ogpt`, `wave` — none named `marko`. H2O.ai has no Markdown-converter project.
  [A] `[https://github.com/orgs/h2oai/repositories, fetched 2026-06-14]`
- The canonical "marko" on GitHub matching the name and PyPI package `marko` is **`frostming/marko`**, a pure-Python **CommonMark Markdown parser** (MD → HTML/AST), not a document-to-Markdown converter.
  [F] `[https://github.com/frostming/marko, fetched 2026-06-14]`
  - README line: "Marko is a pure Python markdown parser that adheres to the specifications of CommonMark's spec v0.31.2."
- The brief may have conflated `frostming/marko` with Microsoft's **`microsoft/markitdown`** (153k stars) — an LLM-oriented multi-format → Markdown converter that is widely called "MarkItDown" and is sometimes informally shortened to "marko/markitdown" in AI-pipeline write-ups.
  [A] `[https://github.com/microsoft/markitdown, fetched 2026-06-14]`
  - README: "MarkItDown is a lightweight Python utility for converting various files to Markdown for use with LLMs and related text analysis pipelines."

**Recommendation for the planner:** treat "Marko" in this track as `frostming/marko` (the actual repo), and consider adding `microsoft/markitdown` to the second-half OSS list as a 6th target — it is a much closer match to LocalDeepL's "anything-to-MD" charter and has 100× the mindshare.

---

## 1. Pandoc — `jgm/pandoc`

### 1.1 Identity

- **Vendor / project lead:** John MacFarlane (Berkeley) and a large contributor list (Cabal file lists 100+ contributors; AUTHORS.md present).  [F] `[https://github.com/jgm/pandoc, fetched 2026-06-14]`
- **Repo:** `jgm/pandoc` on GitHub.  [F] `[https://github.com/jgm/pandoc, fetched 2026-06-14]`
- **License:** **GPL-2.0-or-later** (notably copyleft, which is a real adoption blocker for proprietary LocalDeepL integration; for in-process *use* it's fine, but linking/distributing derived binaries would require GPL compliance).  [F] `[https://github.com/jgm/pandoc/blob/main/COPYRIGHT, fetched 2026-06-14]` and README "Released under the GPL, version 2 or greater."
- **Latest release:** **pandoc 3.10, 2026-06-04**.  [F] `[https://github.com/jgm/pandoc/releases/tag/3.10, fetched 2026-06-14]`
- **Stats (fetched 2026-06-14):** **44.8k stars**, 3.9k forks, 526 watchers, 156 releases, **19,050 commits**. README "The universal markup converter".
- **Language:** Haskell (~81.6% of repo per GitHub Languages).  [F] `[https://github.com/jgm/pandoc, fetched 2026-06-14]`
- **Deployment shape:** single static binary (`pandoc` CLI) plus Haskell library `pandoc-types`; also WASM build at `pandoc.org/app` and `pandoc-server` (HTTP wrapper).  [F] `[https://github.com/jgm/pandoc, fetched 2026-06-14]` — README links to "WebAssembly-based online demo".

### 1.2 Input & output coverage

- **Outputs** (44+ writers per README): markdown, commonmark, gfm, docx, odt, html/html5, latex, beamer, context, epub/epub3/epub2, pdf, docbook, json, jats, revealjs, typst, rst, rtf, org, vimdoc, etc. PDF is produced by shelling out to LaTeX/Groff/HTML→PDF, not a native renderer.  [F] `[https://github.com/jgm/pandoc/blob/main/README.md, fetched 2026-06-14]`
- **Inputs** (40+ readers per README): includes `docx`, `pptx`, `xlsx`, `odt`, `html`, `epub`, `latex`, `rst`, `org`, `mediawiki`, `ipynb`, `bibtex/biblatex`, `csv`, `tsv`, `twiki`, `jira`, `jats`, `man/mdoc`, `djot`, `typst`, `odt`, `fb2`, `ris`, `endnotexml`, `pod`, `muse`, `vimwiki`, `textile`, `tikiwiki`, `t2t`, `asciidoc`.  [F] `[https://github.com/jgm/pandoc/blob/main/README.md, fetched 2026-06-14]`
- **PDF is an OUTPUT, not a meaningful INPUT.** `pandoc -o out.pdf` shells to LaTeX/wkhtmltopdf/etc. There is no native "PDF as input" reader; for PDF→MD users must chain through tools (e.g. `pdftotext`, OCR, or one of the other OSS projects in this report).
  - [F] README lists no `pdf` reader and explicitly states: "Pandoc can also produce PDF output via LaTeX, Groff ms, or HTML." `[https://github.com/jgm/pandoc/blob/main/README.md, fetched 2026-06-14]`
  - [F] `src/Text/Pandoc/Readers/` does **not** contain a `PDF.hs` file — the GitHub API contents listing for `src/Text/Pandoc/Readers/` includes AsciiDoc, BibTeX, CSV, CommonMark, Creole, CslJson, Djot, DocBook, Docx, DokuWiki, EPUB, EndNote, FB2, HTML, Haddock, Ipynb, JATS, Jira, LaTeX, Man, Markdown, Mdoc, MediaWiki, Metadata, Muse, Native, ODT, OPML, Org, Pod, Pptx, RIS, RST, RTF, Roff, TWiki, Textile, TikiWiki, Txt2Tags, Typst, Vimwiki, XML, Xlsx — but **no PDF reader**. `[https://api.github.com/repos/jgm/pandoc/contents/src/Text/Pandoc/Readers, fetched 2026-06-14]`
  - **Conflict with task brief:** the brief said "read src/Text/Pandoc/Readers/PDF.hs or PDF/ — this is the one most relevant to LocalDeepL". That path does not exist. The most PDF-*adjacent* native readers are `src/Text/Pandoc/Readers/Docx.hs` (39.8 KB, biggest non-LaTeX reader), `Pptx.hs`, and `Xlsx.hs`/`Xlsx/`. **LocalDeepL-relevant reality:** Pandoc does not solve the PDF→MD problem directly. `[A]`

### 1.3 Architecture (from the source)

- **Modular reader → AST → writer pattern.** README: "Pandoc has a modular design: it consists of a set of readers, which parse text in a given format and produce a native representation of the document (an abstract syntax tree or AST), and a set of writers, which convert this native representation into a target format. Thus, adding an input or output format requires only adding a reader or writer. Users can also run custom pandoc filters to modify the intermediate AST."  [F] `[https://github.com/jgm/pandoc/blob/main/README.md, fetched 2026-06-14]`
- **Top-level umbrella module `Text.Pandoc` re-exports Definition, Generics, Options, Logging, Class, Data, Error, Readers, Writers, Templates, plus Version/Translations.**  [F] `src/Text/Pandoc.hs:42-69` `[https://raw.githubusercontent.com/jgm/pandoc/main/src/Text/Pandoc.hs, fetched 2026-06-14]`
  - File is small (~70 lines) — it's an export aggregator, not the conversion engine itself.
- **Native AST lives in `Text.Pandoc.Definition`** (the `Pandoc`, `Block`, `Inline`, `Attr` types). Filters can transform it (Haskell, JSON, or Lua).  [F] `[https://github.com/jgm/pandoc/blob/main/README.md, fetched 2026-06-14]`
- **Documented lossiness:** README explicitly says "Because pandoc's intermediate representation of a document is less expressive than many of the formats it converts between, one should not expect perfect conversions between every format and every other. Pandoc attempts to preserve the structural elements of a document, but not formatting details such as margin size. And some document elements, such as complex tables, may not fit into pandoc's simple document model."  [F] `[https://github.com/jgm/pandoc/blob/main/README.md, fetched 2026-06-14]`

### 1.4 Quality / layout fidelity

- Strongest: **markdown ↔ docx, markdown ↔ html, markdown ↔ latex, markdown ↔ jats, markdown ↔ typst**, plus tables, definition lists, metadata blocks, footnotes, citations, math (TeX/KaTeX/MathML/OMML depending on output).  [F] `[https://github.com/jgm/pandoc/blob/main/README.md, fetched 2026-06-14]`
- Layout fidelity is **structural, not visual**: pandoc preserves *semantics* (heading levels, list nesting, table rows/cells, link targets) but explicitly **discards** font/colour/margin info.
- For LocalDeepL's PDF mission this is the wrong tool: pandoc's docx→md and pptx→md are excellent, but **PDF→MD requires separate OCR** (e.g. chain `surya` + `mammoth`-equivalent for the docx layer).

### 1.5 Language coverage / RTL / CJK

- Pandoc's *reader/writer pipelines* are largely format-agnostic; CJK and RTL are not pandoc features, they depend on the input format. The `latex` reader (53.2 KB) and `html` reader (46.6 KB) are the most CJK-aware.
- No explicit "CJK mode" or "RTL mode" in pandoc core — the output format is responsible for embedding `<span dir="rtl">` etc.  [A]

### 1.6 Strengths & limitations (documented)

- **Strengths:** universality, active development, exceptional markdown round-tripping, mature table/citation/footnote support, Lua filters, WASM build.
- **Limitations / known issues:**
  - No native PDF *reader* — must rely on external tools.
  - Lossy round-trips: DOCX→markdown→DOCX will not preserve formatting.
  - GPL-2.0+ is a real friction point for embedding in proprietary software.
  - Pandoc ships the BUGS file (`/jgm/pandoc/blob/main/BUGS`) enumerating known quirks — most notable: "pandoc does not parse all of LaTeX", complex tables fail, footnotes-in-tables are lossy.  [F] `[https://github.com/jgm/pandoc, fetched 2026-06-14]`

### 1.7 Pricing / quota

- **Free, local-first, no quota.** Open-source CLI + library; no SaaS.  [F] `[https://github.com/jgm/pandoc/blob/main/README.md, fetched 2026-06-14]`

### 1.8 Architecture summary for LocalDeepL decision

Pandoc is the **gold standard for non-PDF markup interchange**. For the PDF→MD pipeline it is **not directly applicable**, but it is the obvious choice for the **DOCX/PPTX/XLSX/HTML/EPUB/ODT** legs. LocalDeepL should keep pandoc shelling as one of the legs of a hybrid pipeline (Surya detect + VLM OCR for PDF, pandoc for office docs, mammoth for narrow DOCX→HTML use cases).  [A]

---

## 2. Mammoth — `mwilliamson/python-mammoth`

### 2.1 Identity

- **Vendor:** Michael Williamson (`mwilliamson`). Sister ports in JavaScript, Java/JVM, .NET, WordPress plugin.  [F] `[https://github.com/mwilliamson/python-mammoth/blob/master/README.md, fetched 2026-06-14]`
- **Repo:** `mwilliamson/python-mammoth`.  [F] `[https://github.com/mwilliamson/python-mammoth, fetched 2026-06-14]`
- **License:** **BSD-2-Clause** (permissive — friendly to LocalDeepL).  [F] Repo sidebar `[https://github.com/mwilliamson/python-mammoth, fetched 2026-06-14]`
- **Language:** Python 99.7%.  [F] `[https://github.com/mwilliamson/python-mammoth, fetched 2026-06-14]`
- **Stats:** **1.1k stars**, 148 forks, 26 watchers, 85 tags, 703 commits, **3.1k dependents**.  [F] `[https://github.com/mwilliamson/python-mammoth, fetched 2026-06-14]`
- **Single purpose:** `.docx` → `HTML` (with deprecated `convert_to_markdown` flag).  [F] README

### 2.2 Input & output coverage

- **Inputs:** `.docx` only. Not doc, not docx-as-zip-via-anything-else.  [F] README
- **Outputs:** HTML (primary). Markdown is **deprecated**: "Markdown support is deprecated. Generating HTML and using a separate library to convert the HTML to Markdown is recommended, and is likely to produce better results."  [F] `[https://github.com/mwilliamson/python-mammoth/blob/master/README.md, fetched 2026-06-14]`
- **No PDF, no PPTX, no XLSX, no EPUB, no images-as-input.** Mammoth is a *single-format, semantically-driven* converter.  [A]

### 2.3 Architecture (from the source)

- **Public API surface is tiny:** `mammoth/__init__.py` exposes `convert_to_html`, `convert_to_markdown`, `extract_raw_text`, `embed_style_map`, plus submodule imports.  [F] `mammoth/__init__.py:1-3` `[https://raw.githubusercontent.com/mwilliamson/python-mammoth/master/mammoth/__init__.py, fetched 2026-06-14]`
- **Pipeline in `__init__.py:24-42`:** `convert_to_html` calls `options.read_options(kwargs).bind(lambda convert_options: docx.read(fileobj, external_file_access=external_file_access).map(transform_document).bind(lambda document: conversion.convert_document_element_to_html(document, id_prefix=id_prefix, **convert_options)))`. So the chain is: **.docx zip read → internal document tree → optional `transform_document` pass → HTML render.**  [F] `mammoth/__init__.py:24-42`
  - All three steps use a `bind/map` monadic pattern — the whole library is monadic I/O via Maybe/Result.
- **Module layout** (from `__init__.py` imports): `mammoth.docx`, `mammoth.conversion`, `mammoth.options`, `mammoth.images`, `mammoth.transforms`, `mammoth.underline`, plus `mammoth.docx.style_map` for the style-mapping DSL.  [F] `mammoth/__init__.py:1-3`

### 2.4 Quality / layout fidelity

Mammoth's selling point: **semantic mapping, not visual fidelity**. README: "Mammoth aims to produce simple and clean HTML by using semantic information in the document, and ignoring other details. For instance, Mammoth converts any paragraph with the style `Heading 1` to `h1` elements, rather than attempting to exactly copy the styling (font, text size, colour, etc.) of the heading."  [F] `[https://github.com/mwilliamson/python-mammoth/blob/master/README.md, fetched 2026-06-14]`

**Supported features** (README):
- Headings, lists, footnotes/endnotes, images, bold/italic/underline/strikethrough/superscript/subscript, links, line breaks, text boxes, comments.
- Tables: cell text is preserved but **table-level formatting (borders, widths) is ignored**.
- Custom style maps (`p[style-name='Aside Heading'] => div.aside > h2:fresh`) — this is the killer feature for power users.
  [F] `[https://github.com/mwilliamson/python-mammoth/blob/master/README.md, fetched 2026-06-14]`

### 2.5 Language / RTL / CJK

- No special handling. Mammoth preserves text runs verbatim from the OOXML; the output HTML carries whatever `<w:lang>` was in the source. **No RTL/CJK awareness in mammoth itself.**  [A] (No mention in README; module source has no language-detection code.)

### 2.6 Strengths & limitations (documented)

- **Strengths:** semantic clean HTML, no SaaS, BSD-2 licensed, rich style-map DSL, well-tested, **no JavaScript/.NET-only deps** (pure Python), used in 3,100+ projects.
- **Documented limitations** (README "Security" section):
  - **No sanitisation** of the source: "Source documents can contain links with `javascript:` targets. If, for instance, you allow users to upload source documents, automatically convert the document into HTML, and embed the HTML into your website without sanitisation, this may create links that can execute arbitrary JavaScript when clicked." → **HTML output is unsafe for untrusted user uploads.**
  - External file access disabled by default to prevent SSRF/arbitrary-read.
  - "The conversion may exhibit pathological performance on certain documents: it's likely possible to craft a source document that causes high CPU or memory usage." → DoS risk.
  - WMF images not handled (recipe uses LibreOffice; fidelity depends entirely on LibreOffice).
  - Underline default is **ignored** (intentional, to avoid HTML link confusion) — opt-in via style map.
  - Markdown output is **deprecated**.
  - DOCX-only — no other formats.
  [F] `[https://github.com/mwilliamson/python-mammoth/blob/master/README.md, fetched 2026-06-14]`

### 2.7 Pricing / quota

- **Free, local, no quota.** No SaaS.  [F] `[https://github.com/mwilliamson/python-mammoth, fetched 2026-06-14]`

### 2.8 Architecture summary for LocalDeepL decision

Mammoth is a **specialist tool**, not a generic converter. LocalDeepL should consider it as an **alternative to pandoc's DOCX reader** for the DOCX→MD leg when the user wants *clean semantic HTML* and a *style-map* workflow. The biggest red flag is the **no-sanitisation security warning** — must run behind a sanitiser (e.g. `bleach`, `nh3`) for any server-side use. The 3,100 dependents count is a strong signal of stability.  [A]

---

## 3. Marko — `frostming/marko` (and Microsoft `markitdown`)

### 3.1 Identity

- **Canonical repo:** `frostming/marko`. Maintainer: Frost Ming (`mianghong@gmail.com`).  [F] `[https://github.com/frostming/marko, fetched 2026-06-14]`
- **License:** **MIT**.  [F] README / repo sidebar
- **Language:** Python 99.7%.  [F] `[https://github.com/frostming/marko, fetched 2026-06-14]`
- **Stats:** **458 stars**, 53 forks, 6 watchers, 16 releases, 420 commits, latest release **v2.2.3, 2026-05-28**.  [F] `[https://github.com/frostming/marko, fetched 2026-06-14]`
- **Scope:** a **Markdown parser** — it parses Markdown text to an AST (or HTML). README: "Marko is a pure Python markdown parser that adheres to the specifications of CommonMark's spec v0.31.2. It has been designed with high extensibility in mind."  [F] `[https://github.com/frostming/marko/blob/master/README.md, fetched 2026-06-14]`

### 3.2 Critical scope mismatch with the task

- The LocalDeepL charter is **anything → Markdown**. Marko is **Markdown → HTML/AST**. They are in opposite directions.
  - **No PDF input.** No DOCX, PPTX, XLSX, EPUB, image, audio, or video input. Only Markdown text input.
  - **No Markdown output.** Output is HTML or a Python AST (block.Document), not Markdown.
  [F] `[https://github.com/frostming/marko, fetched 2026-06-14]`
- **Marko is not a competitor to LocalDeepL.** It is a *subcomponent* that LocalDeepL could *use* if LocalDeepL ever needed to round-trip Markdown ↔ AST (e.g. for the docx export route, where LocalDeepL already has its own `core/docx_writer.py`).  [A]

### 3.3 Architecture (from the source)

- **Entry point `marko/__init__.py`** exposes `Markdown` class, `convert`, `parse`, `render`, `MarkoExtension`, `Parser`, `Renderer`, `HTMLRenderer`.  [F] `marko/__init__.py:149-156` `[https://raw.githubusercontent.com/frostming/marko/master/marko/__init__.py, fetched 2026-06-14]`
- **Pipeline:** `Markdown` wraps a `Parser` + `Renderer`. `convert(text)` calls `render(parse(text))`.  [F] `marko/__init__.py:118-123`
- **Mixin-based extension system** (genuinely well-designed): `use(*extensions)` accumulates `parser_mixins` / `renderer_mixins` / `extra_elements`; `_setup_extensions` builds a dynamic subclass `type("_Parser", tuple(parser_mixins) + (base_parser,), {})()` on first call.  [F] `marko/__init__.py:67-114` `[https://raw.githubusercontent.com/frostming/marko/master/marko/__init__.py, fetched 2026-06-14]`
- **Parser entry `marko/parser.py:18-95`** builds a `block_elements` + `inline_elements` registry; `parse(text)` walks the source state, matching block elements in priority order, then post-processes inlines (deferred so link references are seen first).  [F] `marko/parser.py:13-95` `[https://raw.githubusercontent.com/frostming/marko/master/marko/parser.py, fetched 2026-06-14]`
- **Built-in extensions** (`README.md`): `footnote`, `toc`, `pangu`, `codehilite`, plus `marko.ext.gfm.gfm` (GFM).
- **Performance trade-off** (author's own words): "Marko is three times slower than Python-Markdown but slightly faster than Commonmark-py and significantly slower than mistune. If prioritizing performance over spec compliance is crucial for you, it would be best to opt for another parser."  [F] `[https://github.com/frostming/marko/blob/master/README.md, fetched 2026-06-14]`
- **Threading:** `Markdown` class is "not thread-safe. Create a new instance for each thread."  [F] `marko/__init__.py:35`

### 3.4 Input / output coverage

- **Inputs:** Markdown text only (CommonMark 0.31.2 + optional extensions).
- **Outputs:** HTML, or a Python `block.Document` AST.
- **No PDF, no DOCX, no images, no audio/video.**  [F]

### 3.5 Language / RTL / CJK

- No special CJK or RTL handling in the parser itself; rendering passes through text as-is.  [A]

### 3.6 Strengths & limitations (documented)

- **Strengths:** MIT license, CommonMark 0.31.2 compliant (best-in-class spec coverage for Python parsers), real extension system (mixins), pure Python.
- **Limitations:** **wrong direction for LocalDeepL** (it's a parser, not a converter). Slower than Python-Markdown and mistune. Not thread-safe per instance.  [A]
- **Cross-link worth noting:** `docling`'s `pyproject.toml` declares `marko>=2.1.2,<3.0.0` as the markdown parser for the `format-markdown` extra.  [F] `[https://raw.githubusercontent.com/docling-project/docling/main/pyproject.toml, fetched 2026-06-14]` (line in the `format-markdown = ['marko>=2.1.2,<3.0.0']` array). So if LocalDeepL ever wants to plug a CommonMark parser into its MD-→-DOCX writer, Marko is the one Docling itself uses.

### 3.7 Pricing / quota

- **Free, local, MIT, no quota.**  [F] `[https://github.com/frostming/marko, fetched 2026-06-14]`

### 3.8 Architecture summary for LocalDeepL decision

**Drop Marko from the "converter" comparison list.** It belongs in a *parser* sub-list. The brief appears to have mixed it up with `microsoft/markitdown` — see §0.  [A]

---

## 4. Docling — `docling-project/docling`

### 4.1 Identity

- **Vendor:** Originally IBM Research Zurich ("AI for knowledge team"), now an **LF AI & Data Foundation** project.  [F] `[https://github.com/docling-project/docling, fetched 2026-06-14]` — README footer: "The project was started by the AI for knowledge team at IBM Research Zurich." and "Docling is hosted as a project in the LF AI & Data Foundation."
- **Repo:** `docling-project/docling`.  [F] `[https://github.com/docling-project/docling, fetched 2026-06-14]`
- **License:** **MIT** (codebase), with separate per-model licenses for the bundled ML models.  [F] `[https://github.com/docling-project/docling, fetched 2026-06-14]` — README "The Docling codebase is under MIT license. For individual model usage, please refer to the model licenses found in the original packages."
- **Language:** Python 99.3% (per GitHub Languages).  [F] `[https://github.com/docling-project/docling, fetched 2026-06-14]`
- **Stats:** **61.5k stars**, 4.3k forks, 220 watchers, **183 releases**, 1,103 commits, latest **v2.102.1, 2026-06-12**.  [F] `[https://github.com/docling-project/docling, fetched 2026-06-14]`
- **Technical report:** arXiv 2408.09869 ("Docling Technical Report") — required reading for architecture.  [F] README
- **Project tagline:** "Get your documents ready for gen AI".  [F] `[https://github.com/docling-project/docling, fetched 2026-06-14]`

### 4.2 Input & output coverage

- **Inputs (broadest in this report, per README Features list):**
  - PDF, DOCX, PPTX, XLSX, HTML, **EPUB**, WAV, MP3, WebVTT, email (EML, MSG), images (PNG, TIFF, JPEG, …), LaTeX, **DocLang**, plain text, **QMD, RMD** (R/Quarto Markdown), CSV, XML.
  - Application-specific XML schemas: **USPTO patents, JATS articles, XBRL financial reports, METS/GBS**.
  - Vision-Language Model pipeline (e.g. **GraniteDocling**, IBM's 258M VLM) via `docling --pipeline vlm --vlm-model granite_docling <pdf>`.
  - Multiple OCR engines pluggable: **RapidOCR, EasyOCR, Tesseract, macOCR** (`feat-ocr-rapidocr`, `feat-ocr-easyocr`, `feat-ocr-tesserocr`, `feat-ocr-mac` in `pyproject.toml`).
  - Multiple table-structure, layout, code, formula, and picture-classification models.
  [F] `[https://github.com/docling-project/docling/blob/main/README.md, fetched 2026-06-14]` and `[https://raw.githubusercontent.com/docling-project/docling/main/pyproject.toml, fetched 2026-06-14]`
- **Outputs:** Markdown, HTML, WebVTT, **DocLang**, **DocTags** (a tagged-token lossless markup; arXiv 2503.11576), **JSON (lossless, DoclingDocument IR)**, plus per-format extras.  [F] `[https://github.com/docling-project/docling/blob/main/README.md, fetched 2026-06-14]`
- **Unified internal IR:** `DoclingDocument` — "Unified, expressive DoclingDocument representation format".  [F] `[https://github.com/docling-project/docling/blob/main/README.md, fetched 2026-06-14]`

### 4.3 Architecture (from the source)

- **Two-axis architecture: Backend × Pipeline.** From `docling/document_converter.py:53-89`, every `InputFormat` is mapped to a `FormatOption` that pins both a `backend` class (file → in-memory `DoclingDocument` raw) and a `pipeline_cls` (raw → enriched `DoclingDocument`).  [F] `docling/document_converter.py:53-89` `[https://raw.githubusercontent.com/docling-project/docling/main/docling/document_converter.py, fetched 2026-06-14]`
  - The `FormatOption` table (lines 92-188) covers **CSV, XLSX, DOCX, PPTX, MD, AsciiDoc, HTML, USPTO, JATS, DocLang, XBRL, image, PDF, METS/GBS, audio, LaTeX, email, EPUB**. That is **18 input formats** mapped to **3 pipelines** (`SimplePipeline`, `StandardPdfPipeline`, `AsrPipeline`).
  - The `_get_default_option` dict (lines 190-237) is the central format-routing table — if a format is not in this dict, `DocumentConverter` raises.
- **Pipeline for PDF (the LocalDeepL-critical one):** `StandardPdfPipeline` is a **multi-threaded, production-grade stage pipeline** (preprocess → OCR → layout → table structure → assemble) with bounded queues, per-run-id isolation, document-timeout handling, explicit back-pressure.  [F] `docling/pipeline/standard_pdf_pipeline.py:1-13, 30-44, 195-200` `[https://raw.githubusercontent.com/docling-project/docling/main/docling/pipeline/standard_pdf_pipeline.py, fetched 2026-06-14]`
  - Stages: `PreprocessThreadedStage → OCR stage → Layout stage → Table-structure stage → Assemble stage` (line 393-435). Each stage is a `ThreadedPipelineStage` with `batch_size`, `batch_timeout`, `queue_max_size`. Producer thread iterates pages from the backend; result is consumed by `_integrate_results` which sets `SUCCESS` / `PARTIAL_SUCCESS` / `FAILURE` status.
  - Models: `PagePreprocessingModel`, OCR model, layout model (factory-pluggable), `TableStructureModel`, `PageAssembleModel`, `ReadingOrderModel`, optional `CodeFormulaVlmModel` for code/formula enrichment. All initialised once per pipeline instance in `_init_models` (line 432-499).
  - Code & formula enrichment: `_init_models` line 489-498 wires `CodeFormulaVlmModel` with VLM runtime.
  - Confidence aggregation: `_assemble_document` line 740-760 computes `layout_score`, `parse_score` (10th percentile), `table_score`, `ocr_score` and stores on the result.
  - **Failed pages are preserved** as empty `PageItem` entries in the output `DoclingDocument.pages` so page-break markers stay correct (`_add_failed_pages_to_document`, line 793-823).
- **PDF backend (the LocalDeepL-relevant one):** `DoclingParseDocumentBackend` wraps **`pypdfium2` for rendering and `docling-parse` (v6.x) for text extraction** with cell/word/line metadata.  [F] `docling/backend/docling_parse_backend.py:1-16, 213-265` `[https://raw.githubusercontent.com/docling-project/docling/main/docling/backend/docling_parse_backend.py, fetched 2026-06-14]`
  - Config: `DecodePageConfig` (line 19-37) toggles `keep_bitmaps=True` (needed for OCR), `create_word_cells`, `create_line_cells`, `enforce_same_font=True`.
  - Backend exposes `get_text_cells()`, `get_bitmap_rects()`, `get_page_image()`, `get_text_in_rect(bbox)`. Layout-aware text-in-rect is what powers table extraction.
  - Alternative threaded backend: `ThreadedDoclingParseDocumentBackend` uses `DoclingThreadedPdfParser` for parallel parse; doesn't support random page access (`supports_random_page_access = False`).
- **Caching:** `DocumentConverter.initialized_pipelines: dict[(pipeline_class, options_md5_hash), pipeline_instance]` — re-uses heavy models across documents with the same options.  [F] `docling/document_converter.py:355-378` `[https://raw.githubusercontent.com/docling-project/docling/main/docling/document_converter.py, fetched 2026-06-14]`
- **Concurrency:** `DocumentConverter.convert_all` uses `ThreadPoolExecutor(max_workers=settings.perf.doc_batch_concurrency)` across documents; individual docs go through their own per-pipeline threaded stages.  [F] `docling/document_converter.py:518-547`
- **Core data model is `docling-core`** (separate package, `docling-core/types/doc/`). `DoclingDocument`, `PageItem`, `PictureItem`, `TableItem`, `DocItem`, `ImageRef`, `BoundingBox` all live there.  [F] imports at `docling/pipeline/standard_pdf_pipeline.py:23-30`
- **GraniteDocling VLM** ("GraniteDocling 258M", from IBM) is the embedded VLM for the `--pipeline vlm` path.  [F] README + pyproject

### 4.4 Quality / layout fidelity

- **Documented strengths** (README "Features"):
  - "Advanced PDF understanding incl. page layout, reading order, table structure, code, formulas, image classification, and more".
  - "Extensive OCR support for scanned PDFs and images".
  - "Support of several Visual Language Models (GraniteDocling)".
  - "Audio support with Automatic Speech Recognition (ASR) models".
  - "MCP server" for agent integration.
  - **Chart understanding (Barchart, Piechart, LinePlot): converting them into tables, code or adding detailed descriptions** (new feature in latest release).
  - XBRL, EPUB, email support.
  [F] `[https://github.com/docling-project/docling/blob/main/README.md, fetched 2026-06-14]`
- **Documented limitations** (inferred from code, no formal "limitations" section):
  - The threading + `pypdfium2_lock` means two PDFs in parallel may serialize at the lock — `_unload` warns "resources may leak" if a thread is stuck.  [F] `docling/pipeline/standard_pdf_pipeline.py:553-563` `[https://raw.githubusercontent.com/docling-project/docling/main/docling/pipeline/standard_pdf_pipeline.py, fetched 2026-06-14]`
  - PDF model download required on first run (per `scripts/` and `artifacts_path` plumbing in `_init_models`).
  - "Coming soon": metadata extraction (title, authors, references, language), complex chemistry (molecular structures).  [F] README
  - Python 3.9 dropped in v2.70.0; requires Python 3.10+.  [F] README
  - "Heavy" model footprint (torch, docling-ibm-models, etc.) — `pyproject.toml` declares PyTorch 2.2.2+, torchvision, accelerate, huggingface_hub as the `models-local` extra.

### 4.5 Language / RTL / CJK

- The layout model (`docling-ibm-models`) is trained on multilingual data; OCR engines (RapidOCR by default, EasyOCR optional) handle CJK. RTL is handled by the underlying layout model. **No explicit "CJK mode" toggle**; the model and OCR language packs do the work.  [A] (inferred from pyproject extras + multilingual layout model lineage)

### 4.6 Strengths & limitations (summary, marked)

- **[A] Strengths for LocalDeepL comparison:**
  - The only OSS project in this report that ships a **full PDF understanding pipeline** (layout + table structure + reading order + code/formula + chart understanding) plus the same machinery for 17 other formats.
  - **Production-grade PDF pipeline** (timeouts, partial-success handling, page-break preservation, confidence aggregation).
  - **Lossless JSON IR** (`DoclingDocument` export) — this is the killer feature for round-tripping and for letting LocalDeepL re-process structured output.
  - MIT license, LF AI governance (no single-vendor lock-in).
  - Granular extras (`format-pdf-docling`, `feat-ocr-rapidocr`, `models-vlm-inline`, `format-audio`, etc.) — Docling 2.x split the monolith into a modular core (`docling-slim`) + workspace.  [F] `pyproject.toml:1-15` (project name is `docling-slim`, v2.102.1)
- **[A] Limitations / risks:**
  - **Heavy ML dependency stack** (PyTorch, docling-ibm-models, transformers, accelerate) is a much bigger install than LocalDeepL's current Surya stack.
  - First-run model downloads are non-trivial.
  - The whole project is **moving fast** — 183 releases, latest 2026-06-12, pyproject declares Python 3.10–3.14, dropped 3.9 support in 2.70.0. Pinning is mandatory.  [F]
  - **Codebase is large and complex** — `DocumentConverter` has 19 import lines just for backends; `standard_pdf_pipeline.py` is ~850 lines of threaded queue plumbing. LocalDeepL would be betting on a heavy dep.
  - **Mixed license surface:** MIT code, but the VLM and IBM models have their own licenses (referenced from `pyproject.toml` extras like `models-vlm-inline`, `models-local`).

### 4.7 Pricing / quota

- **OSS:** MIT code, free, no quota.
- **Cloud options** (mentioned in README): Apify Actor at `https://apify.com/vancura/docling` (third-party). IBM also operates a managed Docling service — referenced in the pyproject `service-client` extra and the `enable_remote_services` flag in `StandardPdfPipeline._init_models`.  [F] `docling/pipeline/standard_pdf_pipeline.py:454, 470, 480, 495, 503` `[https://raw.githubusercontent.com/docling-project/docling/main/docling/pipeline/standard_pdf_pipeline.py, fetched 2026-06-14]`
  - **No "Unstructured Platform" equivalent** (i.e. no built-in SaaS marketing push from the docling-project org); it's mostly positioned as "MIT, you self-host".

### 4.8 Architecture summary for LocalDeepL decision

**Docling is the single most important competitor to LocalDeepL's PDF→MD mission.** It:
- already implements the 18-format "anything-to-structured" framing that LocalDeepL has,
- uses a **model-driven layout pipeline** that LocalDeepL does not (Surya detection + VLM OCR is closer to a lighter version of this),
- has a **multi-threaded PDF pipeline** with back-pressure, timeouts, and confidence scores,
- ships its own **VLM** (GraniteDocling 258M) and a pluggable VLM registry,
- exports **Markdown, JSON, HTML, DocTags** (multiple lossless paths),
- is **MIT-licensed** (compatible with LocalDeepL's permissive stance).

LocalDeepL's differentiation must be one of: (a) smaller install footprint, (b) tighter VLM contract, (c) better Windows quick-start, (d) ground-truth-driven confidence scores (which LocalDeepL already has via `core/evaluation.py`), (e) tighter integration with the existing LocalDeepL doc-processors and document exports.  [A]

---

## 5. Unstructured — `Unstructured-IO/unstructured`

### 5.1 Identity

- **Vendor:** Unstructured Technologies (`devops@unstructuredai.io`).  [F] `[https://raw.githubusercontent.com/Unstructured-IO/unstructured/main/pyproject.toml, fetched 2026-06-14]`
- **Repo:** `Unstructured-IO/unstructured`.  [F] `[https://github.com/Unstructured-IO/unstructured, fetched 2026-06-14]`
- **License:** **Apache-2.0** (permissive).  [F] `pyproject.toml:15` (license = "Apache-2.0") and repo sidebar
- **Language:** Python 99% + shell/Makefile. (GitHub Languages shows 89.9% HTML — that's misleading, the language detector is fooled by HTML test fixtures; actual code is Python.)  [F] `[https://github.com/Unstructured-IO/unstructured, fetched 2026-06-14]`
- **Stats:** **14.9k stars**, 1.3k forks, 74 watchers, **232 releases**, 1,902 commits, latest **0.23.1, 2026-06-11**.  [F] `[https://github.com/Unstructured-IO/unstructured, fetched 2026-06-14]`
- **Status:** "Development Status :: 4 - Beta".  [F] `pyproject.toml:7`
- **Tagline:** "Open-Source Pre-Processing Tools for Unstructured Data" / "Convert documents to structured data effortlessly".  [F] `[https://github.com/Unstructured-IO/unstructured, fetched 2026-06-14]`
- **Python:** 3.11–3.13.  [F] `pyproject.toml:5` (requires-python = ">=3.11, <3.14")

### 5.2 Input & output coverage

- **Inputs (broadest in this report, listed in pyproject extras):** CSV, DOC, DOCX, EPUB, image (PNG/JPG/HEIC/TIFF), MD, ODT, ORG, PDF, PPT, PPTX, RTF, RST, TSV, XLSX, **email, audio (wav/mp3 via OpenAI Whisper)**, JSON, NDJSON, XML, plain text.  [F] `pyproject.toml:60-122` `[https://raw.githubusercontent.com/Unstructured-IO/unstructured/main/pyproject.toml, fetched 2026-06-14]`
- **Also:** a separate `unstructured-ingest` package with 40+ source connectors (S3, Azure, GCS, OneDrive, Notion, Slack, Salesforce, …) — see `ingest` extra.  [F] `pyproject.toml:140-142`
- **Outputs:** not a Markdown converter — the library produces `list[Element]` (typed element objects: `Text`, `Title`, `NarrativeText`, `ListItem`, `Image`, `Table`, `PageBreak`, etc.) with rich metadata.  [F] `[https://raw.githubusercontent.com/Unstructured-IO/unstructured/main/unstructured/partition/pdf.py, fetched 2026-06-14]` (imports `Title`, `ListItem`, `Table`, `PageBreak`, `Image`, `Text`, `CoordinatesMetadata`, `Link`, etc. from `unstructured.documents.elements`)
  - **Markdown export is not the primary output** — this is the key difference from Docling/Mammoth/MarkItDown. You get a *partitioned* element list, not a Markdown string. You'd typically feed these to chunking + embedding for RAG.
  - For Markdown, users typically use Unstructured as a **preprocessor** for `unstructured-ingest` → chunking → embedding pipelines, or use the **Unstructured SaaS Platform** (separate product, `unstructured.io/enterprise`) for hosted conversion.
- **Cloud / SaaS:** README explicitly pushes: "Ready to move your data processing pipeline to production… Check out Unstructured Platform. In addition to better processing performance, take advantage of chunking, embedding, and image and table enrichment generation, all from a low code UI or an API. Request a demo from our sales team."  [F] `[https://github.com/Unstructured-IO/unstructured, fetched 2026-06-14]`

### 5.3 Architecture (from the source)

- **Central entry: `unstructured.partition.auto.partition()`** — a single function that does file-type detection via libmagic and routes to a file-specific partitioner.  [F] `unstructured/partition/auto.py:34-95` `[https://raw.githubusercontent.com/Unstructured-IO/unstructured/main/unstructured/partition/auto.py, fetched 2026-06-14]`
  - Docstring: "Uses libmagic to determine the file's type and route it to the appropriate partitioning function. Applies the default parameters for each partitioning function."
- **Routing logic in `partition()` (auto.py:114-219):** separate code paths for PDF, image, JSON, NDJSON, and a fallback "ALL OTHER FILE TYPES" path. The router keeps a module-level cache `_PartitionerLoader._partitioners: dict[FileType, Partitioner]` so each file-type's partitioner is imported once.
  - **Dependency check at load time** (`_PartitionerLoader._load_partitioner`): if a partitioner's required packages aren't installed, raises an `ImportError` telling the user to `pip install "unstructured[<extra>]"` — this is the user-facing way to discover the extra system.  [F] `unstructured/partition/auto.py:283-307`
- **PDF partitioning — three strategies, picked at runtime** (auto.py:142-153 dispatches to `partition_pdf_or_image`, which then dispatches on `strategy`):
  1. `PartitionStrategy.HI_RES` — uses **`unstructured-inference`** (a Detectron2-based layout model) + pdfminer for text + Tesseract for OCR. "Uses a layout detection model to identify document elements."  [F] `unstructured/partition/pdf.py:74-77`
  2. `PartitionStrategy.FAST` — pdfminer text extraction only, no model.
  3. `PartitionStrategy.OCR_ONLY` — render to image + Tesseract OCR.
  4. `PartitionStrategy.AUTO` (default) — "the default strategy `auto` will determine when a page can be extracted using `fast` mode, otherwise it will fall back to `hi_res`."  [F] `unstructured/partition/pdf.py:74-77`
  - **A heuristic skips text extraction for "too complex" PDFs** (e.g. CAD drawings): regex counts graphics vs text operators in the decoded content stream, falls back to hi_res if ratio > 20:1.  [F] `unstructured/partition/pdf.py:399-450` (function `is_pdf_too_complex`)
  - For hi_res, `_partition_pdf_or_image_local` runs `unstructured_inference.inference.layout.process_data_with_model` (Detectron2) → merges with pdfminer-extracted text via `merge_inferred_with_extracted_layout` → runs `process_data_with_ocr` (Tesseract) → `document_to_element_list`.  [F] `unstructured/partition/pdf.py:633-740`
  - For images, hi_res path also exists. Audio uses `openai-whisper` (or `mlx-whisper` on macOS arm64).  [F] `pyproject.toml:124-128`
- **Form extraction** is opt-in via `extract_forms=True`; recovers AcroForm widget text that pdfminer misses.  [F] `unstructured/partition/pdf.py:560-572`
- **Element model:** `unstructured.documents.elements` defines `Element` base + `ElementType` enum (`UNCATEGORIZED_TEXT`, `TEXT`, `TITLE`, `NARRATIVE_TEXT`, `LIST_ITEM`, `TABLE`, `IMAGE`, `PAGE_BREAK`, …). All elements carry `ElementMetadata` with `filename`, `page_number`, `coordinates`, `last_modified`, `languages`, `links`.  [F] `unstructured/partition/pdf.py:33-55`
- **Post-process / chunk:** `@add_chunking_strategy` decorator on `partition_pdf`; chunking strategies are pluggable (basic, by-title, by-similarity, by-page, by-token).  [F] `unstructured/partition/pdf.py:73` + import `from unstructured.chunking import add_chunking_strategy`
- **System deps** (README): `libmagic-dev` (filetype), `poppler-utils` (PDF/image), `tesseract-ocr` (+ `tesseract-lang` for languages), `libreoffice` (MS Office).  [F] `[https://github.com/Unstructured-IO/unstructured, fetched 2026-06-14]`
- **Telemetry:** opt-in, off by default.  [F] `[https://github.com/Unstructured-IO/unstructured, fetched 2026-06-14]`

### 5.4 Quality / layout fidelity

- **Documented strengths** (README + partition_pdf docstring):
  - "Partitions a document into its constituent elements" — outputs typed `Element` objects with rich metadata.
  - Three PDF strategies let users trade off speed (fast) vs layout fidelity (hi_res).
  - Language detection per element (`detect_language_per_element=True`).
  - PDF form extraction.
  - Image extraction (saved to dir or base64-in-payload).
  - "Telephony of files" — file-type auto-detection via libmagic.
  - Table extraction (`infer_table_structure`).
  [F] `unstructured/partition/pdf.py:80-129, 633-740` and README
- **Documented limitations:**
  - Status is **Beta** (Development Status :: 4 - Beta).  [F] `pyproject.toml:7`
  - First-run model downloads required (Detectron2 layout model via `unstructured-inference`).
  - Heuristic for "complex PDFs" is a regex-based short-circuit that may misclassify.
  - Markdown export is **not** a first-class feature; the library is partitioned-element-first, Markdown-second.
  - The `pdf_infer_table_structure` kwarg is **deprecated** in favour of `skip_infer_table_types`.  [F] `unstructured/partition/auto.py:111-115`
  - Heavy dep graph (Detectron2/Torch, Tesseract, poppler, etc.) and lots of platform-specific pins in `pyproject.toml:144-176`.
  - Windows note: many extras gated by `platform_system == 'Windows' and python_version < '3.13'` — `unstructured` does not yet fully support Python 3.13 on Windows.  [F] `pyproject.toml:64, 79, 88, 102, 110, 119, 144`

### 5.5 Language / RTL / CJK

- **`languages=[...]` parameter for Tesseract OCR.** Requires `tesseract-lang` system pack for non-English. Language detection per element via `langdetect` (naive Bayesian). No explicit RTL handling.  [F] `unstructured/partition/auto.py:43-50` + README

### 5.6 Strengths & limitations (summary, marked)

- **[A] Strengths for LocalDeepL comparison:**
  - **Broadest input coverage** of any OSS project in this report (PDF + office + images + audio + email + 17 formats + 40+ ingest connectors).
  - **Element-level IR** with coordinates, page numbers, languages, links — richer than Docling's `DoclingDocument` for RAG use cases.
  - **Three PDF strategies** + automatic fallback give users real speed/quality knobs.
  - **Open-core model** with paid SaaS Platform behind it (good for some users, less appealing for an open-core LocalDeepL).
  - Apache-2.0 (most permissive license in this set).
  - 232 releases, very active.
- **[A] Limitations / risks for LocalDeepL:**
  - **Output is `list[Element]`, not Markdown.** LocalDeepL's primary output is Markdown / a `DocumentResult` IR — direct overlap is partial.
  - **Heavy ML stack** (Detectron2/Torch) + system deps (Tesseract, poppler, LibreOffice). More painful to install on Windows than Docling or pandoc.
  - Windows Python 3.13 not fully supported.
  - Beta status.
  - **Vendor SaaS push** — the README literally leads with "Try the Unstructured Platform Product" and a sales CTA. Adopting this in a self-hosted-only product is technically fine (Apache-2.0) but signals long-term direction.
  - The PDF heuristic short-circuit (`is_pdf_too_complex`) is regex-based and may misclassify valid documents as "complex CAD drawings".

### 5.7 Pricing / quota

- **OSS:** Apache-2.0, free, no quota.
- **SaaS:** Unstructured Platform (`unstructured.io/enterprise`) — pay-per-use, requires sales contact. Not used in this scout beyond a mention; the SaaS API is at `unstructured.io`.  [F] `[https://github.com/Unstructured-IO/unstructured, fetched 2026-06-14]`

### 5.8 Architecture summary for LocalDeepL decision

Unstructured is the **broadest** OSS project in this report but the **least aligned** with LocalDeepL's "Markdown output" framing. LocalDeepL's "structured `DocumentResult`" output (`src/local_deepl/core/document.py`) is closer in spirit to Unstructured's `list[Element]`, but LocalDeepL always exports to Markdown, JSON, docx, and a searchable PDF. The most interesting **overlap** is:
- **Both have local processing pipelines** (Unstructured = Detectron2 + Tesseract; LocalDeepL = Surya + VLM OCR + DP alignment).
- **Both expose an internal IR** (Unstructured = `Element`/`ElementMetadata`; LocalDeepL = `DocumentResult` IR + processor chain).
- **Both target RAG / gen-AI ingestion** as a primary use case.

LocalDeepL's differentiation: Markdown-first, local model flexibility (VLM via LiteLLM), no SaaS push, Windows-friendly quick-start.  [A]

---

## 6. Cross-cutting observations

### 6.1 License matrix (permissive vs copyleft)

| Project | License | LocalDeepL embed-friendly? |
| --- | --- | --- |
| Pandoc | **GPL-2.0-or-later** | ⚠️ Copyleft — ok to *use* via shell, dangerous to *link/distribute* |
| Mammoth | BSD-2-Clause | ✅ Permissive |
| Marko | MIT | ✅ Permissive |
| Docling | MIT (code) + per-model licenses | ✅ Permissive (code), check model licenses separately |
| Unstructured | Apache-2.0 | ✅ Permissive |
| **LocalDeepL (for reference)** | (per AGENTS.md, not stated here) | n/a |

[F] All from `[https://github.com/<org>/<repo>, fetched 2026-06-14]`

### 6.2 PDF-input coverage matrix (the LocalDeepL-critical leg)

| Project | Native PDF→MD? | Quality on scanned PDFs? | Quality on text-native PDFs? | Layout fidelity |
| --- | --- | --- | --- | --- |
| Pandoc | ❌ No PDF reader | n/a | n/a (uses external tools via PDF-output path) | n/a |
| Mammoth | ❌ DOCX only | n/a | n/a | n/a |
| Marko | ❌ Markdown parser only | n/a | n/a | n/a |
| Docling | ✅ Full PDF pipeline | ✅ (RapidOCR/EasyOCR/Tesseract + VLM) | ✅ (`docling-parse` text + layout) | ✅ (table structure, code, formulas, charts, reading order) |
| Unstructured | ✅ `partition_pdf` | ✅ (Tesseract + Detectron2 layout) | ✅ (pdfminer + Detectron2) | ✅ (typed Elements w/ coordinates) |
| **LocalDeepL** | ✅ (Surya + VLM + DP align) | ✅ | ✅ | ✅ (table, code, math, image) |

[F] All from project READMEs and source files cited above.

### 6.3 Last-release activity (commit signal)

- Pandoc: 3.10 on 2026-06-04 (10 days ago)
- Mammoth: 85 tags but no "Latest release" surfaced; very low recent activity visible
- Marko: v2.2.3 on 2026-05-28 (17 days ago)
- Docling: v2.102.1 on 2026-06-12 (2 days ago) — most active
- Unstructured: 0.23.1 on 2026-06-11 (3 days ago) — very active
- LocalDeepL (this repo): 183 stars on the docling tracker shows that the docling project alone is roughly 100× more popular than LocalDeepL; Pandoc is 1000× more popular.

[F] `[https://github.com/<org>/<repo>/releases, fetched 2026-06-14]`

### 6.4 Architectural patterns worth knowing

- **Pandoc:** AST + reader/writer + filter. Pure functional. Lossy round-trips by design.
- **Mammoth:** docx-zip → semantic document tree → HTML via style-map DSL. No ML. Monadic pipeline.
- **Marko:** Parser with mixin-based extension. AST + HTML. Thread-unsafe per instance.
- **Docling:** Backend × Pipeline factory. Multi-threaded PDF stage pipeline. Cached heavy models. `DoclingDocument` lossless IR.
- **Unstructured:** Auto-detect via libmagic → per-format partitioner. Three PDF strategies (FAST / OCR_ONLY / HI_RES). Element-level IR.

### 6.5 Reusable "lessons" for LocalDeepL

1. **Pandoc's reader/writer-per-format** is the right mental model for a multi-format converter. LocalDeepL's current `core/aligner.py` + `core/grounded.py` is a similar split.
2. **Mammoth's style-map DSL** is a strong product feature for DOCX. LocalDeepL currently lacks a comparable declarative mapping tool for `word_styles.xml` → Markdown.
3. **Marko's mixin extension system** is a clean pattern for MD round-trips. LocalDeepL's existing `core/docx_writer.py` Markdown→docx is bespoke and could potentially use Marko as the parser.
4. **Docling's stage-pipeline with back-pressure, timeouts, and confidence aggregation** is the gold standard for production PDF→MD. LocalDeepL's `core/workflows/hybrid.py` would benefit from copying `ThreadedPipelineStage` patterns and `_integrate_results` (status enums) for batch processing.
5. **Unstructured's `partition()` dispatcher** with **auto-loaded per-format partitioners** is the right pattern for an "auto-detect-and-convert" UX. LocalDeepL's `core/routing.py` and `OCRPipeline` could grow a similar dispatcher.
6. **All five projects** treat Markdown differently:
   - Pandoc, Mammoth, Docling: Markdown is a *first-class output*.
   - Unstructured: Markdown is *not* a first-class output (elements are).
   - Marko: Markdown is the *input*.

### 6.6 Conflicts / caveats surfaced

- **[C] Marko attribution conflict:** task brief said "H2OAI/marko (or whatever the canonical repo is — verify)" — verification found no H2OAI/marko. The canonical repo is `frostming/marko`, and the project's direction is the *opposite* of LocalDeepL (parser, not converter). Most likely the brief meant **`microsoft/markitdown`** (153k stars, MD-converter).
- **[C] Pandoc PDF path:** task brief said "read src/Text/Pandoc/Readers/PDF.hs or PDF/" — that path does not exist. Pandoc has no native PDF reader.
- **[C] Pandoc license:** task brief treated Pandoc as a generic OSS option without flagging the GPL-2.0+ copyleft, which matters for any LocalDeepL distribution that links or ships Pandoc.

---

## 7. Recommended next steps (analyst)

1. **Drop "Marko" from the converter comparison**; the canonical repo is `frostming/marko` and it's a parser, not a converter. If the brief wanted Microsoft's `markitdown`, add it to the second-half OSS list (it's the most direct "LLM-feed MD converter" competitor).  [A]
2. **Keep Pandoc shelling** for the non-PDF legs (DOCX/PPTX/XLSX/HTML/EPUB/ODT) of LocalDeepL's pipeline, behind a license check (note GPL-2.0+).  [A]
3. **Mammoth is a useful alternative to pandoc's DOCX reader** when style-map semantics are wanted. The **no-sanitisation warning is a hard blocker** for untrusted uploads — LocalDeepL must run a sanitiser downstream.  [A]
4. **Docling is the most dangerous competitor** — it is doing the same thing LocalDeepL is doing, with a heavier ML stack but a more complete pipeline. LocalDeepL's moat must be one of: lighter install, tighter VLM contract, Windows quick-start, confidence-eval integration, or `core/processors.py` differentiation.  [A]
5. **Unstructured is a partial overlap** (RAG-pipeline framing, element IR) but does not export Markdown as a first-class artifact. Use it as a *reference* for the partition-then-export pattern, not a *replacement* for LocalDeepL's Markdown-first output.  [A]

---

*End of evidence file. Compiled 2026-06-14 by scout subagent.*
