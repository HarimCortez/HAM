"""Step 2 (Intake): the public requester surface — drafts, verification challenges, access
links, `RequesterContext` building, requester email builders, purge jobs (intake.md §2).

S2.3 (this slice) implements everything except `validity.py` (S2.1, rules-owned).
"""

from django.apps import AppConfig


class RequesterPortalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ham.requester_portal"
    label = "requester_portal"

    def ready(self) -> None:
        # Imported inside ready(), not at module top (Django app configs must not import
        # other apps' models before every app is loaded) — this is what makes the two
        # `@jobs.periodic_job`-decorated purge functions actually register with Procrastinate
        # at process startup, mirroring `ham.identity.authn`'s hourly purge job.
        from . import jobs  # noqa: F401
