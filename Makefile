.PHONY: help install lint format typecheck test test-live check clean

.DEFAULT_GOAL := help

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-12s %s\n", $$1, $$2}'

install: ## Install dependencies with uv
	uv sync

lint: ## Run Ruff lint and format checks
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-format and fix lint issues
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Run mypy (strict)
	uv run mypy

test: ## Run the default test suite (no live calls)
	uv run pytest

test-live: ## Run tests that call real providers (needs credentials)
	uv run pytest -m live || [ $$? -eq 5 ]  # exit code 5 = no live tests collected yet

check: lint typecheck test ## Run lint, typecheck and tests

clean: ## Remove caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -not -path './.venv/*' -prune -exec rm -rf {} +
