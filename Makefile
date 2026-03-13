.PHONY: help install install-dev lint format typecheck test test-cov clean build

PYTHON ?= python

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install the package in editable mode
	$(PYTHON) -m pip install -e .

install-dev: ## Install with all development dependencies
	$(PYTHON) -m pip install -e ".[all]"

lint: ## Run ruff linter
	$(PYTHON) -m ruff check crossdisc_extractor/ tests/ scripts/

format: ## Auto-format code with ruff
	$(PYTHON) -m ruff format crossdisc_extractor/ tests/ scripts/
	$(PYTHON) -m ruff check --fix crossdisc_extractor/ tests/ scripts/

typecheck: ## Run mypy type checker
	$(PYTHON) -m mypy crossdisc_extractor/

test: ## Run tests with pytest
	$(PYTHON) -m pytest tests/ -v

test-cov: ## Run tests with coverage report
	$(PYTHON) -m pytest tests/ --cov=crossdisc_extractor --cov-report=term-missing --cov-report=html

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .mypy_cache .pytest_cache .ruff_cache htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

build: ## Build distribution packages
	$(PYTHON) -m build

ci: lint typecheck test ## Run all CI checks (lint + typecheck + test)
