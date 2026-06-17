# Schema & Table Extraction from Documents — Landscape Scout (2026)

> Scout report for LocalDeepL. Date: 2026-06-14. Author: general-purpose worker.
> Method: web_search + webfetch against vendor docs, GitHub READMEs, arXiv preprints, benchmark leaderboards. For every major OSS project, the repo was opened, the README read, and at least one core file was inspected with `file_path:line_number` citations. Full evidence ledger: `C:\Users\rahin\LocalDeepL\.mavis\plans\scout\track-schema-evidence.md`.
> [F] = fact stated by source. [A] = synthesis / inference.

---

## 1. Executive Summary

The schema / structured-output / table-extraction landscape in 2026 has consolidated into two camps:

1. **Cloud incumbents** (Google Document AI, Azure AI Document Intelligence, AWS Textract + Bedrock Data Automation, IBM watsonx Discovery, ABBYY Vantage). These offer pay-per-page APIs, JSON or Markdown output, and "no-training-needed" extraction via either prebuilt schemas or generative-AI custom extractors. They are best for compliance-heavy enterprise pipelines, but lock in customer data and pricing scales poorly at 1M+ pages/mo.

2. **Open-source + VLM wave** (Marker, Docling, Unstructured, PaddleOCR-VL, Surya, Microsoft TATR, Camelot, pdfplumber, MinerU, Qwen3-VL, dots.ocr, MonkeyOCR, PaddleOCR-VL-1.6). The 2024-2026 inflection is the rise of small vision-language models (0.1B – 3B) trained on table-rich data that now match or beat cloud APIs on benchmarks like OmniDocBench v1.6 (e.g., PaddleOCR-VL-1.6 96.3% vs Gemini 3 Pro 92.91% on the same leaderboard). The 0.9B PaddleOCR-VL-1.5 is the SOTA Pareto-frontier entry for open weights; Surya 0.65B is the best under-1B multilingual entry.

**Three structural observations LocalDeepL should plan around:**

- **Schema is the new surface.** The 2025 OpenAI Structured Outputs / Anthropic tool use / Gemini function calling all accept a Pydantic-derived JSON Schema. The frontier battle is no longer "can you get a table?" but "can you coerce the table into the user's exact schema without manual post-processing?" Marker-PDF already ships a `ExtractionConverter` for this; LangChain / LlamaIndex / OpenAI / Anthropic all have first-class integrations.
- **Layout is the floor.** Every OSS leader in 2026 (Marker, Docling, PaddleOCR-VL, Surya) starts with a layout model (DocLayNet, TableFormer, or a VLM that emits layout JSON) before doing anything else. The "table extraction" problem is inseparable from "page layout understanding." LocalDeepL's existing Surya detection path is a competitive starting point; the gap is structural-recovery + schema-coercion downstream.
- **Multilingual + RTL + dense tables are still hard.** Surya's "OldScan" 41.8% pass rate on olmOCR-bench and the 60% accuracy drop on Arabic (72.7%) vs English (92.3%) show the long tail. No current product dominates the combination of scientific/financial/RTL/heavy-table cases.

**For LocalDeepL specifically**, the three white-space gaps to consider:
- A first-class, transparent Pydantic-schema path for table extraction that lets the user define `class Invoice(BaseModel)` and get back `List[Invoice]` per page, without manually post-processing the LLM JSON.
- A combined hybrid: Surya for layout + TATR-v1.1-All for structure + OpenAI Structured Outputs / Instructor for the user-defined schema. None of the OSS leaders currently wire this together cleanly.
- A long-tail evaluation harness on the user's actual document mix (not the public benchmarks) — the OmniDocBench v1.6 per-document-type leaderboard shows the spread.

---

## 2. Players (by tier)

### Tier 1 — Cloud Incumbents

