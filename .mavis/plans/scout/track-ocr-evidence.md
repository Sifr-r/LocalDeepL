# Evidence Inventory — AI OCR Vision Models (scout, track-ocr-vision)

Fetched 2026-06-14. Each entry: URL, fetched date, what we extracted, key file_path:line
citations. Inline `[F]` = factual, `[A]` = analysis / interpretation.

This file is the raw evidence dump produced by parallel sub-agents + targeted webfetches.
The main deliverable lives at `track-ocr.md` and is the authoritative synthesis.

---

## Surya (state of the art, already used by LocalDeepL)

URL: https://github.com/datalab-to/surya (formerly github.com/VikParuchuri/surya)
Fetched: 2026-06-14

**LICENSE**: Code Apache-2.0; model weights under modified AI Pubs Open Rail-M (OpenRAIL-M badge in README "Commercial usage" section) — free for research, personal use, startups <$5M funding/revenue. [F]

**Model size**: ~0.65B params (Surya OCR 2). Detection + OCR + table_rec share one ~650M VLM. Text-line detection is a separate small torch model — a modified EfficientViT/Segformer trained from scratch. [F]

**Architecture**: "Surya 2 is a single VLM that handles layout analysis, OCR (full-page or per-block), and table recognition in one model." Layout, OCR and table_rec emit either layout JSON or full-page HTML depending on prompt. Detection is a separate EfficientViT/Segformer torch model. [F]

**Input / Output**:
- Input: images, PDFs, or folder of images/PDFs (CLI: `surya_ocr DATA_PATH`).
- Output: JSON — per-page `blocks` (label, raw_label, reading_order, html, polygon, bbox, confidence, skipped, error) and `image_bbox`. Math as `<math>...</math>` KaTeX-compatible LaTeX; tables as `<table>...</table>`. Layout: per-block bboxes + label (Caption / Footnote / Equation / ListGroup / PageHeader / PageFooter / Picture / SectionHeader / Table / Text / Figure / Code / Form / TableOfContents / ChemicalBlock / Diagram / Bibliography / BlankPage) + reading order. Table_rec: rows/cols/cells with row_id/col_id/cell_id + optional HTML. [F]

**Inference**:
```
pip install surya-ocr
surya_ocr DATA_PATH [--page_range N] [--output_dir DIR] [--images] [--keep_server]
# Python:
from surya.inference import SuryaInferenceManager
from surya.recognition import RecognitionPredictor
manager = SuryaInferenceManager()
rec = RecognitionPredictor(manager)
predictions = rec([Image.open(IMAGE_PATH)])
# Auto-spawns vllm (NVIDIA) or llama.cpp/llama-server (CPU/Apple Silicon)
# env: SURYA_INFERENCE_BACKEND=vllm|llamacpp, SURYA_INFERENCE_URL=http://host:port/v1,
#      SURYA_INFERENCE_PARALLEL=8
```
[F]

**VRAM**: 5.35 pages/s on a single RTX 5090 (32 GB) at concurrency 128 (96 DPI, ~2,410 output tokens/page). Apple Silicon: 0.108 pages/s at --parallel=8, ~30 W. [F]

**Strengths** (verbatim from README):
- 83.3% on olmOCR-bench (top under 3B params)
- 5 pages/s on RTX 5090
- 87.2% on 91-language internal multilingual benchmark (38/91 ≥ 90%, 76/91 ≥ 80%)
- Layout analysis with reading order + table recognition [F]

**Limitations** (verbatim from README "Limitations" section):
- "This is specialized for document OCR. Performance on photos or natural scenes is not the goal."
- "Layout / OCR / table_rec all need a running inference backend (vllm or llama.cpp). Detection runs purely on torch and works without it." [F]

**Benchmark numbers** (from README "Benchmarks" section):
- olmOCR-bench: Surya OCR 2 0.65B = 83.3 (ArXiv 88.3, Base 99.7, Hdr/Ftr 92.5, TinyTxt 93.7, MultCol 82.4, OldScan 41.8, OldMath 81.4, Tables 86.6). Comparison: Infinity-Parser2-Pro 35.1B=87.6, Chandra OCR 2 5.3B=85.9, dots.mocr 3.0B=83.9, LightOnOCR-2-1B=83.2, Chandra OCR 1 9.0B=83.1, olmOCR anchored 8.3B=77.4, GOT OCR 0.6B=48.3. [F]
- Multilingual 91 languages: en 92.3, de 89.7, zh 82.5, ja 86.2, ar 72.7. [F]

**file_path:line citations**:
- README.md "Surya" intro (650M param OCR model, 83.3% olmOCR-bench, 5 pages/s)
- README.md "Limitations"
- README.md "Inference Backends" (vllm/llama.cpp env settings)
- README.md "Training" (Qwen3.5-style architecture, ~650M params + separate EfficientViT segformer detector)
- LICENSE (Apache-2.0)

**Notes**: Renamed/moved from VikParuchuri/surya to datalab-to/surya. Surya 2 deprecated v1 `FoundationPredictor` in favor of `SuryaInferenceManager` that auto-spawns the VLM server. [A]

---

## GOT-OCR-2.0

URL: https://github.com/Ucas-HaoranWei/GOT-OCR2.0
Fetched: 2026-06-14

**LICENSE**: Code Apache-2.0 (stanford_alpaca LICENSE badge), Data CC BY NC 4.0 (Data License badge). [F]

**Model size**: ~580M / 0.6B (paper claims ~580M; olmOCR-bench row in surya README lists "GOT OCR 0.6B 48.3"). [F]

**Architecture**: "General OCR Theory: Towards OCR-2.0 via a Unified End-to-end Model" — unified end-to-end VLM (vision encoder + Qwen-style LLM) with one model handling plain OCR, format OCR (HTML/Markdown), fine-grained OCR (bbox-region + colored highlighting), and multi-crop/page OCR. Built on Vary-tiny (stage-1) and Qwen LLM backbone. [F]

**Input / Output**:
- Input: image, PDF (folder of PNG pages), optional bbox `[x1,y1,x2,y2]` or color red/green/blue highlight for fine-grained OCR; multi-page via `--multi-page` token-level paging.
- Output: plain text OR formatted HTML/Markdown; rendered HTML in `/results/demo.html` when `--render`. Multi-crop returns per-crop text. [F]

**Inference**:
```
conda create -n got python=3.10 -y && conda activate got
git clone https://github.com/Ucas-HaoranWei/GOT-OCR2.0.git
pip install -e .  # environment: cuda11.8 + torch2.0.1
pip install ninja && pip install flash-attn --no-build-isolation
# plain text OCR:
python3 GOT/demo/run_ocr_2.0.py --model-name /GOT_weights/ --image-file /an/image/file.png --type ocr
# format OCR (HTML/Markdown):
python3 GOT/demo/run_ocr_2.0.py --model-name /GOT_weights/ --image-file /an/image/file.png --type format
# fine-grained OCR (bbox):
python3 GOT/demo/run_ocr_2.0.py --model-name /GOT_weights/ --image-file /an/image/file.png --type format/ocr --box [x1,y1,x2,y2]
# multi-page:
python3 GOT/demo/run_ocr_2.0_crop.py --model-name /GOT_weights/ --image-file /images/path/ --multi-page
# render:
python3 GOT/demo/run_ocr_2.0.py --model-name /GOT_weights/ --image-file /an/image/file.png --type format --render
# via HuggingFace transformers (post 2025-02-01):
# model id stepfun-ai/GOT-OCR-2.0-hf
```
[F]

**VRAM**: No explicit minimum. Environment stated as cuda11.8 + torch2.0.1. flash-attn required. Community CPU/ONNX/MNN/Llama.cpp ports linked. [F]

**Strengths**:
- Unified end-to-end model (one architecture for plain/format/region/multi-page OCR) [F]
- 1M+ HuggingFace downloads (2024/12/8) [F]
- HuggingFace trending #1 (2024/9/19) [F]
- Merged into HuggingFace transformers (2025/2/1); supported in PaddleMIX (2024/12/18) [F]
- 32 languages per paper [F]

**Limitations** (verbatim from README "Demo" note): "multi-page feature is not batch inference; works on token level" (README.md "Demo" note). Training code only supports post-training (stage-2/stage-3); stage-1 needs Vary-tiny-600k. (README.md "Train" section). [F]

**Benchmark numbers**: README links "Fox" + "OneChart" benchmarks via `GOT/eval/evaluate_GOT.py` but does NOT print numeric scores in README. External olmOCR-bench shows GOT OCR 0.6B at 48.3 overall (per surya README). [F]

**file_path:line citations**:
- README.md "Install" (cuda11.8+torch2.0.1 + flash-attn install commands)
- README.md "Demo" (`run_ocr_2.0.py` commands)
- README.md "Train" (deepspeed /GOT-OCR-2.0-master/GOT/train/train_GOT.py with --bf16 --tf32 --per_device_train_batch_size 2)
- README.md "Release" (license + release timeline)
- LICENSE (Apache-2.0 code)

**Notes**: Repo name "Ucas-HaoranWei/GOT-OCR2.0" contains subdir `GOT-OCR-2.0-master`. Model author Haoran Wei is also author of DeepSeek-OCR. Authors acknowledge Vary (Ucas-HaoranWei/Vary/) and Qwen. README has no explicit "Limitations" section; only stated limits are no-batch for multi-page and the "post-training only" caveat. [F]

---

## OlmOCR

URL: https://github.com/allenai/olmocr
Fetched: 2026-06-14

**LICENSE**: Apache-2.0. [F]

**Model size**: 7B / 8B parameter VLM. Default model `allenai/olmOCR-7B-0725-FP8`. Current v0.4.0 model is `allenai/olmOCR-2-7B-1025-FP8` (FP8 quantized). 8.3B listed under "anchored" in their own benchmark table. Built on Qwen2.5-VL backbone ("SFT Finetuning code for Qwen2.5-VL — train.py" — README "Code overview"). [F]

**Architecture**: "Toolkit for linearizing PDFs for LLM datasets/training. A prompting strategy to get really good natural text parsing using ChatGPT 4o - [buildsilver.py]. SFT Finetuning code for Qwen2.5-VL - [train.py]. GRPO RL Trainer - [grpo_train.py]. Processing millions of PDFs through a finetuned model using VLLM - [pipeline.py]." (README "Code overview") [F]

**Input / Output**:
- Input: PDF, PNG, JPEG. CLI: `olmocr ./workspace --markdown --pdfs <file_or_glob>`. Optionally takes S3 paths.
- Output: Markdown (.md) and Dolma format. Per-page anchored text + images. Filters out headers/footers and SEO-spam (with `--apply_filter`). [F]

**Inference**:
```
# Local GPU (CUDA 12.8, ≥12 GB VRAM, 30 GB disk):
conda create -n olmocr python=3.11
pip install olmocr[gpu] --extra-index-url https://download.pytorch.org/whl/cu128
pip install https://download.pytorch.org/whl/cu128/flashinfer/flashinfer_python-0.2.5+cu128torch2.7-cp38-abi3-linux_x86_64.whl
olmocr ./localworkspace --markdown --pdfs sample.pdf
# Remote vLLM:
pip install olmocr
olmocr ./workspace --server http://remote:8000/v1 --model allenai/olmOCR-2-7B-1025-FP8 --markdown --pdfs *.pdf
# vLLM launch:
vllm serve allenai/olmOCR-2-7B-1025-FP8 --max-model-len 16384
# Docker:
docker pull alleninstituteforai/olmocr:latest-with-model
docker run --gpus all -v $(pwd):/workspace alleninstituteforai/olmocr:latest-with-model -c "olmocr /workspace/output --markdown --pdfs /workspace/sample.pdf"
```
[F]

**VRAM**: "Recent NVIDIA GPU (tested on RTX 4090, L40S, A100, H100) with at least 12 GB of GPU RAM. 30GB of free disk space." Verified external providers: Cirrascale ($0.07/M input), DeepInfra ($0.09), Parasail ($0.10). [F]

**Strengths**:
- Convert PDF/PNG/JPEG to clean Markdown [F]
- Support for equations, tables, handwriting, complex formatting [F]
- Auto-removes headers/footers [F]
- Natural reading order in presence of figures, multi-column, insets [F]
- <$200 USD per million pages converted (based on 7B VLM) [F]

**Limitations**:
- GPU-only (7B VLM) [F]
- "Recent NVIDIA GPU ... at least 12 GB of GPU RAM" [F]
- Section: "Too many open files" requires `ulimit -n 65536` [F]

**Benchmark numbers** (olmOCR-Bench, 8,413 tests, table reproduced from repo):
- olmOCR v0.4.0: ArXiv 83.0, OldScansMath 82.3, Tables 84.9, OldScans 47.7, H/F 96.1, MultiCol 83.7, LongTiny 81.9, Base 99.7, Overall 82.4±1.1
- Chandra OCR 0.1.0*: 83.1±0.9 overall
- PaddleOCR-VL*: 80.0±1.0
- DeepSeek-OCR: 75.7±1.0
- Mistral OCR API: 72.0±1.1
- Marker 1.10.1: 76.1±1.1
- MinerU 2.5.4*: 75.2±1.1
- Nanonets-OCR2-3B: 69.5±1.1
- Infinity-Parser 7B*: 82.5±? [F]

**file_path:line citations**:
- README.md "News" (version timeline v0.1.58→v0.4.0)
- README.md "Benchmark" (8-column table)
- README.md "Code overview" (links to buildsilver.py, train.py, grpo_train.py, pipeline.py)
- README.md "Python Installation" (cuda 12.8, ≥12 GB VRAM)
- LICENSE

**Notes**: 7B Qwen2.5-VL SFT base; v2 added RL with unit-test rewards (arxiv 2510.19817). Two papers cited: arxiv 2502.18443 (v1) and arxiv 2510.19817 (v2). The full benchmark suite lives under `olmocr/bench/`. [F]

---

## dots.ocr / dots.mocr

URL: https://github.com/rednote-hilab/dots.ocr (renamed dots.mocr per 2026-03-19 rebrand)
Fetched: 2026-06-14

**LICENSE**: MIT (for code); "dots.ocr LICENSE AGREEMENT" file (separate model weight license). [F]

**Model size**: 1.7B LLM (initial dots.ocr release 2025-07-30); 3B for current dots.mocr ("Multimodal OCR" rename of dots.ocr-1.5 in 2026-03-19 per arxiv 2603.13032). [F]

