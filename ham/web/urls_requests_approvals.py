"""S3.0 URL stub (approvals.md §6, §8 slice table "S3.6 Leadership screens"; docs/ux/
approvals.md screen codes). Empty today (`urlpatterns: list = []`), same "declared ahead of
its build" shape as `ham/web/urls_inbox.py` at S2.0 -- S3.6 fills these in against
`ham/web/views_requests.py` (existing) without needing to touch this file's own name/shape,
and without colliding with `ham/web/urls_requests.py`'s already-live step-2 routes (a separate
worktree editing that file in parallel is the reason these are their own module, not appended
there).

Exact names S3.2-S3.7 code against (see `docs/architecture/approvals-contracts.md` §8 for the
one source of truth -- this list must match it):

| URL name | Path | Screen(s) |
|---|---|---|
| `request_approve` | `requests/<uuid:request_id>/approve` | L12 (approve confirm) |
| `request_reject` | `requests/<uuid:request_id>/reject` | L13 (not-approved sheet) |
| `request_decision_undo` | `requests/<uuid:request_id>/decision/undo` | L2 (decided card, "Undo") |
| `request_certify_urgency` | `requests/<uuid:request_id>/urgency/certify` | L2 urgent banner |
| `request_decline_urgency` | `requests/<uuid:request_id>/urgency/decline` | L2 urgent banner |
| `request_reconsideration_decide` | `requests/<uuid:request_id>/reconsideration/decide` | L14 |
| `request_reconsideration_phone` | `requests/<uuid:request_id>/reconsideration/phone` | L18 |
| `request_decision_phoned` | `requests/<uuid:request_id>/decision/phoned` | L18 |
| `request_question_ask` | `requests/<uuid:request_id>/questions/ask` | L15 |
| `request_question_record_answer` | `.../questions/<uuid:question_id>/answer` | L15, L16 |
| `request_question_withdraw` | `.../questions/<uuid:question_id>/withdraw` | L16 |
| `request_category_change` | `requests/<uuid:request_id>/category` | L17 |

(The last two paths above are relative to `requests/<uuid:request_id>` -- see the row
above them for the full prefix.)
"""

from __future__ import annotations

from django.urls import path

from . import views_requests as views

urlpatterns = [
    path("requests/<uuid:request_id>/approve", views.request_approve, name="request_approve"),
    path("requests/<uuid:request_id>/reject", views.request_reject, name="request_reject"),
    path(
        "requests/<uuid:request_id>/decision/undo",
        views.request_decision_undo,
        name="request_decision_undo",
    ),
    path(
        "requests/<uuid:request_id>/urgency/certify",
        views.request_certify_urgency,
        name="request_certify_urgency",
    ),
    path(
        "requests/<uuid:request_id>/urgency/decline",
        views.request_decline_urgency,
        name="request_decline_urgency",
    ),
    path(
        "requests/<uuid:request_id>/reconsideration/decide",
        views.request_reconsideration_decide,
        name="request_reconsideration_decide",
    ),
    path(
        "requests/<uuid:request_id>/reconsideration/phone",
        views.request_reconsideration_phone,
        name="request_reconsideration_phone",
    ),
    path(
        "requests/<uuid:request_id>/decision/phoned",
        views.request_decision_phoned,
        name="request_decision_phoned",
    ),
    path(
        "requests/<uuid:request_id>/questions/ask",
        views.request_question_ask,
        name="request_question_ask",
    ),
    path(
        "requests/<uuid:request_id>/questions/<uuid:question_id>/answer",
        views.request_question_record_answer,
        name="request_question_record_answer",
    ),
    path(
        "requests/<uuid:request_id>/questions/<uuid:question_id>/withdraw",
        views.request_question_withdraw,
        name="request_question_withdraw",
    ),
    path(
        "requests/<uuid:request_id>/category",
        views.request_category_change,
        name="request_category_change",
    ),
]