| Player | Service | Pricing model | Self-host | Free tier |
| --- | --- | --- | --- | --- |
| Google Cloud | Document AI (Custom Extractor, Form Parser, Layout, Splitter, Classifier) | per 1k pages: $1.50 OCR → $30 Custom Extractor / Form Parser | No (cloud only) | $300 GCP credit |
| Microsoft Azure | AI Document Intelligence v4.0 (prebuilt-layout, prebuilt-read, custom neural) | per 1k pages (S0 tier) | **Yes** (Docker container) | 500 free pages/mo (F0) |
| AWS | Textract (Forms/Tables/Queries/Signatures) + Bedrock Data Automation (multimodal VLM) | per-page per-feature; BDA per-page for custom blueprints | No (cloud only) | Limited free for Textract; BDA free tier in 2025 |
| IBM | watsonx Discovery + Datacap (on-prem capture) | consumption-based | Yes (Datacap) | Lite tier |
| ABBYY | Vantage (cloud skills) + FlexiCapture (on-prem) | per-document | Yes (FlexiCapture) | Trial |

### Tier 2 — OSS Pipelines (general-purpose)

| Player | Stack | License | Output | Self-host |
| --- | --- | --- | --- | --- |
| Datalab Marker | Surya OCR + layout + heuristic + optional LLM | GPL-3.0 (code) / Open Rail-M (weights) | Markdown / JSON / HTML / chunks | Yes (CPU/GPU/MPS) |
| IBM Docling | DocLayNet (layout) + TableFormer (structure) + GraniteDocling (VLM) | MIT | DoclingDocument, Markdown, HTML, JSON, DocTags, DocLang | Yes (CPU/GPU) |
| Unstructured-IO | Heuristics + YoloX + TableTransformer | Apache-2.0 | `Element` JSON (Title/NarrativeText/Table/...) | Yes |
| Microsoft Presidio + TATR | Detection + TATR structure | MIT | HTML / CSV / JSON via inference.py | Yes |
| MinerU2.5-Pro | Open-source pipeline (1.2B VLM + rules) | Apache-2.0 | Markdown / JSON | Yes |

### Tier 3 — OSS VLM / Specialist Models (2024-2026 inflection)

| Model | Vendor | Size | OmniDocBench v1.6 Overall | License |
| --- | --- | --- | --- | --- |
| PaddleOCR-VL-1.6 | Baidu | 0.9B | 96.3% (v1.6 dataset card) | Apache-2.0 |
| PaddleOCR-VL-1.5 | Baidu | 0.9B | 94.93 | Apache-2.0 |
| GLM-OCR | Zhipu | 0.9B | 95.22 | Open |
| MinerU2.5-Pro | OpenDataLab | 1.2B | 95.75 | Apache-2.0 |
| dots.ocr | – | 3B | 90.77 | Open |
| MonkeyOCR-pro-3B | – | 3B | 88.57 | Open |
| HunyuanOCR | Tencent | 1B | 89.95 | Open |
| Qwen3-VL-235B | Alibaba | 235B | 89.78 | Open weights |
| Surya OCR 2 | Datalab | 0.65B | (N/A on OmniDocBench; olmOCR-bench 83.3%) | Apache-2.0 code, Open Rail-M weights |

### Tier 4 — Library / Schema Layer

- **OpenAI Structured Outputs** — `response_format` with strict JSON Schema; gpt-4o-2024-08-06+ and GPT-5.x. [F, platform.openai.com/docs/guides/structured-outputs]
- **Anthropic tool use** — JSON Schema on `input_schema`; Claude 3.5+ and Claude 4. [A]
- **Google Gemini function calling** — `response_schema` + `response_mime_type=application/json`. [A]
- **Pydantic v2** — generates JSON Schema 2020-12 from Python classes. [A]
- **Instructor (567-labs)** — `instructor.from_provider(...)`, retries, streaming, nested, multi-provider. MIT, 13.2k stars. [F, github.com/567-labs/instructor, fetched 2026-06-14]
- **Outline / Outlines (dottxt-ai / outlines-dev)** — grammar-constrained generation (regex, JSON Schema, CFG). [A]
- **PydanticAI** — official agent runtime; uses the same Pydantic models. [A]

### Tier 5 — Long-tail / Niche

