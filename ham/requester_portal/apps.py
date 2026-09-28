"""Step 2 (Intake): the public requester surface — drafts, verification challenges, access
links, `RequesterContext` building, requester email builders, purge jobs (intake.md §2).

S2.3 (this slice) implements everything except `validity.py` (S2.1, rules-owned).
"""

from typing import Any

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
        # intake-contracts.md §8.3: `ham.requests` (S2.2) owns the `AssistanceRequest`/
        # `Requester` models this app needs facts from, but `ham.requests` sits *below*
        # `ham.requester_portal` in the layers contract, so it may never import this app to
        # register itself the other way round. This app does the registering instead — a
        # legal downward import (`ham.requester_portal -> ham.requests`) — wrapping
        # `ham.requests.queries`' plain-value lookups into this app's own `RequestLinkFacts`.
        from ham.outbox import registry
        from ham.requests import queries as requests_queries

        from . import (
            jobs,  # noqa: F401
            notifications,
            services,
        )
        from .subscribers import handle_requester_portal_event

        registry.register("requester_portal", handle_requester_portal_event)

        def _facts_lookup(request_id: Any) -> services.RequestLinkFacts:
            facts = requests_queries.request_facts_for_portal(request_id)
            return services.RequestLinkFacts(
                status=facts.status,
                closed_at=facts.closed_at,
                display_number=facts.display_number,
            )

        services.register_request_facts_lookup(_facts_lookup)
        services.register_request_contact_lookup(requests_queries.request_contact_for_portal)
        services.register_email_to_request_ids_lookup(requests_queries.request_ids_for_portal_email)

        # S2.6 (intake.md §6, docs/ux/intake.md §7): requester email builders (E2/E2u, E3, E5,
        # E6, E7), registered onto the shared email subscriber.
        notifications.register()
