# AI OCR Vision Models — Scout Report (track-ocr-vision)

**Audience**: solo maintainer of LocalDeepL (Windows / uv / pytest-uv workflow, hybrid OCR + grounded pipeline).
**Goal**: identify which AI OCR vision models LocalDeepL should adopt, swap, or compete with, with execution evidence (run commands, VRAM, licenses, benchmark numbers) and code citations.
**Method**: parallel sub-agent webfetches against official GitHub READMEs, model cards on Hugging Face, NVIDIA build.nvidia.com, Microsoft Azure docs, Google Cloud Document AI, and arXiv. All evidence lives in `track-ocr-evidence.md` next to this file.
**Date of scout**: 2026-06-14. Every claim tagged [F] (factual, with source) or [A] (analysis / interpretation). Model state and benchmark numbers are a moving target — re-verify any number before quoting it externally.

---

## 1. Executive Summary

The 2026 OCR landscape has split into four tiers that matter for LocalDeepL:

1. **Closed cloud APIs** (Google Document AI + Gemini, Azure Document Intelligence, Mistral OCR) — best top-line quality on heterogeneous documents, but pure pay-per-page and no self-host. Google Document AI's Gemini-based Custom Extractor now reaches `pretrained-foundation-model-v1.5-pro-2025-06-20` (Gemini 2.5 Pro) and `v1.6-pro-2025-12-01` (Gemini 3 Pro preview), with v4.0 Layout Parser using HTML-table output for merged cells [F — docs.cloud.google.com/document-ai/docs/processors-list, fetched 2026-06-14]. [A — for a local-first product these are reference targets, not adoptable].

2. **Open-source document-OCR VLMs** (Surya, PaliGemma 2, GOT-OCR-2.0, OlmOCR, DeepSeek-OCR, Chandra OCR, dots.mocr, LightOnOCR-2, Qwen2.5-VL / Qwen3-VL) — these are what LocalDeepL should compare against. As of June 2026 the **olmOCR-bench** leaderboard looks like: Datalab API 86.7, Infinity-Parser2-Pro (35.1B) 87.6, Chandra OCR 2 (5.3B) 85.9, Surya OCR 2 (0.65B) 83.3, dots.mocr (3.0B) 83.9, LightOnOCR-2 (1B) 83.2, Chandra OCR 1 (9.0B) 83.1, olmOCR-2 anchored (8.3B) 77.4, GOT-OCR (0.6B) 48.3 [F — datalab-to/surya README "Benchmarks" section, datalab-to/chandra README "Benchmark table", allenai/olmocr README "Benchmark", all fetched 2026-06-14]. **A** — Surya being #4 at 0.65B parameters is the story for a small local product: it is competitive with 5-9B models on this benchmark.

3. **Open-source general VLMs** that can do OCR as a side capability (Qwen2.5/3-VL, InternVL3.5, Phi-4-multimodal, Mistral Pixtral, Llama 3.2 Vision, PaliGemma 2) — these are not the right primary OCR engine, but they make plausible **grounded_backend** candidates (single-call, bbox-native, fewer moving parts than Surya-detection + VLM-OCR). Phi-4-multimodal-instruct 5.6B at 93.2 DocVQA / 84.4 OCRBench is the most credible in the small-class, MIT-licensed slot [F — huggingface.co/microsoft/Phi-4-multimodal-instruct model card, fetched 2026-06-14].

4. **Classical / small models** (Tesseract 5 LSTM, docTR, PP-OCRv6, EasyOCR) — best where the input is line-art / scanned forms / CPU-only. PP-OCRv6 34.5M model claims to beat Qwen3-VL-235B and GPT-5.5 on detection+recognition while running 0.13s on A100 [F — PaddlePaddle/PaddleOCR README "2026.06.11 Release of PaddleOCR 3.7.0", fetched 2026-06-14]. [A] — useful as a CPU-only fallback or for very high-volume low-complexity jobs.

**For LocalDeepL, the actionable picture is**:

- **Surya 2 is currently the right primary detection engine** in the hybrid path — confirmed state-of-the-art for sub-1B param class on olmOCR-bench and 5 pages/s on a single RTX 5090, with separate EfficientViT/Segformer line detector and a Qwen3.5-style VLM under the hood [F — datalab-to/surya README]. The modified-OpenRAIL-M model weight license gates commercial startups >$5M funding/revenue; code is Apache-2.0 [F — same].
- **The grounded path is a real product moat for LocalDeepL**. Single-call bbox-native VLMs (dots.mocr 3B, Chandra OCR 2 5.3B, PaliGemma 2 3B, Phi-4-multimodal 5.6B, Qwen2.5-VL-7B) all output structured bboxes+text in one forward pass, skipping Surya's detection → DP-alignment → refine cycle. The right next move is to expose a `grounded_backend` switch that lets the user pick between them, and to default to **dots.mocr 3B** (Apache-2.0 MIT-style, 0.9 s/page on A100-class, OmniDocBench v1.5 1059 Elo, olmOCR-bench 83.9) [F — rednote-hilab/dots.ocr README "News" / "Hugginface inference", fetched 2026-06-14].
- **License landscape is a 2026 problem, not a 2016 problem**. The new modified-OpenRAIL-M gates on Surya and Chandra; PaliGemma stays on the Gemma terms (non-commercial-friendly for research but problematic for many businesses); Pixtral, Florence-2, Phi-3.5/4, Qwen, InternVL, Mistral, Nougat weights, GOT, DeepSeek-OCR-2, PaddleOCR, Surya code, TATR, docTR are all Apache-2.0 or MIT and clearly commercial-friendly. Nougat's weights are CC-BY-NC (not commercial). [A — synthesis from fetched license fields].

---

## 2. Players by Company

### 2.1 Google

| Product | Role for LocalDeepL | Key evidence |
|---|---|---|
| **Gemini 2.5 Pro** (`gemini-2.5-pro`) | Cloud reference; not local | Custom Extractor `pretrained-foundation-model-v1.5-pro-2025-06-20` is "Production-ready model powered by the Gemini 2.5 Pro LLM" (cloud). [F — docs.cloud.google.com/document-ai/docs/processors-list, fetched 2026-06-14] |
| **Gemini 2.5 Flash** | Cloud reference | Custom Extractor `pretrained-foundation-model-v1.5-2025-05-05` is "Production-ready candidate powered by Gemini 2.5 Flash LLM" (cloud). [F — same] |
| **Gemini 3 Pro** (preview Dec 2025) | Cloud reference | `pretrained-foundation-model-v1.6-pro-2025-12-01` powered by Gemini 3 Pro LLM; uses Vertex AI global endpoint (not DMZ-compliant). [F — same] |
| **Document AI Layout Parser** | Open doc parser (cloud) | API type `LAYOUT_PARSER_PROCESSOR`. Supports PDF, HTML, DOCX, PPTX, XLSX/XLSM. Extracts text/tables/lists and emits "context-aware chunks" for RAG. [F — docs.cloud.google.com/document-ai/docs/processors-list] |
| **Document AI Form Parser** | Form KIE (cloud) | API type `FORM_PARSER_PROCESSOR`. Latest GA `pretrained-form-parser-v2.0-2022-11-10` supports 200+ languages, 11 generic entities. [F — same] |
| **Document AI Enterprise OCR** | OCR (cloud) | API type `OCR_PROCESSOR`. Latest GA `pretrained-ocr-v2.1-2024-08-07` ("better printed text recognition, more precise checkbox detection and more accurate reading order"). 200+ languages including handwriting. [F — same] |
| **PaliGemma 2** (3B / 10B / 28B) | Local VLM candidate for grounded path | HF cards: `google/paligemma2-3b-pt-224`, `google/paligemma2-10b-pt-224`, `google/paligemma2-28b-pt-224`. Code in google-research/big_vision. License: **Gemma terms** (non-commercial-friendly, requires HF click-through). DocVQA val (448-28B ft): 76.1. [F — huggingface.co/google/paligemma2-3b-pt-224 + arXiv 2412.03555, fetched 2026-06-14] |
| **PaliGemma 1** (3B) | Older local VLM | DocVQA val (pt-896 ft): 84.77. Superseded by PaliGemma 2. [F — huggingface.co/google/paligemma-3b-pt-224] |
| **Gemma 4** (latest Gemma open-weight) | Local LLM backbone (text only) | `gemma4_e4b_it` (multimodal) per `google-deepmind/gemma` README; 8GB+ GPU RAM for 2B checkpoint, 24GB+ for 7B. Apache-2.0. [F — github.com/google-deepmind/gemma, fetched 2026-06-14] |

**Local-host equivalents of Google's Gemini/DA cloud** are **not** shipped as open weights; the closest is `zai-org/GLM-OCR` 0.9B which `dot.mocr` README's leaderboards call "performance close to Gemini-3-Pro" on the four sub-tasks of OmniDocBench v1.5 (text/formula/table/info-extraction) [A — secondary citation via rednote-hilab/dots.ocr README "Leaderboard" section, fetched 2026-06-14, originally from Z.AI announcement on wisemodel.cn and ithome.com 2026-02-03]. [F for the 0.9B number and the date].

### 2.2 Microsoft