- **Mathpix** — best for LaTeX math extraction (CDN cost: $0.004/page equivalent). [A]
- **LlamaParse** — best for messy PDF → Markdown. (Compare to Marker heuristic 95.67 vs LlamaParse 84.24.) [F, Marker README "Overall PDF Conversion" table]
- **Mistral OCR** — competitive 85.66 overall on OmniDocBench. [F, OmniDocBench leaderboard]
- **ZAIHostedOCR** — experimental, mentioned in LocalDeepL AGENTS.md as tech debt. [A]

---

## 3. Feature Matrix

Legend: ✅ yes, ❌ no, ⚠ partial / opt-in / requires extra cost, 🅰 via add-on.

| Feature | Google DocAI | Azure DI v4.0 | AWS Textract | AWS BDA | TATR | Camelot | pdfplumber | PaddleOCR | Docling | Marker | Surya | Unstructured | OmniTab | PaddleOCR-VL-1.6 |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| **Input formats** | | | | | | | | | | | | | | |
| PDF | ✅ | ✅ | ✅ | ✅ | ✅¹ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Image (PNG/JPG/TIFF) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| DOCX | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ | ✅ |
| PPTX | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ | ✅ |
| XLSX | ❌ | ✅ (read) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ | ✅ |
| HTML | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ |
| EPUB / email | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ (EML) | ❌ | ❌ |
| **Document classes** | | | | | | | | | | | | | | |
| Ruled tables | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (lattice) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Borderless / whitespace tables | ✅ | ✅ | ⚠ | ✅ | ✅ (TATR-v1.1-Fin) | ✅ (stream/network) | ✅ (text strategy) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Multi-page tables | ⚠ | ⚠ (split-then-merge) | ⚠ | ✅ (BDA split+merge) | ❌ | ✅ (`stack_contiguous`) | ❌ | ✅ | ✅ | ✅ (`--use_llm`) | ❌ | ⚠ | ❌ | ✅ |
| Nested / spanning cells | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠ | ⚠ | ✅ | ✅ | ✅ | ✅ (predict_full) | ✅ | ✅ | ✅ |
| Forms / key-value pairs | ✅ (Form Parser) | ✅ (prebuilt-document) | ✅ (Forms feature) | ✅ | ❌ | ❌ | ❌ | ✅ (PP-StructureV3 KIE) | ⚠ | ✅ | ⚠ | ⚠ | ❌ | ✅ |
| Handwritten | ⚠ | ✅ (handwritten langs) | ⚠ | ✅ | ⚠ | ❌ | ❌ | ✅ | ⚠ | ✅ (use_llm) | ✅ | ⚠ | ❌ | ✅ |
| Financial / scientific | ✅ | ✅ | ✅ | ✅ | ✅ (TATR-v1.1-Fin) | ⚠ | ⚠ | ✅ | ✅ | ✅ (best-in-class on FinTabNet) | ⚠ (OldMath 81.4) | ⚠ | ✅ (FinTabNet) | ✅ |
| Newspaper / magazine | ⚠ | ✅ | ⚠ | ✅ | ⚠ | ❌ | ❌ | ✅ | ✅ | ✅ (98.87 on newspaper) | ✅ | ⚠ | ❌ | ✅ |
| RTL (Arabic, Hebrew) | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ (109 langs) | ⚠ | ⚠ (relies on VLM) | ✅ (ar 72.7%) | ⚠ | ❌ | ✅ |
| **Output schema** | | | | | | | | | | | | | | |
| JSON | ✅ (`Document` proto) | ✅ | ✅ (`Block` graph) | ✅ | ✅ (cells list / bbox JSON) | ✅ | ⚠ (chars+rects) | ✅ | ✅ (DoclingDocument) | ✅ (JSON, tree) | ✅ (results.json) | ✅ (Element list) | ✅ | ✅ |
| HTML | ❌ | ✅ (Markdown w/ HTML tables) | ❌ | ❌ | ✅ (`<table>` w/ colspan/rowspan) | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ (`<table>`) | ❌ | ❌ | ✅ |
| CSV | ❌ | ❌ | ✅ (exporting tables doc) | ❌ | ✅ | ✅ | ✅ (extract_table) | ✅ | ⚠ | ⚠ | ❌ | ❌ | ❌ | ✅ |
| XLSX | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Markdown | ✅ (Layout Parser) | ✅ (Markdown format w/ HTML tables) | ❌ | ✅ (default for docs) | ❌ | ✅ | ❌ | ✅ | ✅ | ✅ (default) | ✅ (with `--use_llm` merge) | ⚠ | ❌ | ✅ |
| Native structured (Pydantic / JSON Schema) | ⚠ (Custom Extractor schema) | ❌ (JSON only) | ❌ | ✅ (custom blueprint) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ (`ExtractionConverter` beta) | ❌ | ❌ | ❌ | ❌ |
| Pydantic-native | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ (`page_schema=Pydantic.model_json_schema()`) | ❌ | ❌ | ❌ | ❌ |
| **Execution mode** | | | | | | | | | | | | | | |
| Local CPU | ❌ | ⚠ (Docker) | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (llama.cpp) | ✅ | ✅ | ✅ |
| Local GPU | ❌ | ⚠ (Docker) | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ (vLLM) | ✅ | ✅ | ✅ |
| Cloud API | ✅ | ✅ | ✅ | ✅ | ❌ (model only) | ❌ | ❌ | ⚠ (PaddleCloud) | ⚠ | ⚠ (datalab.to) | ⚠ (datalab.to) | ⚠ (Unstructured Platform) | ❌ | ⚠ (paddleocr.com) |
| Latency tier (per page, typical) | 1-3 s | 1-3 s | 1-5 s | 2-10 s | 0.1-1 s (CPU) | <0.1 s (text-based) | <0.1 s | 0.13 s (A100) | 0.2-2 s (H100) | 0.18 s (H100) | 5.35 p/s on RTX 5090 | 0.5-5 s | 1-3 s | 0.13 s (A100) |

