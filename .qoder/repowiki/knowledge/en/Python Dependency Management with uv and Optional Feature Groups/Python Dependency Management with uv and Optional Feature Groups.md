---
kind: dependency_management
name: Python Dependency Management with uv and Optional Feature Groups
category: dependency_management
scope:
    - '**'
source_files:
    - pyproject.toml
    - uv.lock
    - Dockerfile
    - compose.yaml
    - Makefile
---

This project manages Python dependencies using **uv** as the primary package manager, with a `pyproject.toml` manifest and a committed `uv.lock` lockfile for reproducible installs. The build system uses **hatchling** as the backend, and the project targets Python ≥3.11 (with classifiers for 3.11–3.13).

**Core dependency declaration**: All runtime dependencies are declared in `[project.dependencies]` in `pyproject.toml`, including OCR engines (`surya-ocr>=0.17.0`, `torch>=2.0.0`, `torchvision>=0.15.0`), PDF handling (`pymupdf>=1.26.7`, `pillow>=11.3`), and LLM clients (`openai>=2.11.0`). Transitive dependency gaps are explicitly patched — for example, `requests>=2.31` is listed because `surya-ocr` imports it without declaring it.

**Optional feature groups**: Dependencies are split into optional extras via `[project.optional-dependencies]` to keep the base install minimal:
- `web`: FastAPI, uvicorn, websockets, python-multipart
- `preprocessing`: opencv-python-headless, numpy
- `async-translation`: celery, redis, langgraph (intentionally excludes chromadb/sentence-transformers to avoid heavy torch deps)
- `memory`: chromadb, sentence-transformers (lexicon-backed RAG)
- `trocr` / `nllb`: transformers + sentencepiece for specialized OCR/translation fallbacks
- `quality` / `comet`: translation scoring metrics

**Dependency overrides**: The `[tool.uv]` section declares `override-dependencies = ["pillow>=11.3"]` to force Pillow ≥11.3 despite `surya-ocr 0.17.x` pinning `<11`. This override is reflected in the lockfile's `[manifest].overrides` section.

**Lockfile strategy**: `uv.lock` pins every transitive dependency with exact versions and SHA256 hashes across multiple platform markers (Darwin, Linux x86_64/aarch64, Windows, Android, iOS). It enforces `requires-python = ">=3.11"` and includes resolution markers for different Python/platform combinations.

**Development dependencies**: Declared under `[dependency-groups].dev` (pytest, pytest-asyncio, ruff, mypy, pyyaml) and installed via `uv sync --extra web` or `make setup`.

**Containerization**: The multi-stage `Dockerfile` copies `pyproject.toml` and `uv.lock` first, runs `uv sync --no-install-project` to cache dependencies, then copies source and completes installation. Both `web` and `async-translation` extras are baked into the image by default.

**CI/CD integration**: GitHub Actions workflows (`nightly.yml`, `release.yml`, `test.yml`) use `uv` for dependency resolution. The `Makefile` wraps common commands (`setup`, `run`, `test`, `lint`, `typecheck`, `clean`, `doctor`) through `uv run`.

**No vendoring**: There is no `vendor/` directory or pip `-r requirements.txt` files; all third-party code is resolved from PyPI at install time via uv.