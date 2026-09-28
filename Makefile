.PHONY: install test lint typecheck migrate run worker tokens dev-db dev-db-stop fmt frontend

VENV := .venv/bin

install:
	uv venv .venv --python 3.11
	uv pip install -e ".[dev]"
	npm ci --prefix frontend

frontend:
	npm run build --prefix frontend

migrate:
	$(VENV)/python manage.py migrate

run:
	$(VENV)/python manage.py runserver 0.0.0.0:8000

worker:
	# Security review C2: job args may (until the app-level Fernet encryption in
	# ham.integrations.email.service) be sensitive; --delete-jobs=successful removes
	# procrastinate_jobs rows for jobs that finished normally so nothing lingers at rest,
	# in addition to (not instead of) encrypting the payload.
	$(VENV)/python manage.py procrastinate worker --delete-jobs=successful

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
