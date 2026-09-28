from django.apps import AppConfig


class IdentityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ham.identity"
    label = "identity"

    def ready(self) -> None:
        # Imported inside ready(), not at module top: Django app configs must not import
        # other apps' models before all apps are loaded (see IntegrationsConfig.ready()).
        from . import notifications

        notifications.register()
