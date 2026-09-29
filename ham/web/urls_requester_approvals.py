"""S3.0 URL stub (approvals.md §6, §8 slice table "S3.7 Requester screens"; docs/ux/
approvals.md screen codes R13/R14). Empty today, same shape/reasoning as
`ham.web.urls_requests_approvals`'s own module docstring -- S3.7 fills these in against
`ham/web/views_requester.py` (existing), without colliding with `ham/web/urls_requester.py`'s
already-live step-2 routes.

Exact names S3.4/S3.5/S3.7 code against (`docs/architecture/approvals-contracts.md` §8 is the
one source of truth -- this list must match it). Both sit under the existing token-scoped
secure-page prefix (`request-help/r/<str:token>/...`, same as every other requester route).

| URL name | Path | Screen |
|---|---|---|
| `request_help_reconsider` | `request-help/r/<str:token>/reconsider` | R13 |
| `request_help_question_answer` | `.../r/<str:token>/questions/<uuid:question_id>/answer` | R14 |
"""

from __future__ import annotations

urlpatterns: list = []
