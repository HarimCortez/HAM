"""PLACEHOLDER — S2.2 owns the real `AssistanceRequest` model (intake.md §3), which is built
in a parallel worktree and not yet merged into this one.

S2.4b (`ham.media`) needs a real FK target to migrate against (`"requests.AssistanceRequest"`,
per `docs/architecture/intake-contracts.md` §6 coordination note: "reference it by string ...
if that doesn't exist in your worktree, create a minimal placeholder migration only if needed,
and say so clearly so I can reconcile"). This is that placeholder: just enough columns
(`id`, `status`, `closed_at`) for `ham.media`'s retention sweep (§47, Q-128) and FK integrity
to compile and be tested in isolation.

**Orchestrator: when merging S2.2 and S2.4b, drop this file and
`ham/requests/migrations/0001_initial.py`, keep S2.2's real ones, and rewrite
`ham/media/migrations/0001_initial.py`'s dependency on `("requests", "0001_initial")` to point
at whichever migration in S2.2's history actually creates `AssistanceRequest` (it may not be
S2.2's own 0001 once merged after other requests-app migrations).**
"""

from __future__ import annotations

from django.db import models

from ham.platform.ids import UUID7Field
from ham.requests.states import RequestStatus


class AssistanceRequest(models.Model):
    id = UUID7Field()
    status = models.CharField(
        max_length=32,
        choices=[(s.value, s.value) for s in RequestStatus],
        default=RequestStatus.SUBMITTED.value,
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "requests_assistance_request"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"AssistanceRequest({self.id})"