¹ TATR requires a separate OCR / text-extraction step to populate cells (image-only model). All other table extractors either bundle OCR or operate on PDF's text layer.

---

## 4. Benchmark Table (raw numbers + citations)

### OmniDocBench v1.6 — End-to-End Document Parsing (CVPR 2025, CVF)

> "Comprehensive evaluation of document parsing on OmniDocBench (v1.6_full)"; source: https://github.com/opendatalab/OmniDocBench README, fetched 2026-06-14.

| Model | Size | Overall ↑ | TextEdit ↓ | FormulaCDM ↑ | TableTEDS ↑ | TableTEDS-S ↑ | ReadOrderEdit ↓ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **MinerU2.5-Pro** | 1.2B | **95.75** | **0.036** | 97.45 | 93.42 | 95.92 | 0.120 |
| GLM-OCR | 0.9B | 95.22 | 0.044 | 97.18 | 92.83 | 95.39 | 0.133 |
| PaddleOCR-VL-1.5 | 0.9B | 94.93 | 0.038 | 96.89 | 91.67 | 94.37 | 0.130 |
| PaddleOCR-VL | 0.9B | 94.18 | 0.040 | 95.91 | 90.65 | 93.74 | 0.135 |
| Youtu-Parsing | 2.5B | 93.74 | 0.044 | 93.63 | 92.02 | **95.00** | **0.116** |
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
| **PaddleOCR-VL-1.6** | 0.9B | **96.3% (v1.6 dataset card)** | – | – | – | – | – |

