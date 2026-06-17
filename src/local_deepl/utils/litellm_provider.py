LITELLM_KNOWN_PREFIXES = (
    "openai/",
    "anthropic/",
    "gemini/",
    "deepseek/",
    "groq/",
    "vertex_ai/",
    "ollama/",
    "huggingface/",
    "vllm/",
    "bedrock/",
    "sagemaker/",
    "azure/",
    "together_ai/",
    "replicate/",
    "mistral/",
    "cohere/",
)


def resolve_custom_provider(model: str) -> str | None:
    if model.startswith(LITELLM_KNOWN_PREFIXES):
        return None
    return "openai"