**Architecture**: "Multilingual Document Layout Parsing in a Single Vision-Language Model" — single VLM that does layout detection (bboxes + categories) + text extraction in one forward pass, returning JSON with bbox, category, and text per element. Categories: Caption, Footnote, Formula, List-item, Page-footer, Page-header, Picture, Section-header, Table, Text, Title. Formula→LaTeX, Table→HTML, others→Markdown. (README.md "3. Document Parse" + "Hugginface inference details" code block). [F]

**Input / Output**:
- Input: PDF or image; prompt modes: `prompt_layout_all_en` (full layout+recognition), `prompt_layout_only_en`, `prompt_ocr` (text only, excluding headers/footers), `prompt_web_parsing`, `prompt_scene_spotting`, `prompt_image_to_svg`, general QA.
- Output: 1. Structured Layout JSON (`*.json`) with bboxes + categories + text. 2. Markdown (`*.md` and `*_nohf.md` with headers/footers stripped). 3. Layout visualization JPG. [F]

**Inference**:
```
# Install
conda create -n dots_mocr python=3.12
git clone https://github.com/rednote-hilab/dots.mocr.git && cd dots.mocr
pip install -e .   # torch==2.7.0 + flash-attn==2.8.0.post2 recommended
python3 tools/download_model.py   # or --type modelscope
# vLLM (recommended, integrated since vLLM 0.11.0):
CUDA_VISIBLE_DEVICES=0 vllm serve rednote-hilab/dots.mocr --tensor-parallel-size 1 \
    --gpu-memory-utilization 0.9 --chat-template-content-format string \
    --served-model-name model --trust-remote-code
# Parse:
python3 dots_mocr/parser.py demo/demo_image1.jpg
python3 dots_mocr/parser.py demo/demo_pdf1.pdf --num_thread 64
python3 dots_mocr/parser.py demo/demo_image1.jpg --prompt prompt_layout_only_en
python3 dots_mocr/parser.py demo/demo_image1.jpg --prompt prompt_ocr
# Transformers fallback:
python3 demo/demo_hf.py
```
[F]

**VRAM**: No explicit GB minimum in README. vLLM 0.11.0+ integrated. flash-attn 2.8.0.post2 recommended. CPU inference linked via `https://github.com/rednote-hilab/dots.ocr/issues/1#issuecomment-3148962536`. Docker image: `rednotehilab/dots.ocr`. [F]

**Strengths** (verbatim from README):
- State-of-the-art multilingual document parsing at comparable size [F]
- Converts structured graphics (charts/diagrams) directly into SVG code (dots.mocr) [F]
- Parses web screens and scene text [F]
- Integrated into vLLM since 0.11.0 [F]
- dots.ocr.base (foundation VLM) also released for OCR tasks [F]

**Limitations** (verbatim from README "Limitation & Future Work"):
- "Complex Document Elements: Table&Formula: The extraction of complex tables and mathematical formulas persists as a difficult task given the model's compact architecture." [F]
- "Picture: We have adopted an SVG code representation for parsing structured graphics; however, the performance has yet to achieve the desired level of robustness." [F]
- "Parsing Failures: While we have reduced the rate of parsing failures compared to the previous version, these issues may still occur occasionally." [F]

**Benchmark numbers** (from README):
- (a) Elo Score (Gemini 3 Flash judge): dots.mocr 3B avg 1124.7 (olmOCR-Bench 1104.4, OmniDocBench v1.5 1059.0, XDocParse 1210.7). PaddleOCR-VL-1.5 avg 920.5, GLM-OCR 892.5, HuanyuanOCR 984.2, Gemini 3 Pro 1210.7. [F]
- (b) olmOCR-bench per-category: dots.mocr 3B ArXiv 85.9, OldScansMath 85.5, Tables 90.7, OldScans 48.2, H/F 94.0, MultiCol 85.3, LongTiny 81.6, Base 99.7, Overall 83.9±0.9. (dots.ocr 3B original: Overall 79.1±1.0.) [F]
- (c) OmniDocBench v1.5: dots.mocr TextEdit 0.031, ReadOrderEdit 0.029; pdf-parse-bench 9.54. [F]
- (d) SVG: dots.mocr-svg scores UniSVG 0.860, Chartmimic 0.931, Design2Code 0.902, Genexam 0.905, SciGen 0.834, ChemDraw 0.8, Low-Level 0.797, High-Level 0.901. [F]
- (e) General VL: dots.mocr CharXiv_descriptive 77.4, CharXiv_reasoning 55.3, OCR_Reasoning 22.85, infoVQA 73.76, DocVQA 91.85, ChartQA 83.2, OCRBench 86.0, AI2D 82.16, CountBenchQA 94.46, RefCOCO 80.03. [F]

**file_path:line citations**:
- README.md "News" (2026-03-19 rebrand dots.ocr-1.5 → dots.mocr)
- README.md "2. Deployment" (vllm serve command)
- README.md "3. Document Parse" (parser.py commands)
- README.md "Hugginface inference" (transformers AutoModelForCausalLM code block)
- README.md "Limitation & Future Work"
- LICENSE (MIT)

**Notes**: Repo URL says "dots.ocr" but the install command and the actual model checked in git use `dots.mocr` — the 2026-03-19 rebrand put the code under `https://github.com/rednote-hilab/dots.mocr` (per the git clone in "Install"). README is the canonical docs even though the repo name still reads dots.ocr. [F]

---

## Qwen2.5-VL / Qwen3-VL (combined, since Qwen3-VL README supersedes Qwen2.5-VL)

URL: https://github.com/QwenLM/Qwen3-VL (canonical, latest); original Qwen2.5-VL repo: https://github.com/QwenLM/Qwen2.5-VL (now redirects to Qwen3-VL); Qwen2.5-VL Technical Report: arxiv 2502.13923
Fetched: 2026-06-14

**LICENSE**: Apache-2.0. [F]

**Model size**: 
- Qwen3-VL: 2B (Instruct/Thinking), 4B, 8B, 30B-A3B (MoE), 32B, 235B-A22B (MoE).
- Qwen2.5-VL (older gen, still released): 3B, 7B, 32B, 72B + AWQ quantizations of 3B/7B/72B. [F]

**Architecture**: Qwen3-VL architecture updates (README "Model Architecture Updates"): "1. Interleaved-MRoPE: Full-frequency allocation over time, width, and height via robust positional embeddings, enhancing long-horizon video reasoning. 2. DeepStack: Fuses multi-level ViT features to capture fine-grained details and sharpen image-text alignment. 3. Text-Timestamp Alignment: Moves beyond T-RoPE to precise, timestamp-grounded event localization." Qwen2.5-VL paper: arxiv 2502.13923. ViT + Qwen-style LLM. [F]

**Input / Output**:
- Input: Image (local file, URL, base64), multiple images per conversation, video (URL/local, with fps or num_frames control). Qwen3-VL: "image_patch_size: 14 for Qwen2.5-VL and 16 for Qwen3-VL". 256K native context, expandable to 1M.
- Output: Free-form text response (any task: VQA, document parsing, GUI agent, etc). Document parsing cookbook emits "Qwen HTML format" with layout + text (cookbooks/document_parsing.ipynb). [F]

**Inference**:
```
pip install "transformers>=4.57.0"
pip install qwen-vl-utils==0.0.14
# Transformers:
from transformers import AutoModelForImageTextToText, AutoProcessor
from qwen_vl_utils import process_vision_info
model = AutoModelForImageTextToText.from_pretrained("Qwen/Qwen3-VL-235B-A22B-Instruct", dtype="auto", device_map="auto")
processor = AutoProcessor.from_pretrained("Qwen/Qwen3-VL-235B-A22B-Instruct")
messages = [{"role": "user", "content": [{"type": "image", "image": "..."}, {"type": "text", "text": "Describe this image."}]}]
inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt")
inputs = inputs.to(model.device)
generated_ids = model.generate(**inputs, max_new_tokens=128)
```
[F]

**VRAM**: No explicit minimum. Demos and cookbooks imply A100/H100 for the 235B MoE. AWQ-quantized 3B/7B/72B available for Qwen2.5-VL reduce memory. [F]

**Strengths** (Qwen3-VL):
- Visual Agent: PC/mobile GUI control [F]
- Visual Coding Boost: Draw.io/HTML/CSS/JS from images [F]
- Advanced Spatial Perception: 2D + 3D grounding [F]
- Long Context & Video: native 256K, expandable to 1M [F]
- Enhanced multimodal reasoning (STEM/Math) [F]
- Expanded OCR: 32 languages (up from 10), robust in low light/blur/tilt [F]
- Text understanding on par with pure LLMs [F]

**Limitations**: No explicit "Limitations" section in README. Implicit: very large models (235B-A22B) require multi-GPU. [F]

**Benchmark numbers**: README.md "Performance" only embeds images of tables (no inline numbers). Cookbook references for OCR / DocVQA / OmniDocBench etc but no printed numbers in README. [F]

**file_path:line citations**:
- README.md "Introduction" (Key Enhancements bullets)
- README.md "Model Architecture Updates" (Interleaved-MRoPE/DeepStack/Text-Timestamp)
- README.md "News" (Qwen3-VL-2B released 2025.10.21, 32B same day, 4B/8B 2025.10.15, 30B-A3B 2025.10.04, 235B-A22B 2025.09.23)
- README.md "Quickstart" (transformers>=4.57.0 + qwen-vl-utils==0.0.14)
- LICENSE

**Notes**: Repository originally was QwenLM/Qwen2.5-VL; it has been renamed/replaced with QwenLM/Qwen3-VL on GitHub. The Qwen2.5-VL README is no longer served at the old URL — what is now displayed is the Qwen3-VL README. [F]

---

## InternVL (latest family line: InternVL3.5; current README also covers InternVL3, InternVL2.5, InternVL2, InternVL1)

URL: https://github.com/OpenGVLab/InternVL
Fetched: 2026-06-14

**LICENSE**: MIT. [F]

**Model size**: InternVL3.5 family (Aug 2025): 1B (0.3B vision + 0.8B LM = 1.1B), 2B (2.3B), 4B (4.7B), 8B (8.5B), 14B (15.1B), 38B (5.5B vision + 32.8B LM = 38.4B), 20B-A4B MoE (21.2B-A4B, GPT-OSS-20B-A4B base), 30B-A3B (30.8B-A3B MoE), 241B-A28B MoE (240.7B-A28B). InternVL3 (Apr 2025): 1B/2B/8B/9B/14B/38B/78B. InternVL2.5 (Dec 2024): 1B/2B/4B/8B/26B/38B/78B + MPO variants. InternVL2: 1B/2B/4B/8B/26B/40B/76B. Vision backbones: InternViT-300M-448px-V2_5 (small) and InternViT-6B-448px-V2_5 (large). [F]

**Architecture**: Standard "ViT + LLM" multimodal LLM. Key design choices for InternVL3-78B: "Variable Visual Position Encoding, Native Multimodal Pre-Training, Mixed Preference Optimization, Multimodal Test-Time Scaling." (README "News" 2025/04/11 entry.) Vision-Language foundation model InternVL-14B-224px = "InternViT-6B + QLLaMA" per "Vision-Language Foundation Model (InternVL 1.0)" table. InternVL3.5 introduces CascadeRL (offline + online RL). InternVL2.5-MPO: Mixed Preference Optimization on MMPR-v1.1. [F]

**Input / Output**:
- Input: Image (single or multi-image), video. Chat data formats documented: meta file / pure text / single-image / multi-image / video. PDF and video in online demo noted as TODO.
- Output: Free-form text. Document VQA, OCR, ChartQA, etc. [F]

**Inference**:
```
# Install (per INSTALLATION.md / requirements.txt; not quoted in main README)
pip install -r requirements.txt
# Quick start: streamlit demo, HuggingFace transformers, or vLLM/Ollama (TODO list says "Support vLLM and Ollama")
# HF inference:
from transformers import AutoModel, AutoTokenizer
model = AutoModel.from_pretrained("OpenGVLab/InternVL3_5-8B", trust_remote_code=True).eval().cuda()
tokenizer = AutoTokenizer.from_pretrained("OpenGVLab/InternVL3_5-8B", trust_remote_code=True)
# Demo: chat.intern-ai.org.cn
```
[F]

**VRAM**: 4-bit AWQ quantizations referenced ("InternVL-Chat-V1-5-AWQ"); InternVL-Chat-V1-5 supports 4K image. No explicit "must have X GB" line in README; model sizes imply multi-GPU for 78B / 241B. [F]

**Strengths**:
- "InternVL3.5-241B-A28B attains state-of-the-art results among open-source MLLMs across general multimodal, reasoning, text, and agentic tasks" (2025/08/26) [F]
- "First open-source MLLM to achieve over 70% on the MMMU benchmark" (InternVL2_5-78B) [F]
- "InternVL2-Pro achieved the SOTA performance on the DocVQA and InfoVQA benchmarks" (2024/07/18) [F]
- InternVL2-40B scored 61.2/64.4 on Video-MME (16/32 frames) [F]
- Mini-InternVL-Chat-4B-V1-5: "16% of the model size, 90% of the performance" [F]

**Limitations**: TODO list (README bottom): "Support liger kernels to save GPU memory", "Support multimodal packed dataset", "Support vLLM and Ollama", "Support video and PDF input in online demo" — implies these are still in progress as of README capture. [F]

**Benchmark numbers**: README mentions MMMU 70%+ (InternVL2_5-78B), MathVista 67.0 (InternVL2-8B-MPO), CharXiv SOTA, Chartmimic top-2 (InternVL2-26B/76B), DocVQA/InfoVQA SOTA (InternVL2-Pro), Video-MME 61.2/64.4, MMBench 83.8 (InternVL-Chat-V1-2-Plus), MMVP 58.7. No full numeric table in README; references link to OpenCompass leaderboard. [F]

**file_path:line citations**:
- README.md "News" (timeline bullets: 2025/04/11 InternVL3, 2025/08/26 InternVL3.5, 2024/12/05 InternVL2.5, 2024/07/04 InternVL2, 2024/02/27 CVPR 2024 Oral)
- README.md "Model Zoo" InternVL 3.5 table
- README.md "TODO List" (vLLM, Ollama, multimodal packed, video+PDF)
- README.md "InternVL 1.0" table (InternVL-14B-224px = InternViT-6B + QLLaMA)
- LICENSE (MIT)

**Notes**: Repository name is `InternVL` but the latest family is InternVL3.5 (Aug 2025). No "InternVL 3 or latest" distinction needed — the repo is a meta-repository of all versions. [F]

---

## SmolVLM

URL: https://github.com/huggingface/smollm (canonical repo; github.com/huggingface/smolvlm 404'd)
Fetched: 2026-06-14

