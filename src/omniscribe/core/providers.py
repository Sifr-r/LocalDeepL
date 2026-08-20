"""LLM Provider Registry & Catalog for OmniScribe.

Defines native metadata for all major global, regional, and local LLM providers:
- Provider ID, Display Name, Region, Category (Cloud / Local / Custom)
- Default API Base URL
- Direct "Get API Key" console link
- Popular Vision/OCR preset models
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMProvider:
    id: str
    name: str
    region: str
    category: str  # "cloud", "local", "custom"
    api_base: str
    get_api_key_url: str | None
    preset_models: list[str] = field(default_factory=list)
    requires_api_key: bool = True
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "region": self.region,
            "category": self.category,
            "api_base": self.api_base,
            "get_api_key_url": self.get_api_key_url,
            "preset_models": self.preset_models,
            "requires_api_key": self.requires_api_key,
            "description": self.description,
        }


# Catalog of all major LLM providers
PROVIDERS_CATALOG: list[LLMProvider] = [
    # -----------------------------------------------------------------------
    # Alibaba Cloud Model Studio (DashScope)
    # -----------------------------------------------------------------------
    LLMProvider(
        id="alibaba-china",
        name="Alibaba Cloud Model Studio - China (Beijing)",
        region="China (Beijing)",
        category="cloud",
        # Workspace-dedicated domain (preferred). The legacy shared domain
        # `https://dashscope.aliyuncs.com/compatible-mode/v1` still works but
        # is officially deprecated for new integrations. Replace
        # `{WorkspaceId}` with the value shown in the Alibaba Model Studio
        # console.
        api_base="https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        get_api_key_url="https://dashscope.console.aliyun.com/apiKey",
        preset_models=[
            "qwen-vl-max",
            "qwen2.5-vl-72b-instruct",
            "qwen2.5-vl-7b-instruct",
            "qwen-vl-plus",
            "qwen-max",
        ],
        description="Alibaba Cloud Model Studio (Beijing region). Workspace-dedicated OpenAI-compatible endpoint.",
    ),
    LLMProvider(
        id="alibaba-singapore",
        name="Alibaba Cloud Model Studio - Singapore",
        region="Singapore / Asia-Pacific",
        category="cloud",
        # Workspace-dedicated domain (preferred). The legacy shared domain
        # `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` still works
        # but is officially deprecated for new integrations. Replace
        # `{WorkspaceId}` with the value shown in the Alibaba Model Studio
        # console.
        api_base="https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        get_api_key_url="https://alibabacloud.com/help/en/model-studio/developer-reference/use-qwen-by-calling-api",
        preset_models=[
            "qwen-vl-max",
            "qwen2.5-vl-72b-instruct",
            "qwen2.5-vl-7b-instruct",
            "qwen-vl-plus",
        ],
        description="Alibaba Cloud Model Studio International (Singapore region). Workspace-dedicated OpenAI-compatible endpoint.",
    ),
    LLMProvider(
        id="alibaba-us",
        name="Alibaba Cloud Model Studio - America",
        region="United States (US East/West)",
        category="cloud",
        api_base="https://dashscope-us.aliyuncs.com/compatible-mode/v1",
        get_api_key_url="https://alibabacloud.com/help/en/model-studio/",
        preset_models=[
            "qwen-vl-max",
            "qwen2.5-vl-72b-instruct",
            "qwen2.5-vl-7b-instruct",
        ],
        description="Alibaba Cloud Model Studio International (US region).",
    ),
    # -----------------------------------------------------------------------
    # Z.ai (Zhipu AI / GLM)
    # -----------------------------------------------------------------------
    LLMProvider(
        id="zai-china",
        name="Z.ai - China (Zhipu BigModel)",
        region="China",
        category="cloud",
        api_base="https://open.bigmodel.cn/api/paas/v4",
        get_api_key_url="https://open.bigmodel.cn/usercenter/apikeys",
        preset_models=[
            "glm-4v-flash",
            "glm-4v-plus",
            "glm-4v",
            "glm-4-flash",
        ],
        description="Zhipu AI GLM-4V multimodal vision & language platform (China).",
    ),
    LLMProvider(
        id="zai-international",
        name="Z.ai - International",
        region="Global",
        category="cloud",
        api_base="https://api.z.ai/v1",
        get_api_key_url="https://z.ai/developers",
        preset_models=[
            "glm-4v-flash",
            "glm-4v-plus",
            "glm-4v",
        ],
        description="Z.ai International API endpoint.",
    ),
    # -----------------------------------------------------------------------
    # Kimi (Moonshot AI)
    # -----------------------------------------------------------------------
    LLMProvider(
        id="kimi",
        name="Kimi (Moonshot AI) - China",
        region="China",
        category="cloud",
        api_base="https://api.moonshot.cn/v1",
        get_api_key_url="https://platform.moonshot.cn/console/api-keys",
        preset_models=[
            "moonshot-v1-8k",
            "moonshot-v1-32k",
            "moonshot-v1-128k",
            "moonshot-v1-auto",
        ],
        description="Moonshot AI Kimi long-context API endpoint (China region).",
    ),
    LLMProvider(
        id="kimi-global",
        name="Kimi (Moonshot AI) - Global",
        region="Global",
        category="cloud",
        api_base="https://api.moonshot.ai/v1",
        get_api_key_url="https://platform.moonshot.ai/console/api-keys",
        preset_models=[
            "kimi-k2-0711-preview",
            "moonshot-v1-8k",
            "moonshot-v1-32k",
            "moonshot-v1-128k",
        ],
        description="Moonshot AI Kimi international endpoint (api.moonshot.ai). Separate account from the China region.",
    ),
    # -----------------------------------------------------------------------
    # MiniMax
    # -----------------------------------------------------------------------
    LLMProvider(
        id="minimax-china",
        name="MiniMax - China",
        region="China",
        category="cloud",
        # Corrected from the previous `https://api.minimax.chat/v1` (no
        # longer the canonical China host) to the platform-documented
        # China endpoint (verified 2026-07-18). The `minimax` template
        # already covers international; the duplicate
        # `minimax-international` template has been removed.
        api_base="https://api.minimaxi.com/v1",
        get_api_key_url="https://platform.minimaxi.com/user-center/basic-information/interface-key",
        preset_models=[
            "minimax-text-01",
            "abab6.5s-chat",
            "abab6.5t-chat",
        ],
        description="MiniMax LLM platform (China endpoint).",
    ),
    # -----------------------------------------------------------------------
    # DeepSeek
    # -----------------------------------------------------------------------
    LLMProvider(
        id="deepseek",
        name="DeepSeek",
        region="Global",
        category="cloud",
        api_base="https://api.deepseek.com/v1",
        get_api_key_url="https://platform.deepseek.com/api_keys",
        preset_models=[
            "deepseek-chat",
            "deepseek-reasoner",
        ],
        description="DeepSeek AI high-performance API endpoint.",
    ),
    # -----------------------------------------------------------------------
    # SiliconFlow
    # -----------------------------------------------------------------------
    LLMProvider(
        id="siliconflow",
        name="SiliconFlow (SiliconCloud)",
        region="Global",
        category="cloud",
        api_base="https://api.siliconflow.cn/v1",
        get_api_key_url="https://cloud.siliconflow.cn/account/ak",
        preset_models=[
            "Qwen/Qwen2.5-VL-72B-Instruct",
            "Qwen/Qwen2.5-VL-7B-Instruct",
            "deepseek-ai/DeepSeek-V3",
            "deepseek-ai/DeepSeek-R1",
        ],
        description="SiliconFlow open-source model cloud platform.",
    ),
    # -----------------------------------------------------------------------
    # OpenAI
    # -----------------------------------------------------------------------
    LLMProvider(
        id="openai",
        name="OpenAI",
        region="Global",
        category="cloud",
        api_base="https://api.openai.com/v1",
        get_api_key_url="https://platform.openai.com/api-keys",
        preset_models=[
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "o1",
            "o3-mini",
        ],
        description="Official OpenAI API endpoint.",
    ),
    # -----------------------------------------------------------------------
    # Google Gemini
    # -----------------------------------------------------------------------
    LLMProvider(
        id="google-gemini",
        name="Google Gemini",
        region="Global",
        category="cloud",
        api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
        get_api_key_url="https://aistudio.google.com/app/apikey",
        preset_models=[
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-2.0-flash-exp",
            "gemini-2.0-flash",
        ],
        description="Google Gemini OpenAI-compatible endpoint.",
    ),
    # -----------------------------------------------------------------------
    # Groq
    # -----------------------------------------------------------------------
    LLMProvider(
        id="groq",
        name="Groq Cloud",
        region="Global",
        category="cloud",
        api_base="https://api.groq.com/openai/v1",
        get_api_key_url="https://console.groq.com/keys",
        preset_models=[
            "llama-3.2-11b-vision-preview",
            "llama-3.2-90b-vision-preview",
            "llama-3.3-70b-versatile",
        ],
        description="Groq LPU ultra-fast inference cloud.",
    ),
    # -----------------------------------------------------------------------
    # OpenRouter
    # -----------------------------------------------------------------------
    LLMProvider(
        id="openrouter",
        name="OpenRouter",
        region="Global",
        category="cloud",
        api_base="https://openrouter.ai/api/v1",
        get_api_key_url="https://openrouter.ai/keys",
        preset_models=[
            "allenai/olmocr-7b-0225-preview",
            "qwen/qwen-2.5-vl-72b-instruct",
            "google/gemini-2.0-flash-001",
            "anthropic/claude-3.5-sonnet",
        ],
        description="Unified API for multi-provider models (Claude, Qwen, Gemini, Llama).",
    ),
    # -----------------------------------------------------------------------
    # Mistral AI
    # -----------------------------------------------------------------------
    LLMProvider(
        id="mistral",
        name="Mistral AI",
        region="Global",
        category="cloud",
        api_base="https://api.mistral.ai/v1",
        get_api_key_url="https://console.mistral.ai/api-keys/",
        preset_models=[
            "pixtral-12b-2409",
            "pixtral-large-2411",
            "mistral-large-latest",
        ],
        description="Mistral AI multimodal vision and language models.",
    ),
    # -----------------------------------------------------------------------
    # Novita AI
    # -----------------------------------------------------------------------
    LLMProvider(
        id="novita",
        name="Novita AI",
        region="Global",
        category="cloud",
        # Current OpenAI-compatible base URL (the legacy `/v3/openai` path
        # has been retired in favor of `/openai`).
        api_base="https://api.novita.ai/openai",
        get_api_key_url="https://novita.ai/dashboard/key",
        preset_models=[
            "qwen/qwen-2.5-vl-72b-instruct",
            "meta-llama/llama-3.2-11b-vision-instruct",
        ],
        description="Novita AI cloud GPU inference endpoint.",
    ),
    # -----------------------------------------------------------------------
    # Together AI
    # -----------------------------------------------------------------------
    LLMProvider(
        id="together",
        name="Together AI",
        region="Global",
        category="cloud",
        # Current Together domain is `.ai`; the legacy `.xyz` host is being
        # phased out.
        api_base="https://api.together.ai/v1",
        get_api_key_url="https://api.together.ai/settings/api-keys",
        preset_models=[
            "meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo",
            "meta-llama/Llama-3.2-90B-Vision-Instruct-Turbo",
            "Qwen/Qwen2.5-VL-72B-Instruct",
        ],
        description="Together AI cloud inference platform.",
    ),
    # -----------------------------------------------------------------------
    # Local Backends
    # -----------------------------------------------------------------------
    LLMProvider(
        id="lmstudio",
        name="LM Studio (Local)",
        region="Local Computer",
        category="local",
        api_base="http://localhost:1234/v1",
        get_api_key_url=None,
        preset_models=[
            "allenai/olmocr-2-7b",
            "qari-ocr-0.4.0-vl-4b-instruct",
            "arabic-english-handwritten-ocr-v3",
            "mbzuai-ain-7b",
        ],
        requires_api_key=False,
        description="Local desktop vision LLM server via LM Studio.",
    ),
    LLMProvider(
        id="ollama",
        name="Ollama (Local)",
        region="Local Computer",
        category="local",
        api_base="http://localhost:11434/v1",
        get_api_key_url=None,
        preset_models=[
            "llama3.2-vision",
            "llava",
            "qwen2-vl",
        ],
        requires_api_key=False,
        description="Local Ollama OpenAI-compatible inference server.",
    ),
    LLMProvider(
        id="vllm",
        name="vLLM / Local Server",
        region="Local / Self-Hosted",
        category="local",
        api_base="http://localhost:8000/v1",
        get_api_key_url=None,
        preset_models=[
            "allenai/olmocr-2-7b",
            "Qwen/Qwen2.5-VL-72B-Instruct",
        ],
        requires_api_key=False,
        description="Self-hosted vLLM or custom OpenAI-compatible server.",
    ),
    LLMProvider(
        id="custom",
        name="Custom OpenAI-Compatible API",
        region="Custom Endpoint",
        category="custom",
        api_base="http://localhost:1234/v1",
        get_api_key_url=None,
        preset_models=[],
        requires_api_key=False,
        description="Any custom OpenAI-compatible vision/OCR endpoint.",
    ),
    # -----------------------------------------------------------------------
    # Local providers — ported from OmniRoute reference (2026-08-19)
    # ComfyUI and SD WebUI are intentionally excluded: they are image-gen
    # pipelines, not chat/VLM endpoints, and do not fit OmniScribe's OCR use
    # case. `llama-cpp` and `llamafile` both default to port 8080 — only run
    # one at a time, or override via the `LLAMACPP_HOST` / `LLAMAFILE_HOST`
    # env vars.
    # -----------------------------------------------------------------------
    LLMProvider(
        id="llama-cpp",
        name="llama.cpp server",
        region="Local Computer",
        category="local",
        api_base="http://127.0.0.1:8080/v1",
        get_api_key_url=None,
        preset_models=["local-model"],
        requires_api_key=False,
        description="llama.cpp's `llama-server` (OpenAI-compatible REST). Override via `LLAMACPP_HOST`.",
    ),
    LLMProvider(
        id="llamafile",
        name="Mozilla Llamafile",
        region="Local Computer",
        category="local",
        api_base="http://localhost:8080/v1",
        get_api_key_url=None,
        preset_models=["LLaMA_CPP"],
        requires_api_key=False,
        description="Mozilla Llamafile (single-file LLM distribution). Override via `LLAMAFILE_HOST`. ⚠ Port 8080 collides with llama-cpp.",
    ),
    LLMProvider(
        id="docker-model-runner",
        name="Docker Model Runner",
        region="Local Computer",
        category="local",
        # OpenAI-compat surface is `/engines/v1`, not `/v1`. Enable with
        # `docker desktop enable model-runner --tcp 12434`.
        api_base="http://localhost:12434/engines/v1",
        get_api_key_url=None,
        preset_models=[],
        requires_api_key=False,
        description="Docker Desktop's Model Runner. Override via `DMR_HOST`.",
    ),
    LLMProvider(
        id="lemonade",
        name="Lemonade Server",
        region="Local Computer",
        category="local",
        api_base="http://localhost:13305/v1",
        get_api_key_url=None,
        preset_models=[],
        requires_api_key=False,
        description="Lemonade Server (AMD-optimized local LLM runtime). Override via `LEMONADE_HOST`.",
    ),
    LLMProvider(
        id="oobabooga",
        name="oobabooga text-generation-webui",
        region="Local Computer",
        category="local",
        # Requires the `--api` flag (or `--extensions openai`) at launch.
        api_base="http://127.0.0.1:5000/v1",
        get_api_key_url=None,
        preset_models=[],
        requires_api_key=False,
        description="oobabooga's text-generation-webui with the OpenAI extension. Override via `OOBABOOGA_HOST`.",
    ),
    LLMProvider(
        id="triton",
        name="NVIDIA Triton Inference Server (OpenAI frontend)",
        region="Local Computer",
        category="local",
        # The OpenAI-compatible frontend listens on `openai-port` (default
        # 9000). Triton's native HTTP port (8000) does not speak the
        # OpenAI schema.
        api_base="http://localhost:9000/v1",
        get_api_key_url=None,
        preset_models=[],
        requires_api_key=False,
        description="NVIDIA Triton with the OpenAI-compatible frontend enabled. Override via `TRITON_HOST`.",
    ),
    LLMProvider(
        id="xinference",
        name="Xorbits XInference",
        region="Local Computer",
        category="local",
        api_base="http://localhost:9997",
        get_api_key_url=None,
        preset_models=[],
        requires_api_key=False,
        description="Xorbits XInference (model serving for LLMs / embeddings / VLMs). Override via `XINFERENCE_HOST`.",
    ),
    # -----------------------------------------------------------------------
    # API-key providers — ported from OmniRoute reference (2026-08-19)
    # All OpenAI-compatible unless noted. Where a URL contains placeholders
    # (`<resource>`, `<account_id>`, `{WorkspaceId}`) the user MUST edit the
    # URL in their provider config after enabling the template.
    # -----------------------------------------------------------------------
    LLMProvider(
        id="azure-ai",
        name="Azure AI Foundry",
        region="Global",
        category="cloud",
        # Replace `<resource>` with the Azure resource name. The legacy
        # `<resource>.openai.azure.com` form is also accepted.
        api_base="https://<resource>.services.ai.azure.com/openai/v1",
        get_api_key_url="https://ai.azure.com/",
        preset_models=[
            "gpt-4o",
            "gpt-4o-mini",
            "Phi-3.5-vision-instruct",
            "meta-llama/Llama-3.2-11B-Vision-Instruct",
        ],
        requires_api_key=True,
        description="Azure AI Foundry multi-model endpoint. Replace `<resource>` with your Azure resource name. Uses `AZURE_AI_API_KEY` env var.",
    ),
    LLMProvider(
        id="bailian-coding-plan",
        name="Alibaba Cloud Bailian Token Plan (Singapore)",
        region="Singapore",
        category="cloud",
        # Team Edition Singapore default. Beijing uses
        # `token-plan.cn-beijing.maas.aliyuncs.com`, US uses
        # `token-plan.us-west-1.maas.aliyuncs.com`. Requires a dedicated
        # `sk-sp-...` key.
        api_base="https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        get_api_key_url="https://bailian.console.aliyun.com/",
        preset_models=["qwen-vl-max", "qwen2.5-vl-72b-instruct", "qwen3-vl-plus"],
        requires_api_key=True,
        description="Alibaba Bailian Token Plan — subscription-tier access to Qwen-VL. Uses `DASHSCOPE_API_KEY`.",
    ),
    LLMProvider(
        id="chutes",
        name="Chutes.ai",
        region="Global",
        category="cloud",
        api_base="https://llm.chutes.ai/v1",
        get_api_key_url="https://chutes.ai/",
        preset_models=["Qwen/Qwen2.5-VL-72B-Instruct", "deepseek-ai/DeepSeek-V3"],
        requires_api_key=True,
        description="Chutes.ai open-source model gateway. Uses `CHUTES_API_KEY`.",
    ),
    LLMProvider(
        id="clarifai",
        name="Clarifai",
        region="Global",
        category="cloud",
        # Auth uses a Personal Access Token (PAT) sent as `Bearer`. Env var
        # is `CLARIFAI_PAT` (not `CLARIFAI_API_KEY`).
        api_base="https://api.clarifai.com/v2/ext/openai/v1",
        get_api_key_url="https://clarifai.com/settings/security",
        preset_models=[],
        requires_api_key=True,
        description="Clarifai model platform (OpenAI-compatible). Uses `CLARIFAI_PAT` env var.",
    ),
    LLMProvider(
        id="cloudflare-ai",
        name="Cloudflare Workers AI",
        region="Global",
        category="cloud",
        # Replace `<account_id>` with the value from dash.cloudflare.com.
        # The newer AI Gateway surface additionally requires a
        # `cf-aig-gateway-id` header.
        api_base="https://api.cloudflare.com/client/v4/accounts/<account_id>/ai/v1",
        get_api_key_url="https://dash.cloudflare.com/profile/api-tokens",
        preset_models=[
            "@cf/meta/llama-3.2-11b-vision-instruct",
            "@cf/llava-1.5-7b-hf",
        ],
        requires_api_key=True,
        description="Cloudflare Workers AI. Replace `<account_id>` in the URL. Uses `CLOUDFLARE_API_TOKEN` env var.",
    ),
    LLMProvider(
        id="fireworks",
        name="Fireworks AI",
        region="Global",
        category="cloud",
        api_base="https://api.fireworks.ai/inference/v1",
        get_api_key_url="https://fireworks.ai/account/api-keys",
        preset_models=[
            "accounts/fireworks/models/llama-3.2-11b-vision-instruct",
            "accounts/fireworks/models/qwen2-vl-72b-instruct",
        ],
        requires_api_key=True,
        description="Fireworks AI inference platform. Uses `FIREWORKS_API_KEY`.",
    ),
    LLMProvider(
        id="github-models",
        name="GitHub Models",
        region="Global",
        category="cloud",
        # The Azure-hosted `models.inference.ai.azure.com` endpoint was
        # retired 2025-10-17; the new GitHub-hosted base is
        # `models.github.ai`. The new endpoint does NOT expose `/v1/models`
        # — the static preset list is the source of truth.
        api_base="https://models.github.ai/v1",
        get_api_key_url="https://github.com/settings/tokens",
        preset_models=[
            "gpt-4o",
            "gpt-4o-mini",
            "meta-llama/Llama-3.2-11B-Vision-Instruct",
            "Phi-3.5-vision-instruct",
        ],
        requires_api_key=True,
        description="GitHub Models (free-tier inference marketplace). Uses `GITHUB_TOKEN`.",
    ),
    LLMProvider(
        id="huggingface",
        name="HuggingFace Inference (Router)",
        region="Global",
        category="cloud",
        # Legacy `api-inference.huggingface.co` was decommissioned late
        # 2025 (now 410 Gone). The OpenAI-compatible surface is the new
        # router at `router.huggingface.co/v1`.
        api_base="https://router.huggingface.co/v1",
        get_api_key_url="https://huggingface.co/settings/tokens",
        preset_models=[],
        requires_api_key=True,
        description="HuggingFace Inference Providers via the new router. Uses `HF_TOKEN`.",
    ),
    LLMProvider(
        id="hyperbolic",
        name="Hyperbolic",
        region="Global",
        category="cloud",
        api_base="https://api.hyperbolic.xyz/v1",
        get_api_key_url="https://app.hyperbolic.ai/settings",
        preset_models=[
            "meta-llama/Llama-3.2-90B-Vision-Instruct",
            "Qwen/Qwen2.5-VL-72B-Instruct",
        ],
        requires_api_key=True,
        description="Hyperbolic open-source model cloud. Uses `HYPERBOLIC_API_KEY`.",
    ),
    LLMProvider(
        id="lambda-ai",
        name="Lambda AI Inference",
        region="Global",
        category="cloud",
        # ⚠ Lambda announced the Inference API is winding down in favor of
        # customer self-hosted deployments on Lambda GPU instances (as of
        # 2026-05-29). The endpoint still works for now.
        api_base="https://api.lambda.ai/v1",
        get_api_key_url="https://cloud.lambdalabs.com/api-keys",
        preset_models=[],
        requires_api_key=True,
        description="Lambda AI hosted inference (winding down per Lambda's 2026-05-29 announcement). Uses `LAMBDA_API_KEY`.",
    ),
    LLMProvider(
        id="nvidia",
        name="NVIDIA NIM (integrate.api.nvidia.com)",
        region="Global",
        category="cloud",
        api_base="https://integrate.api.nvidia.com/v1",
        get_api_key_url="https://build.nvidia.com/",
        preset_models=[
            "meta/llama-3.2-90b-vision-instruct",
            "nvidia/neva-22b",
            "qwen/qwen2-vl-72b-instruct",
        ],
        requires_api_key=True,
        description="NVIDIA NIM hosted inference (build.nvidia.com). Uses `NVIDIA_API_KEY`.",
    ),
    LLMProvider(
        id="requesty",
        name="Requesty (LLM Router)",
        region="Global",
        category="cloud",
        # EU alternative: `https://router.eu.requesty.ai/v1`.
        api_base="https://router.requesty.ai/v1",
        get_api_key_url="https://requesty.ai/keys",
        preset_models=[],
        requires_api_key=True,
        description="Requesty unified LLM router (300+ models, quota-aware failover). Uses `REQUESTY_API_KEY`.",
    ),
    LLMProvider(
        id="sambanova",
        name="SambaNova (SambaCloud)",
        region="Global",
        category="cloud",
        api_base="https://api.sambanova.ai/v1",
        get_api_key_url="https://cloud.sambanova.ai/dashboard",
        preset_models=[
            "Meta-Llama-3.2-11B-Vision-Instruct",
            "Llama-3.2-90B-Vision-Instruct",
        ],
        requires_api_key=True,
        description="SambaNova hosted inference (SambaCloud). Uses `SAMBANOVA_API_KEY`.",
    ),
    LLMProvider(
        id="scaleway",
        name="Scaleway Generative APIs",
        region="Europe (Paris)",
        category="cloud",
        api_base="https://api.scaleway.ai/v1",
        get_api_key_url="https://console.scaleway.com/iam/api-keys",
        preset_models=[
            "llama-3.2-11b-vision-instruct",
            "qwen2.5-vl-72b-instruct",
        ],
        requires_api_key=True,
        description="Scaleway Generative APIs (EU/GDPR, Paris region, free during beta). Uses `SCALEWAY_API_KEY`.",
    ),
    LLMProvider(
        id="stepfun",
        name="StepFun",
        region="China",
        category="cloud",
        # Standard OpenAI-compat surface. The "Step Plan" subscription
        # tier uses `https://api.stepfun.com/step_plan/v1` instead.
        api_base="https://api.stepfun.com/v1",
        get_api_key_url="https://platform.stepfun.ai/",
        preset_models=["step-1v-8k", "step-1o-vision-32k"],
        requires_api_key=True,
        description="StepFun Step-1V / Step-1O multimodal models. Uses `STEPFUN_API_KEY`.",
    ),
    LLMProvider(
        id="vercel-ai-gateway",
        name="Vercel AI Gateway",
        region="Global",
        category="cloud",
        api_base="https://ai-gateway.vercel.sh/v1",
        get_api_key_url="https://vercel.com/dashboard/ai-gateway",
        preset_models=[],
        requires_api_key=True,
        description="Vercel AI Gateway (multi-provider router with built-in logging/caching). Uses `VERCEL_AI_GATEWAY_API_KEY`.",
    ),
    LLMProvider(
        id="vertex",
        name="Google Vertex AI (OpenAI-compat)",
        region="Global",
        category="cloud",
        # Vertex has no single base URL — it varies by region, project,
        # and deployment. The user MUST edit the URL after enabling the
        # template. Common shapes:
        #   https://{region}-aiplatform.googleapis.com/v1/projects/{p}/locations/{r}/endpoints/openapi
        #   https://{endpoint_id}.{region}-{project}.prediction.vertexai.goog/v1/projects/{p}/locations/{r}/endpoints/{id}:predict
        api_base="https://aiplatform.googleapis.com/v1",
        get_api_key_url="https://console.cloud.google.com/vertex-ai",
        preset_models=[
            "gemini-1.5-pro",
            "gemini-2.0-flash-exp",
            "claude-3-5-sonnet@20240620",
        ],
        requires_api_key=True,
        description="Google Vertex AI (OpenAI-compat surface). Replace the URL with your region/project/deployment-specific endpoint. Uses `VERTEX_API_KEY`.",
    ),
    LLMProvider(
        id="xai",
        name="xAI (Grok)",
        region="Global",
        category="cloud",
        api_base="https://api.x.ai/v1",
        get_api_key_url="https://console.x.ai/",
        preset_models=["grok-2-vision-1212", "grok-vision-beta"],
        requires_api_key=True,
        description="xAI Grok models (vision-capable). Uses `XAI_API_KEY`.",
    ),
    LLMProvider(
        id="xiaomi-mimo",
        name="Xiaomi MiMo",
        region="China",
        category="cloud",
        # Pay-as-you-go OpenAI-compat surface. The Xiaomi Token Plan tier
        # uses `https://token-plan-cn.xiaomimimo.com/v1` (or `-sgp`/`-ams`
        # for Singapore/Europe) and a `tp-...` key.
        api_base="https://api.xiaomimimo.com/v1",
        get_api_key_url="https://mimo.mi.com/",
        preset_models=["mimo-v2.5-vl", "mimo-v2-vl-72b"],
        requires_api_key=True,
        description="Xiaomi MiMo multimodal models. Uses `MIMO_API_KEY`.",
    ),
    LLMProvider(
        id="zenmux",
        name="ZenMux",
        region="Global",
        category="cloud",
        api_base="https://zenmux.ai/api/v1",
        get_api_key_url="https://zenmux.ai/",
        preset_models=[],
        requires_api_key=True,
        description="ZenMux unified AI gateway. Uses `ZENMUX_API_KEY`.",
    ),
]


_PROVIDER_MAP: dict[str, LLMProvider] = {p.id: p for p in PROVIDERS_CATALOG}


def get_provider(provider_id: str) -> LLMProvider | None:
    """Return provider by ID, or None if unknown."""
    return _PROVIDER_MAP.get(provider_id)


def list_providers() -> list[dict[str, Any]]:
    """Return all catalog providers as dictionary list."""
    return [p.to_dict() for p in PROVIDERS_CATALOG]


__all__ = [
    "PROVIDERS_CATALOG",
    "LLMProvider",
    "get_provider",
    "list_providers",
]
