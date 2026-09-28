"""`Notification` rows, the `inapp` outbox subscriber + builder registry, the attention-
provider registry (intake.md §2; foundation.md §2 "with staffing", needed now for Inbox/urgent).
"""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ham.notifications"
    label = "ham_notifications"

    def ready(self) -> None:
        # Imported inside ready(), not at module top: Django app configs must not import other
        # apps' models before all apps are loaded (see ham.integrations.apps.ready()).
        from ham.outbox import registry

        from .inapp import handle_inapp_event

        registry.register("inapp", handle_inapp_event)
