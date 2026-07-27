---
kind: error_handling
name: Error Handling Strategy in LocalDeepL
category: error_handling
scope:
    - '**'
source_files:
    - src/local_deepl/core/ocr/exceptions.py
    - src/local_deepl/api/services/security_middleware.py
    - src/local_deepl/core/ocr/resilience.py
    - src/local_deepl/api/services/security.py
    - src/local_deepl/api/routers/common.py
    - src/local_deepl/api/routers/ocr.py
    - src/local_deepl/api/services/ocr_response.py
---

LocalDeepL employs a layered error handling strategy that combines custom exception types, ASGI middleware guards, and structured HTTP responses across its FastAPI web server and OCR pipeline.

**Custom Exception Types**
The codebase defines domain-specific exceptions rather than relying on generic Python exceptions:
- `LLMCallError` and `ModelNotLoadedError` in `src/local_deepl/core/ocr/exceptions.py` wrap LLM endpoint failures with diagnostic messages that include the API base URL and model information, making debugging straightforward without sifting through stack traces.
- `UploadValidationError` in `src/local_deepl/api/services/security.py` extends `ValueError` with an attached `status_code` attribute for consistent HTTP error responses during file upload validation.
- `CircuitOpenError` in `src/local_deepl/core/ocr/resilience.py` signals when the circuit breaker is open due to consecutive failures, distinguishing infrastructure-level failures from per-page OCR errors.

**ASGI Middleware Guards**
Three dedicated middlewares in `src/local_deepl/api/services/security_middleware.py` enforce security constraints at the ASGI layer before FastAPI routing:
- `BearerAuthMiddleware` rejects unauthorized requests using constant-time token comparison
- `MaxUploadSizeMiddleware` prevents memory exhaustion by checking Content-Length before reading request bodies
- `RateLimitMiddleware` implements per-IP rate limiting with a sliding window

These middlewares return standardized JSON error responses (`{"error": "..."}`) with appropriate HTTP status codes (401, 413, 429).

**Structured HTTP Responses**
The application uses consistent response patterns:
- Validation errors return 422 with detailed Pydantic error information via `_validation_error_response()`
- Upload validation errors use `UploadValidationError` with embedded status codes
- Server errors return a stable message via `_stable_server_error()` to avoid leaking internal details
- The `SERVER_ERROR_MESSAGE` constant provides user-friendly error text

**Resilience Patterns**
The OCR pipeline implements sophisticated error resilience:
- `is_transient_error()` classifies exceptions as retryable based on HTTP status codes (429, 500, 502, 503, 504) and error message patterns
- `CircuitBreaker` prevents cascading failures by failing fast when downstream services are down
- Per-page error isolation allows partial document processing even when some pages fail

**Router-Level Error Handling**
FastAPI routers catch specific exception types and convert them to appropriate HTTP responses. The main OCR endpoint handles `ValidationError`, `UploadValidationError`, `ValueError`, and generic `Exception` cases, each with proper cleanup of temporary files and job history recording.

**Configuration-Driven Behavior**
Error behavior is tunable through environment variables like `LOCAL_DEEPL_LLM_MAX_RETRIES`, `LOCAL_DEEPL_CB_FAILURE_THRESHOLD`, and `LOCAL_DEEPL_CB_COOLDOWN`, allowing deployments to adapt error handling without code changes.