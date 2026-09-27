# HAM production image (Render web service + background worker share this image;
# render.yaml selects the process with a different startCommand). ffmpeg is included ahead
# of the media step (§45 video compression) so this image doesn't need to change later.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

FROM base AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv export --no-dev --format requirements-txt > requirements.txt \
    && pip install --prefix=/install -r requirements.txt

FROM base
WORKDIR /app
COPY --from=build /install /usr/local
COPY . .
RUN python manage.py build_tokens --brand "${HAM_BRAND:-miami-temple}" --check \
    && DJANGO_SETTINGS_MODULE=config.settings.prod DJANGO_SECRET_KEY=build-only \
       DATABASE_URL=postgresql://build:build@localhost/build \
       DJANGO_ALLOWED_HOSTS=localhost \
       python manage.py collectstatic --noinput --ignore=*.map || true

ENV DJANGO_SETTINGS_MODULE=config.settings.prod
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