| Product | Role for LocalDeepL | Key evidence |
|---|---|---|
| **Florence-2** (0.23B / 0.77B) | Local bbox+OCR task tokens | Tasks include `<OCR>`, `<OCR_WITH_REGION>`, `<OD>`, `<CAPTION>`, `<CAPTION_TO_PHRASE_GROUNDING>`, `<OPEN_VOCABULARY_DETECTION>`, `<REFERRING_EXPRESSION_SEGMENTATION>`. MIT. Florence-2-large 0.77B 4k context. CIDEr 135.6 on COCO Cap. [F — huggingface.co/microsoft/Florence-2-large, fetched 2026-06-14] |
| **Florence-VL** (2025 paper only) | Research only | "Florence-VL: Enhancing Vision-Language Models with Generative Vision Encoder and Index-Aware Generation" — Microsoft Research Asia paper, no first-party weights or repo. [A — negative finding; no first-party product discoverable] |
| **Phi-3.5-vision** (4.2B) | Local small VLM | MIT. vLLM, SGLang, Ollama, llama.cpp, LM Studio, Docker Model Runner. MMMU 43.0, ChartQA 81.8, TextVQA 72.0, BLINK 57.0, Video-MME 50.8. [F — huggingface.co/microsoft/Phi-3.5-vision-instruct, fetched 2026-06-14] |
| **Phi-4-multimodal** (5.6B) | Local small VLM with audio | MIT. DocVQA 93.2, OCRBench 84.4, MMMU 55.1, ChartQA 81.4, InfoVQA 72.7, AI2D 82.3. ASR WER 6.14% (HF OpenASR #1 as of Mar 2025). First open-sourced model that can do speech summarization. [F — huggingface.co/microsoft/Phi-4-multimodal-instruct, fetched 2026-06-14] |
| **LayoutLMv3** (base/large/base-chinese) | Document KIE / classification | **CC BY-NC-SA 4.0 (non-commercial)**. FUNSD F1 0.9059 (base-ft), PubLayNet mAP 95.1. Requires Detectron2 + CUDA 11.1. Code in microsoft/unilm. [F — github.com/microsoft/unilm/tree/master/layoutlmv3, fetched 2026-06-14] |
| **Table Transformer (TATR v1.1)** | Table structure recognition | MIT. TATR-v1.1-Pub/Fin/All, DETR R18, 110 MB. GriTSTop 0.9849 on PubTables-1M. Requires external OCR or PDF text. Code in microsoft/table-transformer. [F — github.com/microsoft/table-transformer, fetched 2026-06-14] |
| **Azure AI Document Intelligence** v4.0 | Cloud reference for production | Service, not model. Prebuilt: Read, Layout, Form Parser, Invoice, Receipt, Contract, US unified tax (W-2/W-4/1040/1095/1098/1099 etc.), US mortgage, Marriage cert, Credit card, ID, Health insurance, Bank check, Bank statement, payStub. Add-ons: ocrHighResolution, formulas, styleFont, barcodes, languages, keyValuePairs, queryFields, searchablePDF. v4.0 GA 2024-11-30; markdown output via `outputContentFormat=markdown`. On-prem Docker containers available. [F — learn.microsoft.com/en-us/azure/ai-services/document-intelligence/, fetched 2026-06-14] |
| **PhiCookBook** | Examples / fine-tuning guides | microsoft/PhiCookBook — Phi-3.5-vision and Phi-4-multimodal examples. [F — github.com/microsoft/PhiCookBook, fetched 2026-06-14] |

### 2.3 NVIDIA

| Product | Role for LocalDeepL | Key evidence |
|---|---|---|
| **Nemotron Parse 1.1** (885M, encoder-decoder) | Local OCR + bboxes (single GPU) | arXiv 2511.20478 (2025-11-25). Tasks: general OCR, markdown formatting, structured table parsing, text+chart+diagram extraction, bboxes with semantic classes. English only. Tokenizer CC-BY-4.0; model NVIDIA Community Model License. TC variant 20% faster. NIM hosted + HF weights downloadable. [F — arxiv.org/abs/2511.20478 + build.nvidia.com/nvidia/nemotron-parse, fetched 2026-06-14] |
| **Nemoretriever-Parse-1.0** (predecessor) | NIM OCR | build.nvidia.com/nvidia/nemotron-parse (1.0 lineage) "Cutting-edge vision-language model exceling in retrieving text and metadata from images." [F — same] |
| **NeMo Retriever** (NIM stack) | Pipeline platform, not a single model | Components: nemoretriever-page-elements-v2, nemoretriever-table-structure-v1, nemoretriever-graphic-elements-v1, nv-yolox-structured-image-v1, plus PaddleOCR, plus llava-onevision, plus llama-3.2-nv-embedqa-1b-v2 (embedding), plus Nemotron rerank. Claims "50% fewer incorrect answers" Recall@5, "15× higher multimodal extraction throughput" vs OSS. 1×H100 SXM benchmark. Open source: github.com/NVIDIA/nv-ingest (`release/25.6.3`). [F — developer.nvidia.com/nemo-retriever + github.com/NVIDIA/nv-ingest, fetched 2026-06-14] |
| **build.nvidia.com** catalog | Catalog | 139 models (June 2026), 10 in "Image-to-Text" use-case. 77 free endpoints, 43 partner, 105 downloadable. Publishers: NVIDIA 74, Meta 11, Google 6, Mistral AI 6, Qwen 5. Container GPUs: B200, H100 80GB HBM3, H200, L40S, A100 SXM4 80GB. NIM run command pattern: `docker run nvcr.io/nim/publisher_name/model_name`. [F — build.nvidia.com/models, fetched 2026-06-14] |
| **Nemotron-3 Ultra / Nano / Content Safety** (Catalog) | Reference, not OCR | Various sizes; not OCR-specific. [F — build.nvidia.com/models listing] |
| **Cosmos-3 Nano** (catalog) | Physical-AI / video, not OCR | Per build.nvidia.com catalog, Cosmos3-nano "Generates physics-aware videos from text prompts or an image prompt for physical AI development" — not a document model. [A — for LocalDeepL document OCR use case, Cosmos is irrelevant] |

**Note**: the user's task brief said "NV-OCR-1.0 / newer NV-OCR". NVIDIA does not currently ship a model specifically named "NV-OCR" in build.nvidia.com. The closest functional equivalents are **Nemotron Parse 1.1** (encoder-decoder OCR) and the **Nemoretriever Page Elements v2** NIM (page segmentation). The user's task brief also mentioned "Cosmos-OCR" and "VISTA-3D" — neither exists as an OCR model; Cosmos is a world-foundation-model family and VISTA-3D is a medical-imaging 3D segmentation model. [A — negative findings, verified by build.nvidia.com catalog scan 2026-06-14].

### 2.4 Meta

| Product | Role for LocalDeepL | Key evidence |
|---|---|---|
| **Nougat** (0.1.0-small, 0.1.0-base) | Academic paper OCR → Mathpix Markdown | Donut-style encoder-decoder. **Code MIT, weights CC-BY-NC (non-commercial)** — "Nougat was trained on scientific papers found on arXiv and PMC. ... Chinese, Russian, Japanese etc. will not work." CLI: `nougat path/to/file.pdf -o output_dir`. Optional FastAPI server `nougat_api` (port 8503). [F — github.com/facebookresearch/nougat, fetched 2026-06-14] |
| **Llama 3.2 Vision** (11B, 90B) | Local VLM, large | Released 2024-09-25. Llama 3.2 community license (commercial OK with AUP). 700M-download cap per 24h on direct Meta URL. HF class `MllamaForConditionalGeneration`. [F — github.com/meta-llama/llama-models README "Llama Models" table, fetched 2026-06-14] |
| **SAM 2 / SAM 2.1** (38.9M / 46M / 80.8M / 224.4M) | Local segmentation (not OCR) | Apache 2.0. SAM 2.1 large 224.4M = 39.5 FPS on A100, SA-V J&F 79.5, MOSE 74.6, LVOS v2 80.6. Useful as upstream segmentation for layout / region detection. [F — github.com/facebookresearch/sam2 README "Model Description", fetched 2026-06-14] |

**Note**: Meta does not ship a general-purpose document OCR VLM in 2026; the closest is Llama 3.2 Vision which is a multimodal chat model, not a document parser. [A].

### 2.5 Mistral

| Product | Role for LocalDeepL | Key evidence |
|---|---|---|
| **Pixtral 12B** (12B LM + 400M vision) | Local VLM (Apache 2.0) | vLLM, mistral-inference. DocVQA 90.7, ChartQA 81.8, MathVista 58.0, MMMU 52.5. Variable image sizes, 128k context. Limitations: "The Pixtral model does not have any moderation mechanisms." GitHub `mistralai/pixtral` 404s — only HF + vllm. [F — huggingface.co/mistralai/Pixtral-12B-2409, fetched 2026-06-14] |
| **Pixtral Large** (124B, 2024-11) | Cloud reference | 124B model, proprietary, not in this scout's local-host scope. [A — from Pixtral 12B card reference, not directly fetched] |

**Note**: Mistral's "Mistral OCR" service is a separate API product (referenced as "Mistral OCR API" in olmOCR-bench tables, e.g. 72.0±1.1 on allenai/olmocr README). [A — cited but not directly fetched; see evidence file].

### 2.6 Open-source (selected 12 most relevant, by ecosystem)

In tier order — by olmOCR-bench performance where applicable.

#### Tier 1: Best-in-class open document-OCR VLMs (≤ ~5B)

1. **Surya OCR 2** (0.65B) — Datalab. Apache-2.0 code, modified OpenRAIL-M weights. 83.3 olmOCR-bench, 5 pages/s RTX 5090, 90+ languages. Layout+OCR+table_rec in one VLM + separate EfficientViT/Segformer detector. **[Already used by LocalDeepL as the `aligner` / detection backbone in `core/workflows/hybrid.py`]**. [F — datalab-to/surya README, fetched 2026-06-14]

2. **dots.mocr** (3.0B) — rednote-hilab. MIT code, separate model weight license. Single VLM does layout + recognition in one forward. 83.9 olmOCR-bench (Chandra citation). 1124.7 Elo on benchmark-of-Elo (Gemini 3 Flash judge) vs PaddleOCR-VL-1.5 920.5, GLM-OCR 892.5, HuanyuanOCR 984.2, Gemini 3 Pro 1210.7. DocVQA 91.85, ChartQA 83.2, OCRBench 86.0, infoVQA 73.76. vLLM 0.11.0+ integrated. [F — github.com/rednote-hilab/dots.ocr README, fetched 2026-06-14]

3. **Chandra OCR 2** (5.3B) — Datalab. Apache-2.0 code, modified OpenRAIL-M weights. 85.9 olmOCR-bench (only Datalab API 86.7 is higher in the same table). 90+ languages, handwriting, forms w/ checkboxes, images+diagrams with captions. CLI: `chandra input.pdf ./output` via vLLM or HF. H100 throughput 1.44 pages/s @ concurrency 96. [F — github.com/datalab-to/chandra README, fetched 2026-06-14]

4. **OlmOCR** (7B / 8.3B anchored) — Allen AI. Apache-2.0. 7B Qwen2.5-VL SFT + GRPO RL (v2). olmOCR-bench v0.4.0: ArXiv 83.0, OldScansMath 82.3, Tables 84.9, OldScans 47.7, H/F 96.1, MultiCol 83.7, LongTiny 81.9, Base 99.7, Overall 82.4±1.1. CLI: `olmocr ./workspace --markdown --pdfs <file>`. vLLM supported. ≥12 GB VRAM, ≥30 GB disk. <$200 / million pages at 7B. [F — github.com/allenai/olmocr README, fetched 2026-06-14]

5. **GOT-OCR-2.0** (0.58B) — Stepfun / Ucas-HaoranWei. Apache-2.0 code, CC BY NC 4.0 data. Unified end-to-end VLM, plain/format/region/multi-page OCR. olmOCR-bench 48.3 (low — see benchmark table). HuggingFace trending #1, 1M+ downloads. [F — github.com/Ucas-HaoranWei/GOT-OCR2.0 README, fetched 2026-06-14]

6. **DeepSeek-OCR** (3B) — DeepSeek. MIT. "Contexts Optical Compression" — LLM-centric view of vision encoder. Multiple resolution modes (Tiny 512² / Small 640² / Base 1024² / Large 1280²) + dynamic Gundam. olmOCR-bench 75.7±1.0 (below top models but unique design). Author Haoran Wei — same as GOT-OCR. DeepSeek-OCR-2 ("Visual Causal Flow") released Jan 2026, Apache-2.0. [F — github.com/deepseek-ai/DeepSeek-OCR + dots.ocr/olmocr/chandra READMEs cross-referencing, fetched 2026-06-14]

7. **Qwen2.5-VL / Qwen3-VL** (2B / 4B / 8B / 32B / 72B / 235B-A22B MoE) — Alibaba. Apache-2.0. vLLM, SGLang, transformers, Ollama (Qwen2.5). Native 256K context, expandable to 1M. 32 OCR languages. Qwen3-VL architecture: Interleaved-MRoPE, DeepStack, Text-Timestamp Alignment. 2B and 8B AWQ quantizations for Qwen2.5-VL reduce VRAM. Qwen3-VL is the canonical Qwen LM README as of 2026-06-14 (Qwen2.5-VL repo redirects). [F — github.com/QwenLM/Qwen3-VL README, fetched 2026-06-14]

8. **InternVL3.5** (1B / 2B / 4B / 8B / 14B / 38B / 20B-A4B MoE / 30B-A3B MoE / 241B-A28B MoE) — Shanghai AI Lab / OpenGVLab. MIT. InternViT-300M-448px-V2_5 (small) and InternViT-6B-448px-V2_5 (large) vision backbones. CascadeRL. InternVL2-Pro "SOTA on DocVQA and InfoVQA benchmarks" (2024-07). Mini-InternVL-Chat-4B-V1-5: "16% of the model size, 90% of the performance". [F — github.com/OpenGVLab/InternVL README, fetched 2026-06-14]

9. **PaliGemma 2** (3B / 10B / 28B) — Google. **Gemma terms (non-commercial, click-through)**. Code in google-research/big_vision. DocVQA val (448-28B ft): 76.1. ChartQA aug (448-10B ft): 90.1. Strong on fine-tuning, weak zero-shot. [F — huggingface.co/google/paligemma2-3b-pt-224, fetched 2026-06-14]

10. **Mistral Pixtral 12B** (12B + 400M) — Mistral. Apache 2.0. vLLM, mistral-inference. DocVQA 90.7, ChartQA 81.8. Variable image sizes, 128k context. [F — huggingface.co/mistralai/Pixtral-12B-2409, fetched 2026-06-14]

#### Tier 2: Small / classical / on-device

11. **PaddleOCR-VL** (0.9B) + **PP-OCRv6** (1.5M / 7.7M / 34.5M) + **PP-StructureV3** — Baidu. Apache-2.0. NaViT dynamic high-res visual encoder + ERNIE-4.5-0.3B LM. 111 languages. OmniDocBench v1.6 96.3% (SOTA), v1.5 94.5%, Real5-OmniDocBench SOTA. PP-OCRv6 medium 34.5M claims +4.6% det / +5.1% rec over PP-OCRv5_server, "surpassing Qwen3-VL-235B and GPT-5.5". CPU speedup 5.2× OpenVINO, 6.1× Apple M4 (tiny), 0.13s on A100. DOCX export since 3.5.0. [F — github.com/PaddlePaddle/PaddleOCR README, fetched 2026-06-14]

12. **Tesseract 5** (no param count) — Apache-2.0. LSTM engine since Tesseract 4 (line recognition only). 100+ languages via separate traineddata. Outputs: plain text, hOCR (HTML), PDF, invisible-text PDF, TSV, ALTO, PAGE. **No native PDF input, CPU only, line-level only.** 5.5.2 released Dec 2025. [F — github.com/tesseract-ocr/tesseract README, fetched 2026-06-14]

#### Tier 3: Specialized / older but interesting

- **docTR** (Mindee) — Apache-2.0. Two-stage detector (DBNet/LinkNet/FAST) + recognizer (CRNN/SAR/MASTER/ViTSTR/PARSeq/VIPTR). PyTorch. Streamlit demo, FastAPI template, Docker (CUDA 12.2). No top-line benchmark numbers in README — flex-arch, not SOTA. [F — github.com/mindee/doctr, fetched 2026-06-14]
- **SmolVLM** (HuggingFace) — Apache-2.0. 2B total. SigLIP 384×384 + SmolLM2 1.7B + 9× pixel shuffle. Min GPU RAM 5.02 GB. DocVQA test 81.6, MMMU 38.8. Trained with Idefics3 implementation in transformers. [F — github.com/huggingface/smollm README, fetched 2026-06-14]
- **LayoutLMv3** (Microsoft) — CC BY-NC-SA 4.0 (non-commercial). Document KIE. [F — see §2.2].
- **Table Transformer (TATR v1.1)** (Microsoft) — MIT. Table detection/structure. [F — see §2.2].
- **Nougat** (Meta) — CC-BY-NC weights. Academic paper OCR. [F — see §2.4].

#### Tier 4: Not adopted in 2026 — not competitive

- **Florence-2** (Microsoft) — 2023-vintage. Still useful for task-token-conditional bbox+OCR; not state-of-the-art on olmOCR-bench-style metrics. [A].
- **PaliGemma 1** — superseded by PaliGemma 2. [A].
- **EasyOCR** — not in this scout's evidence pass. Would need a dedicated fetch. [A].
- **LightOnOCR-2 1B** — appears in olmOCR-bench comparison (83.2). No direct README fetch in this scout. [A — third-party citation only, see evidence file].
- **Mimo-7B-OCR** — recent (2025-2026) addition; not covered in this scout. [A].

---

## 3. Execution / Deployment Matrix

For each row, the "Run command" column is the **exact** line from the official README or model card. "Min VRAM" is taken from the cited source where it states a minimum or a measured throughput tier; otherwise the column gives the recommended GPU class based on the model size and inference stack.

| Model | Size | License (commercial OK?) | Inference server / run | Min VRAM (or rec GPU) | Precision | Notes for LocalDeepL |
|---|---|---|---|---|---|---|
| **Surya 2** (VLM) | 0.65B | Apache-2.0 code + **modified OpenRAIL-M** weights (gated on startup funding/revenue) | vLLM (auto-spawned by `SuryaInferenceManager`) or llama-server (Apple Silicon / CPU) | ~6 GB VRAM; 5.35 pages/s on RTX 5090 (32 GB) | bfloat16 native | **Already used by LocalDeepL `aligner`**. Env vars: `SURYA_INFERENCE_BACKEND=vllm\|llamacpp`, `SURYA_INFERENCE_URL`, `SURYA_INFERENCE_PARALLEL=8`. [F — datalab-to/surya README, fetched 2026-06-14] |
| **Surya detector** (EfficientViT/Segformer) | small (separate from VLM) | Apache-2.0 + modified OpenRAIL-M | torch (no VLM required) | CPU-friendly; GPU optional | fp32 / fp16 | Already used in `core/aligner.py`. [F — same] |
| **dots.mocr** | 3.0B | MIT code + separate model weight license (rednote-hilab) | vLLM 0.11.0+ (integrated) | 1× A100/H100 (no explicit GB; uses `gpu-memory-utilization 0.9`) | bf16 | Strong grounded-backend candidate. `CUDA_VISIBLE_DEVICES=0 vllm serve rednote-hilab/dots.mocr --tensor-parallel-size 1 --gpu-memory-utilization 0.9 --chat-template-content-format string --served-model-name model --trust-remote-code`. [F — rednote-hilab/dots.ocr README, fetched 2026-06-14] |
| **Chandra OCR 2** | 5.3B | Apache-2.0 code + **modified OpenRAIL-M** weights (gated on startup funding/revenue + non-competitive-use clause) | vLLM (Docker) or HF (transformers) | 1×H100 80GB (measured 1.44 pages/s @ concurrency 96) | bf16 | `pip install chandra-ocr`; `chandra_vllm`; `chandra input.pdf ./output --method hf`. Slowest OCR VLM in this scout. [F — datalab-to/chandra README, fetched 2026-06-14] |
| **OlmOCR** (2-7B-FP8) | 7B (FP8) | Apache-2.0 | vLLM (`vllm serve allenai/olmOCR-2-7B-1025-FP8 --max-model-len 16384`) | ≥12 GB VRAM, ≥30 GB disk; RTX 4090 / L40S / A100 / H100 | FP8 | `pip install olmocr[gpu] --extra-index-url https://download.pytorch.org/whl/cu128`. [F — allenai/olmocr README, fetched 2026-06-14] |
| **GOT-OCR-2.0** | 0.58B | Apache-2.0 code + CC BY NC 4.0 data | Custom Python (transformers, flash-attn) | cuda11.8 + torch2.0.1; no explicit GB | bf16 | `python3 GOT/demo/run_ocr_2.0.py --model-name /GOT_weights/ --image-file /x.png --type ocr`. [F — Ucas-HaoranWei/GOT-OCR2.0 README, fetched 2026-06-14] |
| **DeepSeek-OCR** (v1) | 3B | MIT | vLLM 0.8.5+ (upstream supported since 2025-10-23) | A100-40G demonstrated | bf16 | `vllm serve deepseek-ai/DeepSeek-OCR` with `NGramPerReqLogitsProcessor` for grounding. [F — deepseek-ai/DeepSeek-OCR README, fetched 2026-06-14] |
| **DeepSeek-OCR-2** (Visual Causal Flow) | (unspecified) | Apache-2.0 | vLLM | A100-40G demonstrated | bf16 | Released Jan 2026. [F — same] |
| **Qwen3-VL** | 2B / 4B / 8B / 32B / 30B-A3B / 235B-A22B | Apache-2.0 | vLLM, SGLang, transformers (>=4.57.0), qwen-vl-utils==0.0.14, Ollama (Qwen2.5 only) | 2B fits 8 GB; 235B requires multi-GPU | bf16 + AWQ 4-bit | `transformers >= 4.57.0`; `qwen-vl-utils==0.0.14`. [F — QwenLM/Qwen3-VL README, fetched 2026-06-14] |
| **Qwen2.5-VL** | 3B / 7B / 32B / 72B + AWQ | Apache-2.0 | Same as Qwen3-VL | AWQ-quantized 3B/7B/72B reduce VRAM | bf16 + AWQ 4-bit | Original Qwen2.5-VL repo now redirects to Qwen3-VL. [F — same] |
| **InternVL3.5** | 1B / 2B / 4B / 8B / 14B / 38B + 20B-A4B / 30B-A3B / 241B-A28B MoE | MIT | transformers (trust_remote_code=True); vLLM + Ollama listed as TODO | 1B-8B single-GPU; 78B+ multi-GPU | bf16 | `from transformers import AutoModel, AutoTokenizer; model = AutoModel.from_pretrained("OpenGVLab/InternVL3_5-8B", trust_remote_code=True).eval().cuda()`. [F — OpenGVLab/InternVL README, fetched 2026-06-14] |
| **PaliGemma 2** | 3B / 10B / 28B | **Gemma terms** (non-commercial-friendly, click-through) | transformers (PaliGemmaProcessor, PaliGemmaForConditionalGeneration); vLLM, SGLang, bitsandbytes 4/8-bit | bf16; CPU float32 supported | bf16 + 4/8-bit | `vllm serve "google/paligemma2-3b-pt-224"`. License not commercial-safe in some jurisdictions. [F — huggingface.co/google/paligemma2-3b-pt-224, fetched 2026-06-14] |
| **Pixtral 12B** | 12B + 400M | Apache 2.0 | vLLM (>=0.6.2) + mistral_common (>=1.4.4); mistral-inference (>=1.4.1) | Not stated; vLLM default `max_model_len=32768`; lower on low-VRAM | bf16 | `vllm serve mistralai/Pixtral-12B-2409 --tokenizer_mode mistral --limit_mm_per_prompt 'image=4'`. [F — huggingface.co/mistralai/Pixtral-12B-2409, fetched 2026-06-14] |
| **Phi-3.5-vision** | 4.2B | MIT | vLLM, SGLang, Ollama, llama.cpp, LM Studio, Docker Model Runner; transformers (>=4.43.0) | A100/A6000/H100 (flash-attn required); V100 with `_attn_implementation='eager'` | bf16 | `vllm serve "microsoft/Phi-3.5-vision-instruct"`. [F — huggingface.co/microsoft/Phi-3.5-vision-instruct, fetched 2026-06-14] |
| **Phi-4-multimodal** | 5.6B | MIT | transformers (>=4.48.2); vLLM with vision-lora + speech-lora; ONNX | A100/A6000/H100 | bf16 | `python -m vllm.entrypoints.openai.api_server --model 'microsoft/Phi-4-multimodal-instruct' --dtype auto --trust-remote-code --max-model-len 131072 --enable-lora --max-lora-rank 320 --lora-extra-vocab-size 0 --limit-mm-per-prompt audio=3,image=3 --max-loras 2 --lora-modules speech=… vision=…`. [F — huggingface.co/microsoft/Phi-4-multimodal-instruct, fetched 2026-06-14] |
| **Florence-2** | 0.23B / 0.77B | MIT | transformers (trust_remote_code=True); vLLM; Docker Model Runner | float16; cuda:0 tested; no specific GB stated | fp16 | `vllm serve "microsoft/Florence-2-large"`; `docker model run hf.co/microsoft/Florence-2-large`. [F — huggingface.co/microsoft/Florence-2-large, fetched 2026-06-14] |
| **Nemotron Parse 1.1** | 885M (256M LM) | NVIDIA Community Model License + CC-BY-4.0 tokenizer | NIM (cloud + container); HF | Single GPU typical (A100/H100 class) | bf16 / TF32 | NIM run pattern: `docker run nvcr.io/nim/publisher_name/model_name`. API ref: https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-parse. English only. [F — arxiv.org/abs/2511.20478 + build.nvidia.com/nvidia/nemotron-parse, fetched 2026-06-14] |
| **NeMo Retriever** (NIM stack) | mixed | NVIDIA NIM commercial + nv-ingest open source | nv-ingest CLI; NIM Docker | 1×H100 SXM benchmark | mixed | `nv-ingest-cli`; `docker run nvidia/nemoretriever-*-nim:*`. [F — developer.nvidia.com/nemo-retriever, fetched 2026-06-14] |
| **Nougat** | small/base (Donut) | MIT code + **CC-BY-NC weights** (non-commercial) | pip + CLI; optional FastAPI server | CPU supported; GPU optional | fp16/fp32 | `pip install nougat-ocr; nougat path.pdf -o out/`. [F — facebookresearch/nougat README, fetched 2026-06-14] |
| **Llama 3.2 Vision** | 11B / 90B | Llama 3.2 community license (commercial OK with AUP) | transformers (MllamaForConditionalGeneration); vLLM; llama-models pip | Not stated for 11B/90B; multi-GPU likely | bf16 | `pip install llama-models; llama-model download --source meta --model-id CHOSEN_MODEL_ID`. 700M-download cap per 24h. [F — meta-llama/llama-models README, fetched 2026-06-14] |
| **SAM 2.1** | 38.9M / 46M / 80.8M / 224.4M | Apache 2.0 | pip install SAM-2; SAM2ImagePredictor / SAM2VideoPredictor | A100 measured; CUDA kernel compile required | bf16 | `pip install -e .` from facebookresearch/sam2; `cd checkpoints && ./download_ckpts.sh`. [F — facebookresearch/sam2 README, fetched 2026-06-14] |
| **PaddleOCR-VL** (0.9B) | 0.9B | Apache-2.0 | pip install paddleocr; Paddle static graph, Paddle dynamic graph, or Transformers (since 3.5.0) | Multi-tier (CPU + GPU); 0.13s on A100 | bf16 / fp16 | Acceleration: OpenVINO, ONNX Runtime, TensorRT, ONNX format. PaddleOCR.js for browser. [F — PaddlePaddle/PaddleOCR README, fetched 2026-06-14] |
| **PP-OCRv6** (tiny/small/medium) | 1.5M / 7.7M / 34.5M | Apache-2.0 | Same as PaddleOCR-VL | Tiny/Small: CPU-friendly (5.2× OpenVINO, 6.1× Apple M4); Medium: 0.13s on A100 | mixed | Excellent CPU-only fallback. [F — same] |
| **Tesseract 5** | (engine + traineddata) | Apache-2.0 | CLI + C/C++ library (libtesseract); leptonica | **CPU only** | n/a | `tesseract imagename outputbase [-l lang] [--oem 1] [--psm 6]`. 5.5.2 (Dec 2025). [F — tesseract-ocr/tesseract README, fetched 2026-06-14] |
| **docTR** | det+reco (DBNet/CRNN+ others) | Apache-2.0 | pip install python-doctr; Docker (CUDA 12.2) | No explicit min; CPU supported | fp32 / fp16 | `pip install python-doctr; from doctr.models import ocr_predictor; model = ocr_predictor(pretrained=True)`. [F — mindee/doctr README, fetched 2026-06-14] |
| **SmolVLM** | 2B | Apache-2.0 | transformers (AutoModelForVision2Seq); flash_attention_2 if CUDA | 5.02 GB min VRAM (smallest in its class) | bf16 | `HuggingFaceTB/SmolVLM-Instruct` via AutoProcessor + AutoModelForVision2Seq. [F — huggingface/smollm README, fetched 2026-06-14] |
| **LayoutLMv3** | base / large / base-chinese | **CC BY-NC-SA 4.0 (non-commercial)** | transformers; Detectron2 (detection FT); CUDA 11.1 | Fine-tune: 8 GPUs (FUNSD/CORD), 16 GPUs (PubLayNet) | fp32 | Detectron2 + PyTorch 1.10.0 + CUDA 11.1. Not commercial. [F — microsoft/unilm/tree/master/layoutlmv3 README, fetched 2026-06-14] |
| **TATR v1.1** | DETR R18 (110 MB) | MIT | python main.py (conda tables-detr) | No specific GB; PyTorch 1.13.1 | fp32 | `conda env create -f environment.yml; conda activate tables-detr`. [F — microsoft/table-transformer README, fetched 2026-06-14] |
| **Azure AI Document Intelligence** v4.0 | (service) | (commercial cloud) | REST + Python SDK; Docker on-prem | Cloud (Azure) | n/a | `from azure.ai.documentintelligence import DocumentIntelligenceClient`. v4.0 GA 2024-11-30. [F — learn.microsoft.com/en-us/azure/ai-services/document-intelligence/, fetched 2026-06-14] |
| **Google Document AI** (Custom Extractor, Layout Parser, Form Parser, Enterprise OCR) | (service) | (commercial cloud) | REST; client libraries (Python, Node, Java, Go) | Cloud (Google Cloud) | n/a | `pretrained-foundation-model-v1.5-pro-2025-06-20` (Gemini 2.5 Pro); `v1.6-pro-2025-12-01` (Gemini 3 Pro). [F — docs.cloud.google.com/document-ai/docs/processors-list, fetched 2026-06-14] |

---

## 4. Benchmark Table

All numbers are quoted from the cited source. Where the same benchmark has multiple sources (e.g. olmOCR-bench is reproduced by several different projects' READMEs), I prefer the **most recent and most third-party** number and note the discrepancy.

### 4.1 olmOCR-bench (the de-facto 2026 OCR VLM leaderboard)

Source: `datalab-to/surya` README "Benchmarks" + `datalab-to/chandra` README "Benchmark table" + `allenai/olmocr` README "Benchmark". All three READMEs reproduce the same comparison table. 8,413 test cases across 1,400 documents. **Updated 2026-06-14 fetch.**

| Model | Size | olmOCR-bench Overall | ArXiv | OldScansMath | Tables | OldScans | H/F | MultiCol | LongTiny | Base | Source |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Datalab API | n/a | **86.7 ± 0.8** | 90.4 | 90.2 | 90.7 | 54.6 | 91.6 | 83.7 | 92.3 | 99.9 | chandra README |
| Infinity-Parser 2 Pro | 35.1B | 87.6 | — | — | — | — | — | — | — | — | surya README |
| **Chandra OCR 2** (Datalab) | 5.3B | 85.9 ± 0.8 | 90.2 | 89.3 | 89.9 | 49.8 | 92.5 | 83.5 | 92.1 | 99.6 | both |
| **dots.mocr** | 3.0B | 83.9 | 85.9 | 85.5 | 90.7 | 48.2 | 94.0 | 85.3 | 81.6 | 99.7 | both |
| **Surya OCR 2** (Datalab) | 0.65B | **83.3** | 88.3 | — | 86.6 | 41.8 | 92.5 | 82.4 | 93.7 | 99.7 | surya README |
| LightOnOCR-2 | 1B | 83.2 | — | — | — | — | — | — | — | — | surya README |
| **Chandra OCR 1** (Datalab) | 9.0B | 83.1 ± 0.9 | 82.2 | 80.3 | 88.0 | 50.4 | 90.8 | 81.2 | 92.3 | 99.9 | chandra README |
| **olmOCR 2** (anchored) | 8.3B | 82.4 ± 1.1 | 83.0 | 82.3 | 84.9 | 47.7 | 96.1 | 83.7 | 81.9 | 99.7 | olmocr README |
| Infinity-Parser 7B | 7B | 82.5 | — | — | — | — | — | — | — | — | olmocr README |
| PaddleOCR-VL | 0.9B | 80.0 ± 1.0 | — | — | — | — | — | — | — | — | olmocr README |
| **dots.ocr 1.0** (rednote-hilab) | 1.7B | 79.1 ± 1.0 | — | — | — | — | — | — | — | — | chandra README |
| **olmOCR v0.3.0** | 7B | 78.5 ± 1.1 | — | — | — | — | — | — | — | — | chandra README |
| Marker 1.10.1 (Datalab) | n/a | 76.1 ± 1.1 / 76.5 ± 1.0 | — | — | — | — | — | — | — | — | olmocr / chandra |
| Datalab Marker v1.10.0 | n/a | 76.5 ± 1.0 | — | — | — | — | — | — | — | — | chandra README |
| **DeepSeek-OCR** | 3B | 75.7 ± 1.0 / 75.4 ± 1.0 | 77.2 | 73.6 | 80.2 | 33.3 | 96.1 | 66.4 | 79.4 | 99.8 | olmocr / chandra |
| MinerU 2.5.4 | n/a | 75.2 ± 1.1 | — | — | — | — | — | — | — | — | olmocr README |
| Mistral OCR API | n/a | 72.0 ± 1.1 | — | — | — | — | — | — | — | — | chandra README |
| Nanonets-OCR2-3B | 3B | 69.5 ± 1.1 | — | — | — | — | — | — | — | — | olmocr README |
| GPT-4o (Anchored) | n/a | 69.9 ± 1.1 | — | — | — | — | — | — | — | — | chandra README |
| Qwen 3 VL 8B | 8B | 64.6 ± 1.1 | — | — | — | — | — | — | — | — | chandra README |
| Gemini Flash 2 (Anchored) | n/a | 63.8 ± 1.2 | — | — | — | — | — | — | — | — | chandra README |
| **GOT-OCR-2.0** | 0.58B | **48.3** | — | — | — | — | — | — | — | — | surya README |

**[A] Interpretation**: the olmOCR-bench leaderboard strongly favors VLMs that emit layout + text in one shot over two-stage detector+recognizer approaches. Surya 2 punches above its 0.65B weight (83.3 ≈ Chandra OCR 1 at 9.0B ≈ dots.mocr 3.0B); GOT-OCR-2.0 (0.58B) is the outlier at 48.3 — its prompt format is constrained to its own output tokens, which loses on the free-form judge. [A — based on the cross-model pattern].

### 4.2 DocVQA / ChartQA / OCRBench (selected subset)

| Model | DocVQA | ChartQA | OCRBench | Notes / Source |
|---|---|---|---|---|
| **Phi-4-multimodal** (5.6B, MIT) | **93.2** | 81.4 | **84.4** | HF model card, fetched 2026-06-14. Strongest local-class MIT. |
| **dots.mocr** (3.0B, MIT) | 91.85 | 83.2 | 86.0 | rednote-hilab/dots.ocr README, fetched 2026-06-14 |
| **Pixtral 12B** (12B, Apache-2.0) | 90.7 (ANLS) | 81.8 (CoT) | n/a | mistralai/Pixtral-12B-2409 model card |
| **PaliGemma 2 28B ft (448²)** | 76.1 (val) | 85.1 (ChartQA aug) | n/a | google/paligemma2-3b-pt-224 model card (per-size table) |
| **InternVL3.5-241B-A28B** | (SOTA per README "News" 2025/08/26) | (SOTA) | (SOTA) | OpenGVLab/InternVL README, fetched 2026-06-14 |
| **Surya OCR 2** (0.65B) | n/a directly | n/a directly | n/a directly | datalab-to/surya README focuses on olmOCR-bench + multilingual |
| **Phi-3.5-vision** (4.2B) | n/a | 81.8 | n/a | HF card; MMMU 43.0, AI2D 78.1, TextVQA 72.0 |
| **Chandra OCR 2** (5.3B) | n/a directly | n/a directly | n/a directly | datalab-to/chandra README focuses on olmOCR-bench |
| **GOT-OCR-2.0** (0.58B) | n/a | n/a | n/a | Ucas-HaoranWei/GOT-OCR2.0 README has no DocVQA table; BLEU 0.972 reported but per its own eval |
| **Florence-2-large-ft** (0.77B) | TextCaps 151.1 (CIDEr), TextVQA 73.5 | n/a | n/a | microsoft/Florence-2-large HF card |
| **PaliGemma 1 3B pt-896 ft** | 84.77 (ANLS) | 71.36 (ChartQA mean) | n/a | google/paligemma-3b-pt-224 model card |
| **InternVL2-Pro** (per 2024-07) | SOTA | n/a | n/a | OpenGVLab/InternVL README "News" 2024/07/18 |
| **Qwen 2.5-VL-3B-ins** (per Phi-4-multimodal comparison) | n/a directly | n/a | n/a | cited as baseline in Phi-4-multimodal card |
| **Qwen 2.5-VL-7B-ins** (per Phi-4-multimodal comparison) | n/a | n/a | n/a | cited as baseline |

### 4.3 OmniDocBench (Baidoo family; cross-OCR benchmark)

Source: `rednote-hilab/dots.ocr` README and `PaddlePaddle/PaddleOCR` README, both fetched 2026-06-14. Per `dots.ocr` README Elo Score (Gemini 3 Flash judge):

| Model | OmniDocBench v1.5 (Elo) | Notes / Source |
|---|---|---|
| Gemini 3 Pro | 1210.7 | rednote-hilab/dots.ocr README Elo table |
| **dots.mocr** (3.0B) | 1059.0 (avg 1124.7 across benchmarks) | rednote-hilab/dots.ocr README Elo table |
| HuanyuanOCR | 984.2 | same |
| PaddleOCR-VL-1.5 | 920.5 (avg) | same |
| **GLM-OCR** (0.9B) | 892.5 (avg) | same; "performance close to Gemini-3-Pro" per Z.AI 2026-02-03 release notes |

OmniDocBench v1.5 per-page (TextEdit / ReadOrderEdit, lower is better):

| Model | TextEdit | ReadOrderEdit | Source |
|---|---|---|---|
| **dots.mocr** (3.0B) | **0.031** | **0.029** | dots.ocr README |
| PaddleOCR-VL | 0.035 | 0.043 | dots.ocr README |
| GLM-OCR | 0.04 | 0.043 | dots.ocr README |
| Gemini-2.5-Pro | 0.075 | 0.097 | dots.ocr README |

**PaddleOCR's own v1.5 / v1.6 claims (PaddleOCR README, 2026-05-28 / 2026-06-11)**:
- **PaddleOCR-VL-1.6 (0.9B)**: OmniDocBench v1.6 = **96.3% (SOTA)**, v1.5 SOTA, Real5-OmniDocBench SOTA. [F]
- **PaddleOCR-VL-1.5 (0.9B)**: OmniDocBench v1.5 = **94.5%**. [F]
- **PP-OCRv6 medium (34.5M)**: "+4.6% detection / +5.1% recognition over PP-OCRv5_server; surpasses Qwen3-VL-235B and GPT-5.5." [F — PaddleOCR README, 2026-06-11 release note]

### 4.4 Throughput (pages/sec) — same hardware where possible

| Model | Hardware | Throughput | Source |
|---|---|---|---|
| **Surya OCR 2** (0.65B) | 1× RTX 5090 (32 GB), concurrency 128, 96 DPI, ~2,410 output tokens/page | **5.35 pages/s** | datalab-to/surya README "Throughput" |
| **Surya OCR 2** (0.65B) | Apple Silicon (M-series), --parallel=8, ~30 W | 0.108 pages/s | same |
| **Chandra OCR 2** (5.3B) | 1× H100 80GB, vLLM @ 96 concurrent sequences | 1.44 pages/s (P95 156s, 60s avg) | datalab-to/chandra README "Throughput" |
| **PP-OCRv6 medium** (34.5M) | A100 | 0.13s / page (~7.7 pages/s) | PaddlePaddle/PaddleOCR README "2026.06.11" |
| **PP-OCRv6 tiny** (1.5M) | Apple M4 (CPU via OpenVINO) | 6.1× speedup over previous | same |
| **DeepSeek-OCR** (3B) | A100-40G (PDF) | ~2500 tokens/s concurrency | deepseek-ai/DeepSeek-OCR README |
| **PaddleOCR-VL-1.6** (0.9B) | A100 | 1.86 pages/s (real-time tier) | rednote-hilab/dots.ocr README (cites GLM-OCR spec, not direct; per ithome.com 2026-02-03 GLM-OCR = 1.86 pages/s) — [A — careful, that's a Z.AI claim not Paddle] |
| **GLM-OCR** (0.9B) | unspecified | 1.86 pages/s (per Z.AI release) | ithome.com / wisemodel.cn 2026-02-03 announcement, secondary |

---

## 5. Architecture Patterns

Synthesizing the fetched evidence, the 2026 OCR VLM landscape collapses to four architectural patterns. LocalDeepL's `HybridEngine` and `GroundedEngine` correspond to two of them. Understanding the others helps decide what to add.

### 5.1 Pattern A — Two-stage classical pipeline (Tesseract 5, docTR, PP-OCRv6 + PP-StructureV3)

- **Detector** (line or region) + **Recognizer** (per region), with optional **layout/structure head** and **language model** post-processing.
- Strengths: fast on CPU, mature, trainable on small data, predictable latency. PaddleOCR PP-OCRv6 34.5M beats Qwen3-VL-235B and GPT-5.5 on detection+recognition while running 0.13s on A100 [F — PaddlePaddle/PaddleOCR README "2026.06.11"]. Tesseract 5 with LSTM engine is line-recognition only and 100+ languages out of the box.
- Weaknesses: no semantic understanding, no document-level reasoning, no handwriting beyond what was trained, no automatic schema extraction.
- **For LocalDeepL**: this is the right *fallback* path when no VLM server is available, or for high-throughput low-complexity jobs. Already partially covered by Surya's EfficientViT/Segformer detector; PP-OCRv6 / Tesseract 5 would be new fallback options for `aligner` slot swap or `page_preprocessor` if those need a CPU path. [A]

### 5.2 Pattern B — Single VLM, one-pass page OCR (Surya 2, PaliGemma 2, GOT-OCR-2.0, Pixtral, Phi-3.5/4, Qwen2.5/3-VL, InternVL, Florence-2, Nougat, SmolVLM)

- **Encoder-decoder or decoder-only VLM** that takes a full page (or crop) and emits a text sequence — sometimes with task tokens (Florence-2 `<OCR>` / `<OCR_WITH_REGION>`, PaliGemma 2 task prefix) to control output structure.
- Strengths: one forward pass, can do VQA / caption / OCR in same model, easiest to wire to vLLM.
- Weaknesses: bbox grounding is prompt-dependent and not always precise; long pages require either tiling or long-context.
- **For LocalDeepL**: this is what most candidates for `ocr_processor` slot are. The choice is *which* one and at what size. PaliGemma 2 / Phi-4-multimodal are the small / MIT-or-non-commercial choices; Qwen2.5-VL-7B is the mid-tier; Qwen2.5-VL-72B / InternVL 78B / 241B are out of LocalDeepL's target VRAM range.

### 5.3 Pattern C — Single VLM, layout + text in one shot (the "grounded" path)

- **Bbox-native VLM** (dots.mocr, Chandra OCR 2, DeepSeek-OCR with `<|grounding|>` token, GLM-OCR, PaddleOCR-VL with `prompt_layout_all_en`). One forward pass returns structured JSON or HTML with bbox, category, and text per element.
- Strengths: matches LocalDeepL's existing `GroundedEngine` pattern in `core/workflows/grounded.py`. Best quality for downstream consumption (RAG, search, post-processing). Highest scores on olmOCR-bench.
- Weaknesses: model sizes are mostly 1-9B, some are licensed with modified OpenRAIL-M (Datalab gates).
- **For LocalDeepL**: this is the right *primary* path forward. Dots.mocr 3.0B is the strongest Apache-2.0 candidate; Chandra 2 5.3B is the strongest quality candidate (but modified-OpenRAIL-M gated).

### 5.4 Pattern D — Detector + VLM-OCR + post-processing (the existing LocalDeepL hybrid path)

- Surya detection → VLM OCR per box (Litellm-via-OCRPipeline) → DP alignment → optional refine → post-process. See `core/workflows/hybrid.py` for the LocalDeepL implementation.
- This is the "best of both" pattern: classical detection is fast and predictable, VLM-OCR is per-crop and accurate, DP alignment merges them.
- Strengths: flexibility (swap detector or OCR backend independently), supports both images and PDFs, can switch to dense vs sparse mode (`dense_mode="auto"` in `core/workflows/hybrid.py`).
- Weaknesses: more moving parts, two inference stacks, harder to debug, throughput bounded by both stages.

### 5.5 Cross-cutting architectural notes

- **Natively multimodal vs ViT+LLM**. Most 2026 OCR VLMs (Qwen2.5/3-VL, InternVL3.5, Pixtral, Phi-4, PaliGemma 2) are ViT + LLM. PaddleOCR-VL's NaViT-style dynamic high-resolution encoder + ERNIE-4.5-0.3B and GLM-OCR's CogViT + GLM-0.5B follow the same pattern. The "native multimodal" claim (Gemini, "one Transformer") is blog-level for Gemini 3.1 Pro [A] and not the consensus pattern.
- **Resolution strategy**. Models handle page resolution in three ways: (a) fixed (PaliGemma 2 224² / 448²), (b) variable (Pixtral, Qwen3-VL), (c) multi-mode (DeepSeek-OCR Tiny/Small/Base/Large + Gundam). For document OCR, (b) and (c) matter because a single A4 page at 200 DPI is 1654×2339 px.
- **Bbox grounding**. Florence-2 (task tokens), dots.mocr (built-in), Chandra (built-in), DeepSeek-OCR (`<|grounding|>` token), Qwen2.5-VL (built-in 2D/3D grounding), InternVL3.5 (built-in), GLM-OCR (built-in). Tesseract / docTR / PP-OCR do not emit bboxes for layout (only word-level). PaliGemma 2 emits bbox coordinates only for "detect" task prefix. Pixtral does not natively emit bboxes.
- **Layout detection or assumes external**. Florence-2, dots.mocr, Chandra, GOT-OCR-2.0, PaddleOCR-VL, PaddleOCR-StructureV3, LayoutLMv3, TATR, Nougat (Nougat is academic-paper-only — does layout *and* text in one pass). Pixtral, Phi-3.5/4, Qwen2.5/3-VL, InternVL, PaliGemma 2, SmolVLM assume you bring your own detector or do layout-agnostic OCR. Surya 2 *includes* layout + OCR + table_rec in one VLM — a unique selling point.
- **License posture** (synthesis): the 2026 trend is "Apache-2.0 or MIT for code, but increasingly modified-OpenRAIL-M or click-through for weights" (Datalab models, Gemma 2 terms, Llama 3.2 community). For a commercial local-first product, the safest picks are: PaddleOCR, GOT-OCR-2.0 code (data is CC-BY-NC — careful), DeepSeek-OCR MIT, Florence-2 MIT, Phi-3.5/4 MIT, Pixtral Apache-2.0, Qwen2.5/3-VL Apache-2.0, InternVL3.5 MIT, docTR Apache-2.0, TATR MIT, Tesseract Apache-2.0, Nougat code MIT (weights CC-BY-NC). Risky for commercial: Surya 2 weights (modified OpenRAIL-M with $5M gate), Chandra OCR 2 weights (modified OpenRAIL-M with $2M gate + no competitive use), PaliGemma / Gemma license, LayoutLMv3 CC BY-NC-SA 4.0, Nougat weights CC-BY-NC. [A — synthesis from fetched license fields]

---

## 6. License Constraints

For a commercial local-first product like LocalDeepL, license is the single biggest difference between "drop-in candidate" and "do not adopt without legal review". Sorted by strictness.

### 6.1 Commercial-friendly (Apache-2.0 / MIT)

- **PaddleOCR** (Apache-2.0) — PaddlePaddle/PaddleOCR
- **PaddleOCR-VL-1.6 / VL-1.5** (Apache-2.0) — same
- **PP-OCRv6** (Apache-2.0) — same
- **PP-StructureV3** (Apache-2.0) — same
- **Tesseract 5** (Apache-2.0 code; Leptonica BSD 2-clause) — tesseract-ocr/tesseract
- **docTR** (Apache-2.0) — mindee/doctr
- **Table Transformer (TATR v1.1)** (MIT) — microsoft/table-transformer
- **Florence-2** (MIT) — huggingface.co/microsoft/Florence-2-large
- **Phi-3.5-vision** (MIT) — huggingface.co/microsoft/Phi-3.5-vision-instruct
- **Phi-4-multimodal** (MIT) — huggingface.co/microsoft/Phi-4-multimodal-instruct
- **Pixtral 12B** (Apache-2.0) — huggingface.co/mistralai/Pixtral-12B-2409
- **Qwen2.5-VL / Qwen3-VL** (Apache-2.0) — QwenLM/Qwen3-VL
- **InternVL3.5 / InternVL3 / InternVL2.5 / InternVL2** (MIT) — OpenGVLab/InternVL
- **SmolVLM / SmolVLM2** (Apache-2.0) — huggingface/smollm
- **Gemma 4** (Apache-2.0 code) — google-deepmind/gemma
- **SAM 2 / SAM 2.1** (Apache 2.0) — facebookresearch/sam2
- **DeepSeek-OCR** (MIT) — deepseek-ai/DeepSeek-OCR
- **DeepSeek-OCR-2** (Apache-2.0) — deepseek-ai/DeepSeek-OCR-2
- **OlmOCR** (Apache-2.0) — allenai/olmocr
- **dots.ocr / dots.mocr** (MIT code, separate model weight license — need to check) — rednote-hilab/dots.ocr
- **GOT-OCR-2.0 code** (Apache-2.0) — Ucas-HaoranWei/GOT-OCR2.0
- **NeMo Retriever nv-ingest** (open source) — github.com/NVIDIA/nv-ingest
- **Nougat code** (MIT) — facebookresearch/nougat

### 6.2 Modified-OpenRAIL-M / click-through (commercial use gated)

- **Surya 2 weights** — modified AI Pubs Open Rail-M: free for research, personal use, startups <$5M funding/revenue. Code is Apache-2.0. Datalab explicitly calls this out in their README "Commercial usage" section.
- **Chandra OCR 2 weights** — modified OpenRAIL-M: free for research, personal use, startups <$2M funding/revenue; **cannot be used competitively with the Datalab API**. Code is Apache-2.0.
- **Nemotron Parse 1.1** — NVIDIA Community Model License (NVIDIA NIM weights). Tokenizer CC-BY-4.0.
- **Llama 3.2 Vision** — Llama 3.2 community license (commercial OK with Acceptable Use Policy). 700M-download cap per 24h on direct Meta URL.
- **PaliGemma 2** — Gemma license (non-commercial-friendly for some uses; requires HF click-through). "License: gemma" tag.

### 6.3 Non-commercial (do not adopt for commercial product without legal review)

- **Nougat weights** — CC-BY-NC. "Nougat was trained on scientific papers found on arXiv and PMC."
- **GOT-OCR-2.0 data** — CC BY NC 4.0 (data only, code is Apache-2.0). Important: even if the code is fine, the data used to fine-tune is CC-BY-NC, which propagates non-commercial obligations in some jurisdictions. [A — cautious interpretation, worth a legal review].
- **LayoutLMv3** — CC BY-NC-SA 4.0 (non-commercial + share-alike).
- **Chandra OCR 2 weights** — modified OpenRAIL-M (already listed in 6.2, but the $2M startup gate + no-competitive-use clause is closer to a non-commercial vibe than a typical OSS license).

### 6.4 Cloud-only (commercial terms per-call)

- **Google Document AI** — Google Cloud terms; per-page pricing.
- **Azure AI Document Intelligence** — Azure terms; per-page pricing; on-prem Docker containers available.
- **Mistral OCR API** — Mistral terms.
- **NVIDIA build.nvidia.com NIM endpoints** — NVIDIA NIM API terms (free tiers + paid); downloadable NIM containers have their own license.

---

## 7. LocalDeepL Gaps and Opportunities

Cross-referenced against the existing extension points documented in `AGENTS.md` and the LocalDeepL repo (`grounded_backend`, `document_processors`, `aligner`, `ocr_processor`, `page_preprocessor`, `output_writer`).

### 7.1 Gaps — what the 2026 landscape exposes in LocalDeepL

1. **No commercial-friendly open-weights grounded alternative to Surya.** LocalDeepL's `core/workflows/grounded.py` only supports a small set of grounded backends. The strongest commercial-friendly grounded candidate is `rednote-hilab/dots.mocr` 3.0B (MIT code; model weights under separate rednote license) with olmOCR-bench 83.9. [A — gap; see evidence file and §3 run command]
2. **OCR VLM provider list is small and tied to a single host.** LocalDeepL's `core/ocr.py` wraps a single Litellm-driven VLM. The 2026 ecosystem has converged on vLLM as the standard host for OCR VLMs (dots.mocr, OlmOCR, Chandra, Qwen3-VL, Pixtral, Phi-4, PaliGemma 2 all ship vLLM run instructions). Adopting a vLLM-first or vLLM-alongside-Litellm contract would unlock most of Tier 1. [A]
3. **Multilingual coverage is uneven.** Surya covers 90+ languages but accuracy on Arabic 72.7 and Chinese 82.5 is materially lower than English 92.3. PaliGemma 2 28B is explicitly multilingual (Pali-X mix); Pixtral 12B is multilingual. Adopting a 7B-class multilingual grounded VLM as a fallback for non-English documents would close the gap. [A]
4. **No formal table-extraction VLM**. LocalDeepL's `table_extraction` document processor is implemented in `core/processors.py` but it relies on TATR + table-transformer or a generic VLM. PaddleOCR-VL-1.6 (0.9B) has SOTA on OmniDocBench v1.6 for tables and ships under Apache-2.0 — a clean drop-in. [A]
5. **No formulas / chemistry / music support** as first-class. Surya emits KaTeX math but not ChemDraw / SMILES / music. GOT-OCR-2.0 supports those. DeepSeek-OCR "Parse the figure" prompt handles figures. For LocalDeepL's value proposition (anything-to-MD), covering these in the grounded-backend or a new `ocr_processor` would matter. [A]
6. **No /mavis/plan hook for graceful failure / fallback**. If a VLM server is down, LocalDeepL currently has no automatic fallback to a smaller engine. PP-OCRv6 (34.5M) on A100 in 0.13s is the obvious fallback target. [A]
7. **Public benchmarks are missing from LocalDeepL's own measurement**. `scripts/confidence_eval.py` measures against the `examples/*.pdf` fixtures, which is good for regression but doesn't track olmOCR-bench, DocVQA, ChartQA, OCRBench — i.e. it doesn't tell you when a new public model arrives that beats the current default. Adding a (small subset) olmOCR-bench runner in `scripts/` would make "is there a better grounded backend?" answerable in <1 hour. [A]
8. **The CPU/Apple-Silicon path is weak in the VLM tier**. Surya falls back to llama-server; Phi-3.5-vision works in Ollama; SmolVLM is the smallest at 5.02 GB. PaddleOCR PP-OCRv6 / Tesseract 5 / docTR are the CPU-only tier but they're not the `ocr_processor` — they're at most `aligner`. Wiring them as a CPU-only fallback for `ocr_processor` would let LocalDeepL run on truly low-VRAM hardware. [A]
9. **License posture is undocumented**. LocalDeepL ships with `surya-ocr` as a dep. If the maintainer wants to grow beyond a $5M-funded company, the modified-OpenRAIL-M of Surya is a real ceiling. Same for `chandra-ocr`. Worth documenting in the README. [A]
10. **eval/regression harness is not in CI**. The `pytest -m slow` gate exists but is not run on every PR. Adding a fast `olmOCR-bench-mini` (a 50-doc subset of olmOCR-bench) into a CI lane would catch regressions. [A]

### 7.2 Opportunities — concrete plays for LocalDeepL

Ranked by ease-of-integration / impact ratio. Each opportunity is a distinct LocalDeepL extension-point (from AGENTS.md).

#### 7.2.1 Add `dots.mocr` as a `grounded_backend` candidate (HIGH PRIORITY)

- **Where**: `core/grounded.py` parser contract.
- **Why**: 83.9 olmOCR-bench, MIT code, vLLM-integrated, returns layout JSON with bboxes + category + text per element (same shape LocalDeepL's parser already expects).
- **Cost**: ~2-3 days to wire up (vLLM client, parser, prompt routing).
- **Risk**: model weight license is "separate from MIT" per rednote-hilab — needs a quick legal scan.
- **Evidence**: github.com/rednote-hilab/dots.ocr README "Hugginface inference details" + parser.py usage; vLLM 0.11.0+ integrated.

#### 7.2.2 Add `Chandra OCR 2` as a quality `grounded_backend` (MEDIUM PRIORITY)

- **Where**: `core/grounded.py` parser contract.
- **Why**: 85.9 olmOCR-bench, the highest open-weights number, two inference modes (HF + vLLM).
- **Cost**: ~2 days.
- **Risk**: modified-OpenRAIL-M with $2M startup gate + no-competitive-use clause — relevant if LocalDeepL is itself a $2M+ startup or is sold next to a competing cloud OCR service. Read the LICENSE in the repo.
- **Evidence**: github.com/datalab-to/chandra README "Quickstart" and "Commercial usage".

#### 7.2.3 Add `Phi-4-multimodal` as a small `ocr_processor` candidate (MEDIUM PRIORITY)

- **Where**: `core/ocr.py` provider list (the Litellm-driven VLM).
- **Why**: 5.6B, MIT, 93.2 DocVQA, 84.4 OCRBench — beats most larger models; vLLM-supported.
- **Cost**: ~1 day.
- **Risk**: flash-attn requirement; A100/H100-class GPU.
- **Evidence**: huggingface.co/microsoft/Phi-4-multimodal-instruct model card "vLLM inference" example.

#### 7.2.4 Add `PaddleOCR-VL` as an `aligner` / `page_preprocessor` swap (MEDIUM PRIORITY)

- **Where**: `core/aligner.py` (replacing or augmenting Surya's detection) OR a new `page_preprocessor` slot.
- **Why**: 0.9B Apache-2.0, 96.3% on OmniDocBench v1.6, multi-tier CPU+GPU deployment, fast (1.86 pages/s on A100 per GLM-OCR's spec — PaddleOCR-VL should be similar).
- **Cost**: ~3-4 days; needs a PaddlePaddle install path and a Python bridge.
- **Risk**: PaddlePaddle is a large install; the inference stack is not vLLM.
- **Evidence**: github.com/PaddlePaddle/PaddleOCR README "Key Features" + "2026.05.28" release note for PaddleOCR-VL-1.6.

#### 7.2.5 Add `Qwen2.5-VL-7B` (AWQ) as a balanced `ocr_processor` (LOW PRIORITY)

- **Where**: `core/ocr.py`.
- **Why**: Apache-2.0, 32 OCR languages, 256K context, AWQ 4-bit reduces VRAM to a single 24 GB consumer GPU.
- **Cost**: ~1 day.
- **Risk**: 7B + AWQ is heavier than Phi-4-multimodal for the same OCRBench; picks up GUI/agent capability (might be a feature or noise for OCR).
- **Evidence**: github.com/QwenLM/Qwen2.5-VL (now redirects to Qwen3-VL README).

#### 7.2.6 Add `Florence-2` task-token routing for `ocr_processor` (LOW PRIORITY)

- **Where**: `core/ocr.py`.
- **Why**: 0.77B, MIT, `<OCR>` / `<OCR_WITH_REGION>` / `<OD>` task tokens — light, fast, fast feedback for bbox-grounded OCR.
- **Cost**: ~1-2 days.
- **Risk**: 2023-vintage; not state-of-the-art on DocVQA / OCRBench. Useful as a low-VRAM tier.
- **Evidence**: huggingface.co/microsoft/Florence-2-large model card.

#### 7.2.7 Wire `PaddleOCR-VL` (or `PP-OCRv6` for CPU) as a `page_preprocessor` first-pass detector (MEDIUM PRIORITY)

- **Where**: `core/preprocessing.py` (new `PagePreprocessor`).
- **Why**: PaddleOCR's PP-DocLayoutV3 is a layout algorithm that returns the regions LocalDeepL's hybrid path could then OCR via the existing per-box VLM. This is a Surya-detection-replacement with a different layout detector.
- **Cost**: ~4-5 days (Paddle install + integration with the existing per-box flow).
- **Risk**: layout detector without line-level coords might mismatch the per-box OCR; needs an evaluation pass on `examples/dense.pdf`.
- **Evidence**: github.com/PaddlePaddle/PaddleOCR README "PP-StructureV3".

#### 7.2.8 Wire `Nemotron Parse 1.1` as a NIM-backed `grounded_backend` (LOW PRIORITY)

- **Where**: `core/grounded.py`.
- **Why**: 885M, NVIDIA NIM-supported (matches LocalDeepL's NIM pattern if any), good for dense-document markdown output.
- **Cost**: ~2-3 days; requires NIM container or HF.
- **Risk**: English-only.
- **Evidence**: arxiv.org/abs/2511.20478 + build.nvidia.com/nvidia/nemotron-parse.

#### 7.2.9 Add a `multilingual_ocr` `document_processor` (MEDIUM PRIORITY)

- **Where**: new processor in `core/processors.py` + `DocumentProcessorName` enum in `api/schemas/requests.py`.
- **Why**: Surya handles 90+ languages but accuracy drops on Arabic (72.7). A 7B multilingual VLM (Qwen2.5-VL-7B AWQ or Pixtral 12B) as a fallback for non-English document batches would close the multilingual gap without changing the default Surya path.
- **Cost**: ~3 days (processor scaffolding + a quality eval).
- **Risk**: routing logic needs a language-detect pre-step (Surya has it for free; otherwise needs fastText langid or similar).
- **Evidence**: synthesis from Qwen2.5-VL README "Expanded OCR: 32 languages" + Pixtral card.

#### 7.2.10 Add a CPU-only `aligner` fallback (PP-OCRv6 + DBNet or Tesseract 5) (LOW PRIORITY)

- **Where**: `core/aligner.py` slot.
- **Why**: Lets LocalDeepL run on machines without a GPU. PP-OCRv6 34.5M is 5.2× faster on OpenVINO. Tesseract 5 is the safety net.
- **Cost**: ~3 days.
- **Risk**: accuracy regression vs Surya; needs a quality gate in `scripts/confidence_eval.py` to enforce a minimum.
- **Evidence**: github.com/PaddlePaddle/PaddleOCR README "2026.06.11" + tesseract-ocr/tesseract README.

#### 7.2.11 Add an `olmocr-bench-mini` regression script (MEDIUM PRIORITY)

- **Where**: `scripts/` (a new file like `scripts/olmocr_bench_mini.py`).
- **Why**: olmOCR-bench is the de-facto 2026 OCR VLM leaderboard. Running a 50-doc subset against the current default backend in CI would let LocalDeepL detect regressions when a new Surya/Chandra/Qwen2.5 release lands.
- **Cost**: ~1 day to write; ~0.5 day to seed the subset from the open `allenai/olmocr-bench` fixtures.
- **Risk**: olmOCR-bench is 8,413 tests; a 50-doc subset loses statistical power.
- **Evidence**: github.com/allenai/olmocr README "Benchmark" + github.com/jina-ai/olmocr-bench (the public runner).

#### 7.2.12 Add a license-audit CI check (LOW PRIORITY)

- **Where**: `.github/workflows/` + `pyproject.toml` audit.
- **Why**: Surya 2 (modified OpenRAIL-M, $5M gate) and Chandra OCR 2 (modified OpenRAIL-M, $2M gate) are bundled via `surya-ocr` and `chandra-ocr` pip packages. Documenting this in the README and warning the maintainer if either package's license changes is cheap insurance.
- **Cost**: ~0.5 day (use `pip-licenses` or `liccheck`).
- **Risk**: false positives if the package's LICENSE field is the Apache-2.0 code, not the modified-OpenRAIL-M weights.
- **Evidence**: datalab-to/surya LICENSE + datalab-to/chandra MODEL_LICENSE.

---

## 8. LocalDeepL — How It Already Stacks Up

Brief self-evaluation against the 2026 landscape (this complements the localdeepl-state track; do not duplicate).

- **Surya-detection + VLM-OCR hybrid (`HybridEngine`)** is a legitimate 2026 architecture pattern. Pattern D in §5 maps to LocalDeepL's `core/workflows/hybrid.py` (Surya detection → per-box VLM OCR → DP alignment → refine). Few competitors publish this exact pipeline; the closest is the open-source PaddleOCR-StructureV3 (layout + recognition in two stages).
- **Grounded-OCR path (`GroundedEngine`)** is the right strategic bet. `core/workflows/grounded.py` exists; the gap is *which* grounded backend to default to and *which* to expose as alternates.
- **`document_processors` slot** is well-designed but the catalog (table_extraction, layout_enrichment, section_analysis, reading_order, quality_analysis, structure_analysis) is light vs. what PaddleOCR-VL, Chandra, and dots.mocr do natively.
- **Output writers** (`docx_writer`) is the start of a broader story; missing HTML / JATS-XML / annotated-PDF writers would help RAG consumers.
- **Routing / quality scoring** is in `core/routing.py` — a good foundation; should be wired to the language-detect idea in 7.2.9.
- **Eval harness** (`scripts/confidence_eval.py`, `scripts/confidence_image.py`) is fixture-bound; lacks public-benchmark coverage.

The **synthesis** (`PLAN.md`) task in this plan should tie all four tracks together; this scout's contribution is the inputs and 12 ranked opportunities above.

---

## 9. References

Every URL was fetched on 2026-06-14. Inline [F]/[A] markers in the body tell which claims are factual (verbatim from the source) vs analytical (synthesis from multiple sources).

### 9.1 Google

- https://ai.google.dev/gemini-api/docs/document-processing — Gemini document understanding
- https://docs.cloud.google.com/document-ai/docs/processors-list — Document AI full processor list with version IDs and capabilities
- https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk — Gemini layout parser
- https://docs.cloud.google.com/document-ai/docs/enterprise-document-ocr — Enterprise Document OCR details
- https://docs.cloud.google.com/document-ai/docs/form-parser — Form Parser details
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/2-5-pro — Gemini 2.5 Pro capabilities
- https://github.com/google-deepmind/gemma — Gemma 4 (open-weight LLM library)
- https://huggingface.co/google/paligemma-3b-pt-224 — PaliGemma 1 (3B) model card
- https://huggingface.co/google/paligemma2-3b-pt-224 — PaliGemma 2 (3B) model card
- arXiv 2407.07726 — PaliGemma 1 paper
- arXiv 2412.03555 — PaliGemma 2 paper

### 9.2 Microsoft

- https://huggingface.co/microsoft/Florence-2-large — Florence-2 model card
- https://huggingface.co/microsoft/Phi-3.5-vision-instruct — Phi-3.5-vision model card
- https://huggingface.co/microsoft/Phi-4-multimodal-instruct — Phi-4-multimodal model card
- https://github.com/microsoft/unilm/tree/master/layoutlmv3 — LayoutLMv3 README
- https://github.com/microsoft/table-transformer — Table Transformer README
- https://github.com/microsoft/dstoolkit-finetuning-florence-2 — Florence-2 finetuning accelerator
- https://github.com/microsoft/PhiCookBook — Phi-3 / Phi-4 examples
- https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/ — Azure Document Intelligence docs
- https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/model-overview — prebuilt model list
- https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout — Layout model details
- arXiv 2311.06242 — Florence-2 paper
- arXiv 2404.14219 — Phi-3 technical report
- arXiv 2503.01743 — Phi-4-multimodal technical report

### 9.3 NVIDIA

- https://arxiv.org/abs/2511.20478 — Nemotron Parse 1.1 paper
- https://build.nvidia.com/models — NIM catalog
- https://build.nvidia.com/nvidia/nemotron-parse — Nemotron Parse NIM card
- https://developer.nvidia.com/nemo-retriever — NeMo Retriever overview
- https://developer.nvidia.com/nim — NIM for Developers
- https://github.com/NVIDIA/nv-ingest — nv-ingest (NeMo Retriever open-source library)
- https://github.com/NVIDIA/NeMo — NeMo framework

### 9.4 Meta

- https://github.com/facebookresearch/nougat — Nougat (academic paper OCR)
- https://github.com/meta-llama/llama-models — Llama models table (3.2 Vision, 4 Scout, etc.)
- https://github.com/facebookresearch/sam2 — SAM 2.1 (segmentation, not OCR)
- arXiv 2308.13418 — Nougat paper
- arXiv 2408.00714 — SAM 2 paper

### 9.5 Mistral

- https://huggingface.co/mistralai/Pixtral-12B-2409 — Pixtral 12B model card
- https://github.com/mistralai/mistral-inference — mistral-inference (Pixtral supported)
- https://vllm-project/vllm — vLLM (Pixtral examples/offline_inference_pixtral.py)

### 9.6 Open-source OCR / VLMs

- https://github.com/datalab-to/surya — Surya OCR 2 (also legacy: VikParuchuri/surya)
- https://github.com/Ucas-HaoranWei/GOT-OCR2.0 — GOT-OCR-2.0
- https://github.com/allenai/olmocr — OlmOCR
- https://github.com/jina-ai/olmocr-bench — olmOCR-bench runner
- https://github.com/rednote-hilab/dots.ocr — dots.ocr / dots.mocr
- https://github.com/QwenLM/Qwen3-VL — Qwen3-VL (also legacy Qwen2.5-VL)
- https://github.com/QwenLM/Qwen2.5-VL — Qwen2.5-VL (now redirects)
- https://github.com/OpenGVLab/InternVL — InternVL3.5 / 3 / 2.5 / 2 / 1
- https://github.com/huggingface/smollm — SmolVLM (canonical repo)
- https://huggingface.co/blog/smolvlm — SmolVLM blog with architecture details
- https://github.com/tesseract-ocr/tesseract — Tesseract 5
- https://github.com/tesseract-ocr/tessdata — Tesseract traineddata
- https://github.com/PaddlePaddle/PaddleOCR — PaddleOCR (PaddleOCR-VL, PP-OCRv6, PP-StructureV3)
- https://github.com/mindee/doctr — docTR
- https://github.com/datalab-to/chandra — Chandra OCR 2
- https://github.com/deepseek-ai/DeepSeek-OCR — DeepSeek-OCR v1
- https://github.com/deepseek-ai/DeepSeek-OCR-2 — DeepSeek-OCR-2 (Visual Causal Flow)
- arXiv 2502.13923 — Qwen2.5-VL technical report
- arXiv 2502.18443 — OlmOCR v1 paper
- arXiv 2510.19817 — OlmOCR v2 paper (unit-test rewards)
- arXiv 2510.18234 — DeepSeek-OCR paper
- arXiv 2507.05595 — PaddleOCR 3.0 technical report
- arXiv 2510.14528 — PaddleOCR-VL paper
- arXiv 2601.21957 — PaddleOCR-VL-1.5 paper
- arXiv 2606.03264 — PaddleOCR-VL-1.6 paper
- arXiv 2409.01704 — GOT-OCR-2.0 paper
- arXiv 2311.06242 — Florence-2 paper
- arXiv 2404.14219 — Phi-3 technical report
- arXiv 2503.01743 — Phi-4-multimodal technical report

### 9.7 Cross-cutting

- https://arxiv.org/abs/2511.20478 — NVIDIA Nemotron Parse 1.1 paper
- https://www.codesota.com/ocr — OCR SOTA Router 2026 (cross-model leaderboard reference)
- https://ithome.com/0/918/637.htm — Z.AI GLM-OCR 2026-02-03 release announcement
- https://wisemodel.cn/models/ZhipuAI/GLM-OCR — GLM-OCR model card
- https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-parse — Nemotron Parse NIM API reference

---

## 10. Open Questions / Contradictions

These are surfaced to the synthesis task, not silently resolved.

1. **"NV-OCR-1.0" naming**. The user's task brief said "NV-OCR-1.0 / newer NV-OCR". NVIDIA does not ship a model called "NV-OCR". The closest functional equivalents are Nemotron Parse 1.1 and Nemoretriever Page Elements v2. **Caveat**: this is a brand-naming assumption, not a real product. The synthesis task should not assume a model named "NV-OCR" exists.
2. **"Cosmos-OCR"**. The user mentioned "Cosmos-OCR as applicable". NVIDIA Cosmos is a world-foundation-model family for physical-AI video generation, not OCR. There is no "Cosmos-OCR" model. The synthesis task should drop this.
3. **"VISTA-3D"**. Mentioned in the user brief. VISTA-3D is a medical-imaging 3D segmentation model from NVIDIA, not a document OCR model. Drop.
4. **Florence-VL is a research paper, not a product.** No first-party Microsoft weights or repo. Synthesis should treat as "no candidate".
5. **Pixtral Large (124B)**. The user said "Mistral: Pixtral / Pixtral 12B / 124B". The 124B Pixtral Large exists (Nov 2024) but its model card was not directly fetched in this scout. Treat as a cloud/closed reference only.
6. **Surya 2 license ceiling for LocalDeepL's growth**. The current `core/workflows/hybrid.py` uses Surya as the default aligner. If LocalDeepL wants to scale past $5M, the modified-OpenRAIL-M is a ceiling. Synthesis should surface "adopt a non-Datalab default" as a real future play.
7. **Mimo-7B-OCR and LightOnOCR-2** are not directly fetched in this scout (cited only via third-party benchmark tables). Synthesis should re-verify before quoting numbers.
8. **Nemotron Parse 1.1 specific benchmark numbers** are "competitive accuracy" per the arXiv abstract; the full tables are in the PDF body which this scout did not deep-read. Numbers cited as "in arXiv PDF body" should be re-verified.
9. **dots.mocr model weight license**. README says "dots.ocr LICENSE AGREEMENT" file is separate from MIT. This scout did not open that file. Synthesis should request a license-scan if dots.mocr becomes a primary candidate.
10. **Conflict in DeepSeek-OCR 3B size**. allenai/olmocr README says "DeepSeek-OCR" 3B; chandra README says "Deepseek OCR" with no size (in same table). The 3B is the consistent claim but should be re-verified against the DeepSeek-OCR repo's model card.
11. **PaddleOCR PP-OCRv6 "surpasses Qwen3-VL-235B and GPT-5.5" claim** is from PaddleOCR's own README. It is a vendor benchmark, not an independent one. Synthesis should weight this claim carefully.
12. **GOT-OCR-2.0 olmOCR-bench 48.3** is cited by the surya README. GOT-OCR-2.0's own README has no DocVQA/OCRBench/OmniDocBench numbers. The 48.3 is third-party and should be treated as a sanity check, not a primary claim.

---

*End of track-ocr-vision scout deliverable. Companion evidence file: `track-ocr-evidence.md`.*
