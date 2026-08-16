.DEFAULT_GOAL := help

.PHONY: help setup run build-frontend test lint typecheck audit clean doctor

help: ## Show available developer commands
	@uv run python -c "print('Available targets:\\n  help           Show available developer commands\\n  setup          Install project, web, and preprocessing dependencies\\n  build-frontend Build Svelte 5 + Tailwind v4 frontend static assets\\n  run            Start the web server on port 8000\\n  test           Run the fast test suite\\n  lint           Run Ruff lint and format checks\\n  typecheck      Run mypy against production code\\n  audit          Run pip-audit dependency vulnerability scan\\n  clean          Remove generated caches and build artifacts\\n  doctor         Report Python, uv, Redis, and model server health')"

setup: ## Install project, web, and preprocessing dependencies
	uv sync --extra web --extra preprocessing
	cd frontend && npm install

build-frontend: ## Build Svelte 5 + Tailwind v4 frontend static assets
	cd frontend && npm run build

run: ## Start the web server on port 8000
	uv run omniscribe-server --port 8000

test: ## Run the fast test suite
	uv run pytest -m "not slow"

lint: ## Run Ruff lint and format checks
	uv run ruff check src tests --no-fix
	uv run ruff format src tests --check

typecheck: ## Run mypy against production code
	uv run mypy src

# PYSEC-2026-311 / CVE-2026-45829 (CVSS 9.3): pre-auth code injection in the
# chromadb *server* via `trust_remote_code` on create_collection, plus a
# client-side variant that executes a poisoned collection's stored embedding
# function. Affects chromadb 1.0.0-1.5.9; no patched release exists on PyPI
# yet (upstream chroma-core/chroma#6717 is open with no fix PR), so there is
# no version to bump to. Risk-accepted because neither vector is reachable:
#   1. OmniScribe never runs a Chroma HTTP server - core/translation.py uses
#      an embedded `chromadb.PersistentClient` on a local path only.
#   2. `get_chroma_collection()` always passes an explicit
#      `embedding_function=`, so no collection-stored embedding config is
#      ever instantiated, and no `trust_remote_code` flag is used anywhere.
# Drop the --ignore-vuln flag once chromadb ships a fixed release (>1.5.9)
# and the [project.dependencies] / [memory] constraints are bumped to it.
audit: ## Run pip-audit dependency vulnerability scan
	uv run pip-audit --ignore-vuln PYSEC-2026-311

clean: ## Remove generated caches and build artifacts
	uv run python scripts/dev.py clean

doctor: ## Report Python, uv, Redis, and model server health
	uv run python scripts/dev.py doctor
