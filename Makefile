# =============================================================================
# Vartalaap Makefile
# =============================================================================
# Common development commands for the voice bot platform.
#
# Usage:
#   make install      # Install all dependencies
#   make dev          # Run dev server
#   make test         # Run tests
#   make generate     # Run code generation
# =============================================================================

.PHONY: install install-dev install-all dev admin worker test lint format typecheck generate migration migrate clean

# =============================================================================
# Installation
# =============================================================================

install:
	uv sync

install-dev:
	uv sync --extra dev

install-all:
	uv sync --all-extras

# =============================================================================
# Development Servers
# =============================================================================

dev:
	uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

admin:
	uv run streamlit run admin/app.py --server.port 8501

worker:
	uv run arq src.worker.WorkerSettings

# =============================================================================
# Testing & Quality
# =============================================================================

test:
	uv run ward

test-cov:
	uv run coverage run -m ward
	uv run coverage report -m
	uv run coverage html

lint:
	uv run ruff check src/ admin/ tests/

lint-fix:
	uv run ruff check --fix src/ admin/ tests/

format:
	uv run ruff format src/ admin/ tests/

typecheck:
	uv run mypy src/

check: lint typecheck test
	@echo "All checks passed!"

# =============================================================================
# Code Generation
# =============================================================================

generate:
	./scripts/generate.sh

schemas:
	./scripts/generate.sh schemas

# =============================================================================
# Database Migrations
# =============================================================================

# Create a new migration
# Usage: make migration msg="Add new table"
migration:
	uv run alembic revision --autogenerate -m "$(msg)"

# Apply all pending migrations
migrate:
	uv run alembic upgrade head

# Rollback last migration
migrate-down:
	uv run alembic downgrade -1

# Show migration history
migrate-history:
	uv run alembic history

# =============================================================================
# Cleanup
# =============================================================================

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	@echo "Cleaned up cache files"

# =============================================================================
# Help
# =============================================================================

help:
	@echo "Vartalaap Development Commands"
	@echo ""
	@echo "Installation:"
	@echo "  make install       Install core dependencies"
	@echo "  make install-dev   Install with dev tools"
	@echo "  make install-all   Install all extras"
	@echo ""
	@echo "Development:"
	@echo "  make dev           Run FastAPI dev server"
	@echo "  make admin         Run Streamlit admin UI"
	@echo "  make worker        Run arq background worker"
	@echo ""
	@echo "Quality:"
	@echo "  make test          Run tests with ward"
	@echo "  make lint          Check code style with ruff"
	@echo "  make format        Format code with ruff"
	@echo "  make typecheck     Type check with mypy"
	@echo "  make check         Run all checks"
	@echo ""
	@echo "Code Generation:"
	@echo "  make generate      Run all code generation"
	@echo "  make schemas       Generate Pydantic from JSON Schema"
	@echo ""
	@echo "Database:"
	@echo "  make migration msg=\"desc\"  Create new migration"
	@echo "  make migrate       Apply pending migrations"
	@echo "  make migrate-down  Rollback last migration"
