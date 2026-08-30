.PHONY: sync test coverage lint format typecheck check

sync:
	uv sync

test:
	uv run pytest

coverage:
	uv run pytest --cov=insider_turning_engine --cov-report=term-missing

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

check: lint typecheck test
