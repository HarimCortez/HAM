from __future__ import annotations

import uuid

import pytest

from ham.authz.context import ActorContext, RequesterContext, SystemContext
from ham.requests.certifications import required_statements
from ham.requests.services import SubmittedRequestPayload
from ham.requests.states import VerificationMethod


def actor_ctx(*, roles: frozenset[str], **overrides) -> ActorContext:
    return ActorContext(
        user_id=overrides.pop("user_id", uuid.uuid4()),
        real_user_id=overrides.pop("real_user_id", None),
        roles=roles,
        is_active=True,
        mfa_satisfied=True,
        **overrides,
    )


def make_payload(**overrides) -> SubmittedRequestPayload:
    relationship = overrides.pop("relationship_to_property", "owner")
    defaults = dict(
        full_name="Jane Test",
        phone="+13055550111",
        email="jane@example.org",
        line1="123 Main St",
        city="Metropolis",
        state="FL",
        postal_code="33101",
        property_type="house",
        relationship_to_property=relationship,
        need_category="plumbing_or_water",
        preferred_contact_method="email",
        attested_statements=required_statements(relationship),
        verification_method=VerificationMethod.EMAIL_CODE,
        verified_value="jane@example.org",
    )
    defaults.update(overrides)
    return SubmittedRequestPayload(**defaults)


def no_email_payload(**overrides) -> SubmittedRequestPayload:
    overrides.setdefault("email", None)
    overrides.setdefault("email_opt_out", True)
    overrides.setdefault("verification_method", VerificationMethod.STAFF_PHONE_CALL)
    overrides.setdefault("verified_value", "")
    overrides.setdefault("full_name", "No Email Guy")
    overrides.setdefault("phone", "+13055550122")
    return make_payload(**overrides)


@pytest.fixture
def requester_ctx() -> RequesterContext:
    return RequesterContext(request_id=None)


@pytest.fixture
def system_ctx() -> SystemContext:
    return SystemContext()


@pytest.fixture
def director_ctx() -> ActorContext:
    return actor_ctx(roles=frozenset({"HAM_DIRECTOR"}))


@pytest.fixture
def assistant_director_ctx() -> ActorContext:
    return actor_ctx(roles=frozenset({"ASSISTANT_DIRECTOR"}))


@pytest.fixture
def pastor_ctx() -> ActorContext:
    return actor_ctx(roles=frozenset({"PASTOR"}))


@pytest.fixture
def board_rep_ctx() -> ActorContext:
    return actor_ctx(roles=frozenset({"BOARD_REPRESENTATIVE"}))


@pytest.fixture
def administrator_ctx() -> ActorContext:
    return actor_ctx(roles=frozenset({"ADMINISTRATOR"}))
