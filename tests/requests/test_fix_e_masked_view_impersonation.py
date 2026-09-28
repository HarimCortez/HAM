"""FIX-E N5/Q-151 regression: `ham.requests.queries.is_masked_view(ctx)` must be true when
the *real* signed-in actor is an Administrator who is impersonating -- the plain role check
(`ADMINISTRATOR in ctx.effective_roles`) is blind to this, since `effective_roles` reflects
the impersonation *target's* roles while impersonating, not the real actor's. Same class of
bug the L7/Q-151 fix already closed for `reveal_requester_pii`'s reveal button; this closes it
for the gallery/contact masking that decides whether the reveal button, full photo gallery,
and detail-page contact block are shown at all. New file per wave brief.
"""

from __future__ import annotations

import uuid

import pytest

from ham.authz import roles
from ham.authz.context import SystemContext
from ham.identity.models import RoleAssignment
from ham.platform.clock import now as clock_now
from ham.requests.queries import get_request_detail, is_masked_view
from ham.requests.services import complete_intake_checks, submit_request

from .conftest import actor_ctx, make_payload

pytestmark = pytest.mark.django_db


def _submit(requester_ctx):
    req = submit_request(
        requester_ctx,
        draft_id=uuid.uuid4(),
        verification_id=uuid.uuid4(),
        payload=make_payload(),
    )
    return req


def test_administrator_impersonating_a_pastor_is_still_masked(make_user):
    admin_user = make_user("admin@example.org")
    RoleAssignment.objects.create(user=admin_user, role=roles.ADMINISTRATOR, granted_at=clock_now())

    # `effective_roles` reflects the impersonation *target's* role (Pastor) -- the plain role
    # check alone would say "not masked" here.
    ctx = actor_ctx(
        roles=frozenset({roles.PASTOR}),
        real_user_id=admin_user.id,
        impersonation_id=uuid.uuid4(),
    )
    assert is_masked_view(ctx)


def test_administrator_impersonating_a_director_detail_row_is_masked(requester_ctx, make_user):
    req = _submit(requester_ctx)
    complete_intake_checks(SystemContext(), request_id=req.id)

    admin_user = make_user("admin2@example.org")
    RoleAssignment.objects.create(user=admin_user, role=roles.ADMINISTRATOR, granted_at=clock_now())
    ctx = actor_ctx(
        roles=frozenset({roles.HAM_DIRECTOR}),
        real_user_id=admin_user.id,
        impersonation_id=uuid.uuid4(),
    )
    detail = get_request_detail(ctx, req.id)
    assert detail is not None
    assert detail.is_masked_view is True
    assert detail.photo_count_only is True


def test_a_non_administrator_impersonating_a_director_is_not_masked(make_user):
    """Sanity check: this is specifically about the *real* actor being an Administrator, not
    about impersonation in general."""
    director_user = make_user("director@example.org")
    RoleAssignment.objects.create(
        user=director_user, role=roles.HAM_DIRECTOR, granted_at=clock_now()
    )
    ctx = actor_ctx(
        roles=frozenset({roles.HAM_DIRECTOR}),
        real_user_id=director_user.id,
        impersonation_id=uuid.uuid4(),
    )
    assert not is_masked_view(ctx)


def test_administrator_not_impersonating_is_still_masked(make_user):
    """Unaffected by this fix: the plain, non-impersonating Administrator case."""
    admin_user = make_user("admin3@example.org")
    RoleAssignment.objects.create(user=admin_user, role=roles.ADMINISTRATOR, granted_at=clock_now())
    ctx = actor_ctx(roles=frozenset({roles.ADMINISTRATOR}), user_id=admin_user.id)
    assert is_masked_view(ctx)
