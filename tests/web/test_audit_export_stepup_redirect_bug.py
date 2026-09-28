"""BUG (found while building the Playwright smoke suite, foundation.md §9.7): after a
successful step-up for `audit.export`, the server redirects a real browser into a dead end.

`ham/web/views_audit.py::audit_export`'s `StepUpRequired` handler calls
`redirect_to_step_up(request, request.path, _EXPORT_KIND)` -- `request.path` is
`/audit/export` itself, a **POST-only** route (`@require_http_methods(["POST"])`). The
`/step-up` screen's own success handler (`ham/web/auth_views.py::step_up`) does
`return redirect(next_url)`, which is always a **GET**. So the very next request a real
browser makes after entering the TOTP code is `GET /audit/export`, which Django's
`require_http_methods` refuses with `405 Method Not Allowed` -- the export never happens on
the first attempt, contradicting `tests/web/test_admin_screens.py::test_audit_export_requires_
step_up`'s implicit assumption (it never follows the redirect; it manually re-POSTs a third
time instead, which is why this went unnoticed at the Django-test-client level).

Contrast with the two other step-up-gated actions that redirect through a page instead of a
bare POST endpoint (both survive a GET fine because they render a confirm form):
`admin_impersonate`/`admin_mfa_reset` pass their own GET+POST confirm-page URL as `next`, not
a POST-only action URL.

Suggested fix: `audit_export`'s `except StepUpRequired` branch should pass the **audit log
list page** (`reverse("web:audit_log")`, which has the same filters and its own Export
button/form) as `next`, not `request.path`. That mirrors the `admin_impersonate` pattern and
lets the person land somewhere they can actually re-trigger the export from after stepping up.

The Playwright smoke suite (`tests/e2e/test_smoke.py`) routes around this by clicking "Export"
a second time after the step-up form submits (which is what a person would realistically do
next), so it still exercises a full step-up round trip and a successful download -- but this
test pins the redirect-target defect precisely so it isn't lost.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from ham.identity import totp
from ham.identity.crypto import encrypt
from ham.identity.models import RoleAssignment, SharedIdentityProfile, TOTPDevice
from ham.platform.clock import now

_DEV_SECRET = totp.new_secret()


@pytest.fixture
def director_client(client, make_user):
    user = make_user("marcus@example.org")
    SharedIdentityProfile.objects.create(user=user, full_name="Marcus Bell")
    RoleAssignment.objects.create(user=user, role="HAM_DIRECTOR", granted_at=now())
    client.force_login(user)
    TOTPDevice.objects.update_or_create(
        user=user,
        defaults={
            "secret_encrypted": encrypt(_DEV_SECRET),
            "created_at": now(),
            "confirmed_at": now(),
        },
    )
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return client


@pytest.mark.django_db
@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: audit_export's StepUpRequired redirect target is the POST-only /audit/export "
        "URL itself; a real browser following the post-step-up GET redirect gets 405 Method "
        "Not Allowed instead of the CSV. See this module's docstring for the fix."
    ),
)
def test_following_the_step_up_redirect_actually_completes_the_export(director_client):
    response = director_client.post(reverse("web:audit_export"), {})
    assert response.status_code == 302
    assert response["Location"].startswith("/step-up")

    step_up = director_client.post(
        response["Location"],
        {
            "next": reverse("web:audit_export"),
            "kind": "audit_export",
            "code": totp.current_code(_DEV_SECRET),
        },
    )
    assert step_up.status_code == 302

    # A real browser's next request is a GET to `step_up["Location"]` (the redirect target),
    # not another hand-crafted POST -- that's exactly what breaks.
    followed = director_client.get(step_up["Location"])
    assert followed.status_code == 200
    assert followed["Content-Type"].startswith("text/csv")
