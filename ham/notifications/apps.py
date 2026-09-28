"""`Notification` rows, the `inapp` outbox subscriber + builder registry, the attention-
provider registry (intake.md §2; foundation.md §2 "with staffing", needed now for Inbox/urgent).

Empty in S2.0 (a seam only, intake.md §10): S2.5 owns the models/services.
"""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ham.notifications"
    label = "ham_notifications"
