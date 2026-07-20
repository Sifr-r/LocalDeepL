---
kind: configuration_system
name: Environment-Driven Runtime Configuration with In-Memory Hot Reload
category: configuration_system
scope:
    - '**'
source_files:
    - src/local_deepl/server.py
    - src/local_deepl/api/services/security_config.py
    - src/local_deepl/api/routers/config.py
    - src/local_deepl/core/translation_config.py
    - src/local_deepl/api/celery_app.py
    - compose.yaml
---

LocalDeepL uses a lightweight, environment-driven configuration system built on `python-dotenv` and plain Python dataclasses. There is no centralized config file format (YAML/JSON/TOML) consumed at startup; instead, every runtime knob is read from the process environment, optionally preloaded from a `.env` file, and exposed through a small in-memory store that can be mutated at runtime via the `/api/config` endpoint.

### What system/approach is used
- **`.env` loading**: `dotenv.load_dotenv()` is called early in `server.py` and again in `core/ocr/processor.py`, so any `.env` file present in the working directory is automatically picked up.
- **Environment variables as source of truth**: All settings are read via `os.getenv(...)`. No Pydantic `BaseSettings` or dedicated config parser is used — each module defines its own small helpers (`_env_int`, `_env_bool`, `_env_list_csv`) to parse values with defaults and validation.
- **In-memory mutable config store**: A module-level `_config: RuntimeConfigDict` dictionary in `src/local_deepl/api/routers/config.py` holds OCR + translation knobs. It is initialized once from env vars and updated live by POSTing to `/api/config`.
- **Typed boundaries for downstream consumers**: Two frozen dataclasses wrap subsets of the config:
  - `SecuritySettings` (`api/services/security_config.py`) — app-wide security knobs (`LOCAL_DEEPL_*`).
  - `TranslationSettings` (`core/translation_config.py`) — OpenAI-compatible endpoint knobs (`LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL`).
- **Docker Compose as deployment-time config**: `compose.yaml` demonstrates the intended production posture by setting `LLM_API_BASE`, `LOCAL_DEEPL_MAX_UPLOAD_MB`, `LOCAL_DEEPL_RATE_LIMIT_PER_MIN`, and an optional `LOCAL_DEEPL_AUTH_TOKEN`.

### Key files and packages
- `src/local_deepl/server.py` — top-level entry point; calls `load_dotenv()` before importing anything else, wires `SecuritySettings.from_env()` into middleware.
- `src/local_deepl/api/services/security_config.py` — `SecuritySettings` dataclass with `from_env()`, parsing `LOCAL_DEEPL_AUTH_TOKEN`, `LOCAL_DEEPL_CORS_ORIGINS`, `LOCAL_DEEPL_MAX_UPLOAD_MB`, `LOCAL_DEEPL_RATE_LIMIT_PER_MIN`.
- `src/local_deepl/api/routers/config.py` — in-memory `_config` dict, GET/POST `/api/config`, GET `/api/models`; also re-imports `load_dotenv()`.
- `src/local_deepl/core/translation_config.py` — `TranslationSettings` dataclass with `from_env()` / `from_mapping()`.
- `src/local_deepl/api/celery_app.py` — reads `REDIS_URL` from env for Celery broker/backend.
- `compose.yaml` — example environment overrides for LLM base URL, upload cap, rate limit, auth token.
- `src/local_deepl/core/ocr/processor.py` — calls `load_dotenv()` so OCR pipeline honors `.env` even when invoked outside the web server.

### Architecture and conventions
1. **Single dotenv load per import path** — `server.py` loads `.env` first; other modules that need it call `load_dotenv()` again (idempotent). This lets both the CLI scripts and the web server pick up `.env`.
2. **Naming convention for env vars**:
   - App-wide security knobs use the `LOCAL_DEEPL_*` prefix.
   - LLM/OpenAI-compatible endpoint knobs use `LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL`.
   - OCR pipeline knobs use the `OCR_*` prefix (e.g. `OCR_DENSE_MODE`, `OCR_CONCURRENCY`, `OCR_PIPELINE_MODE`, `OCR_SPELLCHECK`).
3. **Defaults are baked into code**, not files. Each setting has a sensible local-dev default (e.g. `http://localhost:1234/v1` for `LLM_API_BASE`, `lm-studio` for key), so the app runs out-of-the-box without any env var.
4. **Runtime mutability**: The `/api/config` POST endpoint updates the in-memory `_config` dict in place, so changes take effect immediately without restart. Sensitive fields like `api_key` are masked on GET responses.
5. **SSRF guard on mutable endpoints**: Updating `api_base` or querying `/api/models` runs the value through `is_ssrf_target()` to reject localhost/private-range URLs, preventing accidental self-referential configuration.
6. **Celery worker config is separate**: `api/celery_app.py` reads `REDIS_URL` directly from env; there is no shared config object between the FastAPI process and the Celery worker — they must agree on env layout.

### Rules developers should follow
- **Add new env-driven knobs by following the existing pattern**: define a small `_env_<type>` helper if needed, add the field to the relevant dataclass (`SecuritySettings` or `TranslationSettings`), document it in the docstring, and wire it into the in-memory `_config` dict if it should be hot-reloadable via `/api/config`.
- **Use the `LOCAL_DEEPL_*` prefix for app-wide security/runtime knobs**; use `LLM_*` for LLM endpoint settings; use `OCR_*` for pipeline tuning flags. Keep them out of code unless they are truly compile-time constants.
- **Never hard-code secrets**. If a secret is required, read it from env with a clear default and surface it through the typed settings class.
- **When adding a new setting that affects async workers**, remember to update `api/celery_app.py` separately — the worker does not share the in-memory `_config` dict.
- **Validate aggressively**: prefer `_env_int` / `_env_bool` helpers that log warnings on invalid input rather than letting `int()` / `bool()` raise uncaught exceptions at boot time.