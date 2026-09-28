from django.apps import AppConfig


class PlatformConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ham.platform"
    label = "platform"
    verbose_name = "HAM platform"
