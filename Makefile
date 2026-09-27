.PHONY: install test lint typecheck migrate run worker tokens dev-db dev-db-stop fmt

VENV := .venv/bin

install:
	uv venv .venv --python 3.11
	uv pip install -e ".[dev]"
	npm ci --prefix frontend || true

migrate:
	$(VENV)/python manage.py migrate

run:
	$(VENV)/python manage.py runserver 0.0.0.0:8000

worker:
	$(VENV)/python manage.py procrastinate worker

tokens:
	$(VENV)/python manage.py build_tokens --brand miami-temple --check

test:
	$(VENV)/python -m pytest

lint:
	$(VENV)/ruff check .
	$(VENV)/ruff format --check .
	$(MAKE) typecheck

fmt:
	$(VENV)/ruff format .
	$(VENV)/ruff check --fix .

typecheck:
	DJANGO_SETTINGS_MODULE=config.settings.test $(VENV)/mypy .

dev-db:
	./scripts/dev_db.sh start

dev-db-stop:
	./scripts/dev_db.sh stop
