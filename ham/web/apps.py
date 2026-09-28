from django.apps import AppConfig


class WebConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ham.web"
    label = "web"
    verbose_name = "HAM app shell"
