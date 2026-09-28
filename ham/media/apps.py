"""Step 2 (Intake): `RequestMediaBatch`/`RequestMedia`, upload intents, processing job
(intake.md §2). Reserved in foundation.md §1; starts in step 2.

S2.4b: registers the `media` outbox subscriber, which closes any still-open media batch when
a request is cancelled (`RequestCancelled`). This is how `ham.media` reacts to a
`ham.requests`-originated event without `ham.requests` ever importing `ham.media`
(intake.md §2's layering rule: media is above requests, never the reverse).
"""

from django.apps import AppConfig


class MediaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ham.media"
    label = "ham_media"

    def ready(self) -> None:
        from ham.outbox import registry

        from . import (
            jobs,  # noqa: F401 - registers the procrastinate tasks (@jobs.job/periodic_job)
        )
        from .subscribers import handle_media_event

        registry.register("media", handle_media_event)
