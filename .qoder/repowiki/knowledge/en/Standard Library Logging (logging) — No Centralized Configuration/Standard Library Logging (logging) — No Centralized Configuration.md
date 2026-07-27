---
kind: logging_system
name: Standard Library Logging (logging) — No Centralized Configuration
category: logging_system
scope:
    - '**'
source_files:
    - src/local_deepl/server.py
    - scripts/visualize_comparison.py
    - src/local_deepl/api/routers/ocr.py
    - src/local_deepl/core/ocr/resilience.py
---

The repository uses Python's standard library `logging` module exclusively. There is no centralized logging configuration, no third-party logging framework (loguru, structlog, etc.), and no dedicated logging module.

**How it works:**
- Every module that needs to log creates a logger via `logger = logging.getLogger(__name__)` at module scope. This produces hierarchical loggers named after the importing module (e.g., `local_deepl.api.routers.ocr`, `local_deepl.core.ocr.resilience`).
- Log messages are emitted through the usual level methods: `logger.info(...)`, `logger.warning(...)`, `logger.error(...)`, `logger.exception(...)`, and `logger.debug(...)`.
- The only place where logging is configured is in `scripts/visualize_comparison.py`, which calls `logging.basicConfig(level=logging.INFO)` before use. The main FastAPI server (`src/local_deepl/server.py`) does not configure logging at all; it delegates to uvicorn's default handler when run via `uvicorn.run(...)`.

**Architecture & conventions:**
- Logger instances are module-local variables, following the standard Python pattern of one logger per module.
- There is no shared `__init__.py` logger, no custom formatter, no file handlers, and no structured log fields. Output goes to stderr by default (via root logger or uvicorn's handler).
- One exception: `core/postprocess.py` explicitly names its logger `pdf_ocr.postprocess` rather than using `__name__`, likely for historical reasons.

**Constraints observed:**
- No environment variable controls log level or output destination within the application code itself.
- No central config file or CLI flag adjusts logging verbosity at runtime.
- Error paths consistently use `logger.exception(...)` to include tracebacks; warnings use `logger.warning(...)` with descriptive messages.