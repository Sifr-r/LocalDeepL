---
kind: error_handling
name: Structured Exception Hierarchy with ASGI Middleware and Stable API Responses
category: error_handling
scope:
    - '**'
source_files:
    - src/local_deepl/core/ocr/exceptions.py
    - src/local_deepl/api/services/security.py
    - src/local_deepl/api/services/security_middleware.py
    - src/local_deepl/api/routers/ocr.py
    - src/local_deepl/api/routers/common.py
    - src/local_deepl/server.py
---

LocalDeepL uses a layered error-handling strategy that combines domain-specific exception types, per-route try/except blocks in FastAPI routers, and thin ASGI middleware for security- and transport-level failures. The approach is deliberately shallow — there is no global exception handler; instead each endpoint catches the exceptions it knows about and returns stable JSON responses.

Exception hierarchy:
- LLMCallError (subclass of RuntimeError) wraps any failure talking to the local OpenAI-compatible LLM server (connection refused, timeout, auth). It carries a diagnostic message naming api_base and model so callers can surface actionable text.
- ModelNotLoadedError (subclass of LLMCallError) raised when the configured model ID is not loaded on the remote server. This is checked before OCR work starts via _list_loaded_model_ids / verify_backend_model, preventing silent LM Studio fallbacks.
- UploadValidationError (subclass of ValueError) carries an HTTP status code (400, 413, 415) alongside a user-facing message; thrown by save_validated_upload and detect_upload_suffix.

These are defined in src/local_deepl/core/ocr/exceptions.py and src/local_deepl/api/services/security.py.

Router-level handling: The OCR /process endpoint (src/local_deepl/api/routers/ocr.py) is the canonical example. It catches pydantic.ValidationError and returns a structured validation response, checks SSRF targets and returns 403 with SAFE_API_BASE_ERROR, catches UploadValidationError and returns its embedded status_code, catches ValueError from the pipeline as 400 Invalid input, and falls through to a bare Exception handler that logs via logger.exception, records the job as error, then returns _stable_server_error() which always yields {"error": SERVER_ERROR_MESSAGE} regardless of the underlying traceback. This pattern ensures clients never see stack traces or internal class names.

ASGI middleware layer: Three middlewares in src/local_deepl/api/services/security_middleware.py intercept requests before routing. BearerAuthMiddleware rejects missing/mismatched Authorization headers with 401 Unauthorized. MaxUploadSizeMiddleware checks Content-Length against max_bytes and replies 413 without buffering the body. RateLimitMiddleware enforces per-IP fixed-window limits and replies 429. They write raw ASGI responses directly so they run even if dependency loading fails.

Server bootstrap: src/local_deepl/server.py wraps optional imports in _load_optional_module, catching ModuleNotFoundError and re-raising as RuntimeError with a human-readable hint about installing [web] extras. The CLI entrypoint converts that into SystemExit so a missing dependency produces a clean exit code rather than a Python traceback.

Conventions developers should follow:
1. Define new domain errors as subclasses of existing base types (LLMCallError, UploadValidationError) rather than raising bare Exception.
2. Catch known exceptions at the router boundary and return JSONResponse with a single "error" key whose value is one of the documented constants (SAFE_API_BASE_ERROR, SERVER_ERROR_MESSAGE) or a short user-facing string.
3. Never log or expose internal traceback details over the wire; use logger.exception inside the catch-all branch and still return the stable 500 response.
4. For configuration/validation failures, raise pydantic.ValidationError or custom ValueError subclasses carrying a status_code attribute.
5. Prefer pre-flight checks (model-loaded verification, SSRF target check) that raise descriptive exceptions early, so expensive work is never started on invalid inputs.