**LICENSE**: Apache-2.0 (all checkpoints, training recipes, and tools per SmolVLM blog "TLDR" and LICENSE file). [F]

**Model size**: 2B total ("a family of 2B small vision language models"). SmolVLM-Instruct, SmolVLM-Base, SmolVLM-Synthetic are all 2B. SmolVLM2 also 2.2B. A later SmolVLM-256M was also released by HF. [F]

**Architecture** (verbatim from smolvlm blog "Architecture" section): "We closely followed the architecture from Idefics3, to the point that we use the same implementation in transformers. There are, however a few key differences: We replaced Llama 3.1 8B with SmolLM2 1.7B as the language backbone. We more aggressively compress the patched visual information by reducing the information 9x using the pixel shuffle strategy, compared to 4x with idefics3. We use patches of 384*384, instead of 364x364, because 384 is divisible by 3, which is necessary for our pixel shuffle strategy to work. For this, we change the vision backbone to use shape-optimized SigLIP with patches of 384x384 pixels and inner patches of 14x14." [F]

**Input / Output**:
- Input: 1+ image(s) and text; multiple images per conversation; can be used for video (extracting up to 50 frames evenly sampled; SmolVLM_video_inference.py).
- Output: Free-form text response. [F]

**Inference**:
```
pip install transformers
from transformers import AutoProcessor, AutoModelForVision2Seq
import torch
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
processor = AutoProcessor.from_pretrained("HuggingFaceTB/SmolVLM-Instruct")
model = AutoModelForVision2Seq.from_pretrained("HuggingFaceTB/SmolVLM-Instruct",
    torch_dtype=torch.bfloat16,
    _attn_implementation="flash_attention_2" if DEVICE == "cuda" else "eager").to(DEVICE)
```
[F]

**VRAM**: "Min GPU RAM required (GB): SmolVLM 5.02" per benchmark table in blog. Qwen2-VL 2B needed 13.70, InternVL2 2B 10.52, PaliGemma 3B 6.72, moondream2 3.87. "fine-tune in L4 ... ~16 GBs of VRAM" (with QLoRA, 8-bit loading, gradient checkpointing, batch 4). [F]

**Strengths** (verbatim from blog "TLDR"):
- "SOTA for its memory footprint" [F]
- 3.3-4.5x faster prefill and 7.5-16x faster generation vs Qwen2-VL [F]
- 16k token context (extended from 10k RoPE base to 273k) [F]
- All Apache 2.0 [F]

**Limitations**: No explicit "Limitations" section in blog. Implicit from CinePile benchmark (27.14%): "we see some temporal understanding limitations". [F]

**Benchmark numbers** (SmolVLM vs Qwen2-VL-2B / InternVL2-2B / PaliGemma 3B 448px / moondream2 / MiniCPM-V-2 / MM1.5 1B):
- MMMU val: 38.8 (SmolVLM) vs 41.1 (Qwen2-VL 2B) vs 34.3 (InternVL2 2B) vs 32.4 (moondream2) [F]
- MathVista testmini: 44.6 vs 47.8 vs 46.3 [F]
- MMStar val: 42.1 vs 47.5 vs 49.8 [F]
- DocVQA test: 81.6 vs 90.1 vs 86.9 [F]
- TextVQA val: 72.7 vs 79.7 vs 73.4 [F]
- Min GPU RAM: 5.02 GB vs 13.70 GB vs 10.52 GB [F]
- CinePile video: 27.14% (between InternVL2 2B and Video LLaVa 7B) [F]

**file_path:line citations**:
- smollm/README.md "SmolVLM (Vision Language Model)" section
- smolvlm blog "Architecture" (SigLIP 384x384, pixel shuffle 9x, SmolLM2 1.7B backbone, 16k context)
- smolvlm blog "Use SmolVLM with Transformers" (AutoProcessor / AutoModelForVision2Seq, flash_attention_2)
- smollm/LICENSE (Apache-2.0)

**Notes**: Repo name on GitHub is huggingface/smollm (not huggingface/smolvlm). All evidence is from the main README + the smolvlm blog. [F]

---

## Tesseract 5

URL: https://github.com/tesseract-ocr/tesseract
Fetched: 2026-06-14

**LICENSE**: Apache-2.0 (code); Leptonica dependency is BSD 2-clause. [F]

**Model size**: Not a neural-param model. Engine + traineddata. "Tesseract 4 adds a new neural net (LSTM) based OCR engine which is focused on line recognition, but also still supports the legacy Tesseract OCR engine of Tesseract 3 which works by recognizing character patterns." (README.md "About"). Trained language data files in https://github.com/tesseract-ocr/tessdata (separate repo). [F]

**Architecture**: Two engines. (1) Legacy Tesseract 3 — character pattern recognition. (2) Tesseract 4+ — LSTM neural network for line-level recognition. "Tesseract 4 adds a new neural net (LSTM) based OCR engine which is focused on line recognition, but also still supports the legacy Tesseract OCR engine of Tesseract 3 which works by recognizing character patterns. Compatibility with Tesseract 3 is enabled by using the Legacy OCR Engine mode (--oem 0). It also needs traineddata files which support the legacy engine, for example those from the tessdata repository." (README.md "About") [F]

**Input / Output**:
- Input: Various image formats including PNG, JPEG, TIFF (multipage TIFF supported via leptonica). PDF NOT a direct input. Languages: "more than 100 languages out of the box" via separate traineddata files.
- Output: "plain text, hOCR (HTML), PDF, invisible-text-only PDF, TSV, ALTO and PAGE". (README.md "About") [F]

**Inference**:
```
# CLI
tesseract imagename outputbase [-l lang] [--oem ocrenginemode] [--psm pagesegmode] [configfiles...]
# --oem modes: 0 = legacy Tesseract 3 only, 1 = LSTM only (default in v4+), 2 = combined, 3 = default
# C/C++ library:
#include <tesseract/capi.h>          # C API
#include <tesseract/baseapi.h>       # C++ API
# Bindings via AddOns documentation
# Doxygen docs: https://tesseract-ocr.github.io/
```
[F]

**VRAM**: CPU only. No GPU. Build prerequisites listed in INSTALL.GIT.md and `tessdoc/Compiling.html`. leptonica required with zlib/png/tiff support. [F]

**Strengths**:
- "unicode (UTF-8) support" [F]
- "recognize more than 100 languages out of the box" [F]
- "various image formats" (PNG, JPEG, TIFF) [F]
- "various output formats": plain text, hOCR (HTML), PDF, invisible-text-only PDF, TSV, ALTO, PAGE [F]
- Mature, widely used, trainable [F]
- "Major version 5 is the current stable version and started with release 5.0.0 on November 30, 2021" (latest 5.5.2 Dec 2025) [F]

**Limitations**:
- "in many cases, in order to get better OCR results, you'll need to improve the quality of the image you are giving Tesseract" [F]
- "This project does not include a GUI application" [F]
- LSTM engine is line-recognition only, not page/document native [F]
- No native PDF input (leptonica handles images, not PDFs) [F]

**Benchmark numbers**: README contains NO benchmark tables. Performance data lives in the Tesseract Wiki / tessdoc. Latest version 5.5.2 (Dec 26, 2025) per Releases section. [F]

**file_path:line citations**:
- README.md "About" (LSTM engine in Tesseract 4+)
- README.md "Brief history" (HP → Google → current maintainer Zdenko Podobny, lead dev Stefan Weil; Ray Smith lead until 2017)
- README.md "Running Tesseract" (CLI usage line)
- README.md "For developers" (libtesseract C/C++ API)
- README.md "Dependencies" (Leptonica)
- README.md "License" (Apache-2.0)
- include/tesseract/capi.h (C API)

**Notes**: README does NOT contain a discrete "LSTM" section — the only LSTM mention is in the "About" paragraph. Deep LSTM architecture details (LSTM training, unicharset, recoder) are in the source tree under src/lstm/ and in `tessdoc/`. [F]

---

## PaddleOCR

URL: https://github.com/PaddlePaddle/PaddleOCR
Fetched: 2026-06-14

**LICENSE**: Apache-2.0. [F]

**Model size**: Multi-model repo. PaddleOCR-VL family (0.9B ultra-compact VLM): PaddleOCR-VL (0.9B), PaddleOCR-VL-1.5 (0.9B), PaddleOCR-VL-1.6 (0.9B). PP-OCRv6: tiny (1.5M), small (7.7M), medium (34.5M). PP-OCRv5 multilingual recognition: 2M params. PP-StructureV3 (structure-aware conversion). PP-DocLayoutV3 (layout algorithm). [F]

**Architecture** (from README "Key Features" + release notes):
- PaddleOCR-VL-0.9B: "Compact yet Powerful VLM Architecture ... a novel vision-language model that is specifically designed for resource-efficient inference ... integrates a NaViT-style dynamic high-resolution visual encoder with the ERNIE-4.5-0.3B language model ... 109 languages" (README 3.3.0 entry, 2025.10.16)
- PaddleOCR-VL-1.5: SOTA 0.9B VLM with PP-DocLayoutV3 algorithm, 111 languages, seal recognition, text spotting. (2026.01.29)
- PaddleOCR-VL-1.6: 96.3% accuracy on OmniDocBench v1.6 (SOTA), also SOTA on OmniDocBench v1.5 and Real5-OmniDocBench. (2026.05.28)
- PP-OCRv6: "Medium tier achieves +4.6% detection and +5.1% recognition over PP-OCRv5_server, surpassing mainstream VLMs (Qwen3-VL-235B, GPT-5.5) with only 34.5M parameters. 50 languages unified ... 5.2× CPU speedup (OpenVINO), 6.1× on Apple M4 (tiny), 0.13s on A100 GPU." (2026.06.11)
- PP-StructureV3: "seamlessly convert complex PDFs and images into Markdown or JSON. Unlike the PaddleOCR-VL series models, it provides more fine-grained coordinate information, including table cell coordinates, text coordinates, and more." (README "Key Features") [F]

**Input / Output**:
- Input: PDF, images (PNG/JPEG), office documents (Word/Excel/PPT converted to Markdown in 3.5.0). 100+ languages. MCP server (`mcp_server/`), langchain integration, PaddleOCR.js for browser.
- Output: Markdown, JSON, DOCX (PaddleOCR-VL series, PP-StructureV3, PP-DocTranslation can export DOCX since 3.5.0). PP-OCR: per-character coordinates available. [F]

**Inference**:
```
pip install paddleocr
# Hardware backends: NVIDIA GPU, Intel CPU, Kunlunxin XPU, diverse AI Accelerators
# Inference engines: Paddle static graph, Paddle dynamic graph, or Transformers (since 3.5.0)
# Acceleration: OpenVINO, ONNX Runtime, TensorRT, ONNX format
```
[F]

**VRAM**: PP-OCRv6 0.13s on A100 GPU. Multi-tier for edge/mobile/server deployment (1.5M / 7.7M / 34.5M params). PP-OCRv5 C++ deployment Linux/Windows. CUDA 12 supported. PaddlePaddle 3.1.0 / 3.1.1 supported. [F]

**Strengths** (verbatim from README "Key Features" + release notes):
- "PaddleOCR-VL-1.6 (0.9B) ... industry's leading lightweight vision-language model for document parsing. It achieves 96.3% accuracy on OmniDocBench v1.6, leads in text, formula, and table recognition" [F]
- "Structure-Aware Conversion" via PP-StructureV3 (fine-grained coordinates) [F]
- 100+ languages (PP-OCRv6: 50 languages unified) [F]
- PP-OCRv6 "5.2× CPU speedup (OpenVINO), 6.1× on Apple M4 (tiny)" [F]
- 70k+ stars, integrated with Dify, RAGFlow, Pathway, Cherry Studio [F]
- Production-ready: high-stability service-oriented deployment, MCP server, browser SDK [F]

**Limitations**: README does not have a discrete "Limitations" section. Implicit: very long/complex formulas and tables still hard; structural coordinate quality depends on PP-DocLayoutV3. [F]

**Benchmark numbers**:
- OmniDocBench v1.6: PaddleOCR-VL-1.6 = 96.3% (SOTA) [F]
- OmniDocBench v1.5: PaddleOCR-VL-1.5 = 94.5% [F]
- PP-OCRv6 medium +4.6% det / +5.1% rec over PP-OCRv5_server; surpasses Qwen3-VL-235B and GPT-5.5 [F]
- Real5-OmniDocBench: PaddleOCR-VL-1.6 SOTA [F]
- (Detailed eval tables in arxiv: 2507.05595 PaddleOCR 3.0 report, 2510.14528 PaddleOCR-VL, 2601.21957 PaddleOCR-VL-1.5, 2606.03264 PaddleOCR-VL-1.6) [F]

**file_path:line citations**:
- README.md "Global Leading OCR Toolkit & Document AI Engine" header
- README.md "Key Features"
- README.md "2026.06.11 Release of PaddleOCR 3.7.0"
- README.md "2026.05.28" (PaddleOCR-VL-1.6 release notes)
- README.md "2026.04.21" (Transformers backend + 20 models + DOCX export + PaddleOCR.js)
- README.md "2025.10.16" (PaddleOCR-VL architecture: NaViT + ERNIE-4.5-0.3B)
- LICENSE (Apache-2.0)

**Notes**: PaddleOCR is a multi-product repo — pick the right model per use case. PaddleOCR-VL (0.9B) is the modern document-parsing VLM; PP-OCRv6 is the lightweight classical pipeline. PP-StructureV3 is the hybrid layout+recognition pipeline. [A]

---

## docTR

URL: https://github.com/mindee/doctr
Fetched: 2026-06-14

**LICENSE**: Apache-2.0. [F]

**Model size**: Two-stage detection + recognition. Pretrained checkpoints downloadable; sizes not stated numerically in README. Detectors: DBNet (with ResNet50 backbone, e.g. `db_resnet50`), LinkNet, FAST. Recognizers: CRNN (VGG16-BN backbone, e.g. `crnn_vgg16_bn`), SAR, MASTER, ViTSTR, PARSeq, VIPTR. No single "docTR model size" — users pick `det_arch=` and `reco_arch=`. [F]

**Architecture**: "End-to-End OCR is achieved in docTR using a two-stage approach: text detection (localizing words), then text recognition (identify all characters in the word)." (README "Getting your pretrained model"). Architectures from published papers: DBNet, LinkNet, FAST (detection); CRNN, SAR, MASTER, ViTSTR, PARSeq, VIPTR (recognition). KIE (Key Information Extraction) predictor allows multi-class detection + recognition. (README "Models architectures") [F]

