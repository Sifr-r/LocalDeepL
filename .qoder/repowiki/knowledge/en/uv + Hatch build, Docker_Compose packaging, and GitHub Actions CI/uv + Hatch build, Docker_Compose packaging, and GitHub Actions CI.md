---
kind: build_system
name: uv + Hatch build, Docker/Compose packaging, and GitHub Actions CI
category: build_system
scope:
    - '**'
source_files:
    - pyproject.toml
    - Dockerfile
    - compose.yaml
    - .github/workflows/test.yml
    - .github/workflows/nightly.yml
    - .github/workflows/release.yml
---

LocalDeepL uses a modern Python toolchain centered on uv for dependency resolution/installation, Hatchling as the PEP 517 build backend, and Docker/Compose for containerized deployment. CI is implemented with three GitHub Actions workflows covering fast lint/type/test, nightly slow-end-to-end runs, and version-driven releases.

Build and packaging:
- Dependency management: pyproject.toml declares core dependencies plus optional extras (web, async-translation, memory, trocr, nllb, quality, comet). uv.lock pins every transitive dep; tool.uv.override-dependencies forces Pillow >=11.3 to satisfy surya-ocr's implicit requests import while enabling native AVIF decoding.
- Build backend: hatchling.build produces wheel and sdist via [build-system]; [tool.hatch.build.targets.wheel] packages src/local_deepl only, and [tool.hatch.build.targets.sdist] whitelists source, README, LICENSE, and pyproject.
- Installable entry point: [project.scripts.local-deepl-server] = "local_deepl.server:main" exposes the CLI used by the Docker CMD.
- Dev extras: [dependency-groups.dev] groups pytest, ruff, mypy, pyyaml for local dev.

Containerization:
- Multi-stage Dockerfile: Stage 1 installs uv and the pinned deps (with --extra web --extra async-translation --no-install-project) so the dependency layer is cacheable independent of source; stage 2 copies src/ and completes installation. Runs as non-root user app:app, exposes port 8000, and defaults to local-deepl-server --host 0.0.0.0 --port 8000.
- docker-compose stack (compose.yaml): Three services - api (FastAPI), worker (Celery worker, profile async), and redis (broker/backend). The API depends on redis health, sets default env vars (LLM_API_BASE, upload/rate-limit headers), and uses extra_hosts to reach host-local LM Studio/Ollama at host.docker.internal:1234/v1.

CI pipelines (GitHub Actions):
- test.yml (fast tier): On push to main / PRs, runs on Python 3.11 and 3.13 matrix. Steps: uv sync --extra web, ruff check src tests --no-fix, mypy src, then pytest -m "not slow". Skips slow (Surya model download) and live_llm markers.
- nightly.yml (slow tier): Cron at 03:00 UTC (+ manual dispatch). Installs both web and async-translation extras, caches ~/.cache/huggingface keyed by Python version, runs pytest -m slow --no-header -v, uploads .pytest_cache/v/cache/lastfailed artifact on failure.
- release.yml (version-driven): Triggered when pyproject.toml changes on main or via workflow_dispatch. Reads version from pyproject, validates PEP 440, checks tag uniqueness, builds wheel+sdist via uv build, updates any @vX.Y.Z pin in README.md, commits if changed, tags v<version>, pushes, and publishes a GitHub release with artifacts attached.

Conventions developers should follow:
- Keep pyproject.toml as the single source of truth for version, dependencies, and extras; bump version there to trigger a release.
- Use uv sync --extra <name> locally matching the extras installed in CI to avoid environment drift.
- Mark long-running or network-dependent tests with @pytest.mark.slow or @pytest.mark.live_llm so they are skipped in the fast tier.
- New optional features belong in their own [project.optional-dependencies] extra rather than being added to core deps.
- When adding new CLI entry points, register them under [project.scripts] so the Docker image can invoke them.