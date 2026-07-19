"""Exception types for the LLM-based OCR processor."""

from __future__ import annotations


class LLMCallError(RuntimeError):
    """Raised when a call to the local LLM OCR endpoint fails.

    Wraps the underlying exception (connection refused, model not loaded,
    timeout, auth, ...) with a message that names the api-base and model
    so the user can diagnose without digging through a stack trace.
    """


class ModelNotLoadedError(LLMCallError):
    """Raised when the requested model is not loaded on the LLM server.

    LM Studio silently falls back to whatever model is currently loaded
    when an OpenAI-compat client requests an unavailable model ID — so a
    typo in --model or a forgotten model swap produces subtly wrong OCR
    output with no surface error. This exception is raised by
    :meth:`OCRProcessor.ensure_model_loaded` (and the grounded equivalent)
    *before* any OCR work starts so the user sees the mismatch immediately
    instead of debugging strange output later.
    """
