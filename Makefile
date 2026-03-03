.PHONY: test lint fmt check setup

setup:
	uv sync --dev
	uv run pre-commit install

test:
	uv run pytest tests/ -q

lint:
	uv run ruff check src/ tests/

fmt:
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

check: fmt lint test
