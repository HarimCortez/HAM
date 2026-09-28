"""Step 2 (Intake): the public requester surface — drafts, verification challenges, access
links, `RequesterContext` building, requester email builders, purge jobs (intake.md §2).

Empty in S2.0 (a seam only, intake.md §10): S2.1 owns `validity.py`; S2.3 owns the rest.
"""

from django.apps import AppConfig


class RequesterPortalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ham.requester_portal"
    label = "requester_portal"
