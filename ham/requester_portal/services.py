"""`ham.requester_portal`'s own write path (intake.md §2 "The portal orchestrates submission:
it verifies the draft, calls `requests.services.submit_request`, then issues the link, all in
one transaction").

S2.0 ships only the `issue_link` signature (a seam; see `ham.requests.services.submit_request`'s
docstring and `docs/architecture/intake-contracts.md` for the full contract).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class IssuedLink:
    """What `issue_link` hands back — the raw token (shown/emailed exactly once; only its hash
    and an encrypted copy are ever stored, intake.md §3 `RequesterAccessLink`) plus the row."""

    token: str
    link: Any  # RequesterAccessLink, once S2.3 defines the model.


def issue_link(
    *,
    request_id: UUID,
    kind: str,
    verification_id: UUID | None = None,
) -> IssuedLink:
    """`ham.requester_portal.services.issue_link` (S2.3 implements). Creates a new
    `RequesterAccessLink`, revoking any still-live link for the same request in the same
    transaction (`revoke_reason="superseded"`) — intake.md §4 "Issuing any link revokes the
    previous one in the same transaction. This is §76 'auto-invalidate', computed when read,
    so no job is needed."

    Contract (`docs/architecture/intake-contracts.md`):
    - `request_id`: the `AssistanceRequest` this link grants access to.
    - `kind`: `"initial"` (right after `ham.requests.services.submit_request`, no `expires_at`
      while the request stays open) or `"regenerated"` (Q-103/Q-117: same lifetime as the
      normal link if issued before normal access ended, else `REGENERATED_REQUESTER_LINK_
      LIFETIME`).
    - `verification_id`: the `RequesterVerificationChallenge` that authorized issuing this
      link (`purpose="intake"` for the initial link, `purpose="link_regeneration"` otherwise),
      stored on the new row so `requester_link.issued`/`requester_link.regenerated` audit
      events can reference it.
    - Returns an `IssuedLink` (the raw, one-time-visible token + the created row). The caller
      (the view, or the requester-facing confirmation email builder) is responsible for
      putting the token in the URL it sends; nothing else ever sees the raw token again.
    - Does not itself record an audit event or send an email — the caller
      (`ham.requester_portal`'s orchestration / notification builders, S2.3/S2.6) does that,
      since the audit action name (`requester_link.issued` vs `.regenerated`) and the outbox
      event (`RequesterAccessLinkIssued`) depend on `kind`.
    - Raises `NotImplementedError` until S2.3 lands.
    """
    raise NotImplementedError("S2.3 implements ham.requester_portal.services.issue_link")


def resolve_token(token: str, *, now: dt.datetime | None = None) -> Any:
    """`ham.requester_portal.services.resolve_token` (S2.3 implements): looks up a
    `RequesterAccessLink` by `ham.platform.otp.hash_matches` against every configured
    `HAM_TOKEN_HMAC_KEYS`, checks `ham.requester_portal.validity` (S2.1), and returns a
    `RequesterContext` for the request it grants access to, or `None` for an unknown/expired/
    revoked token (intake.md §7: "Unknown and invalid tokens get the same page").

    Declared here (not yet implemented) so S2.2's leadership screens and S2.3's own requester
    views can both be written against the same name before either side lands its body.
    """
    raise NotImplementedError("S2.3 implements ham.requester_portal.services.resolve_token")
