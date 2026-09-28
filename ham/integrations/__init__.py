"""ham.integrations — the only module that talks to third parties (foundation.md §1).

Everything here plugs into `ham.outbox` as a subscriber (`ham.outbox.registry.register`,
called from `IntegrationsConfig.ready()`) rather than being called directly by domain code,
with one documented exception: `ham.integrations.email.service.send_transactional_email` for
auth flows that cannot wait for the outbox's per-event delivery/retry bookkeeping (S3b
sign-in codes/links).

Each deferred system (Google Drive §50, Fitness & Accountability §36, Google Calendar §51) is
behind a small Protocol with a no-op implementation, so a real client can be swapped in later
without touching `ham.outbox` or any domain module.
"""

from __future__ import annotations
