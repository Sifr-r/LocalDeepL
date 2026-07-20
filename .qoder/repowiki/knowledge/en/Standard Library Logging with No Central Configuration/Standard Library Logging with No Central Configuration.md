---
kind: logging_system
name: Standard Library Logging with No Central Configuration
category: logging_system
scope:
    - '**'
source_files:
    - src/local_deepl/server.py
    - pyproject.toml
    - scripts/visualize_comparison.py
---

The project uses Python's built-in `logging` module exclusively — no third-party logging frameworks (loguru, structlog, etc.) are installed or configured. There is no centralized logger setup: no `logging.basicConfig()` call in the application entry point (`src/local_deepl/server.py`), no `LOGGING_CONFIG` dict, and no environment variable like `LOG_LEVEL` wired into the FastAPI app or Celery workers. Loggers are created per-module via the standard `logger = logging.getLogger(__name__)` pattern, and each module calls `logger.debug/info/warning/error/exception` directly.

Key observations:
- **No global configuration**: The server process relies on Python's default logging configuration (which routes to stderr at WARNING level). Only a standalone dev script (`scripts/visualize_comparison.py`) explicitly calls `logging.basicConfig(level=logging.INFO)`.
- **Per-module loggers**: Every router, service, and core module creates its own logger instance using `logging.getLogger(__name__)`, giving hierarchical names like `local_deepl.api.routers.ocr`.
- **Level usage**: `warning` and `exception` are used most frequently for error paths; `info` appears in Celery tasks; `debug` is used sparingly inside parsers.
- **Format style**: Most calls use `%s` formatting (consistent with ruff rule G004 being ignored in pyproject.toml), though some places still use f-strings despite the rule.
- **Structured fields**: None — all messages are plain strings with positional arguments, not JSON or key-value pairs.
- **Sinks**: All output goes to stderr via the default StreamHandler; there are no file handlers, rotating handlers, or external sinks configured anywhere in the codebase.