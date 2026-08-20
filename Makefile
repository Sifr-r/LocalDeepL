.DEFAULT_GOAL := help

.PHONY: help setup run build-frontend test test-slow lint typecheck audit security clean doctor openapi

help: ## Show available developer commands
	@uv run python -c "print('Available targets:\n  help           Show available developer commands\n  setup          Install project, web, and preprocessing dependencies\n  build-frontend Build Svelte 5 + Tailwind v4 frontend static assets\n  run            Start the web server on port 8000\n  test           Run the fast test suite\n  test-slow      Run the slow test suite (Surya, full fixtures) -- pulls model weights on first run\n  lint           Run Ruff lint and format checks\n  typecheck      Run mypy against production code\n  audit          Run pip-audit dependency vulnerability scan\n  security       Run Semgrep static analysis (best-effort, no CI gating)\n  clean          Remove generated caches and build artifacts\n  doctor         Report Python, uv, Redis, and model server health\n  openapi        Regenerate tests/openapi.json from the FastAPI app spec')"

setup: ## Install project, web, and preprocessing dependencies
	uv sync --extra web --extra preprocessing
	cd frontend && npm install

build-frontend: ## Build Svelte 5 + Tailwind v4 frontend static assets
	cd frontend && npm run build

run: ## Start the web server on port 8000
	uv run omniscribe-server --port 8000

test: ## Run the fast test suite
	uv run pytest -m "not slow"

# F5-27 audit fix: dedicated `test-slow` target so the slow tier
# (Surya model load + full-dataset fixtures) is one `make` invocation
# away. ``nightly.yml`` runs the same command on the CI side; local
# operators who want to debug a Surya regression don't have to
# remember the marker incantation.
test-slow: ## Run the slow test suite (Surya, full fixtures) -- pulls model weights on first run
	uv run pytest -m "slow" -v

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

# F5-27 audit fix: `make security` runs the local Semgrep static
# analysis pass on the same ruleset `security.yml` uses in CI. The
# CI path uploads the SARIF; this target prints findings to the
# terminal so a developer can iterate without pushing. Semgrep is
# invoked via ``uvx`` so the local venv doesn't need it as a hard
# dep — matches the pattern ``install.ps1`` uses for ``pip-audit``.
# ``--error`` makes the exit code non-zero on any finding, so this
# target slots into a pre-push hook if anyone wants to wire one.
# The target name is intentionally distinct from `audit` (which is
# dependency scanning); `security` is source-code analysis.
security: ## Run Semgrep static analysis (best-effort, no CI gating)
	@command -v uvx >/dev/null 2>&1 || { echo "uvx not found; install via 'uv tool install uvx' or 'pipx install uvx'." >&2; exit 1; }
	uvx --from semgrep semgrep scan --config=p/owasp-top-ten --config=p/python --config=p/security-audit src/ --error

clean: ## Remove generated caches and build artifacts
	uv run python scripts/dev.py clean

doctor: ## Report Python, uv, Redis, and model server health
	uv run python scripts/dev.py doctor

# Regenerate the checked-in OpenAPI snapshot the frontend contract tests
# diff against. ``tests/test_frontend_openapi_contract.py`` will fail if
# the snapshot drifts; running this target re-syncs the file to whatever
# ``app.openapi()`` currently returns. The redirect uses ``>`` (not ``>>``)
# so stale content is fully replaced on each run.
openapi: ## Regenerate tests/openapi.json from the FastAPI app spec
	uv run python -c "from omniscribe.server import app; import json; print(json.dumps(app.openapi(), indent=2))" > tests/openapi.json
