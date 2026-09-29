"""S3.7 requester step-3 screens (docs/ux/approvals.md §6 R13-R19; approvals-contracts.md §8).
Views live in the existing `ham/web/views_requester.py` (S3.7 owns that file too, alongside
`ham/web/templates/web/requester/*`); this module only holds the two new routes, kept separate
from `ham/web/urls_requester.py` per S3.0's original split note (avoids two slices colliding
on the same URL module during the parallel build).

Both sit under the existing token-scoped secure-page prefix
(`request-help/r/<str:token>/...`), same as every other requester route -- per-request access
control is the link token the view resolves fresh on every call
(`ham.requester_portal.services.resolve_token`), never a session.

| URL name | Path | Screen |
|---|---|---|
| `request_help_reconsider` | `request-help/r/<str:token>/reconsider` | R16 |
| `request_help_question_answer` | `.../r/<str:token>/questions/<uuid:question_id>/answer` | R13 |
"""

from __future__ import annotations

from django.urls import path

from . import views_requester as views

urlpatterns = [
    path(
        "request-help/r/<str:token>/reconsider",
        views.request_help_reconsider,
        name="request_help_reconsider",
    ),
    path(
        "request-help/r/<str:token>/questions/<uuid:question_id>/answer",
        views.request_help_question_answer,
        name="request_help_question_answer",
    ),
]
