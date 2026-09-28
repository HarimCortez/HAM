from django.apps import AppConfig


class AuthzConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ham.authz"
    label = "ham_authz"

    def ready(self) -> None:
        # Wire the command pipeline's audit/outbox sinks here, not as static imports in
        # commands.py, so `ham.audit` never has to import `ham.authz` back (that would cycle
        # with `ham.authz` -> `ham.audit`; see the comment in commands.py).
        from ham.audit.services import record as audit_record
        from ham.outbox.api import emit as outbox_emit

        from .commands import _register_audit_recorder, _register_outbox_emitter

        _register_audit_recorder(audit_record)
        _register_outbox_emitter(outbox_emit)
