"""Step 2 (Intake): requests, requesters, properties, matching (intake.md §2 module list).

Empty in S2.0 (a seam only, intake.md §10): S2.1 owns `states.py`/`matching.py`; S2.2 owns the
rest (models, migrations, services).
"""

from django.apps import AppConfig


class RequestsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ham.requests"
    label = "requests"
