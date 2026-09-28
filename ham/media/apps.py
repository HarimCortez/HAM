"""Step 2 (Intake): `RequestMediaBatch`/`RequestMedia`, upload intents, processing job
(intake.md §2). Reserved in foundation.md §1; starts in step 2.

Empty in S2.0 (a seam only, intake.md §10): S2.4b owns the models/services/processing job.
"""

from django.apps import AppConfig


class MediaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ham.media"
    label = "ham_media"
