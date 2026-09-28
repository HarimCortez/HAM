"""ASGI entrypoint (kept for parity; HAM is served over WSGI in V1)."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_asgi_application()
