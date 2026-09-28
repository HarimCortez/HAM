"""`ham.requests`' own write path (intake.md §2 "a module calls another only through its
services.py, and only downward").

S2.0 ships only the `submit_request` signature (a seam, intake.md §10 "submit_request /
issue_link signatures as stubs raising NotImplementedError, so S2.2 and S2.3 can code against
each other") — see `docs/architecture/intake-contracts.md` for the exact contract S2.2 (this
function's real implementation) and S2.3 (`ham.requester_portal`, the only caller) both build
against without waiting on one another.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from ham.authz.context import RequesterContext


def submit_request(
    ctx: RequesterContext,
    *,
    draft_id: UUID,
    verification_id: UUID,
) -> Any:
    """`@command("request.submit")` (S2.2 implements). Creates the `AssistanceRequest` +
    `Requester` + `Property` rows from a verified `IntakeDraft`, records `request.submitted`
    (and `request.contact_verified`), and emits `RequestSubmitted` — intake.md §3, §4, §6.

    Called once, by `ham.requester_portal.services.submit_and_issue_link` (S2.3), inside the
    one transaction that also issues the first access link. `ctx.request_id` is `None` here
    (the only step-2 action where that's allowed, intake.md §5): the request doesn't exist yet.

    Contract (`docs/architecture/intake-contracts.md`):
    - `draft_id`: the `IntakeDraft` row whose `payload_ciphertext` holds the full submitted
      form (name/email/phone/address/relationship/property type/category/description/
      hazards/availability/contact preference/urgent+justification/certifications).
    - `verification_id`: the `RequesterVerificationChallenge` that must be `consumed_at`
      not-null, `purpose="intake"`, and reference this same `draft_id`, or the call raises
      `ValueError` (the service, not the matrix, enforces "verified before submit", Q-100).
    - Returns the created `AssistanceRequest` row (S2.2's model).
    - Raises `NotImplementedError` until S2.2 lands.
    """
    raise NotImplementedError("S2.2 implements ham.requests.services.submit_request")
