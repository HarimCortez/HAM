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

        # ham.notifications owns the attention-provider registry (intake.md §2) but may
        # still be an empty seam in this worktree (S2.5 runs in parallel) -- register only
        # if it's actually there, same guarded pattern as `issue_link` (wave2-common.md).
        try:
            from ham.notifications.registry import register_attention_provider
        except ImportError:
            pass
        else:
            from . import attention

            attention.register(register_attention_provider)
