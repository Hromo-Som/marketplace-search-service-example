.PHONY: lint format check test migrate migrate-create run consumer

lint:
	uv run ruff check --fix src/ bin/

format:
	uv run ruff format src/ bin/

check: lint format

test:
	uv run python -m pytest tests/ -v

migrate:
	uv run python -m alembic upgrade head

migrate-create:
	uv run alembic revision --autogenerate -m "$(name)"

run:
	uv run python -m bin.api

consumer:
	uv run python -m bin.consumer