PaddleOCR-VL-1.6 (2026-06-11) "achieves over 96.3% on OmniDocBench v1.6, also sets new SOTA on OmniDocBench v1.5 and Real5-OmniDocBench, leading both open-source and proprietary solutions in text, formula, and table recognition." [F, https://github.com/PaddlePaddle/PaddleOCR, arXiv:2606.03264]

### PubTables-1M — Microsoft TATR (CVPR 2022)

> Source: https://github.com/microsoft/table-transformer README "Evaluation Metrics" table, fetched 2026-06-14.

| Model | Test data | AP50 | AP75 | AP | AR | GriTSTop | GriTSCon | GriTSLoc | AccCon |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **DETR R18 (detection)** | PubTables-1M | 0.995 | 0.989 | 0.970 | 0.985 | – | – | – | – |
| **TATR-v1.0 (structure)** | PubTables-1M | 0.970 | 0.941 | 0.902 | 0.935 | 0.9849 | 0.9850 | 0.9786 | 0.8243 |

### FinTabNet — Marker (Datalab, 2026)

> "The table extraction performance is measured by comparing the extracted HTML representation of tables against the original HTML representations using the test split of FinTabNet. The HTML representations are compared using a tree edit distance based metric to judge both structure and content. We filter out tables that we cannot align with the ground truth, since fintabnet and our layout model have slightly different detection methods (this results in some tables being split/merged)." [F, https://github.com/datalab-to/marker README "Table Conversion"]

| Method | Avg score | Total tables |
| --- | --- | --- |
| Marker | 0.816 | 99 |
| Marker w/ use_llm | **0.907** | 99 |
| Gemini 2.0 Flash | 0.829 | 99 |

### olmOCR-bench — Surya Pareto frontier (Datalab, 2026)

> Source: https://github.com/datalab-to/surya README "olmOCR-bench" table, fetched 2026-06-14.

| Model | Params | Score |
| --- | --- | --- |
| Infinity-Parser2-Pro | 35.1B | **87.6** |
| Chandra OCR 2 (Datalab) | 5.3B | 85.9 |
| dots.mocr | 3.0B | 83.9 |
| **Surya OCR 2 (Datalab)** | **0.65B** | **83.3** |
| LightOnOCR 2-1B | 1.0B | 83.2 |
| Chandra OCR 1 (Datalab) | 9.0B | 83.1 |
| olmOCR (anchored) | 8.3B | 77.4 |
| GOT OCR | 0.6B | 48.3 |

**Surya 2 per-source pass rates (default preset, 8,413 tests):** ArXiv 88.3, Base 99.7, Hdr/Ftr 92.5, TinyTxt 93.7, MultCol 82.4, OldScan 41.8, OldMath 81.4, Tables 86.6. [F]

### Marker's Overall PDF Conversion (single pages, H100, 2026)

> Source: https://github.com/datalab-to/marker README "Overall PDF Conversion" table.

| Method | Avg Time (s) | Heuristic Score | LLM Score |
| --- | --- | --- | --- |
| **Marker** | **2.84** | **95.67** | 4.24 |
| Docling | 3.70 | 86.71 | 3.70 |
| Mathpix | 6.36 | 86.43 | 4.16 |
| LlamaParse | 23.35 | 84.24 | 3.98 |

### Surya Multilingual (91 languages, internal benchmark)

> Top 15 widely-spoken: it 93.0%, en 92.3%, es 90.7%, de 89.7%, fr 89.3%, ru 88.8%, ko 86.7%, ja 86.2%, pt 86.1%, bn 82.7%, zh 82.5%, fa 82.3%, hi 82.2%, vi 73.2%, ar 72.7%. [F]

### Best / Worst / Median spread on OmniDocBench v1.6 Overall

- **Best (model ≤ 3B):** PaddleOCR-VL-1.6 96.3 (per dataset card) / MinerU2.5-Pro 95.75
- **Worst (above list):** Marker 78.44
- **Median (~20 entries):** ~89.5 (Qwen3-VL-235B 89.78 is near the median)
- **Best multimodal LLM (any size):** PaddleOCR-VL-1.6 96.3
- **Best closed (proprietary) API:** PaddleOCR-VL-1.6 (also open weights), Gemini 3 Pro 92.91, GPT-5.2 86.59

---

## 5. Pipeline Patterns

Five common pipelines in 2026, each with a representative project. LocalDeepL already does (1) + (2) — the opportunity is wiring (3) and (5) cleanly.

### Pattern 1 — Detection → OCR → Structure (TATR + Surya)

```
page image ──► Surya detection (boxes) ──► crop each table
                 │                               │
                 │                               └─► TATR structure model
                 │                                    emits (rows, columns, cells, header)
                 └─► Surya OCR (text + bboxes)
                                              ↓
                                       cells_to_html / cells_to_csv
                                       (file: src/inference.py:545, src/inference.py:516)
```

Used by: TATR `src/inference.py` (Camelot `flavor="ml"` wires this transparently), Docling, PaddleOCR, Marker.
Strengths: highest accuracy on structured/scientific tables. Weakness: needs a separate OCR step; multi-page stitching is the caller's problem.

### Pattern 2 — Heuristic / line-detection only (Camelot, Tabula, pdfplumber)

```
text-based PDF ──► extract chars/lines/rects (pdfminer.six)
                    │
                    ├─► lattice: find ruled lines + joints + cells (Camelot L186-189)
                    ├─► stream:   find whitespace-aligned columns (Camelot stream)
                    └─► text:     align word baselines (pdfplumber "text" strategy)
                                              ↓
                                       pandas.DataFrame
```

Used by: Camelot, Tabula, pdfplumber. Strengths: zero model, deterministic, sub-100 ms per page. Weakness: text-based PDFs only; fails on scanned pages; weak on borderless scientific tables.

### Pattern 3 — VLM end-to-end (Marker, PaddleOCR-VL, Surya 2, dots.ocr, Qwen3-VL)

```
page image ──► VLM (PaddleOCR-VL / Surya / Qwen3-VL)
              prompt: "transcribe this page to Markdown with table HTML"
                                              ↓
                                       Markdown / HTML
                                       (optionally with constraint:
                                        "JSON conforming to this Pydantic schema")
```

Used by: PaddleOCR-VL-1.6, Surya 2, Marker (`--use_llm`), Marker `ExtractionConverter`.
Strengths: best on long-tail layouts, multilingual, and forms. Weakness: requires GPU; pricing depends on token cost if API; less deterministic for financial tables.

### Pattern 4 — Pipeline + VLM augmentation (Marker default, Docling + GraniteDocling, MinerU)

```
PDF ──► pdftext / Tesseract (text) ─┐
       Surya detection              │
       Surya layout                 ├─► block tree ──► heuristic cleanup ──► Markdown
       TATR structure (per table)  │                   │
                                    │                   └─► (optional) VLM refine / merge
                                    │                        use_llm with Gemini / Ollama
```

Used by: Marker, Docling, MinerU-Pipeline.
Strengths: best of both worlds — fast and accurate on common cases, VLM-amplified on hard cases. Weakness: complex; the LLM augmentation step is where the real value sits (Marker 78.44 → 90+ on individual doc types with use_llm).

### Pattern 5 — Schema-constrained extraction (LocalDeepL opportunity)

```
PDF/image ──► Layout model (Surya)
              │
              └─► Per-page crop ──► VLM call
                                    with:  "Extract into this JSON Schema"
                                           + response_format: { type: "json_schema", strict: true }
                                              ↓
                                       pydantic_validate(parsed) ──► List[MySchema]
```

This is the 2026 frontier. Marker ships it as `ExtractionConverter` (beta). Instructor provides the multi-provider glue. OpenAI Structured Outputs / Anthropic tool use / Gemini function calling all support it natively. No current product combines Surya layout + structured-output VLM into a single LocalDeepL-style "load image + Pydantic model = List[Model]" workflow.

---

## 6. Gaps LocalDeepL Could Fill

A — with product-shape justifications, ordered by my read of value-vs-effort.

### G1. **Pydantic-native table/schema extraction** (high value, medium effort)

Marker has `ExtractionConverter` but it's beta and glued to Marker's pipeline. Instructor is multi-provider but doesn't ship a layout step. Nobody today ships:

```python
from localdeepl import extract
class Invoice(BaseModel):
    vendor: str
    total: float
    line_items: list[LineItem]
invoices: list[Invoice] = extract("invoice.pdf", schema=Invoice)
```

…that runs locally with Surya + PaddleOCR-VL-1.5 + OpenAI Structured Outputs fallback. This is the canonical "schema extraction" API every downstream developer wants. LocalDeepL's VLM/extraction surfaces (`api/routers/extraction.py` already exists per AGENTS.md) could be the natural home.

### G2. **A long-tail evaluation harness the user can run on their own data**

OmniDocBench v1.6 is a public 1,651-page benchmark. But a customer's actual PDF mix (their contracts, their scientific papers, their forms) is different. Marker ships a benchmark script (`marker/benchmarks/overall.py`), but no OSS leader ships "give me 50 of your PDFs and I'll tell you which engine is best for you." LocalDeepL's `examples/` could host a `track-eval-your-mix.py`.

### G3. **Hybrid: Surya layout + TATR-v1.1-All structure + Instructor schema**

This is the pipeline that wins on (a) scientific tables, (b) financial tables, (c) low-resource compute, and (d) deterministic JSON output. Pieces exist in OSS but are not glued together. LocalDeepL's `core/aligner.py` already does Surya-detection + DP alignment, which is the layout half. The structure half (TATR-v1.1-All) and the schema half (Instructor) are missing.

### G4. **A "we did the boring work" package for the Azure / Google / Textract outputs**

The cloud APIs return JSON in three different, mutually incompatible shapes (Azure's `Document` proto, Textract's `Block` graph, DocAI's `Document` proto). A library that normalizes all three into a single `Page` / `Table` / `Cell` Pydantic model with confidence scores would be a small OSS win. LocalDeepL has none of this — every user has to write it.

### G5. **Multi-page table stitching that works on real documents**

Camelot has `stack_contiguous()`; Marker has `--use_llm`; Azure DI says "split then merge" (https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0). None of them are first-class. A "stitch" primitive that takes a Document and returns `list[Table]` where each `Table` knows it spans N pages and which pages — that would be a clean OSS module.

### G6. **A schema-constrained DoclingDocument**

Docling's `DoclingDocument` is a beautiful lossless JSON IR (https://docling-project.github.io/docling/concepts/docling_document/). But it doesn't know about a user's Pydantic schema. A `DoclingDocument.to(Invoice)` projection would let users reuse Docling's layout quality with their own schema.

### G7. **PaddleOCR-VL-1.5/1.6 as a GroundedEngine backend**

Per the LocalDeepL AGENTS.md, the existing `core/grounded.py` already supports a `grounded_backend=` parameter for bbox-native VLM paths. PaddleOCR-VL-1.5 (94.93 on OmniDocBench) is a more recent, more accurate, more permissive (Apache-2.0, 109 languages) option than `ZAIHostedOCR` (the experimental backend listed in tech debt). Swapping is low-risk.

### G8. **RTL and Hebrew/Arabic tables as a first-class test case**

Surya's Arabic 72.7% (vs 92.3% English) and the "OldScan" 41.8% olmOCR pass rate are the long tail. No OSS leader markets "best-in-class RTL table extraction" as a feature. LocalDeepL's multilingual community (PaddleOCR-VL-1.5 supports 109 languages) could position this if it surfaces the support cleanly.

---

## 7. References

### Primary vendor documentation
- Google Document AI product page — https://cloud.google.com/document-ai (fetched 2026-06-14)
- Google Document AI sample output — https://docs.cloud.google.com/document-ai/docs/output
- Google Document AI Custom Extractor — https://docs.cloud.google.com/document-ai/docs/ce-derived-signature
- Azure Document Intelligence Layout v4.0 — https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0 (fetched 2026-06-14; page document_id 7c38afd5-0d67-48f8-9c68-433acf7fd956; updated 2025-11-18)
- Azure Document Intelligence What's New — https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/whats-new?view=doc-intel-4.0.0
- AWS Textract Tables — https://docs.aws.amazon.com/textract/latest/dg/how-it-works-tables.html (fetched 2026-06-14)
- AWS Textract Queries — https://docs.aws.amazon.com/textract/latest/dg/queryresponse.html
- AWS Textract pricing — https://aws.amazon.com/textract/pricing/
- AWS Bedrock Data Automation blog — https://aws.amazon.com/blogs/machine-learning/intelligent-document-processing-at-scale-with-generative-ai-and-amazon-bedrock-data-automation/
- AWS Bedrock Data Automation instruction optimization — https://aws.amazon.com/about-aws/whats-new/2025/12/bedrock-data-automation-optimization-document-blueprints/

### Open-source repositories
- microsoft/table-transformer — https://github.com/microsoft/table-transformer (MIT, fetched 2026-06-14); core file `src/inference.py` (L24-35 detection_transform, L37-41 structure_transform, L42-49 structure class map, L516-542 cells_to_csv, L545-578 cells_to_html)
- camelot-dev/camelot — https://github.com/camelot-dev/camelot (MIT, fetched 2026-06-14); core file `camelot/parsers/lattice.py` (L26-30 _GRID_WHITESPACE_REJECT, L60 engines, L186-189 _resolve_engine, L260-285 _augment_masks_with_vector_lines, L351-353 _reject_table)
- tabulapdf/tabula — https://github.com/tabulapdf/tabula (MIT, fetched 2026-06-14)
- jsvine/pdfplumber — https://github.com/jsvine/pdfplumber (MIT, fetched 2026-06-14)
- PaddlePaddle/PaddleOCR — https://github.com/PaddlePaddle/PaddleOCR (Apache-2.0, fetched 2026-06-14)
- docling-project/docling — https://github.com/docling-project/docling (MIT, fetched 2026-06-14)
- Unstructured-IO/unstructured — https://github.com/Unstructured-IO/unstructured (Apache-2.0, fetched 2026-06-14)
- datalab-to/marker — https://github.com/datalab-to/marker (GPL-3.0 code, Open Rail-M weights, fetched 2026-06-14)
- datalab-to/surya — https://github.com/datalab-to/surya (Apache-2.0 code, Open Rail-M weights, fetched 2026-06-14)
- 567-labs/instructor — https://github.com/567-labs/instructor (MIT, fetched 2026-06-14)
- opendatalab/OmniDocBench — https://github.com/opendatalab/OmniDocBench (Apache-2.0, fetched 2026-06-14)

### arXiv / papers
- PubTables-1M (CVPR 2022) — arXiv:2110.00061
- GriTS (ICDAR 2023) — arXiv:2203.12555
- Aligning benchmark datasets (ICDAR 2023) — arXiv:2303.00716
- Docling Technical Report (v5, 9 Dec 2024) — arXiv:2408.09869
- PaddleOCR 3.0 Technical Report — arXiv:2507.05595
- PaddleOCR-VL (0.9B) — arXiv:2510.14528
- PaddleOCR-VL-1.5 — arXiv:2601.21957
- PaddleOCR-VL-1.6 — arXiv:2606.03264
- ClusterTabNet — arXiv:2402.07502
- Soric et al., "Benchmarking Table Extraction from Heterogeneous Scientific Extraction Documents" — arXiv:2511.16134
- "Beyond String Matching: Semantic Evaluation of PDF Table Extraction" — arXiv:2603.18652
- Infinity-Parser — https://openreview.net/pdf?id=M3GgDDGYec
- "Benchmarking Table Extraction: Multimodal LLMs vs Traditional OCR" — https://aclanthology.org/2025.xllm-1.2.pdf

### Documentation
- OpenAI Structured Outputs guide — https://platform.openai.com/docs/guides/structured-outputs (fetched 2026-06-14)
- olmOCR-bench dataset card — https://huggingface.co/datasets/allenai/olmocr-bench

### Internal LocalDeepL references
- `AGENTS.md` — pipeline paths, current docling/datalab-to/marker references, grounded_backend extension point
- `C:\Users\rahin\LocalDeepL\.mavis\plans\scout\track-schema-evidence.md` — full evidence ledger with file:line citations
- `C:\Users\rahin\LocalDeepL\.mavis\plans\scout\track-schema.md` — this file (deliverable)
