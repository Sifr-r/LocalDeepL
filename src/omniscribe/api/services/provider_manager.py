"""Provider Manager service for OmniScribe based on the Goose API handling specification."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import yaml

from omniscribe.api.schemas.requests import (
    ProviderConfig,
    ProviderCreateRequest,
    ProviderFormatEnum,
    ProviderTemplate,
)

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("~/.config/omniscribe/providers.yaml").expanduser()

PROVIDER_TEMPLATES: dict[str, ProviderTemplate] = {
    "openai": ProviderTemplate(
        id="openai",
        display_name="OpenAI",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.openai.com/v1",
        env_key="OPENAI_API_KEY",
        models=["gpt-4o", "gpt-4o-mini", "o1", "o3-mini"],
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
        requires_auth=True,
    ),
    "groq": ProviderTemplate(
        id="groq",
        display_name="Groq",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.groq.com/openai/v1",
        env_key="GROQ_API_KEY",
        models=["llama-3.2-90b-vision-preview", "llama-3.2-11b-vision-preview"],
        requires_auth=True,
    ),
    "deepseek": ProviderTemplate(
        id="deepseek",
        display_name="DeepSeek",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.deepseek.com/v1",
        env_key="DEEPSEEK_API_KEY",
        models=["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
        requires_auth=True,
    ),
    "minimax": ProviderTemplate(
        id="minimax",
        display_name="MiniMax",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.minimax.io/v1",
        env_key="MINIMAX_API_KEY",
        models=["MiniMax-M3", "MiniMax-Text-01"],
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
        display_name="Alibaba Cloud Model Studio - China",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        env_key="DASHSCOPE_API_KEY",
        models=["qwen-vl-max", "qwen2.5-vl-72b-instruct", "qwen2.5-vl-7b-instruct"],
        requires_auth=True,
    ),
    "alibaba-singapore": ProviderTemplate(
        id="alibaba-singapore",
        display_name="Alibaba Cloud Model Studio - Singapore",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        env_key="DASHSCOPE_API_KEY",
        models=["qwen-vl-max", "qwen2.5-vl-72b-instruct"],
        requires_auth=True,
    ),
    "alibaba-us": ProviderTemplate(
        id="alibaba-us",
        display_name="Alibaba Cloud Model Studio - America",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://dashscope-us.aliyuncs.com/compatible-mode/v1",
        env_key="DASHSCOPE_API_KEY",
        models=["qwen-vl-max", "qwen2.5-vl-72b-instruct"],
        requires_auth=True,
    ),
    "zai-china": ProviderTemplate(
        id="zai-china",
        display_name="Z.ai - China (Zhipu BigModel)",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://open.bigmodel.cn/api/paas/v4",
        env_key="ZHIPU_API_KEY",
        models=["glm-4v-flash", "glm-4v-plus", "glm-4v"],
        requires_auth=True,
    ),
    "zai-international": ProviderTemplate(
        id="zai-international",
        display_name="Z.ai - International",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.z.ai/v1",
        env_key="ZHIPU_API_KEY",
        models=["glm-4v-flash", "glm-4v-plus"],
        requires_auth=True,
    ),
    "kimi": ProviderTemplate(
        id="kimi",
        display_name="Kimi (Moonshot AI)",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.moonshot.cn/v1",
        env_key="MOONSHOT_API_KEY",
        models=["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        requires_auth=True,
    ),
    "minimax-china": ProviderTemplate(
        id="minimax-china",
        display_name="MiniMax - China",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.minimax.chat/v1",
        env_key="MINIMAX_API_KEY",
        models=["minimax-text-01", "abab6.5s-chat"],
        requires_auth=True,
    ),
    "minimax-international": ProviderTemplate(
        id="minimax-international",
        display_name="MiniMax - International",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.minimaxi.com/v1",
        env_key="MINIMAX_API_KEY",
        models=["minimax-text-01"],
        requires_auth=True,
    ),
    "google-gemini": ProviderTemplate(
        id="google-gemini",
        display_name="Google Gemini",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        env_key="GEMINI_API_KEY",
        models=["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"],
        requires_auth=True,
    ),
    "siliconflow": ProviderTemplate(
        id="siliconflow",
        display_name="SiliconFlow (SiliconCloud)",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.siliconflow.cn/v1",
        env_key="SILICONFLOW_API_KEY",
        models=["Qwen/Qwen2.5-VL-72B-Instruct", "deepseek-ai/DeepSeek-V3"],
        requires_auth=True,
    ),
    "mistral": ProviderTemplate(
        id="mistral",
        display_name="Mistral AI",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.mistral.ai/v1",
        env_key="MISTRAL_API_KEY",
        models=["pixtral-12b-2409", "pixtral-large-2411"],
        requires_auth=True,
    ),
    "novita": ProviderTemplate(
        id="novita",
        display_name="Novita AI",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.novita.ai/v3/openai",
        env_key="NOVITA_API_KEY",
        models=["qwen/qwen-2.5-vl-72b-instruct"],
        requires_auth=True,
    ),
    "together": ProviderTemplate(
        id="together",
        display_name="Together AI",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_url="https://api.together.xyz/v1",
        env_key="TOGETHER_API_KEY",
        models=["meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo"],
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
        """Persist active state and provider configurations to disk."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "active_provider_id": self._active_provider_id,
                "providers": {
                    pid: p.model_dump(mode="json") for pid, p in self._providers.items()
                },
            }

            if self._config_path.suffix in (".yaml", ".yml"):
                with open(self._config_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, sort_keys=False)
            else:
                with open(self._config_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
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
        return provider

    def save_provider(self, config: ProviderConfig) -> ProviderConfig:
        """Save or update a provider configuration."""
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

        url: str
        if provider.format == ProviderFormatEnum.OLLAMA_COMPATIBLE:
            url = f"{provider.api_url.rstrip('/')}/api/tags"
        else:
            base = provider.api_url.rstrip("/")
            url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"

        try:
            import httpx

            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    fetched_models: list[str] = []
                    if provider.format == ProviderFormatEnum.OLLAMA_COMPATIBLE:
                        models_list = data.get("models", [])
                        if isinstance(models_list, list):
                            for item in models_list:
                                if isinstance(item, dict):
                                    name = item.get("name") or item.get("model")
                                    if name:
                                        fetched_models.append(str(name))
                                elif isinstance(item, str):
                                    fetched_models.append(item)
                    else:
                        models_list = data.get("data", [])
                        if isinstance(models_list, list):
                            for item in models_list:
                                if isinstance(item, dict) and "id" in item:
                                    fetched_models.append(str(item["id"]))
                                elif isinstance(item, str):
                                    fetched_models.append(item)

                    if fetched_models:
                        for m in fetched_models:
                            if m not in provider.models:
                                provider.models.append(m)
                        self._save()
                        return fetched_models
        except Exception as exc:
            logger.warning(
                "Failed to fetch models for provider '%s' at '%s': %s",
                provider_id,
                url,
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