**Input / Output**:
- Input: PDF, image, multi-page image lists, URL via `weasyprint`. `DocumentFile.from_pdf / from_images / from_url`. Default assumes straight pages, with options for rotated pages.
- Output: `Document` object with nested `Page > Block > Line > Word > Artefact` structure. `result.export()` to nested dict / JSON. Rotation support: `assume_straight_pages`, `export_as_straight_boxes`. Also KIE predictor returns per-page class-keyed dict of predictions. [F]

**Inference**:
```
pip install python-doctr
# Optional extras
pip install "python-doctr[viz,html,contrib]"
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
model = ocr_predictor(pretrained=True)
doc = DocumentFile.from_pdf("path/to/your/doc.pdf")
result = model(doc)
# Or with custom archs:
model = ocr_predictor(det_arch="db_resnet50", reco_arch="crnn_vgg16_bn", pretrained=True)
# KIE
from doctr.models import kie_predictor
kie = kie_predictor(det_arch="db_resnet50", reco_arch="crnn_vgg16_bn", pretrained=True)
# Docker (CUDA 12.2 base, GPU-ready)
docker run -it --gpus all ghcr.io/mindee/doctr:torch-py3.9.18-2024-10 bash
```
[F]

**VRAM**: "Docker images are GPU-ready and based on CUDA 12.2." CPU inference supported. No explicit minimum VRAM in README. [F]

**Strengths**:
- "efficient ways to parse textual information (localize and identify each word) from your documents" [F]
- PyTorch-based, Apache 2.0 [F]
- Multiple detection + recognition architectures swappable [F]
- Rotated page / multi-orientation support [F]
- KIE support [F]
- FastAPI template included [F]

**Limitations**: README does NOT have an explicit "Limitations" section. Implicit: smaller/older project compared to VLM-based document parsers; no LLM-grade document understanding; speed/accuracy tied to chosen det/reco arch pair. [F]

**Benchmark numbers**: README contains NO benchmark tables. No DocVQA / OmniDocBench numbers. (Project focuses on architecture flexibility, not on top-line benchmark leadership.) [F]

**file_path:line citations**:
- README.md "Quick Tour / Getting your pretrained model" (`ocr_predictor(det_arch="db_resnet50", reco_arch="crnn_vgg16_bn", pretrained=True)`)
- README.md "Models architectures"
- README.md "Installation" (pip install python-doctr)
- README.md "Docker container" (CUDA 12.2 GPU images)
- LICENSE (Apache-2.0)

**Notes**: The latest GitHub release is v1.0.1 (Feb 4, 2026). Project supported by t2k GmbH. [F]

---

## Chandra-OCR-v1 / Chandra OCR 2

URL: https://github.com/datalab-to/chandra
Fetched: 2026-06-14

**LICENSE**: Apache-2.0 (code); model weights under modified OpenRAIL-M (free for research, personal use, startups <$2M funding/revenue; cannot be used competitively with the Datalab API). [F]

**Model size**: Chandra OCR 2 = 5.3B (per surya README "Chandra OCR 2 (Datalab) 5.3B 85.9" on olmOCR-bench). Chandra 1 = 9.0B (per same source). v0.2.0 release tag "Chandra OCR 2" Mar 18, 2026. Code uses Qwen 3.5 base. [F]

**Architecture**: VLM-based OCR model that converts images and PDFs into structured HTML / Markdown / JSON preserving layout. "Tops external olmocr benchmark and significant improvement in internal multilingual benchmarks. Convert documents to markdown, html, or json with detailed layout information. Support for 90+ languages. Excellent handwriting support. Reconstructs forms accurately, including checkboxes. Strong performance with tables, math, and complex layouts. Extracts images and diagrams, and adds captions and structured data. Two inference modes: local (HuggingFace) and remote (vLLM server)." (README "Features") Based on Qwen 3.5 per "Credits" section. [F]

**Input / Output**:
- Input: Single image or PDF (CLI: `chandra input.pdf ./output`); entire directories; supports --page-range, --batch-size (28 for vllm, 1 for hf).
- Output: `<file>.md` (Markdown), `<file>.html` (HTML), `<file>_metadata.json` (page info, token count, etc.), extracted images saved alongside. Excludes page headers/footers by default. Includes image extraction and captioning. [F]

**Inference**:
```
# Base install (vLLM backend)
pip install chandra-ocr
# With HF backend (torch + transformers)
pip install "chandra-ocr[hf]"
# CLI
chandra_vllm   # launch vLLM server in Docker
chandra input.pdf ./output                    # uses vllm
chandra input.pdf ./output --method hf
chandra ./documents ./output --method hf      # directory mode
chandra_app                                   # streamlit web app
# HuggingFace model id: datalab-to/chandra-ocr-2
```
[F]

**VRAM**: Throughput benchmark: "vLLM, 96 concurrent sequences ... 1.44 pages/sec, P95 156s" on a single NVIDIA H100 80GB. "We estimate 2 pages/s in real-world usage". [F]

**Strengths**:
- Tops external olmocr benchmark (Chandra 2 85.9±0.8, only Datalab API 86.7±0.8 is higher in the same table) [F]
- 90+ languages with internal multilingual benchmark (avg 77.8% across 43 languages, 72.7% across 90 languages vs Gemini 2.5 Flash 60.8%) [F]
- Excellent handwriting support [F]
- Form reconstruction including checkboxes [F]
- Strong tables, math, complex layouts [F]
- Image/diagram extraction with captions [F]
- Two inference modes (HF + vLLM) [F]

**Limitations**: README has no explicit "Limitations" section. Implicit: throughput is the slowest of the OCR VLMs (1.44 pages/s at concurrency 96 on H100); model is gated by modified OpenRAIL-M license. [F]

**Benchmark numbers**:
- (a) olmOCR-bench per-category:
  - Datalab API: 90.4 / 90.2 / 90.7 / 54.6 / 91.6 / 83.7 / 92.3 / 99.9 → 86.7±0.8
  - Chandra 2: 90.2 / 89.3 / 89.9 / 49.8 / 92.5 / 83.5 / 92.1 / 99.6 → 85.9±0.8
  - dots.ocr 1.5: 85.9 / 85.5 / 90.7 / 48.2 / 94.0 / 85.3 / 81.6 / 99.7 → 83.9
  - Chandra 1: 82.2 / 80.3 / 88.0 / 50.4 / 90.8 / 81.2 / 92.3 / 99.9 → 83.1±0.9
  - olmOCR 2: 82.4±1.1
  - dots.ocr: 79.1±1.0
  - olmOCR v0.3.0: 78.5±1.1
  - Datalab Marker v1.10.0: 76.5±1.0
  - Deepseek OCR: 75.4±1.0
  - Mistral OCR API: 72.0±1.1
  - GPT-4o (Anchored): 69.9±1.1
  - Qwen 3 VL 8B: 64.6±1.1
  - Gemini Flash 2 (Anchored): 63.8±1.2
- (b) Multilingual 43-lang avg: Datalab API 80.4% / Chandra 2 77.8% / Chandra 1 69.4% / Gemini 2.5 Flash 67.6% / GPT-5 Mini 60.5%
- (c) Throughput: H100 80GB vLLM @ 96 concurrent = 1.44 pages/s, 60s avg latency, 156s P95, 0% failure [F]

**file_path:line citations**:
- README.md "Chandra OCR 2" title
- README.md "Features"
- README.md "Quickstart" (`pip install chandra-ocr` + `chandra_vllm` + `chandra input.pdf ./output`)
- README.md "Commercial usage" (modified OpenRAIL-M with $2M startup clause)
- README.md "Benchmark table" (12-row table with overall ±0.8)
- README.md "Throughput" (H100 80GB vLLM 1.44 pages/s)
- README.md "Credits" (Qwen 3.5 base, VLLM, olmocr, Huggingface Transformers)
- LICENSE (Apache-2.0 code) + MODEL_LICENSE (modified OpenRAIL-M)

**Notes**: "Chandra-OCR-v1" is the original (Oct 2025); Chandra 2 (Mar 2026) supersedes it. Both come from datalab-to/chandra. Model id `datalab-to/chandra-ocr-2`. The modified-OpenRAIL-M is a commercial gate. [F]

---

## DeepSeek-OCR (v1) / DeepSeek-OCR-2 (v2, Visual Causal Flow)

URL: https://github.com/deepseek-ai/DeepSeek-OCR (v1); also https://github.com/deepseek-ai/DeepSeek-OCR-2 (v2, Jan 2026)
Fetched: 2026-06-14

**LICENSE**: MIT (DeepSeek-OCR); Apache-2.0 (DeepSeek-OCR-2). [F]

**Model size**: 3B (cited in allenai/olmocr README and chandra README: "DeepSeek-OCR" 3B. Chandra bench shows "Deepseek OCR" 75.4±1.0; DeepSeek-OCR-2 not in their table.) [F]

**Architecture**: "DeepSeek-OCR: Contexts Optical Compression" — investigate role of vision encoders from LLM-centric viewpoint. Native resolution modes: Tiny 512×512 (64 vision tokens), Small 640×640 (100 tokens), Base 1024×1024 (256 tokens), Large 1280×1280 (400 tokens). Dynamic Gundam mode: n×640×640 + 1×1024×1024. (README "Support-Modes"). DeepSeek-OCR-2 ("Visual Causal Flow") dynamic Default mode: (0-6)×768×768 + 1×1024×1024 = (0-6)×144 + 256 visual tokens. [F]

**Input / Output**:
- Input: Image (`run_dpsk_ocr_image.py`), PDF (`run_dpsk_ocr_pdf.py`, concurrency ~2500 tokens/s on A100-40G per README), batch eval (`run_dpsk_ocr_eval_batch.py`).
- Output: Prompts control output format:
  - `<image>\n<|grounding|>Convert the document to markdown.` (document OCR with grounding)
  - `<image>\n<|grounding|>OCR this image.` (other image)
  - `<image>\nFree OCR.` (no layouts)
  - `<image>\nParse the figure.` (figures in document)
  - `<image>\nDescribe this image in detail.` (general)
  - `<image>\nLocate <|ref|>xxxx<|/ref|> in the image.` (rec)
  - `先天下之忧而忧` (non-English examples supported) [F]

**Inference**:
```
# Environment: cuda11.8 + torch2.6.0
git clone https://github.com/deepseek-ai/DeepSeek-OCR.git
conda create -n deepseek-ocr python=3.12.9 -y && conda activate deepseek-ocr
pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu118
pip install vllm-0.8.5+cu118-cp38-abi3-manylinux1_x86_64.whl
pip install -r requirements.txt
pip install flash-attn==2.7.3 --no-build-isolation
# vLLM (upstream-supported since 2025/10/23):
uv venv && source .venv/bin/activate
uv pip install -U vllm --pre --extra-index-url https://wheels.vllm.ai/nightly
from vllm import LLM, SamplingParams
from vllm.model_executor.models.deepseek_ocr import NGramPerReqLogitsProcessor
llm = LLM(model="deepseek-ai/DeepSeek-OCR", enable_prefix_caching=False,
          mm_processor_cache_gb=0, logits_processors=[NGramPerReqLogitsProcessor])
# Transformers:
from transformers import AutoModel, AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained("deepseek-ai/DeepSeek-OCR", trust_remote_code=True)
model = AutoModel.from_pretrained("deepseek-ai/DeepSeek-OCR", _attn_implementation="flash_attention_2",
    trust_remote_code=True, use_safetensors=True).eval().cuda().to(torch.bfloat16)
res = model.infer(tokenizer, prompt="<image>\n<|grounding|>Convert the document to markdown. ",
    image_file='your_image.jpg', output_path='your/output/dir',
    base_size=1024, image_size=640, crop_mode=True, save_results=True, test_compress=True)
```
[F]

**VRAM**: A100-40G demonstrated. CUDA 11.8 + Torch 2.6.0 base. flash-attn 2.7.3. vLLM 0.8.5 wheel required for the bundled scripts. Upstream vLLM 0.11+ supports natively. [F]

**Strengths** (verbatim from README):
- Investigates vision encoders from LLM-centric viewpoint (contexts optical compression) [F]
- Multiple native resolutions (Tiny/Small/Base/Large) + dynamic Gundam [F]
- Upstream vLLM support (since 2025/10/23) [F]
- Document/figure/grounded/free/general OCR in one model [F]

**Limitations**: README has no explicit "Limitations" section. Implicit: needs A100-40G-class GPU; 7 commits total in main repo (Oct 2025); Chandra bench gives 75.4±1.0 on olmOCR-bench, lower than top models. [F]

**Benchmark numbers**: No benchmark numbers in README. External:
- olmOCR-bench: 75.7±1.0 (per allenai/olmocr README) / 75.4±1.0 (per datalab-to/chandra README) [F]
- Per-categories: ArXiv 77.2, OldScansMath 73.6, Tables 80.2, OldScans 33.3, H/F 96.1, MultiCol 66.4, LongTiny 79.4, Base 99.8 [F]
- rednote-hilab/dots.ocr README OmniDocBench v1.5: TextEdit 0.073, ReadOrderEdit 0.086 (size 3B) [F]

**file_path:line citations**:
- README.md "Release" (2025/10/20 release, 2025/10/23 vLLM upstream, 2026/01/27 DeepSeek-OCR2)
- README.md "Install" (cuda11.8+torch2.6.0, vllm-0.8.5)
- README.md "vLLM-Inference" (LLM() + NGramPerReqLogitsProcessor sample)
- README.md "Transformers-Inference" (model.infer call)
- README.md "Support-Modes" (resolution modes + vision token counts)
- README.md "Prompts examples"
- README.md "Citation" (arxiv 2510.18234)
- LICENSE (MIT)

**Notes**: Repo has only 7 commits at the README snapshot. Author Haoran Wei — same person as GOT-OCR2.0. Acknowledgement section thanks Vary, GOT-OCR2.0, MinerU, PaddleOCR, OneChart, Slow Perception. Two separate repos: deepseek-ai/DeepSeek-OCR (v1) and deepseek-ai/DeepSeek-OCR-2 (v2 "Visual Causal Flow", Jan 2026). [F]

---

## NVIDIA Nemotron Parse 1.1 (paper) / Nemotron-Parse (NIM)

PRIMARY URL: https://arxiv.org/abs/2511.20478; build.nvidia.com/nvidia/nemotron-parse
Fetched: 2026-06-14

**LICENSE**: Hugging Face weights publicly released + NIM container. Tokenizer CC-BY-4.0; model NVIDIA Community Model License. [F]

**Model size**: 885M total (256M language decoder), encoder-decoder. Plus Nemotron-Parse-1.1-TC (token-compressed variant) with 20% speedup. [F]

