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
        name="Alibaba Cloud Model Studio - China",
        region="China (Hangzhou)",
        category="cloud",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        get_api_key_url="https://dashscope.console.aliyun.com/apiKey",
        preset_models=[
            "qwen-vl-max",
            "qwen2.5-vl-72b-instruct",
            "qwen2.5-vl-7b-instruct",
            "qwen-vl-plus",
            "qwen-max",
        ],
        description="Alibaba Cloud DashScope OpenAI-compatible endpoint (China region).",
    ),
    LLMProvider(
        id="alibaba-singapore",
        name="Alibaba Cloud Model Studio - Singapore",
        region="Singapore / Asia-Pacific",
        category="cloud",
        api_base="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        get_api_key_url="https://alibabacloud.com/help/en/model-studio/developer-reference/use-qwen-by-calling-api",
        preset_models=[
            "qwen-vl-max",
            "qwen2.5-vl-72b-instruct",
            "qwen2.5-vl-7b-instruct",
            "qwen-vl-plus",
        ],
        description="Alibaba Cloud Model Studio International (Singapore region).",
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
        name="Kimi (Moonshot AI)",
        region="Global",
        category="cloud",
        api_base="https://api.moonshot.cn/v1",
        get_api_key_url="https://platform.moonshot.cn/console/api-keys",
        preset_models=[
            "moonshot-v1-8k",
            "moonshot-v1-32k",
            "moonshot-v1-128k",
            "moonshot-v1-auto",
        ],
        description="Moonshot AI Kimi long-context API endpoint.",
    ),
    # -----------------------------------------------------------------------
    # MiniMax
    # -----------------------------------------------------------------------
    LLMProvider(
        id="minimax-china",
        name="MiniMax - China",
        region="China",
        category="cloud",
        api_base="https://api.minimax.chat/v1",
        get_api_key_url="https://platform.minimaxi.com/user-center/basic-information/interface-key",
        preset_models=[
            "minimax-text-01",
            "abab6.5s-chat",
            "abab6.5t-chat",
        ],
        description="MiniMax LLM platform (China endpoint).",
    ),
    LLMProvider(
        id="minimax-international",
        name="MiniMax - International",
        region="Global",
        category="cloud",
        api_base="https://api.minimaxi.com/v1",
        get_api_key_url="https://platform.minimaxi.com/",
        preset_models=[
            "minimax-text-01",
            "abab6.5s-chat",
        ],
        description="MiniMax International API endpoint.",
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
        api_base="https://api.novita.ai/v3/openai",
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
        api_base="https://api.together.xyz/v1",
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
