---
kind: build_system
name: Build System — uv + Hatch, Docker & GitHub Actions CI/CD
category: build_system
scope:
    - '**'
source_files:
    - pyproject.toml
    - Makefile
    - Dockerfile
    - compose.yaml
    - .github/workflows/test.yml
    - .github/workflows/nightly.yml
    - .github/workflows/release.yml
---

## What system/approach is used
LocalDeepL uses a modern Python build and packaging stack centered on **uv** (the fast Python package manager) for dependency resolution and environment management, **Hatchling** as the build backend for wheel/sdist creation, and **Docker** for containerized deployment. Continuous integration and release automation are implemented with **GitHub Actions** workflows that run linting, type checking, and two tiers of tests (fast and slow).

## Key files and packages
- `pyproject.toml` — project metadata, optional dependency groups (`web`, `async-translation`, `preprocessing`, `trocr`, `nllb`, `memory`, `quality`, `comet`), dev dependencies, pytest/ruff/mypy configuration, and Hatch build settings.
- `Makefile` — developer-facing entry points (`setup`, `run`, `test`, `lint`, `typecheck`, `clean`, `doctor`) all delegated to `uv run ...`.
- `Dockerfile` — multi-stage image: `runtime-base` installs `uv` and pinned deps; `app` copies source and runs `local-deepl-server`. Extras `web` and `async-translation` are baked in so one image serves both API and Celery worker.
- `compose.yaml` — local docker-compose stack with `api` (FastAPI), `worker` (Celery, profile `async`), and `redis` (broker/backend). Profiles control which services start.
- `.github/workflows/test.yml` — PR/push validation: ruff check/format, mypy, and `pytest -m "not slow"` across Python 3.11 and 3.13.
- `.github/workflows/nightly.yml` — scheduled slow-tier suite (`pytest -m slow`) with HF Hub cache for Surya model downloads.
- `.github/workflows/release.yml` — version-driven release: reads `version` from `pyproject.toml`, builds wheel+sdist via `uv build`, updates README pin, tags `vX.Y.Z`, and publishes a GitHub Release with artifacts.
- `scripts/dev.py` — referenced by `make clean` and `make doctor`; provides health checks for Python, uv, Redis, and model server.

## Architecture and conventions
- **Dependency management**: All environments use `uv sync` with explicit extras. The `web` extra pulls FastAPI/uvicorn/websockets; `async-translation` adds Celery/Redis/LangGraph; other features are opt-in (`trocr`, `nllb`, `memory`, `quality`, `comet`). An `override-dependencies` block forces `pillow>=11.3` to satisfy AVIF decoding needs despite `surya-ocr`'s older pin.
- **Packaging**: Hatchling produces wheels and sdists under `src/local_deepl`. The entry point `local-deepl-server = "local_deepl.server:main"` is installed into the venv and invoked directly by the Dockerfile CMD and `make run`.
- **Containerization**: A single image supports both synchronous HTTP serving and async translation workers. The non-root `app` user (uid 1001) is used at runtime. GPU/CUDA support is documented but intentionally out of scope.
- **CI strategy**: Two-tier testing separates quick feedback (PR/main, skipping `slow` and `live_llm`) from nightly deep validation that caches Hugging Face models. Concurrency groups cancel overlapping runs per branch/ref.
- **Release flow**: Version is the single source of truth in `pyproject.toml`. Merging a PR that bumps it triggers an automated release pipeline that validates PEP 440 format, ensures tag uniqueness, builds artifacts, and creates a GitHub Release.

## Conventions and constraints
- **Python versions**: `requires-python = ">=3.11"`; CI tests against 3.11 (floor) and 3.13. Ruff targets `py311`.
- **Linting/formatting**: Ruff enforces E/W/F/I/B/C4/UP/SIM/RUF/G rules with specific per-file ignores for pre-existing violations and test code. Line length 88, handled by formatter.
- **Type checking**: mypy configured with strict flags; `local_deepl.core.*` requires explicit annotations (`disallow_untyped_defs = true`).
- **Testing markers**: `slow` (loads Surya models, ~5s first run) and `live_llm` (hits real LLM endpoint) are defined in pytest config and skipped in fast CI.
- **Environment variables**: Docker Compose sets defaults like `LLM_API_BASE`, `LOCAL_DEEPL_MAX_UPLOAD_MB`, `LOCAL_DEEPL_RATE_LIMIT_PER_MIN`; auth token is opt-in via `LOCAL_DEEPL_AUTH_TOKEN`.
- **Security**: Container drops root, binds to `0.0.0.0` by default (documented to change to `127.0.0.1` behind reverse proxy), and uses a dedicated `app` user/group.