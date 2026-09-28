from __future__ import annotations

from django.apps import AppConfig
from django.conf import settings


class IntegrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ham.integrations"
    label = "integrations"
    verbose_name = "HAM integrations"

    def ready(self) -> None:
        # Imported inside ready(), not at module top: Django app configs must not import
        # other apps' models before all apps are loaded.
        from ham.outbox import registry

        from .calendar import handle_calendar_event
        from .drive import handle_drive_event
        from .email.notifications import handle_email_event
        from .fitness import handle_fitness_event

        registry.register("email", handle_email_event)
        registry.register("calendar", handle_calendar_event)
        registry.register("fitness", handle_fitness_event)
        registry.register("drive", handle_drive_event)

        if settings.DEBUG:
            from .dev_logging import handle_dev_logging_event

            registry.register("dev_logging", handle_dev_logging_event)
