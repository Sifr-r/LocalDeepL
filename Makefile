.DEFAULT_GOAL := help

.PHONY: help setup run test lint typecheck clean doctor

help: ## Show available developer commands
	@uv run python -c "print('Available targets:\\n  help       Show available developer commands\\n  setup      Install project and web dependencies\\n  run        Start the web server on port 8000\\n  test       Run the fast test suite\\n  lint       Run Ruff lint and format checks\\n  typecheck  Run mypy against production code\\n  clean      Remove generated caches and build artifacts\\n  doctor     Report Python, uv, Redis, and model server health')"

setup: ## Install project and web dependencies
	uv sync --extra web

run: ## Start the web server on port 8000
	uv run omniscribe-server --port 8000

test: ## Run the fast test suite
	uv run pytest -m "not slow"

lint: ## Run Ruff lint and format checks
	uv run ruff check src tests --no-fix
	uv run ruff format src tests --check

typecheck: ## Run mypy against production code
	uv run mypy src

clean: ## Remove generated caches and build artifacts
	uv run python scripts/dev.py clean

doctor: ## Report Python, uv, Redis, and model server health
	uv run python scripts/dev.py doctor