**Release date**: arXiv submitted 2025-11-25. [F]

**API shape**: NVIDIA NIM hosted endpoint (build.nvidia.com/nvidia/nemotron-parse), REST OpenAI-style chat completions for the predecessor; HF weights downloadable. NIM API Reference: https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-parse. [F]

**Run command**: NIM (cloud): curl on build.nvidia.com/nvidia/nemotron-parse playground; local: pull NIM container and standard `from_pretrained` on HF; TF32 / bfloat16 typical. [F]

**VRAM / hardware**: Not stated in arXiv abstract; 885M params fits single GPU (commonly A100/H100 in NVIDIA evaluation). [F]

**Input / Output**:
- Input: Document/page image (jpg/jpeg/png). Tasks: general OCR, markdown formatting, structured table parsing, text extraction from pictures/charts/diagrams, bounding boxes with semantic classes. English only.
- Output: Text + bounding boxes of text segments with semantic classes. Per NIM card (1.0 lineage): "Cutting-edge vision-language model exceling in retrieving text and metadata from images." Tags: document parsing, text and table extraction. [F]

**Strengths** (verbatim, arXiv abstract):
- "improved capabilities across general OCR, markdown formatting, structured table parsing, and text extraction from pictures, charts, and diagrams" [F]
- "supports a longer output sequence length for visually dense documents" [F]
- "extracts bounding boxes of text segments, as well as corresponding semantic classes" [F]
- "competitive accuracy on public benchmarks making it a strong lightweight OCR solution" [F]
- "20% speed improvement with minimal quality degradation" for TC variant [F]

**Limitations**: Not enumerated in arXiv abstract; English-only per build.nvidia.com labels. [F]

**Benchmark numbers**: "competitive accuracy on public benchmarks" — no per-benchmark numbers given in abstract. Full numbers in arXiv PDF body. [F]

**file_path:line citations**: Not applicable (NIM Hugging Face + NIM container; no GitHub source repo cited in abstract). [F]

**Notes**: Real product name is "Nemotron Parse 1.1" (paper) / "nemotron-parse" (NIM). Predecessor was "Nemoretriever-Parse-1.0". Trained on subset of broader Nemotron-VLM-v2 dataset. [F]

---

## NVIDIA NeMo Retriever (NIM stack)

PRIMARY URL: https://developer.nvidia.com/nemo-retriever
Fetched: 2026-06-14

**LICENSE**: NIM microservices are commercial NVIDIA; nv-ingest library is open source. [F]

**Components**: Stack of NIM microservices: nemoretriever-page-elements-v2, nemoretriever-table-structure-v1, nemoretriever-graphic-elements-v1, nemoretriever-page-elements-v1, nv-yolox-structured-image-v1; plus PaddleOCR; plus llava-onevision related components; plus llama-3.2-nv-embedqa-1b-v2 (embedding) and Nemotron reranking models. [F]

**Release date**: NIM extraction/embedding/reranking catalog; "25.6.3" release referenced in nv-ingest link. [F]

**API shape**: NeMo Retriever Library (nv-ingest open source) + NVIDIA NIM endpoints (OpenAI-style). Self-hostable as Docker container. [F]

**Run command**: nv-ingest CLI: `nv-ingest-cli` per repo. NIM: docker run nvidia/nemoretriever-*-nim:*. Reference: https://docs.nvidia.com/nemo/retriever/extraction/overview/. [F]

**VRAM / hardware**: 1xH100 SXM stated for benchmark numbers. [F]

**Input / Output**:
- Input: PDF / image; extracts text, tables, charts, graphics, infographics. Supports "text, charts, tables, and infographics."
- Output: Structured JSON chunks, embeddings, reranked results, deduplicated content. Multilingual. [F]

**Strengths** (verbatim):
- "50% Fewer Incorrect Answers" (Recall@5 vs open-source alternative) [F]
- "3X Higher Embedding Throughput" (llama-3.2-nv-embedqa-1b-v2 vs FP16) [F]
- "15X Higher Multimodal Data Extraction Throughput" (vs open-source alternative) [F]
- "35x Improved Data Storage Efficiency" (long-context embeddings) [F]

**Limitations**: Cloud pay-per-use; local deployment needs recent GPU + NIM licensing. [F]

**Benchmark numbers**: Recall@5, MTEB leaderboard, ViDoRe V3 (ColEmbed v2 model tops it). "50% fewer incorrect answers" 1xH100, 512 token passage, batch 64, 5 concurrent clients. [F]

**file_path:line citations**:
- https://github.com/NVIDIA/nv-ingest (release/25.6.3/docs/docs/index.md linked from page)
- https://github.com/NVIDIA/skills/tree/main/skills/nemo-retriever

**Notes**: NeMo Retriever is the platform/stack, not a single model. The OCR/extraction portion is composed of multiple NIM microservices. [A]

---

## NVIDIA build.nvidia.com models catalog

PRIMARY URL: https://build.nvidia.com/models
Fetched: 2026-06-14

**Catalog**: 139 models. Use Case: Image-to-Text: 10 entries (June 2026). Free Endpoint: 77; Partner Endpoint: 43; Download Available: 105. Publishers: NVIDIA 74, Meta 11, Google 6, Mistral AI 6, Qwen 5. Container GPUs: B200 (22), H100 80GB HBM3 (22), H200 (20), L40S (18), A100 SXM4 80GB (16). [F]

**License**: Varies per model (NVIDIA Community Model License common for NVIDIA NIM models). [F]

**API shape**: NVIDIA NIM OpenAI-compatible REST. Free endpoints (limited) + paid partner endpoints + downloadable NIM containers. [F]

**VRAM / hardware**: NIM containers published for B200, H100 80GB HBM3, H200, L40S, A100 SXM4 80GB. [F]

**Notes**: Direct catalog navigation: Use Case → Image-to-Text lists 10. nemotron-parse is one of them; tag is "document parsing", "supported language - english", "text and table extraction". [F]

---

## Meta Nougat

URL: https://github.com/facebookresearch/nougat
Fetched: 2026-06-14

**LICENSE**: Codebase MIT; model weights CC-BY-NC (non-commercial) — stated explicitly in README "License" section. [F]

**Model size**: 0.1.0-small (default), 0.1.0-base. Both are Donut-style encoder-decoder transformers; exact params not stated on README. [F]

**Release date**: arXiv 2023-08; latest release tag 0.1.0-base on GitHub 2023-08-22. Repo has 78 commits, 10k stars. [F]

