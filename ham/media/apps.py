"""Step 2 (Intake): `RequestMediaBatch`/`RequestMedia`, upload intents, processing job
(intake.md §2). Reserved in foundation.md §1; starts in step 2.

S2.4b: registers the `media` outbox subscriber, which closes any still-open media batch when
a request is cancelled (`RequestCancelled`). This is how `ham.media` reacts to a
`ham.requests`-originated event without `ham.requests` ever importing `ham.media`
(intake.md §2's layering rule: media is above requests, never the reverse).

Security review M4: also registers `services.purge_all_for_request` into `ham.requests.
services.register_media_purge_hook` -- the same layering rule means `ham.requests`'s own
spam purge (`purge_expired_request`) cannot import `ham.media` to delete storage objects
itself, so it calls a hook that `ham.media` (which *can* legally import `ham.requests`,
downward) installs here instead.

S3.4: also registers `notifications.register()` (Q-150's "New photos arrived" in-app notice)
onto `ham.notifications.inapp`.
"""

from django.apps import AppConfig


class MediaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ham.media"
    label = "ham_media"

    def ready(self) -> None:
        from ham.outbox import registry
        from ham.requests.services import register_media_purge_hook

        from . import (
            jobs,  # noqa: F401 - registers the procrastinate tasks (@jobs.job/periodic_job)
            notifications,
        )
        from .services import purge_all_for_request
        from .subscribers import handle_media_event

        registry.register("media", handle_media_event)
        register_media_purge_hook(purge_all_for_request)
        notifications.register()
