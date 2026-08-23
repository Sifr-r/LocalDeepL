"""Provider Manager service for OmniScribe based on the Goose API handling specification."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from omniscribe.api.schemas.requests import (
    ProviderConfig,
    ProviderCreateRequest,
    ProviderFormatEnum,
    ProviderTemplate,
)

logger = logging.getLogger(__name__)


def extract_model_ids_from_response(data: Any) -> list[str]:
    """Extract model identifiers from arbitrary JSON responses.

    Supports:
    - OpenAI standard: {"object": "list", "data": [{"id": "gpt-4o", ...}]}
    - Ollama native: {"models": [{"name": "llama3", "model": "llama3:latest", ...}]}
    - Anthropic: {"data": [{"id": "claude-3-5-sonnet", "display_name": "..."}]}
    - OpenRouter / Together / Custom: {"data": [{"id": "..."}, {"name": "..."}]}
    - Plain models list: {"models": ["model1", "model2"]} or {"models": [{"id": "m1"}]}
    - Result list: {"result": [{"id": "..."}, {"name": "..."}]}
    - Top-level list: [{"id": "m1"}, {"name": "m2"}] or ["m1", "m2"]
    """
    if not data:
        return []

    raw_items: list[Any] = []
    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list):
            raw_items = data["data"]
        elif "models" in data and isinstance(data["models"], list):
            raw_items = data["models"]
        elif "result" in data and isinstance(data["result"], list):
            raw_items = data["result"]
        elif "data" in data and isinstance(data["data"], dict):
            raw_items = list(data["data"].values())
        else:
            for v in data.values():
                if isinstance(v, dict) and any(k in v for k in ("id", "name", "model")):
                    raw_items.append(v)

    model_ids: list[str] = []
    seen: set[str] = set()

    for item in raw_items:
        mid: str | None = None
        if isinstance(item, str) and item.strip():
            mid = item.strip()
        elif isinstance(item, dict):
            for key in ("id", "name", "model", "model_id", "display_name"):
                val = item.get(key)
                if isinstance(val, str) and val.strip():
                    mid = val.strip()
                    break
        if mid and mid not in seen:
            seen.add(mid)
            model_ids.append(mid)

    return model_ids


DEFAULT_CONFIG_PATH = Path("~/.config/omniscribe/providers.yaml").expanduser()

PROVIDER_TEMPLATES: dict[str, ProviderTemplate] = {
    "openai": ProviderTemplate(
        id="openai",
        display_name="OpenAI",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.openai.com/v1",
        env_key="OPENAI_API_KEY",
        models=["gpt-4o", "gpt-4o-mini", "o1", "o3-mini"],
        get_api_key_url="https://platform.openai.com/api-keys",
        requires_auth=True,
    ),
    "anthropic": ProviderTemplate(
        id="anthropic",
        display_name="Anthropic",
        format=ProviderFormatEnum.ANTHROPIC_COMPATIBLE,
        api_url="https://api.anthropic.com/v1",
        env_key="ANTHROPIC_API_KEY",
        models=[
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ],
        get_api_key_url="https://console.anthropic.com/settings/keys",
        requires_auth=True,
    ),
    "openrouter": ProviderTemplate(
        id="openrouter",
        display_name="OpenRouter",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://openrouter.ai/api/v1",
        env_key="OPENROUTER_API_KEY",
        models=[
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
            "google/gemini-flash-1.5",
        ],
        get_api_key_url="https://openrouter.ai/keys",
        requires_auth=True,
    ),
    "ollama": ProviderTemplate(
        id="ollama",
        display_name="Ollama",
        format=ProviderFormatEnum.OLLAMA_COMPATIBLE,
        api_url="http://localhost:11434",
        env_host="OLLAMA_HOST",
        models=["llama3.2-vision", "llava", "qwen2-vl"],
        requires_auth=False,
    ),
    "lmstudio": ProviderTemplate(
        id="lmstudio",
        display_name="LM Studio",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="http://localhost:1234/v1",
        env_host="LMSTUDIO_HOST",
        models=["local-model"],
        requires_auth=False,
    ),
    "databricks": ProviderTemplate(
        id="databricks",
        display_name="Databricks",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="",
        env_host="DATABRICKS_HOST",
        env_key="DATABRICKS_TOKEN",
        models=[],
        get_api_key_url="https://docs.databricks.com/en/dev-tools/auth.html",
        requires_auth=True,
    ),
    "azure": ProviderTemplate(
        id="azure",
        display_name="Azure OpenAI",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="",
        env_host="AZURE_OPENAI_ENDPOINT",
        env_key="AZURE_OPENAI_API_KEY",
        models=[],
        get_api_key_url="https://ai.azure.com/",
        requires_auth=True,
    ),
    "groq": ProviderTemplate(
        id="groq",
        display_name="Groq",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.groq.com/openai/v1",
        env_key="GROQ_API_KEY",
        models=["llama-3.2-90b-vision-preview", "llama-3.2-11b-vision-preview"],
        get_api_key_url="https://console.groq.com/keys",
        requires_auth=True,
    ),
    "deepseek": ProviderTemplate(
        id="deepseek",
        display_name="DeepSeek",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.deepseek.com/v1",
        env_key="DEEPSEEK_API_KEY",
        models=["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
        get_api_key_url="https://platform.deepseek.com/api_keys",
        requires_auth=True,
    ),
    "minimax": ProviderTemplate(
        id="minimax",
        display_name="MiniMax",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.minimax.io/v1",
        env_key="MINIMAX_API_KEY",
        models=["MiniMax-M3", "MiniMax-Text-01"],
        get_api_key_url="https://intl.minimaxi.com/user-center/basic-information/interface-key",
        requires_auth=True,
    ),
    "litellm": ProviderTemplate(
        id="litellm",
        display_name="LiteLLM",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="http://localhost:4000",
        env_host="LITELLM_HOST",
        models=[],
        requires_auth=False,
    ),
    "alibaba-china": ProviderTemplate(
        id="alibaba-china",
        display_name="Alibaba Cloud Model Studio - China (Beijing)",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # Workspace-dedicated domain (preferred). Replace {WorkspaceId} with the
        # value shown in the Alibaba Model Studio console. The legacy shared
        # domain `https://dashscope.aliyuncs.com/compatible-mode/v1` still works
        # but is officially deprecated for new integrations.
        api_url="https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        env_key="DASHSCOPE_API_KEY",
        models=["qwen-vl-max", "qwen2.5-vl-72b-instruct", "qwen2.5-vl-7b-instruct"],
        get_api_key_url="https://dashscope.console.aliyun.com/apiKey",
        requires_auth=True,
    ),
    "alibaba-singapore": ProviderTemplate(
        id="alibaba-singapore",
        display_name="Alibaba Cloud Model Studio - Singapore",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # Workspace-dedicated domain (preferred). Replace {WorkspaceId} with the
        # value shown in the Alibaba Model Studio console. The legacy shared
        # domain `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` still
        # works but is officially deprecated for new integrations.
        api_url="https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        env_key="DASHSCOPE_API_KEY",
        models=["qwen-vl-max", "qwen2.5-vl-72b-instruct"],
        get_api_key_url="https://alibabacloud.com/help/en/model-studio/developer-reference/use-qwen-by-calling-api",
        requires_auth=True,
    ),
    "alibaba-us": ProviderTemplate(
        id="alibaba-us",
        display_name="Alibaba Cloud Model Studio - America",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://dashscope-us.aliyuncs.com/compatible-mode/v1",
        env_key="DASHSCOPE_API_KEY",
        models=["qwen-vl-max", "qwen2.5-vl-72b-instruct"],
        get_api_key_url="https://alibabacloud.com/help/en/model-studio/",
        requires_auth=True,
    ),
    "zai-china": ProviderTemplate(
        id="zai-china",
        display_name="Z.ai - China (Zhipu BigModel)",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://open.bigmodel.cn/api/paas/v4",
        env_key="ZHIPU_API_KEY",
        models=["glm-4v-flash", "glm-4v-plus", "glm-4v"],
        get_api_key_url="https://open.bigmodel.cn/usercenter/apikeys",
        requires_auth=True,
    ),
    "zai-international": ProviderTemplate(
        id="zai-international",
        display_name="Z.ai - International",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.z.ai/v1",
        env_key="ZHIPU_API_KEY",
        models=["glm-4v-flash", "glm-4v-plus"],
        get_api_key_url="https://z.ai/developers",
        requires_auth=True,
    ),
    "kimi": ProviderTemplate(
        id="kimi",
        display_name="Kimi (Moonshot AI) - China",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.moonshot.cn/v1",
        env_key="MOONSHOT_API_KEY",
        models=["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        get_api_key_url="https://platform.moonshot.cn/console/api-keys",
        requires_auth=True,
    ),
    "kimi-global": ProviderTemplate(
        id="kimi-global",
        display_name="Kimi (Moonshot AI) - Global",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.moonshot.ai/v1",
        env_key="MOONSHOT_API_KEY",
        models=[
            "kimi-k2-0711-preview",
            "moonshot-v1-8k",
            "moonshot-v1-32k",
            "moonshot-v1-128k",
        ],
        get_api_key_url="https://platform.moonshot.ai/console/api-keys",
        requires_auth=True,
    ),
    "minimax-china": ProviderTemplate(
        id="minimax-china",
        display_name="MiniMax - China",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # The correct China endpoint per platform docs (verified 2026-07-18).
        # `minimax` (international) and `minimax-china` (this) are the two
        # supported regions; the `minimax-international` template that
        # previously lived here was a duplicate and has been removed.
        api_url="https://api.minimaxi.com/v1",
        env_key="MINIMAX_API_KEY",
        models=["minimax-text-01", "abab6.5s-chat"],
        get_api_key_url="https://platform.minimaxi.com/user-center/basic-information/interface-key",
        requires_auth=True,
    ),
    "google-gemini": ProviderTemplate(
        id="google-gemini",
        display_name="Google Gemini",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        env_key="GEMINI_API_KEY",
        models=["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"],
        get_api_key_url="https://aistudio.google.com/app/apikey",
        requires_auth=True,
    ),
    "siliconflow": ProviderTemplate(
        id="siliconflow",
        display_name="SiliconFlow (SiliconCloud)",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.siliconflow.cn/v1",
        env_key="SILICONFLOW_API_KEY",
        models=["Qwen/Qwen2.5-VL-72B-Instruct", "deepseek-ai/DeepSeek-V3"],
        get_api_key_url="https://cloud.siliconflow.cn/account/ak",
        requires_auth=True,
    ),
    "mistral": ProviderTemplate(
        id="mistral",
        display_name="Mistral AI",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.mistral.ai/v1",
        env_key="MISTRAL_API_KEY",
        models=["pixtral-12b-2409", "pixtral-large-2411"],
        get_api_key_url="https://console.mistral.ai/api-keys/",
        requires_auth=True,
    ),
    "novita": ProviderTemplate(
        id="novita",
        display_name="Novita AI",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # Current OpenAI-compatible base URL (the legacy `/v3/openai` path
        # has been retired in favor of `/openai`).
        api_url="https://api.novita.ai/openai",
        env_key="NOVITA_API_KEY",
        models=["qwen/qwen-2.5-vl-72b-instruct"],
        get_api_key_url="https://novita.ai/dashboard/key",
        requires_auth=True,
    ),
    "together": ProviderTemplate(
        id="together",
        display_name="Together AI",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # Current Together domain is `.ai`; the legacy `.xyz` host is being
        # phased out.
        api_url="https://api.together.ai/v1",
        env_key="TOGETHER_API_KEY",
        models=["meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo"],
        get_api_key_url="https://api.together.ai/settings/api-keys",
        requires_auth=True,
    ),
    "vllm": ProviderTemplate(
        id="vllm",
        display_name="vLLM / Local Server",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="http://localhost:8000/v1",
        env_host="VLLM_HOST",
        models=["allenai/olmocr-2-7b"],
        requires_auth=False,
    ),
    "custom": ProviderTemplate(
        id="custom",
        display_name="Custom OpenAI-Compatible API",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="http://localhost:1234/v1",
        models=[],
        requires_auth=False,
    ),
    # -----------------------------------------------------------------------
    # Local providers — ported from OmniRoute reference (2026-08-19)
    # ComfyUI and SD WebUI are intentionally excluded: they are image-gen
    # pipelines, not chat/VLM endpoints, and do not fit OmniScribe's OCR use
    # case. `llama-cpp` and `llamafile` both default to port 8080 — only run
    # one at a time or override via env_host.
    # -----------------------------------------------------------------------
    "llama-cpp": ProviderTemplate(
        id="llama-cpp",
        display_name="llama.cpp server",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="http://127.0.0.1:8080/v1",
        env_host="LLAMACPP_HOST",
        models=["local-model"],
        requires_auth=False,
    ),
    "llamafile": ProviderTemplate(
        id="llamafile",
        display_name="Mozilla Llamafile",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="http://localhost:8080/v1",
        env_host="LLAMAFILE_HOST",
        models=["LLaMA_CPP"],
        requires_auth=False,
    ),
    "docker-model-runner": ProviderTemplate(
        id="docker-model-runner",
        display_name="Docker Model Runner",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # Docker Model Runner's OpenAI-compatible surface lives at
        # `/engines/v1`, not the usual `/v1`. The default TCP host port is
        # 12434; enable with `docker desktop enable model-runner --tcp 12434`.
        api_url="http://localhost:12434/engines/v1",
        env_host="DMR_HOST",
        models=[],
        requires_auth=False,
    ),
    "lemonade": ProviderTemplate(
        id="lemonade",
        display_name="Lemonade Server",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="http://localhost:13305/v1",
        env_host="LEMONADE_HOST",
        models=[],
        requires_auth=False,
    ),
    "oobabooga": ProviderTemplate(
        id="oobabooga",
        display_name="oobabooga text-generation-webui",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # Requires the `--api` flag (or `--extensions openai`) at launch; the
        # default port is 5000.
        api_url="http://127.0.0.1:5000/v1",
        env_host="OOBABOOGA_HOST",
        models=[],
        requires_auth=False,
    ),
    "triton": ProviderTemplate(
        id="triton",
        display_name="NVIDIA Triton Inference Server (OpenAI frontend)",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # The OpenAI-compatible frontend listens on port 9000 by default
        # (`openai-port`); Triton's native HTTP port is 8000 but does not
        # speak the OpenAI schema.
        api_url="http://localhost:9000/v1",
        env_host="TRITON_HOST",
        models=[],
        requires_auth=False,
    ),
    "xinference": ProviderTemplate(
        id="xinference",
        display_name="Xorbits XInference",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # Xinference's REST root is the bare port; the runtime will append
        # `/v1/models` etc. for OpenAI-compat routes.
        api_url="http://localhost:9997",
        env_host="XINFERENCE_HOST",
        models=[],
        requires_auth=False,
    ),
    # -----------------------------------------------------------------------
    # API-key providers — ported from OmniRoute reference (2026-08-19)
    # All OpenAI-compatible unless noted. Where a URL contains placeholders
    # (`<resource>`, `<account_id>`, `{WorkspaceId}`) the user MUST edit the
    # URL in their provider config after enabling the template.
    # -----------------------------------------------------------------------
    "azure-ai": ProviderTemplate(
        id="azure-ai",
        display_name="Azure AI Foundry",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # Replace `<resource>` with the Azure resource name. The legacy
        # `<resource>.openai.azure.com` form is also accepted.
        api_url="https://<resource>.services.ai.azure.com/openai/v1",
        env_key="AZURE_AI_API_KEY",
        models=[
            "gpt-4o",
            "gpt-4o-mini",
            "Phi-3.5-vision-instruct",
            "meta-llama/Llama-3.2-11B-Vision-Instruct",
        ],
        get_api_key_url="https://ai.azure.com/",
        requires_auth=True,
    ),
    "bailian-coding-plan": ProviderTemplate(
        id="bailian-coding-plan",
        display_name="Alibaba Cloud Bailian Token Plan (Singapore)",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # Team Edition Singapore default. Other regions: replace the
        # domain — Beijing `token-plan.cn-beijing.maas.aliyuncs.com`, US
        # `token-plan.us-west-1.maas.aliyuncs.com`. Requires a dedicated
        # `sk-sp-...` key from the Bailian Token Plan console.
        api_url="https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        env_key="DASHSCOPE_API_KEY",
        models=["qwen-vl-max", "qwen2.5-vl-72b-instruct", "qwen3-vl-plus"],
        get_api_key_url="https://bailian.console.aliyun.com/",
        requires_auth=True,
    ),
    "chutes": ProviderTemplate(
        id="chutes",
        display_name="Chutes.ai",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://llm.chutes.ai/v1",
        env_key="CHUTES_API_KEY",
        models=["Qwen/Qwen2.5-VL-72B-Instruct", "deepseek-ai/DeepSeek-V3"],
        get_api_key_url="https://chutes.ai/",
        requires_auth=True,
    ),
    "clarifai": ProviderTemplate(
        id="clarifai",
        display_name="Clarifai",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # Auth uses a Personal Access Token (PAT) sent as `Bearer`. The env
        # var is intentionally `CLARIFAI_PAT` (not `CLARIFAI_API_KEY`).
        api_url="https://api.clarifai.com/v2/ext/openai/v1",
        env_key="CLARIFAI_PAT",
        models=[],
        get_api_key_url="https://clarifai.com/settings/security",
        requires_auth=True,
    ),
    "cloudflare-ai": ProviderTemplate(
        id="cloudflare-ai",
        display_name="Cloudflare Workers AI",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # Replace `<account_id>` with the value from dash.cloudflare.com.
        # The newer AI Gateway surface additionally requires a
        # `cf-aig-gateway-id` header.
        api_url="https://api.cloudflare.com/client/v4/accounts/<account_id>/ai/v1",
        env_key="CLOUDFLARE_API_TOKEN",
        models=["@cf/meta/llama-3.2-11b-vision-instruct", "@cf/llava-1.5-7b-hf"],
        get_api_key_url="https://dash.cloudflare.com/profile/api-tokens",
        requires_auth=True,
    ),
    "fireworks": ProviderTemplate(
        id="fireworks",
        display_name="Fireworks AI",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.fireworks.ai/inference/v1",
        env_key="FIREWORKS_API_KEY",
        models=[
            "accounts/fireworks/models/llama-3.2-11b-vision-instruct",
            "accounts/fireworks/models/qwen2-vl-72b-instruct",
        ],
        get_api_key_url="https://fireworks.ai/account/api-keys",
        requires_auth=True,
    ),
    "github-models": ProviderTemplate(
        id="github-models",
        display_name="GitHub Models",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # The Azure-hosted `models.inference.ai.azure.com` endpoint was
        # retired 2025-10-17; the new GitHub-hosted base is `models.github.ai`.
        # The new endpoint does NOT expose `/v1/models`; the static list
        # below is the source of truth at runtime.
        api_url="https://models.github.ai/v1",
        env_key="GITHUB_TOKEN",
        models=[
            "gpt-4o",
            "gpt-4o-mini",
            "meta-llama/Llama-3.2-11B-Vision-Instruct",
            "Phi-3.5-vision-instruct",
        ],
        get_api_key_url="https://github.com/settings/tokens",
        requires_auth=True,
    ),
    "huggingface": ProviderTemplate(
        id="huggingface",
        display_name="HuggingFace Inference (Router)",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # The legacy `api-inference.huggingface.co` was decommissioned late
        # 2025 (now 410 Gone). The OpenAI-compatible surface is the new
        # router at `router.huggingface.co/v1`.
        api_url="https://router.huggingface.co/v1",
        env_key="HF_TOKEN",
        models=[],
        get_api_key_url="https://huggingface.co/settings/tokens",
        requires_auth=True,
    ),
    "hyperbolic": ProviderTemplate(
        id="hyperbolic",
        display_name="Hyperbolic",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.hyperbolic.xyz/v1",
        env_key="HYPERBOLIC_API_KEY",
        models=[
            "meta-llama/Llama-3.2-90B-Vision-Instruct",
            "Qwen/Qwen2.5-VL-72B-Instruct",
        ],
        get_api_key_url="https://app.hyperbolic.ai/settings",
        requires_auth=True,
    ),
    "lambda-ai": ProviderTemplate(
        id="lambda-ai",
        display_name="Lambda AI Inference",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # ⚠ Lambda announced the Inference API is winding down in favor of
        # customer self-hosted deployments on Lambda GPU instances (as of
        # 2026-05-29). The endpoint still works for now.
        api_url="https://api.lambda.ai/v1",
        env_key="LAMBDA_API_KEY",
        models=[],
        get_api_key_url="https://cloud.lambdalabs.com/api-keys",
        requires_auth=True,
    ),
    "nvidia": ProviderTemplate(
        id="nvidia",
        display_name="NVIDIA NIM (integrate.api.nvidia.com)",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://integrate.api.nvidia.com/v1",
        env_key="NVIDIA_API_KEY",
        models=[
            "meta/llama-3.2-90b-vision-instruct",
            "nvidia/neva-22b",
            "qwen/qwen2-vl-72b-instruct",
        ],
        get_api_key_url="https://build.nvidia.com/",
        requires_auth=True,
    ),
    "requesty": ProviderTemplate(
        id="requesty",
        display_name="Requesty (LLM Router)",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # EU alternative: `https://router.eu.requesty.ai/v1`.
        api_url="https://router.requesty.ai/v1",
        env_key="REQUESTY_API_KEY",
        models=[],
        get_api_key_url="https://requesty.ai/keys",
        requires_auth=True,
    ),
    "sambanova": ProviderTemplate(
        id="sambanova",
        display_name="SambaNova (SambaCloud)",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.sambanova.ai/v1",
        env_key="SAMBANOVA_API_KEY",
        models=[
            "Meta-Llama-3.2-11B-Vision-Instruct",
            "Llama-3.2-90B-Vision-Instruct",
        ],
        get_api_key_url="https://cloud.sambanova.ai/dashboard",
        requires_auth=True,
    ),
    "scaleway": ProviderTemplate(
        id="scaleway",
        display_name="Scaleway Generative APIs",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # EU region (Paris) only. Free during beta.
        api_url="https://api.scaleway.ai/v1",
        env_key="SCALEWAY_API_KEY",
        models=[
            "llama-3.2-11b-vision-instruct",
            "qwen2.5-vl-72b-instruct",
        ],
        get_api_key_url="https://console.scaleway.com/iam/api-keys",
        requires_auth=True,
    ),
    "stepfun": ProviderTemplate(
        id="stepfun",
        display_name="StepFun",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # Standard OpenAI-compat surface. The "Step Plan" subscription tier
        # uses `https://api.stepfun.com/step_plan/v1` instead.
        api_url="https://api.stepfun.com/v1",
        env_key="STEPFUN_API_KEY",
        models=["step-1v-8k", "step-1o-vision-32k"],
        get_api_key_url="https://platform.stepfun.ai/",
        requires_auth=True,
    ),
    "vercel-ai-gateway": ProviderTemplate(
        id="vercel-ai-gateway",
        display_name="Vercel AI Gateway",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://ai-gateway.vercel.sh/v1",
        env_key="VERCEL_AI_GATEWAY_API_KEY",
        models=[],
        get_api_key_url="https://vercel.com/dashboard/ai-gateway",
        requires_auth=True,
    ),
    "vertex": ProviderTemplate(
        id="vertex",
        display_name="Google Vertex AI (OpenAI-compat)",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # Vertex has no single base URL — it varies by region, project, and
        # deployment. The user MUST edit the URL after enabling the
        # template. Common shapes:
        #   https://{region}-aiplatform.googleapis.com/v1/projects/{p}/locations/{r}/endpoints/openapi
        #   https://{endpoint_id}.{region}-{project}.prediction.vertexai.goog/v1/projects/{p}/locations/{r}/endpoints/{id}:predict
        api_url="https://aiplatform.googleapis.com/v1",
        env_key="VERTEX_API_KEY",
        models=[
            "gemini-1.5-pro",
            "gemini-2.0-flash-exp",
            "claude-3-5-sonnet@20240620",
        ],
        get_api_key_url="https://console.cloud.google.com/vertex-ai",
        requires_auth=True,
    ),
    "xai": ProviderTemplate(
        id="xai",
        display_name="xAI (Grok)",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.x.ai/v1",
        env_key="XAI_API_KEY",
        models=["grok-2-vision-1212", "grok-vision-beta"],
        get_api_key_url="https://console.x.ai/",
        requires_auth=True,
    ),
    "xiaomi-mimo": ProviderTemplate(
        id="xiaomi-mimo",
        display_name="Xiaomi MiMo",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        # Pay-as-you-go OpenAI-compat surface. The Xiaomi Token Plan tier
        # uses `https://token-plan-cn.xiaomimimo.com/v1` (or `-sgp`/`-ams`
        # for Singapore/Europe) and a `tp-...` key.
        api_url="https://api.xiaomimimo.com/v1",
        env_key="MIMO_API_KEY",
        models=["mimo-v2.5-vl", "mimo-v2-vl-72b"],
        get_api_key_url="https://mimo.mi.com/",
        requires_auth=True,
    ),
    "zenmux": ProviderTemplate(
        id="zenmux",
        display_name="ZenMux",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://zenmux.ai/api/v1",
        env_key="ZENMUX_API_KEY",
        models=[],
        get_api_key_url="https://zenmux.ai/",
        requires_auth=True,
    ),
}


class ProviderManager:
    """Manages LLM provider configurations, templates, auto-discovery, and active provider selection."""

    def __init__(self, config_path: Path | str | None = None) -> None:
        if config_path is None:
            self._config_path = DEFAULT_CONFIG_PATH
        else:
            self._config_path = Path(config_path).expanduser().resolve()

        self._providers: dict[str, ProviderConfig] = {}
        self._active_provider_id: str = "openai"

        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """Initialize provider configurations from catalog, env vars, and disk storage."""
        # 1. Populate default provider configs from templates & env vars
        for tmpl in PROVIDER_TEMPLATES.values():
            env_key_val = os.getenv(tmpl.env_key) if tmpl.env_key else None
            env_host_val = os.getenv(tmpl.env_host) if tmpl.env_host else None

            api_url = (
                env_host_val.strip()
                if (env_host_val and env_host_val.strip())
                else tmpl.api_url
            )
            api_key = (
                env_key_val.strip() if (env_key_val and env_key_val.strip()) else None
            )

            configured = bool(api_key) if tmpl.requires_auth else True

            self._providers[tmpl.id] = ProviderConfig(
                id=tmpl.id,
                display_name=tmpl.display_name,
                format=tmpl.format,
                api_url=api_url,
                api_key=api_key,
                models=tmpl.models.copy(),
                get_api_key_url=tmpl.get_api_key_url,
                requires_auth=tmpl.requires_auth,
                configured=configured,
                enabled=True,
            )

        # 2. Load persisted config from file if present
        restored_from_disk = self._load_from_disk()

        # 3. Process LLM_API_BASE / LLM_API_KEY environment fallbacks if set
        llm_base = os.getenv("LLM_API_BASE")
        llm_key = os.getenv("LLM_API_KEY")

        if (
            llm_key
            and "openai" in self._providers
            and not self._providers["openai"].api_key
        ):
            self._providers["openai"].api_key = llm_key
            self._providers["openai"].configured = True

        if llm_base:
            if "localhost:1234" in llm_base and "lmstudio" in self._providers:
                self._providers["lmstudio"].api_url = llm_base
                self._providers["lmstudio"].configured = True
                if not restored_from_disk and not os.getenv(
                    "OMNISCRIBE_ACTIVE_PROVIDER"
                ):
                    self._active_provider_id = "lmstudio"
            elif "openai" in self._providers:
                self._providers["openai"].api_url = llm_base

        # 4. Resolve active provider fallback
        env_active = os.getenv("OMNISCRIBE_ACTIVE_PROVIDER") or os.getenv("PROVIDER_ID")
        if env_active and env_active in self._providers:
            self._active_provider_id = env_active
        elif self._active_provider_id not in self._providers:
            configured_ids = [p.id for p in self._providers.values() if p.configured]
            self._active_provider_id = configured_ids[0] if configured_ids else "openai"

    def _load_from_disk(self) -> bool:
        """Load persisted provider settings from YAML/JSON disk file."""
        if not self._config_path.exists():
            return False

        restored_active_id = False
        try:
            content = self._config_path.read_text(encoding="utf-8")
            if not content.strip():
                return False

            if self._config_path.suffix in (".yaml", ".yml"):
                data = yaml.safe_load(content)
            else:
                data = json.loads(content)

            if not isinstance(data, dict):
                return False

            providers_data = data.get("providers", {})
            if isinstance(providers_data, dict):
                for pid, pdict in providers_data.items():
                    if isinstance(pdict, dict):
                        try:
                            config = ProviderConfig.model_validate(pdict)
                            self._providers[config.id] = config
                        except Exception as exc:
                            logger.warning(
                                "Failed to validate provider config %s from disk: %s",
                                pid,
                                exc,
                            )

            active_id = data.get("active_provider_id")
            if (
                active_id
                and isinstance(active_id, str)
                and active_id in self._providers
            ):
                self._active_provider_id = active_id
                restored_active_id = True
        except Exception as exc:
            logger.warning(
                "Failed to load providers config from %s: %s",
                self._config_path,
                exc,
            )
        return restored_active_id

    def _save(self) -> None:
        """Persist active state and provider configurations to disk atomically."""
        try:
            parent_dir = self._config_path.parent
            parent_dir.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                with contextlib.suppress(Exception):
                    os.chmod(  # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
                        parent_dir, 0o700
                    )

            data = {
                "active_provider_id": self._active_provider_id,
                "providers": {
                    pid: p.model_dump(mode="json") for pid, p in self._providers.items()
                },
            }

            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=str(parent_dir),
                delete=False,
                encoding="utf-8",
                suffix=self._config_path.suffix,
            ) as tf:
                tmp_path = Path(tf.name)
                if self._config_path.suffix in (".yaml", ".yml"):
                    yaml.safe_dump(data, tf, sort_keys=False)
                else:
                    json.dump(data, tf, indent=2)

            if os.name != "nt":
                with contextlib.suppress(Exception):
                    os.chmod(tmp_path, 0o600)

            tmp_path.replace(self._config_path)
            if os.name != "nt":
                with contextlib.suppress(Exception):
                    os.chmod(self._config_path, 0o600)
        except Exception as exc:
            logger.error(
                "Failed to save providers config to %s: %s",
                self._config_path,
                exc,
            )

    def get_templates(self) -> list[ProviderTemplate]:
        """Return all provider templates in the catalog."""
        return list(PROVIDER_TEMPLATES.values())

    def get_providers(self) -> list[ProviderConfig]:
        """Return all registered provider configurations."""
        return list(self._providers.values())

    def get_provider(self, provider_id: str) -> ProviderConfig | None:
        """Return configuration for a given provider ID, or None if not found."""
        return self._providers.get(provider_id)

    def get_active_provider(self) -> ProviderConfig:
        """Return the currently active ProviderConfig."""
        provider = self._providers.get(self._active_provider_id)
        if provider:
            return provider
        if self._providers:
            first_id = next(iter(self._providers))
            self._active_provider_id = first_id
            return self._providers[first_id]

        # Fallback default if _providers is somehow empty
        default_config = ProviderConfig(
            id="openai",
            display_name="OpenAI",
            format=ProviderFormatEnum.OPENAI_COMPATIBLE,
            api_url="https://api.openai.com/v1",
            get_api_key_url="https://platform.openai.com/api-keys",
        )
        self._providers["openai"] = default_config
        self._active_provider_id = "openai"
        return default_config

    def set_active_provider(
        self, provider_id: str, model: str | None = None
    ) -> ProviderConfig:
        """Set the active provider ID and optionally update its active model."""
        if provider_id not in self._providers:
            raise ValueError(f"Provider '{provider_id}' not found")

        self._active_provider_id = provider_id
        provider = self._providers[provider_id]

        if model and model.strip():
            m = model.strip()
            if m in provider.models:
                provider.models.remove(m)
            provider.models.insert(0, m)

        self._save()

        # Sync with environment variables, .env file, and runtime config
        active_model = provider.models[0] if provider.models else ""
        env_updates: dict[str, Any] = {
            "LLM_API_BASE": provider.api_url,
            "LLM_MODEL": active_model,
        }
        if provider.api_key:
            env_updates["LLM_API_KEY"] = provider.api_key

        dotenv_target: Path | None = None
        if self._config_path.parent.is_dir():
            candidate = self._config_path.parent / ".env"
            if candidate.is_file():
                dotenv_target = candidate

        if "PYTEST_CURRENT_TEST" not in os.environ or dotenv_target is not None:
            from omniscribe.utils.env import update_dotenv

            update_dotenv(env_updates, dotenv_path=dotenv_target)

        try:
            from omniscribe.api.routers.config import _config

            _config["api_base"] = provider.api_url
            if active_model:
                _config["model"] = active_model
            if provider.api_key:
                _config["api_key"] = provider.api_key
        except Exception:
            pass

        return provider

    def save_provider(self, config: ProviderConfig) -> ProviderConfig:
        """Save or update a provider configuration."""
        existing = self._providers.get(config.id)
        if existing and config.api_key:
            k = config.api_key.strip()
            if k == "***" or "..." in k:
                config.api_key = existing.api_key

        if config.requires_auth:
            config.configured = bool(config.api_key and config.api_key.strip())
        else:
            config.configured = True

        self._providers[config.id] = config
        self._save()
        return config

    def create_provider(self, request: ProviderCreateRequest) -> ProviderConfig:
        """Create and register a new provider from a creation request."""
        configured = bool(
            (request.api_key and request.api_key.strip()) or not request.requires_auth
        )
        config = ProviderConfig(
            id=request.id,
            display_name=request.display_name,
            format=request.format,
            api_url=request.api_url,
            base_path=request.base_path,
            api_key=request.api_key,
            models=request.models.copy(),
            headers=request.headers.copy(),
            get_api_key_url=request.get_api_key_url,
            supports_streaming=request.supports_streaming,
            requires_auth=request.requires_auth,
            configured=configured,
            enabled=True,
        )
        return self.save_provider(config)

    def delete_provider(self, provider_id: str) -> bool:
        """Delete a provider configuration by ID."""
        if provider_id not in self._providers:
            return False

        del self._providers[provider_id]

        if self._active_provider_id == provider_id:
            remaining = list(self._providers.keys())
            self._active_provider_id = remaining[0] if remaining else "openai"

        self._save()
        return True

    def list_provider_models(self, provider_id: str) -> list[str]:
        """Fetch remote models for provider via HTTP or return cached list on error."""
        provider = self.get_provider(provider_id)
        if not provider:
            return []

        if not provider.api_url:
            return provider.models.copy()

        headers = dict(provider.headers)
        if provider.api_key:
            if provider.format == ProviderFormatEnum.ANTHROPIC_COMPATIBLE:
                headers["x-api-key"] = provider.api_key
                headers["anthropic-version"] = "2023-06-01"
            else:
                headers["Authorization"] = f"Bearer {provider.api_key}"

        base = provider.api_url.rstrip("/")
        candidate_urls: list[str] = []
        if provider.format == ProviderFormatEnum.OLLAMA_COMPATIBLE:
            candidate_urls.append(f"{base}/api/tags")
            candidate_urls.append(
                f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
            )
        else:
            if base.endswith("/v1"):
                candidate_urls.append(f"{base}/models")
            else:
                candidate_urls.append(f"{base}/v1/models")
                candidate_urls.append(f"{base}/models")
            if "11434" in base or "ollama" in base.lower() or "localhost" in base:
                candidate_urls.append(f"{base}/api/tags")

        try:
            import httpx

            with httpx.Client(timeout=5.0) as client:
                for url in candidate_urls:
                    try:
                        resp = client.get(url, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            fetched = extract_model_ids_from_response(data)
                            if fetched:
                                for m in fetched:
                                    if m not in provider.models:
                                        provider.models.append(m)
                                self._save()
                                return fetched
                    except Exception as exc:
                        logger.debug(
                            "Model discovery candidate %s failed for provider %s: %s",
                            url,
                            provider_id,
                            exc,
                        )
        except Exception as exc:
            logger.warning(
                "Failed to fetch models for provider '%s': %s",
                provider_id,
                exc,
            )

        return provider.models.copy()

    async def async_list_provider_models(self, provider_id: str) -> list[str]:
        """Async wrapper for list_provider_models."""
        return await asyncio.to_thread(self.list_provider_models, provider_id)


_provider_manager_instance: ProviderManager | None = None


def get_provider_manager(
    config_path: Path | str | None = None,
) -> ProviderManager:
    """Return singleton instance of ProviderManager."""
    global _provider_manager_instance
    if _provider_manager_instance is None or config_path is not None:
        _provider_manager_instance = ProviderManager(config_path=config_path)
    return _provider_manager_instance


def reset_provider_manager() -> None:
    """Reset the singleton ProviderManager instance (useful for unit tests)."""
    global _provider_manager_instance
    _provider_manager_instance = None


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "PROVIDER_TEMPLATES",
    "ProviderManager",
    "extract_model_ids_from_response",
    "get_provider_manager",
    "reset_provider_manager",
]