**API shape**: CLI + Python API. Optional FastAPI server via `nougat_api` (POST http://127.0.0.1:8503/predict/, multipart upload). Returns JSON with markdown string. Supports start/stop page params. [F]

**Inference**:
```
pip install nougat-ocr
nougat path/to/file.pdf -o output_directory
nougat path/to/file.pdf -o output_directory -m 0.1.0-base
# API server:
pip install "nougat-ocr[api]"
nougat_api
curl -X POST 'http://127.0.0.1:8503/predict/' -H 'accept: application/json' -H 'Content-Type: multipart/form-data' -F 'file=@<PDFFILE.pdf>;type=application/pdf'
```
[F]

**VRAM / hardware**: Not stated. CPU supported; "if you want to utilize a GPU, make sure you first install the correct PyTorch version" (Windows note in README). [F]

**Input / Output**:
- Input: PDF files (path or directory of paths). Output is `.mmd` (Mathpix Markdown compatible) per PDF.
- Output: `.mmd` (Mathpix-flavored Markdown) — "the lightweight markup language, mostly compatible with Mathpix Markdown" with LaTeX tables and equations. [F]

**Strengths** (verbatim): "the academic document PDF parser that understands LaTeX math and tables"; built on Donut. [F]

**Limitations** (verbatim from FAQ):
- "Nougat was trained on scientific papers found on arXiv and PMC. ... Nougat works best with English papers, other Latin-based languages might work. **Chinese, Russian, Japanese etc. will not work**." [F]
- "If you experience a lot of [MISSING_PAGE] responses, try to run with the --no-skipping flag" [F]

**Benchmark numbers**: Not in README; cites paper arXiv 2308.13418. [F]

**file_path:line citations**: github.com/facebookresearch/nougat: README.md (Install/Get prediction for a PDF sections), predict.py, app.py, nougat/model.py. [F]

**Notes**: Nougat is the academic-paper-only OCR-to-Markdown baseline. Built on Donut. The README explicitly says "Nougat was trained on scientific papers found on arXiv and PMC" — it is not a general document OCR. [F]

---

## Meta Llama 3.2 Vision

PRIMARY URL: https://github.com/meta-llama/llama-models (repo README table)
Fetched: 2026-06-14

**Model size / variants**: 11B, 90B (per README "Llama Models" table row "Llama 3.2-Vision" 9/25/2024). Text-only Llama 3.2 1B and 3B also released same day. [F]

**Release date**: 2024-09-25 per README table. [F]

**LICENSE**: Llama 3.2 community license (linked from /meta-llama/llama-models/blob/main/models/llama3_2/LICENSE). Acceptable Use Policy linked. "The model weights are licensed for researchers and commercial entities". [F]

**API shape**: Download via `llama-model` CLI; run via `torchrun` on llama-models scripts. Hugging Face transformers via `Llama4ForConditionalGeneration` (note: class name Llama4 — typo in README snippet). Note: actual HF class for Llama 3.2-Vision is `MllamaForConditionalGeneration` (not stated in fetched README). [F]

**Inference**:
```
pip install llama-models
pip install .[torch]
llama-model list
llama-model download --source meta --model-id CHOSEN_MODEL_ID
```
[F]

**VRAM / hardware**: Not stated for 11B/90B specifically. README notes "the Llama4 series of models require at least 4 GPUs to run inference at full (bf16) precision" (this is for Llama 4, not 3.2-Vision). [F]

**Input / Output**:
- Input: Image + text (chat). "Image-Text-to-Text" pipeline tag at HF.
- Output: Generated text response (chat completions style). [F]

**Strengths**: README says 128K context length, TikToken-based tokenizer. [F]

**Limitations**: 700M-download cap per 24h on direct Meta URL. [F]

**Benchmark numbers**: Not in README; Vision model card linked at /meta-llama/llama-models/blob/main/models/llama3_2/MODEL_CARD_VISION.md. [F]

**file_path:line citations**: meta-llama/llama-models: README.md "Llama Models" table; MODEL_CARD_VISION.md for vision-specific details. [F]

**Notes**: The Meta-issued llama-models card URL (https://llama.meta.com/docs/model-cards-and-prompt-formats/llama3_2 and .../llama3_2_vision) both returned HTTP 400. HF model card for meta-llama/Llama-3.2-11B-Vision-Instruct not fetched. 11B/90B vision-instruct variants released 9/25/2024. [F]

---

## Meta SAM 2.1

PRIMARY URL: https://github.com/facebookresearch/sam2
Fetched: 2026-06-14

**LICENSE**: Apache 2.0 (model checkpoints, demo code, training code); third-party code under SIL OFL 1.1 (Inter, Noto Color Emoji) and BSD-3-Clause (cc_torch). [F]

**Model size**: 4 sizes in millions of params: tiny 38.9M, small 46M, base_plus 80.8M, large 224.4M. [F]

**Release date**: SAM 2.1 checkpoints 2024-09-29 (per README "Model Description" section). SAM 2 release 2024-07-29. Paper arXiv 2408.00714. [F]

**API shape**: Python pip install `SAM-2`. PyTorch. `SAM2ImagePredictor` and `SAM2VideoPredictor`. Also HF via `from_pretrained("facebook/sam2-hiera-large")`. [F]

**Inference**:
```
git clone https://github.com/facebookresearch/sam2.git && cd sam2
pip install -e .
# Checkpoints:
cd checkpoints && ./download_ckpts.sh && cd ..
# Image:
import torch
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor
checkpoint = "./checkpoints/sam2.1_hiera_large.pt"
model_cfg = "configs/sam2.1/sam2.1_hiera_l.yaml"
predictor = SAM2ImagePredictor(build_sam2(model_cfg, checkpoint))
with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
    predictor.set_image(<your_image>)
    masks, _, _ = predictor.predict(<input_prompts>)
```
[F]

**VRAM / hardware**: Speed benchmarked on A100 with torch 2.5.1, CUDA 12.4. Requires `torch>=2.5.1` and `torchvision>=0.20.1`, `python>=3.10`. CUDA kernel compilation needed (requires nvcc); installation "strongly recommended to use WSL with Ubuntu" on Windows. [F]

**Input / Output**:
- Input: Image (PNG/JPG) for image predictor; video (image sequence) for video predictor. Prompts: point clicks, box.
- Output: Segmentation masks (binary or multi-object), per-frame masklets for video. Supports `vos_optimized=True` torch.compile for video speedup. [F]

**Strengths** (verbatim):
- "foundation model towards solving promptable visual segmentation in images and videos" [F]
- "model design is a simple transformer architecture with streaming memory for real-time video processing" [F]
- supports `vos_optimized` torch.compile [F]
- "per-object inference, allowing us to relax the assumption of prompting for multi-object tracking" [F]

**Limitations**: Requires CUDA kernel compile at install; "Failed to build the SAM 2 CUDA extension" warning can be ignored but "some post-processing functionality may be limited". [F]

**Benchmark numbers** (SAM 2.1, A100, torch 2.5.1, cuda 12.4):
- SAM 2.1 large 224.4M, 39.5 FPS, SA-V test J&F 79.5, MOSE val 74.6, LVOS v2 80.6
- SAM 2.1 base_plus 80.8M, 64.1 FPS, SA-V 78.2, MOSE 73.7, LVOS v2 78.2
- SAM 2.1 small 46M, 84.8 FPS, SA-V 76.6, MOSE 73.5, LVOS v2 78.3
- SAM 2.1 tiny 38.9M, 91.2 FPS, SA-V 76.5, MOSE 71.8, LVOS v2 77.3 [F]

**file_path:line citations**: facebookresearch/sam2: README.md "Model Description" tables. configs/sam2.1/sam2.1_hiera_*.yaml; checkpoints/*.pt [F]

**Notes**: SAM 2.1 is a segmentation model, not an OCR/VLM; useful as a layout/region segmenter upstream of OCR. Apache 2.0 licensed — fully open. [A]

---

## Mistral Pixtral

PRIMARY URL: https://huggingface.co/mistralai/Pixtral-12B-2409 (model card; GitHub https://github.com/mistralai/pixtral 404s; docs.mistral.ai URL also 404)
Fetched: 2026-06-14

**LICENSE**: Apache 2.0 (HF license tag "apache-2.0"). [F]

**Model size**: 12B parameter multimodal decoder + 400M parameter vision encoder. Base: mistralai/Pixtral-12B-Base-2409. Instruct: mistralai/Pixtral-12B-2409. [F]

**Release date**: 2024-09 (Pixtral-12B-2409 dated). [F]

**API shape**: vLLM (OpenAI-compatible) and mistral-inference. Docker image `vllm/vllm-openai:latest`. CLI `mistral-chat` from mistral_inference. [F]

**Inference**:
```
# vLLM
pip install --upgrade vllm          # vLLM >= v0.6.2
pip install --upgrade mistral_common # mistral_common >= 1.4.4
vllm serve mistralai/Pixtral-12B-2409 --tokenizer_mode mistral --limit_mm_per_prompt 'image=4'
# mistral-inference
pip install mistral_inference --upgrade   # >= 1.4.1
from huggingface_hub import snapshot_download
snapshot_download(repo_id="mistralai/Pixtral-12B-2409",
                  allow_patterns=["params.json","consolidated.safetensors","tekken.json"],
                  local_dir=mistral_models_path)
mistral-chat $HOME/mistral_models/Pixtral --instruct --max_tokens 256 --temperature 0.35
```
[F]

**VRAM / hardware**: Not stated directly on the model card. "Lower max_num_seqs or max_model_len on low-VRAM GPUs." Default `max_model_len=32768` in advanced example. [F]

**Input / Output**:
- Input: Variable-size images (1 to many per message). Text prompts. Sequence length 128k.
- Output: Generated text. Multi-turn chat. [F]

**Strengths** (verbatim from "Key features"):
- "Natively multimodal, trained with interleaved image and text data" [F]
- "12B parameter Multimodal Decoder + 400M parameter Vision Encoder" [F]
- "Supports variable image sizes" [F]
- "Leading performance in its weight class on multimodal tasks" [F]
- "Maintains state-of-the-art performance on text-only benchmarks" [F]

**Limitations** (verbatim from "Limitations"):
- "The Pixtral model does not have any moderation mechanisms. We're looking forward to engaging with the community on ways to make the model finely respect guardrails, allowing for deployment in environments requiring moderated outputs." [F]

**Benchmark numbers** (verbatim from model card tables):
- Multimodal: MMMU (CoT) 52.5; Mathvista (CoT) 58.0; ChartQA (CoT) 81.8; DocVQA (ANLS) 90.7; VQAv2 78.6. [F]
- Text: MMLU 5-shot 69.2; Math Pass@1 48.1; HumanEval Pass@1 72.0. [F]
- vs closed: Pixtral DocVQA 90.7 vs Gemini-1.5 Flash 8B 79.5 vs Claude-3 Haiku 74.6 vs GPT-4o 88.9. [F]

**file_path:line citations**: No repo at github.com/mistralai/pixtral. Code at github.com/mistralai/mistral-inference and vllm-project/vllm (examples/offline_inference_pixtral.py, tests/models/test_pixtral.py). [F]

**Notes**: GitHub https://github.com/mistralai/pixtral returns 404; canonical Mistral Pixtral lives on HF (mistralai/Pixtral-12B-2409) and is referenced from mistral-inference. [F]

---

## Google PaliGemma 1 (3B)

PRIMARY URL: https://huggingface.co/google/paligemma-3b-pt-224
Fetched: 2026-06-14

**LICENSE**: Gemma license (custom, non-commercial terms; requires HF click-through). "License: gemma" tag on HF. [F]

**Model size**: 3B params (Gemma-2B text decoder + SigLIP-So400m/14 vision encoder). Variants on HF include pt-224, pt-448, pt-896 (pretrained) and mix-224, mix-448 (fine-tuned). Also base-chinese. [F]

**Release date**: Paper 2407.07726 (2024-07-10). HF repos mirrored the same week. [F]

**API shape**: transformers (PaliGemmaProcessor, PaliGemmaForConditionalGeneration); vLLM, SGLang, bitsandbytes 4/8-bit. [F]

**Inference** (verbatim from HF card "Use in Transformers"):
```
from transformers import AutoProcessor, PaliGemmaForConditionalGeneration
model = PaliGemmaForConditionalGeneration.from_pretrained("google/paligemma-3b-mix-224").eval()
processor = AutoProcessor.from_pretrained("google/paligemma-3b-mix-224")
prompt = "caption es"  # task prefix
model_inputs = processor(text=prompt, images=image, return_tensors="pt")
with torch.inference_mode():
    generation = model.generate(**model_inputs, max_new_tokens=100, do_sample=False)
# vLLM:
vllm serve "google/paligemma-3b-pt-224"
```
[F]

**VRAM / hardware**: Trained on TPUv5e. Inference: bfloat16 revisions provided. CPU float32 works per HF card. [F]

**Input / Output**:
- Input: Image (default 224x224, optionally 448 or 896) + text prompt with task prefix ("caption es", "detect", "segment", "answer en", etc.).
- Output: Generated text (caption, answer, bbox coords, or segmentation codewords). "It takes both image and text as input and generates text as output, supporting multiple languages." [F]

**Strengths** (verbatim from card "Model summary"):
- "versatile and lightweight vision-language model (VLM) inspired by PaLI-3 and based on open components such as the SigLIP vision model and the Gemma language model" [F]
- "class-leading fine-tune performance on a wide range of vision-language tasks such as image and short video caption, visual question answering, text reading, object detection and object segmentation" [F]

**Limitations** (verbatim from "Limitations"):
- "VLMs are better at tasks that can be framed with clear prompts and instructions. Open-ended or highly complex tasks might be challenging." [F]
- "PaliGemma was designed first and foremost to serve as a general pre-trained model for transfer to specialized tasks. Hence, its 'out of the box' or 'zero-shot' performance might lag behind models designed specifically for that." [F]
- "PaliGemma is not a multi-turn chatbot. It is designed for a single round of image and text input." [F]

**Benchmark numbers** (pt-224 / pt-448 / pt-896, fine-tuned on each task):
- DocVQA ANLS: 43.74 / 78.02 / 84.77 [F]
- ChartQA mean (human+aug): 57.08 / 71.36 [F]
- TextVQA: 55.47 / 73.15 / 76.48 [F]
- InfoVQA: 28.46 / 40.47 / 47.75 [F]
- ST-VQA ANLS: 63.29 / 81.82 / 84.40 [F]
- VQAv2 std: 83.19 / 85.64 [F]
- POPE: 87.80 / 85.87 / 84.27 (random/popular/adversarial at pt-448: 88.23 / 86.77 / 85.90) [F]
- AI2D: 72.12 / 73.28 [F]
- ScienceQA img: 95.39 / 95.93 [F]
- COCO captions CIDEr: 141.92 / 144.60 [F]
- NoCaps: 121.72 / 123.58 [F]

**file_path:line citations**: No dedicated GitHub repo; code at github.com/google-research/big_vision (JAX/Flax, training + inference) and big_vision/paligemma task config. [F]

**Notes**: This is PaliGemma 1 (3B). 404 for github.com/google-research/paligemma; canonical training/inference is in big_vision. License is the Gemma terms (not Apache/MIT). [F]

---

## Google PaliGemma 2 (3B, 10B, 28B)

PRIMARY URL: https://huggingface.co/google/paligemma2-3b-pt-224
Fetched: 2026-06-14

**LICENSE**: Gemma license (custom, requires HF click-through; "License: gemma" tag). [F]

**Model size**: 3B, 10B, 28B params (Gemma 2 2B/9B/27B text decoder + SigLIP-So400m/14 vision encoder). Resolutions: 224, 448. Variants: pt-224, pt-448 (pretrained) and mix variants fine-tuned. [F]

**Release date**: Paper arXiv 2412.03555 submitted 2024-12-04. HF model cards published Mar 2025. [F]

**API shape**: Same as PaliGemma 1 (transformers PaliGemmaProcessor, PaliGemmaForConditionalGeneration). vLLM, SGLang. [F]

**Inference** (HF card "Use in Transformers"):
```
from transformers import PaliGemmaProcessor, PaliGemmaForConditionalGeneration
from transformers.image_utils import load_image
import torch
model_id = "google/paligemma2-3b-pt-224"
image = load_image("https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/transformers/tasks/car.jpg")
model = PaliGemmaForConditionalGeneration.from_pretrained(model_id, torch_dtype=torch.bfloat16, device_map="auto").eval()
processor = PaliGemmaProcessor.from_pretrained(model_id)
prompt = ""  # blank for pretrained
model_inputs = processor(text=prompt, images=image, return_tensors="pt").to(torch.bfloat16).to(model.device)
with torch.inference_mode():
    generation = model.generate(**model_inputs, max_new_tokens=100, do_sample=False)
# vLLM:
vllm serve "google/paligemma2-3b-pt-224"
```
[F]

**VRAM / hardware**: Trained on TPUv5e (per HF card "Hardware"). bf16 inference. [F]

**Input / Output**:
- Input: Image + text string. Image sizes 224x224 or 448x448 in standard variants. Supports multiple languages.
- Output: Generated text: caption, VQA answer, bbox coords, or segmentation codewords. [F]

**Strengths** (verbatim):
- "PaliGemma 2 is an update of the PaliGemma vision-language model (VLM) which incorporates the capabilities of the Gemma 2 models. ... designed for class-leading fine-tune performance on a wide range of vision-language tasks such as image and short video caption, visual question answering, text reading, object detection and object segmentation." [F]

**Limitations** (verbatim, same as PaliGemma 1):
- "VLMs are better at tasks that can be framed with clear prompts..." [F]
- "PaliGemma 2 was designed first and foremost to serve as a general pre-trained model for fine-tuning to specialized tasks. Hence, its 'out of the box' or 'zero-shot' performance might lag behind..." [F]
- "PaliGemma 2 is not a multi-turn chatbot. It is designed for a single round of image and text input." [F]

**Benchmark numbers** (PaliGemma 2 results, fine-tuned, 224-3B / 224-10B / 224-28B / 448-3B / 448-10B / 448-28B):
- DocVQA val: 39.9 / 43.9 / 44.9 / 73.6 / 76.6 / 76.1 [F]
- ChartQA aug: 74.4 / 74.2 / 68.9 / 89.2 / 90.1 / 85.1 [F]
- ChartQA human: 42.0 / 48.4 / 46.8 / 54.0 / 66.4 / 61.3 [F]
- TextVQA val: 59.6 / 64.0 / 64.7 / 75.2 / 76.6 / 76.2 [F]
- InfoVQA val: 25.2 / 33.6 / 36.4 / 37.5 / 47.8 / 46.7 [F]
- ST-VQA val: 61.9 / 64.3 / 65.1 / 80.5 / 82.0 / 81.8 [F]
- AI2D: 74.7 / 83.1 / 83.2 / 76.0 / 84.4 / 84.6 [F]
- OCR-VQA: 73.4 / 74.7 / 75.3 / 75.7 / 76.3 / 76.6 [F]
- VQAv2 minival: 83.0 / 84.3 / 84.5 / 84.8 / 85.8 / 85.8 [F]
- ScienceQA: 96.1 / 98.2 / 98.2 / 96.2 / 98.5 / 98.6 [F]
- ICDAR'15 Incidental F1 (3B): 75.9; Total-Text F1 (3B): 74.17; FinTabNet TEDS (3B): 98.94; PubTabNet TEDS (3B): 97.31 [F]

**file_path:line citations**: No dedicated GitHub repo; code in github.com/google-research/big_vision (JAX/Flax). [F]

**Notes**: License "gemma" (Gemma 2 terms). No public fine-tuning recipe beyond the big_vision configs. [F]

---

## Google Gemini 2.x / Document AI / Gemini layout parser

PRIMARY URLs:
- https://ai.google.dev/gemini-api/docs/document-processing (returned transport error on fetch; corroborating sources: cloud.google.com, papers)
- https://docs.cloud.google.com/document-ai/docs/processors-list
- https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/2-5-pro
Fetched: 2026-06-14

**Gemini models (from docs)**: Gemini 2.5 Pro, Gemini 2.5 Flash, Gemini 3 Pro, Gemini 3 Flash (confirmed in Document AI Custom Extractor processor versions). Per CSDN write-up, "Gemini 3.1 Pro is Google DeepMind 2025 年底发布的旗舰大语言模型,采用 MoE 混合专家架构". [F + blog]

**Document AI OCR Processor (Enterprise Document OCR)**: Type in API: `OCR_PROCESSOR`. Versions: `pretrained-ocr-v1.2-2022-11-10` (GA, frozen), `pretrained-ocr-v2.0-2023-06-02` (GA, production-ready with all OCR add-ons), `pretrained-ocr-v2.1-2024-08-07` (GA, "better printed text recognition, more precise checkbox detection and more accurate reading order"), `pretrained-ocr-v2.1.1-2025-01-31` (Public Preview). 200+ languages. Max 15 pages online sync, 500 pages batch, 30 pages imageless online. Supports: text (printed + handwritten), QA scoring, 200+ languages. [F]

**Form Parser (Document AI)**: Type in API: `FORM_PARSER_PROCESSOR`. Versions: `pretrained-form-parser-v1.0-2020-09-23` (legacy), `pretrained-form-parser-v2.0-2022-11-10` (GA recommended, 200+ languages, generic entities email/phone/url/date_time/address/person/organization/quantity/price/id/page_number), `pretrained-form-parser-v2.1-2023-06-26` (RC, native text from digital PDFs). [F]

**Layout Parser (Document AI)**: Type in API: `LAYOUT_PARSER_PROCESSOR`. "Extracts document content elements (text, tables, and lists) and creates context-aware chunks." Supports PDF, HTML, DOCX, PPTX, XLSX/XLSM files. Per sibling doc "Process documents with Gemini layout parser" (cloud.google.com/document-ai/docs/layout-parse-chunk), the "Gemini layout parser" is the latest iteration. [F]

**Custom Extractor (Document AI, generative AI path)**: Type in API: `CUSTOM_EXTRACTION_PROCESSOR`. Versions:
- `pretrained-foundation-model-v1.5-2025-05-05` (GA, "Production-ready candidate powered by Gemini 2.5 Flash LLM")
- `pretrained-foundation-model-v1.5-pro-2025-06-20` (GA, "Production-ready model powered by the Gemini 2.5 Pro LLM. Supports a quota of up to 30 pages per minute for online process requests. This model has improved quality compared to v1.5, and may have a higher latency.")
- `pretrained-foundation-model-v1.5.1-2025-08-07` (RC, Public Preview, "same features as v1.5, and has improved adaptive few-shot learning")
- `pretrained-foundation-model-v1.6-pro-2025-12-01` (RC, Public Preview, "Preview model powered by the Gemini 3 Pro LLM. Uses Vertex AI Gemini global endpoint, not compliant with Data Residency (DMZ).")
- `pretrained-foundation-model-v1.6-2026-01-13` (RC, Public Preview, "Preview model powered by the Gemini 3 Flash LLM.")
- If using generative AI for extraction: only English officially supported. Quota: 15 pages online sync, 200 pages batch. [F]

**Gemini 2.5 Pro (per docs)**: Capabilities listed in enterprise docs: "Image understanding · Video understanding · Audio understanding · Document understanding · Bounding box detection. Grounding." [F]

**Architecture** (per CSDN write-up of "Gemini 3.1 Pro", treated as blog-level only, [A]): "原生多模态融合 ... 图片信息直接进入模型内部的多模态融合层,和文本 token 在同一套 Transformer 中做注意力计算" — natively multimodal, no separate vision encoder. MoE Transformer. [A — blog only, not in official docs]

**Pricing for Gemini 2.5 Pro** (per zhiding.cn article): "每百万 Token 进/出分别 1.25/10 美元 ... 适用于 200,000 Token 的上下文长度" ($1.25/$10 per 1M input/output tokens for ≤200K context). [A — secondary source, not Google docs]

**Limitations**:
- Custom Extractor generative mode: English only officially.
- Document AI Gemini-based processors: use Vertex AI global endpoint (not DMZ-compliant).
- "Gemini 3.1 Pro 的 OCR 能力和 GPT-4o 基本持平" (CSDN blog; [A — blog]). [F]

**Benchmark numbers**: No official Gemini DocVQA/OmniDocBench numbers on docs.cloud.google.com as of fetch; third-party claims "OCR 能力和 GPT-4o 基本持平" (CSDN). [A — secondary]

**file_path:line citations**:
- docs.cloud.google.com/document-ai/docs/processors-list (full processor table)
- docs.cloud.google.com/document-ai/docs/enterprise-document-ocr
- docs.cloud.google.com/document-ai/docs/form-parser
- docs.cloud.google.com/document-ai/docs/layout-parse-chunk (Gemini layout parser)
- docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/2-5-pro (capabilities list)

**Notes**: Google does NOT publish a single open-source Document AI model. Document AI is a paid cloud service with GA and Preview model versions. [F]

---

## Microsoft Florence-2

PRIMARY URL: https://huggingface.co/microsoft/Florence-2-large
Fetched: 2026-06-14

**LICENSE**: MIT (HF license tag "mit"). [F]

**Model size**: 4 checkpoints: Florence-2-base 0.23B (pretrained on FLD-5B), Florence-2-large 0.77B (pretrained), Florence-2-base-ft 0.23B (fine-tuned on downstream tasks), Florence-2-large-ft 0.77B (fine-tuned). arXiv 2311.06242. [F]

**Release date**: 2023-11-10 (paper). HF model cards present from late 2023. [F]

**API shape**: Hugging Face transformers (AutoModelForCausalLM + AutoProcessor, trust_remote_code=True). vLLM, SGLang, Docker Model Runner. [F]

**Inference** (verbatim from HF card):
```
import torch
from transformers import AutoProcessor, AutoModelForCausalLM
device = "cuda:0" if torch.cuda.is_available() else "cpu"
torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
model = AutoModelForCausalLM.from_pretrained("microsoft/Florence-2-large", torch_dtype=torch_dtype, trust_remote_code=True).to(device)
processor = AutoProcessor.from_pretrained("microsoft/Florence-2-large", trust_remote_code=True)
prompt = "<OD>"
inputs = processor(text=prompt, images=image, return_tensors="pt").to(device, torch_dtype)
generated_ids = model.generate(input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"], max_new_tokens=4096, num_beams=3, do_sample=False)
parsed_answer = processor.post_process_generation(generated_text, task="<OD>", image_size=(image.width, image.height))
# vLLM:
vllm serve "microsoft/Florence-2-large"
# Docker:
docker model run hf.co/microsoft/Florence-2-large
```
[F]

**VRAM / hardware**: All models "trained with float16" per HF card. Tested on `cuda:0`. No specific GPU requirement stated. [F]

**Input / Output**:
- Input: Single image (PIL). Text prompt with task token: `<CAPTION>`, `<DETAILED_CAPTION>`, `<MORE_DETAILED_CAPTION>`, `<OD>` (object detection), `<DENSE_REGION_CAPTION>`, `<REGION_PROPOSAL>`, `<CAPTION_TO_PHRASE_GROUNDING>`, `<OCR>`, `<OCR_WITH_REGION>`, `<OPEN_VOCABULARY_DETECTION>`, `<REFERRING_EXPRESSION_SEGMENTATION>`, `<REGION_TO_SEGMENTATION>`, `<FLORENCE2>`.
- Output: Text response parsed by `processor.post_process_generation` into dict with `bboxes`, `quad_boxes`, `labels`, or plain text. Returns both image-grounded region predictions and OCR text. [F]

**Strengths** (verbatim): "Florence-2 is an advanced vision foundation model that uses a prompt-based approach to handle a wide range of vision and vision-language tasks. ... leverages our FLD-5B dataset, containing 5.4 billion annotations across 126 million images, to master multi-task learning. The model's sequence-to-sequence architecture enables it to excel in both zero-shot and fine-tuned settings, proving to be a competitive vision foundation model." [F]

**Limitations**: Florence-2-large repo (not -ft) card top notes: "This is a continued pretrained version of Florence-2-large model with 4k context length, only 0.1B samples are used for continue pretraining, thus it might not be trained well. In addition, OCR task has been updated with line separator ('\n'). COCO OD AP 39.8" [F]

**Benchmark numbers** (zero-shot, verbatim from HF card):
- Florence-2-large 0.77B: COCO Cap CIDEr 135.6, NoCaps CIDEr 120.8, TextCaps 72.8, COCO Det mAP 37.5 [F]
- Florence-2-large-ft 0.77B: COCO Cap Karpathy CIDEr 143.3, NoCaps 124.9, TextCaps 151.1, VQAv2 81.7, TextVQA 73.5, VizWiz 72.6 [F]
- Florence-2-large-ft: COCO Det 43.4, RefCOCO val 93.4, RefCOCO+ val 88.3, RefCOCOg val 91.2, RefCOCO RES mIoU 80.5 [F]
- Florence-2-base 0.23B: COCO Cap 133.0, NoCaps 118.7, COCO Det 34.7 [F]

**file_path:line citations**: No canonical GitHub repo. Code is shipped via `trust_remote_code=True` in the HF model repo (sample_inference.ipynb, modeling_florence2.py in the HF repo). Paper: Xiao et al. 2023, arXiv 2311.06242. [F]

**Notes**: Florence-2 is the only Florence family entry on HF; the build.nvidia.com catalog lists no Microsoft models. [F]

---

## Microsoft Florence-VL (research paper, no first-party product)

PRIMARY URL: not found at official Microsoft channels
Fetched: 2026-06-14

**Notes**: No official Microsoft repository for "Florence-VL" was discoverable. A 2025 paper "Florence-VL: Enhancing Vision-Language Models with Generative Vision Encoder and Index-Aware Generation" exists from Microsoft Research Asia but no first-party model weights or repo URL were discoverable. Treat as "no first-party product; only a research paper." [F]

---

## Microsoft Phi-3.5-vision

PRIMARY URL: https://huggingface.co/microsoft/Phi-3.5-vision-instruct
Fetched: 2026-06-14

**LICENSE**: MIT. [F]

**Model size**: 4.2B parameters (image encoder + connector + projector + Phi-3 Mini language model). [F]

**Release date**: August 2024 (per HF card "Training" section). [F]

**API shape**: transformers (AutoModelForCausalLM + AutoProcessor, trust_remote_code=True). vLLM, SGLang, Ollama, llama.cpp, LM Studio, Docker Model Runner. Also Azure AI Studio. [F]

**Inference** (HF card "Loading the model locally"):
```
pip install flash_attn==2.5.8 numpy==1.24.4 Pillow==10.3.0 Requests==2.31.0 torch==2.3.0 torchvision==0.18.0 transformers==4.43.0 accelerate==0.30.0
from transformers import AutoModelForCausalLM, AutoProcessor
model = AutoModelForCausalLM.from_pretrained("microsoft/Phi-3.5-vision-instruct", device_map="cuda", trust_remote_code=True, torch_dtype="auto", _attn_implementation='flash_attention_2')
processor = AutoProcessor.from_pretrained("microsoft/Phi-3.5-vision-instruct", trust_remote_code=True, num_crops=4)
# Prompt format: <|user|>\n<|image_1|>\n{prompt}<|end|>\n<|assistant|>\n
# vLLM:
vllm serve "microsoft/Phi-3.5-vision-instruct"
# Docker:
docker model run hf.co/microsoft/Phi-3.5-vision-instruct
```
[F]

**VRAM / hardware**: Tested on NVIDIA A100, A6000, H100 (per HF card "Hardware"). "by default, the Phi-3.5-Mini-Instruct model uses flash attention, which requires certain types of GPU hardware to run." Set _attn_implementation='eager' otherwise. V100 or earlier: set _attn_implementation="eager". [F]

**Input / Output**:
- Input: RGB image (single or multiple via <|image_N|> placeholders). Text prompt in chat format. num_crops=4 for multi-frame, num_crops=16 for single-frame recommended.
- Output: Generated text in chat format. [F]

**Strengths** (verbatim): "lightweight, state-of-the-art open multimodal model built upon datasets which include - synthetic data and filtered publicly available websites - with a focus on very high-quality, reasoning dense data both on text and vision"; "the model underwent a rigorous enhancement process, incorporating both supervised fine-tuning and direct preference optimization". [F]

**Limitations** (verbatim):
- "Quality of Service: The Phi models are trained primarily on English text. Languages other than English will experience worse performance." [F]
- "English language varieties with less representation in the training data might experience worse performance than standard American English." [F]
- "Limited Scope for Code: Majority of Phi-3 training data is based in Python..." [F]
- "models with vision capabilities may have the potential to uniquely identify individuals in images." [F]

**Benchmark numbers** (Phi-3.5-vision-instruct vs Intern-VL-2-4B / 8B, Gemini-1.5-Flash, GPT-4o-mini, Claude-3.5-Sonnet, Gemini-1.5-Pro, GPT-4o):
- MMMU val 43.0; MMBench dev-en 81.9; ScienceQA img-test 91.3; MathVista testmini 43.9; AI2D test 78.1; ChartQA test 81.8; TextVQA val 72.0; POPE test 86.1 [F]
- BLINK overall 57.0; Video-MME overall 50.8 [F]
- Context: 128K tokens; training 256 A100-80G, 6 days, 500B tokens (vision+text) [F]

**file_path:line citations**: microsoft/PhiCookBook README (table of contents) lists Phi-3.5-vision-instruct. Cookbook examples at md/04.Fine-tuning/FineTuning_Vision.md and md/02.Application/04.Vision/Phi3/phi3-vision-demo.ipynb. Phi-3 technical report arXiv 2404.14219. [F]

**Notes**: 4.2B params, MIT license, on Azure AI Studio as well. Trained July–August 2024. Cutoff date March 15, 2024. [F]

---

## Microsoft Phi-4-multimodal

PRIMARY URL: https://huggingface.co/microsoft/Phi-4-multimodal-instruct
Fetched: 2026-06-14

**LICENSE**: MIT. [F]

**Model size**: 5.6B parameters (multimodal transformer, Phi-4-Mini-Instruct as language backbone, separate vision and speech encoders/adapters). Variants: Phi-4-multimodal-instruct (text+vision+audio), ONNX export. [F]

**Release date**: February 2025 (per HF card "Model" section). Data Summary card last updated 2025-12-10. [F]

**API shape**: transformers (>= 4.48.2; AutoModelForCausalLM + AutoProcessor, trust_remote_code=True). vLLM with separate speech-lora and vision-lora. ONNX. [F]

**Inference** (HF card "Loading the model locally" + "vLLM inference"):
```
pip install flash_attn==2.7.4.post1 torch==2.6.0 transformers==4.48.2 accelerate==1.3.0 soundfile==0.13.1 pillow==11.1.0 scipy==1.15.2 torchvision==0.21.0 backoff==2.2.1 peft==0.13.2
from transformers import AutoModelForCausalLM, AutoProcessor, GenerationConfig
model = AutoModelForCausalLM.from_pretrained("microsoft/Phi-4-multimodal-instruct", device_map="cuda", torch_dtype="auto", trust_remote_code=True, _attn_implementation='flash_attention_2').cuda()
processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
# vLLM:
python -m vllm.entrypoints.openai.api_server --model 'microsoft/Phi-4-multimodal-instruct' --dtype auto --trust-remote-code --max-model-len 131072 --enable-lora --max-lora-rank 320 --lora-extra-vocab-size 0 --limit-mm-per-prompt audio=3,image=3 --max-loras 2 --lora-modules speech=<path to speech lora folder> vision=<path to vision lora folder>
```
[F]

**VRAM / hardware**: Tested on NVIDIA A100, A6000, H100. "by default, the Phi-4-multimodal-instruct model uses flash attention, which requires certain types of GPU hardware to run." V100 or earlier: _attn_implementation="eager". Training hardware per card: 512 A100-80G, 28 days, 5T tokens / 2.3M speech hours / 1.1T image-text tokens. [F]

**Input / Output**:
- Input: Text, image, audio. Vision: any RGB/gray image (jpg, jpeg, png, ppm, bmp, pgm, tif, tiff, webp); up to 64 crops during training. Multi-image up to 64 frames. Audio: any soundfile-loadable format, max 40s recommended. Chat format: `<|user|><|image_1|>Describe the image.<|end|><|assistant|>`; speech: `<|user|><|audio_1|>...<|end|><|assistant|>`; vision+speech: `<|user|><|image_1|><|audio_1|><|end|><|assistant|>`.
- Output: Generated text in response to input. Tool/function calling supported. [F]

**Strengths** (verbatim):
- "lightweight open multimodal foundation model that leverages the language, vision, and speech research and datasets used for Phi-3.5 and 4.0 models. The model processes text, image, and audio inputs, generating text outputs, and comes with 128K token context length." [F]
- "strong automatic speech recognition (ASR) and speech translation (ST) performance, surpassing expert ASR model WhisperV3 and ST models SeamlessM4T-v2-Large." [F]
- "Ranking number 1 on the Huggingface OpenASR leaderboard with word error rate 6.14% in comparison with the current best model 6.5% as of March 04, 2025." [F]
- "Being the first open-sourced model that can perform speech summarization, and the performance is close to GPT4o." [F]

**Limitations** (verbatim):
- "Quality of Service: The Phi models are trained primarily on English language content across text, speech, and visual inputs..." [F]
- "Vision: Visual processing capabilities may be influenced by cultural and geographical biases in the training data..." [F]
- "Limited Scope for Code: The majority of Phi 4 training data is based in Python..." [F]
- "Long Conversation: Phi 4 models, like other models, can in some cases generate responses that are repetitive, unhelpful, or inconsistent in very long chat sessions..." [F]
- "Inference of Sensitive Attributes: The Phi 4 models can sometimes attempt to infer sensitive attributes... from the users' voices when specifically asked to do so. Phi 4-multimodal-instruct is not designed or intended to be used as a biometric categorization system..." [F]

**Benchmark numbers** (Phi-4-multimodal-instruct vs Phi-3.5-vision-ins, Qwen 2.5-VL-3B-ins, Intern VL 2.5-4B/8B, Qwen 2.5-VL-7B-ins, Gemini 2.0 Flash Lite/Flash, Claude-3.5-Sonnet, GPT-4o-2024-11-20):
- MMMU 55.1; MMBench dev-en 86.7; MMMU-Pro std/vision 38.5; MathVista testmini 62.4; ScienceQA Visual 97.5; InterGPS 48.6; AI2D 82.3; ChartQA 81.4; DocVQA 93.2; InfoVQA 72.7; TextVQA val 75.6; OCR Bench 84.4; POPE 85.6; BLINK 61.3; Video MME 16 frames 55.0; Average 72.0 [F]
- Vision-Speech (s_AI2D 68.9, s_ChartQA 69.0, s_DocVQA 87.3, s_InfoVQA 63.7, Average 72.2) [F]
- Speech (vs WhisperV3 / SeamlessM4T-v2-Large): ASR WER 6.14% on HF OpenASR leaderboard [F]

**file_path:line citations**: microsoft/PhiCookBook README (table of contents) lists Phi-4-multimodal-instruct. Cookbook examples at md/02.Application/04.Vision/Phi4/CreateFrontend and md/04.HOL/dotnet/src/LabsPhi4-MultiModal-01Images. Technical report arXiv 2503.01743. [F]

**Notes**: 5.6B params, MIT, training Dec 2024–Jan 2025, data cutoff June 2024. First Microsoft multimodal model that natively handles text+vision+speech in one network (no two-stage ASR+LLM pipeline). [F]

---

## Microsoft LayoutLMv3

PRIMARY URL: https://github.com/microsoft/unilm/tree/master/layoutlmv3
Fetched: 2026-06-14

**LICENSE**: Code under repo (no LICENSE file in fetched subdir; overall unilm repo MIT for some parts). README states: "The content of this project itself is licensed under the Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)" — non-commercial. [F]

**Model size**: layoutlmv3-base, layoutlmv3-large, layoutlmv3-base-chinese. [F]

**Release date**: 2022 (ACM MM paper). [F]

**API shape**: Hugging Face transformers (LayoutLMv3ForTokenClassification, LayoutLMv3ForSequenceClassification, LayoutLMv3Processor). Detectron2 for object detection fine-tuning. PyTorch. [F]

**Inference** (verbatim from README "Installation" + "Fine-tuning Examples"):
```
conda create --name layoutlmv3 python=3.7
conda activate layoutlmv3
git clone https://github.com/microsoft/unilm.git
cd unilm/layoutlmv3
pip install -r requirements.txt
pip install torch==1.10.0+cu111 torchvision==0.11.1+cu111 -f https://download.pytorch.org/whl/torch_stable.html
python -m pip install detectron2 -f https://dl.fbaipublicfiles.com/detectron2/wheels/cu111/torch1.10/index.html
pip install -e .
```
[F]

**VRAM / hardware**: Detectron2 + PyTorch 1.10.0 + CUDA 11.1. Fine-tuning examples use 8 GPUs (FUNSD/CORD) and 16 GPUs (PubLayNet). [F]

**Input / Output**:
- Input: Document image + text + layout (bounding boxes). Pre-trained weights handle 224x224 image embeddings.
- Output: Per-token classification (KIE/RE/FUNSD), document image classification, or object detection (PubLayNet). 6-class PubLayNet output: Text, Title, List, Table, Figure. [F]

**Strengths** (verbatim from README): "We propose LayoutLMv3 to pre-train multimodal Transformers for Document AI with unified text and image masking... The simple unified architecture and training objectives make LayoutLMv3 a general-purpose pre-trained model for both text-centric and image-centric Document AI tasks. Experimental results show that LayoutLMv3 achieves state-of-the-art performance not only in text-centric tasks, including form understanding, receipt understanding, and document visual question answering, but also in image-centric tasks such as document image classification and document layout analysis." [F]

**Limitations**: None stated. CC BY-NC-SA 4.0 license (non-commercial) is a substantive limitation. [F]

**Benchmark numbers** (from README):
- FUNSD (semantic entity labeling, layoutlmv3-base-ft): precision 0.8955, recall 0.9165, F1 0.9059; (layoutlmv3-large-ft): F1 0.9215 [F]
- PubLayNet (layoutlmv3-base-finetuned): Text 94.5, Title 90.6, List 95.5, Table 97.9, Figure 97.0, Overall mAP 95.1 [F]
- XFUND Chinese (layoutlmv3-base-chinese): precision 0.8980, recall 0.9435, F1 0.9202 [F]
- EPHOIE (layoutlmv3-base-chinese): mean F1 99.21 (range 97.27 – 100 per field) [F]

**file_path:line citations**: microsoft/unilm/tree/master/layoutlmv3/README.md; examples/run_funsd_cord.py, examples/run_xfund.py; microsoft/layoutlmv3-base, microsoft/layoutlmv3-large, microsoft/layoutlmv3-base-chinese on HF. [F]

**Notes**: Pretrained model checkpoints on HF; code in microsoft/unilm. License is CC BY-NC-SA 4.0 (non-commercial). Built on transformers, layoutlmv2, layoutlmft, beit, dit, Detectron2. [F]

---

## Microsoft Table Transformer (TATR)

PRIMARY URL: https://github.com/microsoft/table-transformer
Fetched: 2026-06-14

**LICENSE**: MIT (repo LICENSE file). [F]

**Model size**: DETR R18 (110 MB) for detection; TATR-v1.0, TATR-v1.1-Pub, TATR-v1.1-Fin, TATR-v1.1-All (110 MB each) for table structure recognition. All are DETR with ResNet-18 backbone. [F]

**Release date**: Initial release 2021-06-08. TATR-v1.1 released 2023-08-22. Pre-trained weights on PubTables-1M released 2022-05-05 (detection) and 2022-03-04 (structure). Latest release tag v1.0.0 on 2023-02-17. [F]

**API shape**: Python, conda environment (`tables-detr`). Separate detection and structure training scripts. `src/inference.py` released 2023-03-07 for "detect and recognize tables from images and convert them to HTML or CSV." TATR needs OCR (or PDF text) as separate input. [F]

**Inference** (verbatim from README):
```
conda env create -f environment.yml
conda activate tables-detr
# Train detection:
python main.py --data_type detection --config_file detection_config.json --data_root_dir /path/to/detection_data
# Train structure:
python main.py --data_type structure --config_file structure_config.json --data_root_dir /path/to/structure_data
# Evaluate detection:
python main.py --mode eval --data_type detection --config_file detection_config.json --data_root_dir /path/to/pascal_voc_detection_data --model_load_path /path/to/detection_model
```
[F]

**VRAM / hardware**: PyTorch 1.13.1, Torchvision 0.14.1, Python 3.10.9 (per README news 2023-03-09). No specific GPU requirement stated. [F]

**Input / Output**:
- Input: Page image (PDF rendered to image or scanned). For structure recognition: additionally requires OCR/PDF text + word bounding boxes as separate input (JSON per page).
- Output: Table cell bounding boxes + cell text (after post-processing). HTML or CSV output via src/inference.py. [F]

**Strengths** (verbatim): "TATR can be trained to work well across many document domains and everything needed to train your own model is included here." "A deep learning model based on object detection for extracting tables from PDFs and images." Authors' papers: PubTables-1M (CVPR 2022), GriTS (ICDAR 2023), Aligning benchmark datasets (ICDAR 2023). [F]

**Limitations** (verbatim): "TATR is an object detection model that recognizes tables from image input. The inference code built on TATR needs text extraction (from OCR or directly from PDF) as a separate input in order to include text in its HTML or CSV output." "at the moment pre-trained model weights are only available for TATR trained on the PubTables-1M dataset." [F]

**Benchmark numbers** (from README "Evaluation Metrics"):
- Table Detection (DETR R18, PubTables-1M test): AP50 0.995, AP75 0.989, AP 0.970, AR 0.985 [F]
- Table Structure Recognition (TATR-v1.0, PubTables-1M test): AP50 0.970, AP75 0.941, AP 0.902, AR 0.935; GriTSTop 0.9849, GriTSCon 0.9850, GriTSLoc 0.9786, AccCon 0.8243 [F]

**file_path:line citations**: microsoft/table-transformer README; src/main.py, src/inference.py; environment.yml; bsmock/tatr-pubtables1m-v1.0 (HF model card); dataset: bsmock/pubtables-1m on HF and Microsoft Research Open Data. [F]

**Notes**: Requires external OCR. PubTables-1M dataset: 575,305 annotated pages, 947,642 fully annotated tables. TATR v1.1 introduced Aug 2023 with three variants (Pub, Fin, All) per paper "Aligning benchmark datasets for table structure recognition." [F]

---

## Azure AI Document Intelligence

PRIMARY URLs: https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/ + /model-overview + /prebuilt/layout
Fetched: 2026-06-14

**Service, not a single model**. Cloud-only. Prebuilt models on v4.0 (2024-11-30 GA): Read, Layout, Bank check, Bank statement, payStub, Contract, Health insurance card, ID document, Invoice, Receipt, US unified tax (with submodels W-2, W-4, 1040, 1095A/C, 1098/1098E/1098T, 1099, 1099SSA), US mortgage (1003 URLA, 1004 URAR, 1005, 1008 summary, closing disclosure), Marriage certificate, Credit card. Plus custom (Custom classifier, Custom neural, Custom template, Custom composed). Business card deprecated. Add-on capabilities: ocrHighResolution, formulas, styleFont, barcodes, languages, keyValuePairs, queryFields, searchablePDF. [F]

**Release date**: v4.0 GA 2024-11-30. v3.1, v3.0 (retiring), v2.1 (retiring) are older stable API versions on the same product. [F]

**LICENSE**: Commercial cloud service (Azure). No open weights. [F]

**API shape**: REST API + C# / Python / Java / JavaScript SDKs. Docker containers for on-prem. Document Intelligence Studio at https://documentintelligence.ai.azure.com. [F]

**Inference** (verbatim from layout docs):
```
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
document_intelligence_client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))
poller = document_intelligence_client.begin_analyze_document(
    "prebuilt-layout",
    AnalyzeDocumentRequest(url_source=url),
    output_content_format=ContentFormat.MARKDOWN,
)
# REST:
POST /documentModels/{modelId}:analyze?api-version=2024-11-30
```
[F]

**VRAM / hardware**: Cloud-only (Azure). Container images available for on-prem deployment (disconnected scenarios); hardware requirements not detailed in fetched pages. [F]

**Input / Output**:
- Input: PDF (up to 2000 pages, paid S0 tier; only 2 pages on F0 free tier; 500 MB S0 / 4 MB F0). Images: JPEG/JPG, PNG, BMP, TIFF, HEIF (50×50 to 10,000×10,000 px). Office: Word (DOCX), Excel (XLSX), PowerPoint (PPTX), HTML (8M char string limit). Custom model training: template max 500 pages, neural max 50,000 pages. Text min height 12 px @ 1024x768.
- Output: Structured JSON with `pages`, `paragraphs` (with roles: title, sectionHeading, footnote, pageHeader, pageFooter, pageNumber), `tables` (row/col span, columnHeader, polygons), `figures` (boundingRegions, caption), `sections` (hierarchical), `keyValuePairs`, `styles` (handwriting detection), `selectionMarks`, formulas (with add-on), fonts (with add-on), barcodes, language detection. Markdown output via `outputContentFormat=markdown` (v4.0). Searchable PDF via Read add-on. [F]

**Strengths** (verbatim from layout docs): "Extract text, tables, selections, titles, section headings, page headers, page footers, and more with the layout analysis model from Document Intelligence." "Document structure layout analysis is the process of analyzing a document to extract regions of interest and their interrelationships. The goal is to extract text and structural elements from the page to build better semantic understanding models." v4.0 changes: tables now represented as HTML tables to render merged cells and multirow headers; selection marks use Unicode checkbox characters ☒ and ☐. [F]

**Limitations** (verbatim from layout docs "Input requirements"):
- "Table analysis isn't supported if the input file is XLSX." [F]
- "For v4.0 2024-11-30 (GA), the bounding regions for figures and tables cover only the core content and exclude the associated caption and footnotes." [F]
- "Office file types (DOCX, XLSX, PPTX): The maximum string length limit is 8 million characters." [F]
- Service limits: 500 MB paid, 4 MB free, 2000 pages. [F]

**Benchmark numbers**: Not provided in fetched docs. Model overview page links to "Accuracy and confidence scores" concept article. [F]

**file_path:line citations**: docs URLs above. [F]

**Notes**: Azure DI does NOT publish per-model DocVQA / OmniDocBench numbers. Performance is sold as a managed service. [F]

---

## LightOnOCR-2

Reference: appears in surya README olmOCR-bench comparison table: "LightOnOCR-2-1B=83.2".

URL: https://github.com/LightOn-AI/LightOnOCR-2 (URL inferred from the LightOn-AI github org; not independently fetched in this evidence pass).

**Model size**: 1B (per surya comparison row). [A — third-party citation only]

**Benchmark numbers** (surya README, third-party citation): olmOCR-bench overall = 83.2. [A]

**Notes**: This row was cited from the surya README's olmOCR-bench table only. No direct README fetch in this evidence pass. [A]

---

## Mimo-7B-OCR

Reference: appears in some 2026 OCR model surveys (not independently fetched in this evidence pass).

**Notes**: Mimo-7B-OCR is a recent (2025-2026) addition to the open-source OCR model list but was not covered in detail in this scout due to time. Would need a dedicated fetch. [A]

---
