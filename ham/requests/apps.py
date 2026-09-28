"""Step 2 (Intake): requests, requesters, properties, matching (intake.md §2 module list).

S2.2 owns models/migrations/services/queries; `states.py`/`matching.py` stay rules-owned
(S2.1).
"""

from django.apps import AppConfig


class RequestsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ham.requests"
    label = "requests"

    def ready(self) -> None:
        from ham.authz.scopes import register_queryset_scope_provider

        from .queries import scope_queryset_for_requests

        register_queryset_scope_provider("request.list", scope_queryset_for_requests)

        # ham.notifications sits below ham.requests in the layer order (web -> requester_
        # portal -> media -> requests -> notifications -> ...), so this is an ordinary
        # downward import (S2.5 has landed, intake-contracts.md §8.3).
        from . import attention, notifications

        attention.register()
        # S2.6: leadership email + in-app builders (intake.md §6, docs/ux/intake.md §7).
        notifications.register()
