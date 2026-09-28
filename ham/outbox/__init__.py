"""ham.outbox — the transactional outbox (PRD §36.4, §70.3; foundation.md §3, §8 S4).

Domain code's one entry point is `ham.outbox.api.emit(...)`. It must be called inside the
caller's own `transaction.atomic()`: the `OutboxEvent` row (and one pending `OutboxDelivery`
row per registered subscriber) commit together with the domain change they describe, or not
at all. Adapter failures (a subscriber's handler raising) touch only `outbox_delivery` rows —
never the domain transaction, never the event — so a dead Google/anymail/etc. integration
never blocks or rolls back HAM (§70.3).

Subscribers register themselves with `ham.outbox.registry.register(name, handler)` from their
own `AppConfig.ready()` (see `ham.integrations.apps.IntegrationsConfig`); this module never
imports `ham.integrations` (foundation.md §1 layering — outbox sits below web, integrations is
a leaf that plugs into outbox via the registry, not the reverse).
"""

from __future__ import annotations
