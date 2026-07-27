---
kind: configuration_system
name: Environment-Driven Configuration System with Runtime Hot-Swap
category: configuration_system
scope:
    - '**'
source_files:
    - .env.example
    - src/local_deepl/server.py
    - src/local_deepl/api/services/security_config.py
    - src/local_deepl/core/translation_config.py
    - src/local_deepl/api/routers/config.py
    - compose.yaml
---

LocalDeepL uses a layered, environment-variable-driven configuration system centered on `python-dotenv` and in-memory settings objects. There is no centralized config file format; instead, every runtime knob is exposed as an environment variable, loaded at startup and optionally hot-swapped via the `/api/config` endpoint.

**Loading order and sources**
- `.env` files are loaded via `dotenv.load_dotenv()` at module import time (`server.py` line 16), so any `.env` next to the source or project root is picked up automatically.
- The `.env.example` template documents every supported variable with safe local-development defaults and comments explaining each setting's purpose.
- Docker Compose (`compose.yaml`) injects production-oriented defaults (e.g. `LLM_API_BASE=http://host.docker.internal:1234/v1`, rate limiting) directly into the container environment.
- CLI arguments (`--host`, `--port`, `--reload`) parsed by `argparse` in `server.main()` override only the server bind address/port.

**Settings models**
- `SecuritySettings` (`src/local_deepl/api/services/security_config.py`) is a frozen dataclass built from `LOCAL_DEEPL_*` env vars (`AUTH_TOKEN`, `CORS_ORIGINS`, `MAX_UPLOAD_MB`, `RATE_LIMIT_PER_MIN`). It enforces hard caps (absolute max upload 1024 MB) and clamps invalid values with warnings.
- `TranslationSettings` (`src/local_deepl/core/translation_config.py`) reads `LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL` with typed validation and provides both `from_env()` and `from_mapping()` constructors.
- A global in-memory `_config` dict in `src/local_deepl/api/routers/config.py` holds all OCR/runtime knobs (concurrency, DPI, dense mode, pipeline mode, preprocessing toggles, etc.) initialized from `OCR_*` and `LLM_*` env vars.

**Runtime hot-swap API**
The `/api/config` GET endpoint returns the current configuration (with `api_key` masked unless it equals the default `lm-studio`), and POST accepts partial updates through a Pydantic `ConfigUpdate` schema. Unknown keys and wrong types are rejected by validation rather than silently ignored. SSRF protection blocks unsafe `api_base` URLs via `utils.security.is_ssrf_target`. This makes the entire OCR pipeline tunable without restart.

**Middleware wiring**
At app creation (`create_app()` in `server.py`), `SecuritySettings.from_env()` drives middleware registration:
- `BearerAuthMiddleware` for token-based auth when `LOCAL_DEEPL_AUTH_TOKEN` is set
- `MaxUploadSizeMiddleware` using the capped `max_upload_bytes`
- `RateLimitMiddleware` when `LOCAL_DEEPL_RATE_LIMIT_PER_MIN > 0`
- Optional CORS middleware when `LOCAL_DEEPL_CORS_ORIGINS` is non-empty

**Conventions and constraints**
- All new configuration knobs follow the documented pattern: add a parser helper (`_env_str`, `_env_int`, `_env_bool`, `_env_list_csv`), add a field to the relevant dataclass, wire it in `from_env()`, and use it during middleware/app setup.
- Environment variables are consistently prefixed: `LOCAL_DEEPL_*` for security/web settings, `OCR_*` for pipeline behavior, `LLM_*` for VLM endpoints, and `REDIS_URL` for async translation.
- Defaults are intentionally permissive for local development (no auth, same-origin CORS, generous upload limits) and must be tightened explicitly for public exposure.
- Invalid numeric/env values are logged as warnings and fall back to defaults rather than crashing the process.