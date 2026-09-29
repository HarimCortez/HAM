"""Leadership email + in-app builders (PRD §35, §10; intake.md §6 "Who is notified";
docs/ux/intake.md §7 rows L-E1/L-E2/L-E3). Registered once from `RequestsConfig.ready()`,
onto the shared `ham.integrations.email.notifications` and `ham.notifications.inapp`
subscribers -- the same pattern `ham.identity.notifications` already uses for email, and
`ham.requests.attention` already uses for `ham.notifications`' registries.

Subjects/titles carry only the HAM #, category and the urgent flag -- never a requester name,
address, description or ZIP (§68; intake-contracts.md §6). Recipients are resolved through
`ham.identity.services.notification_recipients` (the one place auth tables are read,
intake-contracts.md §7), never by this module reading `User`/`RoleAssignment` itself.

**Duplicate flagged (Q-115):** no separate notification -- `request.duplicates_flagged` is an
audit event only; leaders see it on the request detail page's duplicate panel
(`request.history.view`, L2) the moment they open a request already in Awaiting Approval, so a
second alert would just repeat the same information already on L-E1/L-E2 (documented decision,
not a silent omission).
"""

from __future__ import annotations

from django.conf import settings

from ham.authz import roles
from ham.identity.services import (
    notification_recipients,
    notification_recipients_for_users,
    user_holds_global_role,
)
from ham.integrations.email.notifications import NotificationEmail, register_notification
from ham.notifications.inapp import InAppNotice, register_inapp
from ham.outbox.models import OutboxEvent
from ham.platform.clock import now as clock_now

_PAS_BRD_DIR_AD = (
    roles.PASTOR,
    roles.BOARD_REPRESENTATIVE,
    roles.HAM_DIRECTOR,
    roles.ASSISTANT_DIRECTOR,
)
_DIR_AD = (roles.HAM_DIRECTOR, roles.ASSISTANT_DIRECTOR)


def _request_row(request_id):
    from .models import AssistanceRequest
    from .states import RequestStatus

    request = AssistanceRequest.objects.filter(id=request_id).first()
    if request is None:
        return None
    return request, RequestStatus(request.status)


def _deep_link(request_id) -> str:
    base = str(settings.HAM_BASE_URL).rstrip("/")
    return f"{base}/requests/{request_id}"


def _category_label(request) -> str:
    from .models import NeedCategory

    try:
        return NeedCategory(request.need_category).label
    except ValueError:  # pragma: no cover - defensive; every stored value is a valid choice
        return request.need_category


# ---------------------------------------------------------------------------------------
# L-E3: "Phone check needed" (RequestSubmitted, only when it lands in NEEDS_PHONE_CHECK)
# ---------------------------------------------------------------------------------------
def _phone_check_recipients_and_row(event: OutboxEvent):
    row = _request_row(event.aggregate_id)
    if row is None:
        return None, None
    request, status = row
    from .states import RequestStatus as RS

    if status is not RS.NEEDS_PHONE_CHECK:
        # The email path (SUBMITTED) has no leadership notice of its own yet -- leaders are
        # told once the duplicate check finishes and the request reaches AWAITING_APPROVAL
        # (RequestAwaitingApproval, below).
        return None, None
    return request, notification_recipients(_DIR_AD)


def _build_needs_phone_check_notices(event: OutboxEvent) -> list[InAppNotice] | None:
    request, recipients = _phone_check_recipients_and_row(event)
    if request is None or not recipients:
        return None
    urgent = bool(event.payload.get("urgent"))
    title = f"Phone check needed · {request.display_number}"
    return [
        InAppNotice(
            recipient_user_id=user_id,
            kind="request_needs_phone_check",
            subject_type="request",
            subject_id=request.id,
            title=title,
            urgent=urgent,
            requires_ack=urgent,
        )
        for user_id, _email, _notify_email in recipients
    ]


def _build_needs_phone_check_emails(event: OutboxEvent) -> list[NotificationEmail] | None:
    request, recipients = _phone_check_recipients_and_row(event)
    if request is None or not recipients:
        return None
    urgent = bool(event.payload.get("urgent"))
    subject = f"Phone check needed · {request.display_number}"
    text = (
        f"A request without an email address is waiting for a phone check: "
        f"{request.display_number}.\n\nOpen it: {_deep_link(request.id)}"
    )
    return [
        NotificationEmail(to=email, subject=subject, text_body=text, category="leader_update")
        for _user_id, email, notify_email in recipients
        # Q-133: urgent overrides the preference; everyone else only if they opted in.
        if urgent or notify_email
    ] or None


# ---------------------------------------------------------------------------------------
# L-E1 / L-E2: "Request waiting for review" / "Urgent request needs a pastor"
# (RequestAwaitingApproval)
# ---------------------------------------------------------------------------------------
def _awaiting_approval_notice(*, user_id, request, title: str, urgent: bool) -> InAppNotice:
    return InAppNotice(
        recipient_user_id=user_id,
        kind="request_awaiting_approval",
        subject_type="request",
        subject_id=request.id,
        title=title,
        urgent=urgent,
        requires_ack=urgent,
    )


def _build_awaiting_approval_notices(event: OutboxEvent) -> list[InAppNotice] | None:
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    urgent = bool(event.payload.get("urgent"))
    category = _category_label(request)
    if urgent:
        title = f"Urgent request needs a pastor · {request.display_number} {category}"
        # FIX-3D hand-back item 2: "needs a pastor" addresses the wrong role in a
        # Director/AD/Board-rep Inbox -- they're not the one being asked to act on it, and
        # the wording read like an instruction meant for them. Their own in-app update
        # (Q-121, intake.md §6 "DIR, AD: in-app update") stays factual instead.
        other_title = f"Urgent request awaiting a pastor · {request.display_number} {category}"
    else:
        title = f"Request waiting for review · {request.display_number} {category}"
        other_title = title

    notices = [
        # Fix 3E / FIX-3D hand-back item 2: only pastors get the "needs a pastor" wording (as
        # the urgent, must-acknowledge banner) or, non-urgent, the plain review wording --
        # this notice's recipient targeting is pastors only.
        _awaiting_approval_notice(user_id=user_id, request=request, title=title, urgent=urgent)
        for user_id, _email, _notify_email in notification_recipients((roles.PASTOR,))
    ]
    notices += [
        _awaiting_approval_notice(user_id=user_id, request=request, title=other_title, urgent=False)
        for user_id, _email, _notify_email in notification_recipients(
            (roles.BOARD_REPRESENTATIVE, *_DIR_AD)
        )
    ]
    return notices or None


def _build_awaiting_approval_emails(event: OutboxEvent) -> list[NotificationEmail] | None:
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    urgent = bool(event.payload.get("urgent"))
    category = _category_label(request)
    link = _deep_link(request.id)

    if urgent:
        subject = f"Urgent request needs a pastor · {request.display_number} {category}"
        text = (
            f"An urgent request is waiting for a pastor's review: {request.display_number} "
            f"({category}).\n\nOpen it: {link}"
        )
        # Q-123: every pastor, by email, regardless of their preference. Director/AD get an
        # in-app update only for this event (see `_build_awaiting_approval_notices`).
        emails = [
            NotificationEmail(to=email, subject=subject, text_body=text, category="leader_update")
            for _user_id, email, _notify_email in notification_recipients((roles.PASTOR,))
        ]
        return emails or None

    subject = f"Request waiting for review · {request.display_number} {category}"
    text = (
        f"A request is waiting for a decision: {request.display_number} ({category}).\n\n"
        f"Open it: {link}"
    )
    emails = [
        NotificationEmail(to=email, subject=subject, text_body=text, category="leader_update")
        for _user_id, email, notify_email in notification_recipients(_PAS_BRD_DIR_AD)
        if notify_email
    ]
    return emails or None


# ---------------------------------------------------------------------------------------
# RequestCancelled: in-app update to Director/AD (intake.md §6)
# ---------------------------------------------------------------------------------------
def _build_cancelled_notices(event: OutboxEvent) -> list[InAppNotice] | None:
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    title = f"Closed · {request.display_number}"
    return [
        InAppNotice(
            recipient_user_id=user_id,
            kind="request_cancelled",
            subject_type="request",
            subject_id=request.id,
            title=title,
        )
        for user_id, _email, _notify_email in notification_recipients(_DIR_AD)
    ] or None


# ---------------------------------------------------------------------------------------
# S3.5 (approvals.md §4, docs/ux/approvals.md L-E5-L-E12, Q-168/Q-161/Q-176). Titles carry
# only the HAM # and category -- never a reason, a question/answer, or a decider's name
# (Q-170's "the requester" rule is about *requester*-facing copy; leadership screens may
# show a decider's name on the detail page itself, but this module's own
# subjects/titles/in-app notices stay name-free like every other builder here, matching the
# "no PII in subjects/titles" test convention already used by the S2.6 builders above).
#
# Idempotency: every builder below is a pure read of already-committed rows keyed off the
# event's own ids/payload (`RequestApproved`/`RequestRejected` are themselves only ever
# emitted once, at `effective_at`, by the held-effects job's own idempotency marker,
# approvals-contracts.md §4) -- a redelivered `OutboxDelivery` produces the same recipients
# and copy every time.
# ---------------------------------------------------------------------------------------
def _live_approval_for_stage(request_id, stage: str):
    from .models import Approval

    return (
        Approval.objects.filter(request_id=request_id, stage=stage, undone_at__isnull=True)
        .order_by("-decided_at")
        .first()
    )


def _clear_urgent_banner(request_id) -> None:
    """Q-160/L-E12 "the urgent banner clears": once a pastor has reviewed the urgency
    (certified or declined) every pastor's still-unacknowledged must-ack banner for this
    request is system-cleared, not just the reviewer's own -- `urgent_banner_for` only ever
    shows an unacknowledged `requires_ack` row, so clearing every row for this request's
    subject makes the banner disappear for everyone at once, matching the UX spec's "the
    urgent banner clears" rather than "clears once each pastor happens to dismiss it".

    Security H1: scoped to exactly the pastors' own `request_awaiting_approval` must-ack
    banner (the "Urgent request needs a pastor" card) -- never `request_urgent_approval`
    (the Director/AD "Urgent request approved" alert, Q-160/Q-161), and never a recipient who
    isn't a pastor. The two banners are independent must-ack facts; clearing one must never
    silently acknowledge the other."""
    from ham.notifications.models import Notification

    pastor_ids = [
        user_id for user_id, _email, _notify_email in notification_recipients((roles.PASTOR,))
    ]
    if not pastor_ids:
        return
    Notification.objects.filter(
        subject_type="request",
        subject_id=request_id,
        kind="request_awaiting_approval",
        recipient_user_id__in=pastor_ids,
        requires_ack=True,
        acknowledged_at__isnull=True,
    ).update(acknowledged_at=clock_now())


def clear_pastor_urgent_banner_on_decline(request_id) -> None:
    """UX M9: `reject_request` (an urgent request declined, not certified/reviewed) calls
    this directly -- declining emits no `UrgencyCertified`/`UrgencyNotCertified` event of its
    own for `_clear_urgent_banner` to hang off, but the requirement is the same: once ANY
    decision has been recorded on an urgent request, the other pastors' "needs a pastor"
    must-ack banner is stale and must clear, alarm-fatigue reasoning identical to a
    certify/decline urgency review."""
    _clear_urgent_banner(request_id)


def _clear_urgent_approval_banner(request_id) -> None:
    """UX M9: undoing an urgent approval clears the Director/AD "Urgent request approved"
    must-ack banner (it's no longer true) -- the mirror-image scoping of `_clear_urgent_
    banner` above, for the *other* must-ack kind and the *other* recipient set."""
    from ham.notifications.models import Notification

    dir_ad_ids = [user_id for user_id, _email, _notify_email in notification_recipients(_DIR_AD)]
    if not dir_ad_ids:
        return
    Notification.objects.filter(
        subject_type="request",
        subject_id=request_id,
        kind="request_urgent_approval",
        recipient_user_id__in=dir_ad_ids,
        requires_ack=True,
        acknowledged_at__isnull=True,
    ).update(acknowledged_at=clock_now())


# ---------------------------------------------------------------------------------------
# RequestApproved / RequestRejected (held, approvals-contracts.md §4): the "decision" in-app
# update to Director, AD and the other approvers, not the decider (Q-168). Approvals also go
# by email to Director/AD per preference -- unless the decision is also an urgent approval,
# in which case `RequestUrgentApproval` (below) already reaches them by every channel, so
# this builder skips DIR/AD entirely for that case rather than double-notifying.
# ---------------------------------------------------------------------------------------
def _build_decision_notices(event: OutboxEvent) -> list[InAppNotice] | None:
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    stage = event.payload.get("stage", "initial")
    approval = _live_approval_for_stage(request.id, stage)
    if approval is None:  # pragma: no cover - defensive; the held job only fires once decided
        return None

    approved = event.event_type == "RequestApproved"
    urgent = bool(event.payload.get("urgent_approval"))
    category = _category_label(request)
    title = f"{'Approved' if approved else 'Not approved'} · {request.display_number} {category}"

    notices = [
        InAppNotice(
            recipient_user_id=user_id,
            kind="request_decided",
            subject_type="request",
            subject_id=request.id,
            title=title,
        )
        for user_id, _email, _notify_email in notification_recipients(
            (roles.PASTOR, roles.BOARD_REPRESENTATIVE)
        )
        if user_id != approval.decided_by_user_id
    ]
    if not (approved and urgent):
        notices += [
            InAppNotice(
                recipient_user_id=user_id,
                kind="request_decided",
                subject_type="request",
                subject_id=request.id,
                title=title,
            )
            for user_id, _email, _notify_email in notification_recipients(_DIR_AD)
        ]
    if approval.took_over_from_user_id is not None:
        # Q-157: the original pastor is told in-app that another pastor took over (held
        # until the window closes, same as the rest of this decision's effects).
        notices += [
            InAppNotice(
                recipient_user_id=user_id,
                kind="reconsideration_taken_over",
                subject_type="request",
                subject_id=request.id,
                title=f"Reconsideration taken over · {request.display_number}",
            )
            for user_id, _email, _notify_email in notification_recipients_for_users(
                [approval.took_over_from_user_id]
            )
        ]
    return notices or None


def _build_decision_emails(event: OutboxEvent) -> list[NotificationEmail] | None:
    """Q-168: approvals only, Director/AD, per preference -- rejections get no email (the
    in-app Update covers it); an urgent approval is emailed by `RequestUrgentApproval`
    instead (regardless of preference), so this skips DIR/AD for that case."""
    if event.event_type != "RequestApproved":
        return None
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    if bool(event.payload.get("urgent_approval")):
        return None
    category = _category_label(request)
    subject = f"Approved · {request.display_number} {category}"
    text = (
        f"A request was approved: {request.display_number} ({category}).\n\n"
        f"Open it: {_deep_link(request.id)}"
    )
    emails = [
        NotificationEmail(to=email, subject=subject, text_body=text, category="leader_update")
        for _user_id, email, notify_email in notification_recipients(_DIR_AD)
        if notify_email
    ]
    return emails or None


# ---------------------------------------------------------------------------------------
# L-E5: RequestUrgentApproval (Q-160/Q-161, never held) -- Director/AD, every channel,
# regardless of preference, must-acknowledge in-app banner. Fires exactly once per decision
# (approvals-contracts.md §4/§6: a single, dedicated event, never a second `RequestApproved`
# delivery).
# ---------------------------------------------------------------------------------------
def _build_urgent_approval_notices(event: OutboxEvent) -> list[InAppNotice] | None:
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    category = _category_label(request)
    title = f"Urgent request approved · {request.display_number} {category}"
    return [
        InAppNotice(
            recipient_user_id=user_id,
            kind="request_urgent_approval",
            subject_type="request",
            subject_id=request.id,
            title=title,
            urgent=True,
            requires_ack=True,
        )
        for user_id, _email, _notify_email in notification_recipients(_DIR_AD)
    ] or None


def _build_urgent_approval_emails(event: OutboxEvent) -> list[NotificationEmail] | None:
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    category = _category_label(request)
    subject = f"Urgent request approved · {request.display_number} {category}"
    text = (
        f"An urgent request has been approved: {request.display_number} ({category}).\n\n"
        f"Open it: {_deep_link(request.id)}"
    )
    # Q-161: every supported channel regardless of preference -- no `notify_email` filter.
    return [
        NotificationEmail(to=email, subject=subject, text_body=text, category="leader_urgent")
        for _user_id, email, _notify_email in notification_recipients(_DIR_AD)
    ] or None


# ---------------------------------------------------------------------------------------
# Q-176 "urgent approval was undone" follow-up: `RequestDecisionUndone` (an `Approval`) or
# `RequestUrgencyReviewUndone` (a standalone `UrgencyReview`) -- looked up by the id in the
# payload, per approvals-contracts.md §4's own instruction, never a repeated
# `urgent_approval` flag in the payload itself.
# ---------------------------------------------------------------------------------------
def _any_urgent_alert_emitted_since(request_id, since) -> bool:
    """Security M2 (owner resolution note): "undo of a Board (or any) approval sends the
    Director/AD 'urgent approval was undone' follow-up if any urgent-approval alert was
    emitted for this request since that approval's `decided_at`" -- an Approval that itself
    never triggered the alert (e.g. a Board approval of a not-yet-certified request) can
    still be the thing undone AFTER a later standalone certification made it an urgent
    approval; undoing the approval reverts that state, so the follow-up must still fire.
    Reads only the stored `urgent_approval_emitted` facts, never live status."""
    from .models import Approval, UrgencyReview

    if Approval.objects.filter(
        request_id=request_id, urgent_approval_emitted=True, decided_at__gte=since
    ).exists():
        return True
    return UrgencyReview.objects.filter(
        request_id=request_id, urgent_approval_emitted=True, decided_at__gte=since
    ).exists()


def _build_decision_undone_notices(event: OutboxEvent) -> list[InAppNotice] | None:
    """Security M2/N2: keyed on the stored `urgent_approval_emitted`/`.banner_cleared` facts
    (on this `Approval` and any `UrgencyReview` for the same request) -- set once, at decision
    time -- never re-derived from the request's current status (which may have moved on
    since, e.g. a later re-decision or cancel)."""
    from .models import Approval

    approval_id = event.payload.get("approval_id")
    approval = Approval.objects.filter(id=approval_id).first()
    if approval is None:
        return None
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    notices: list[InAppNotice] = []
    if _any_urgent_alert_emitted_since(request.id, approval.decided_at):
        _clear_urgent_approval_banner(request.id)  # UX M9
        category = _category_label(request)
        title = f"Urgent approval undone · {request.display_number} {category}"
        notices += [
            InAppNotice(
                recipient_user_id=user_id,
                kind="request_urgent_approval_undone",
                subject_type="request",
                subject_id=request.id,
                title=title,
            )
            for user_id, _email, _notify_email in notification_recipients(_DIR_AD)
        ]
    if approval.banner_cleared:
        # Security N2 / UX M9: undoing a decline, or an approve that bundled a certify/
        # decline, restores the pastors' urgent banner this decision had cleared -- keyed
        # only on the stored fact, never on re-reading live status (security L-b).
        notices += _restore_pastor_urgent_banner(request)
    return notices or None


def _build_urgency_review_undone_notices(event: OutboxEvent) -> list[InAppNotice] | None:
    """Security M2/N2: a standalone `UrgencyReview` carries its own `urgent_approval_emitted`/
    `.banner_cleared` facts (set at creation time inside `review_urgency`, same shape as
    `Approval`'s) -- no re-deriving either from the request's live status at undo/dispatch
    time, which could be wrong by then."""
    from .models import UrgencyReview

    review_id = event.payload.get("review_id")
    review = UrgencyReview.objects.filter(id=review_id).first()
    if review is None:
        return None
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    notices: list[InAppNotice] = []
    if review.urgent_approval_emitted:
        _clear_urgent_approval_banner(request.id)  # UX M9
        category = _category_label(request)
        title = f"Urgent approval undone · {request.display_number} {category}"
        notices += [
            InAppNotice(
                recipient_user_id=user_id,
                kind="request_urgent_approval_undone",
                subject_type="request",
                subject_id=request.id,
                title=title,
            )
            for user_id, _email, _notify_email in notification_recipients(_DIR_AD)
        ]
    if review.banner_cleared:
        notices += _restore_pastor_urgent_banner(request)  # UX M9 / security N2
    return notices or None


def _restore_pastor_urgent_banner(request) -> list[InAppNotice]:
    """Security N2 / UX M9: undoing a decision that had cleared the pastors' must-ack "needs
    a pastor" banner restores it -- keyed purely on the caller's own stored `banner_cleared`
    fact (never on re-reading the request's live status, security L-b: that re-derivation is
    exactly what silently dropped the restore for a plain decline/"Not urgent" undo before
    this fix). Skips any pastor who already has an unacknowledged banner for this request, so
    undo never creates a duplicate."""
    from ham.notifications.models import Notification

    already_has_banner = set(
        Notification.objects.filter(
            subject_type="request",
            subject_id=request.id,
            kind="request_awaiting_approval",
            requires_ack=True,
            acknowledged_at__isnull=True,
        ).values_list("recipient_user_id", flat=True)
    )
    category = _category_label(request)
    title = f"Urgent request needs a pastor · {request.display_number} {category}"
    return [
        InAppNotice(
            recipient_user_id=user_id,
            kind="request_awaiting_approval",
            subject_type="request",
            subject_id=request.id,
            title=title,
            urgent=True,
            requires_ack=True,
        )
        for user_id, _email, _notify_email in notification_recipients((roles.PASTOR,))
        if user_id not in already_has_banner
    ]


# ---------------------------------------------------------------------------------------
# UrgencyCertified / UrgencyNotCertified (always immediate, never held): Director/AD get an
# update either way; "Not urgent" also clears the must-ack banner for every pastor and tells
# them the request left the urgent queue (L-E12, Q-160).
# ---------------------------------------------------------------------------------------
def _build_urgency_certified_notices(event: OutboxEvent) -> list[InAppNotice] | None:
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, status = row
    from .states import RequestStatus

    _clear_urgent_banner(request.id)
    if status is RequestStatus.APPROVED:
        # Already covered by `RequestUrgentApproval`, emitted in the same transaction --
        # no second DIR/AD notice for the same fact.
        return None
    category = _category_label(request)
    title = f"Certified urgent · {request.display_number} {category}"
    return [
        InAppNotice(
            recipient_user_id=user_id,
            kind="request_urgency_certified",
            subject_type="request",
            subject_id=request.id,
            title=title,
        )
        for user_id, _email, _notify_email in notification_recipients(_DIR_AD)
    ] or None


def _build_urgency_not_certified_notices(event: OutboxEvent) -> list[InAppNotice] | None:
    """PRD guardian M8 (owner box): "Not urgent" sends no in-app update at all -- only the
    silent pastors' banner clear (H1-scoped, above). Returns `None` unconditionally; kept as
    a registered builder (rather than removed) so the banner-clearing side effect still runs
    on every `UrgencyNotCertified` delivery."""
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    _clear_urgent_banner(request.id)
    return None


# ---------------------------------------------------------------------------------------
# ReconsiderationRequested (immediate): the original decider (or every pastor if that
# person lost the role), every Board rep on the Board route, plus Director/AD awareness
# (Q-168).
# ---------------------------------------------------------------------------------------
def _reconsideration_row(event: OutboxEvent):
    from .models import Reconsideration

    reconsideration_id = event.payload.get("reconsideration_id")
    return Reconsideration.objects.filter(id=reconsideration_id).first()


def _addressed_recipients(reconsideration):
    from .models import ApprovalRoute

    if reconsideration.route == ApprovalRoute.BOARD.value:
        return notification_recipients((roles.BOARD_REPRESENTATIVE,))
    if user_holds_global_role(reconsideration.original_decider_user_id, roles.PASTOR):
        return notification_recipients_for_users([reconsideration.original_decider_user_id])
    return notification_recipients((roles.PASTOR,))


def _build_reconsideration_notices(event: OutboxEvent) -> list[InAppNotice] | None:
    reconsideration = _reconsideration_row(event)
    if reconsideration is None:
        return None
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    category = _category_label(request)
    title = f"Reconsideration asked · {request.display_number} {category}"

    notices = [
        InAppNotice(
            recipient_user_id=user_id,
            kind="reconsideration_requested",
            subject_type="request",
            subject_id=request.id,
            title=title,
        )
        for user_id, _email, _notify_email in _addressed_recipients(reconsideration)
    ]
    notices += [
        InAppNotice(
            recipient_user_id=user_id,
            kind="reconsideration_requested",
            subject_type="request",
            subject_id=request.id,
            title=title,
        )
        for user_id, _email, _notify_email in notification_recipients(_DIR_AD)
    ]
    return notices or None


def _build_reconsideration_emails(event: OutboxEvent) -> list[NotificationEmail] | None:
    reconsideration = _reconsideration_row(event)
    if reconsideration is None:
        return None
    row = _request_row(event.aggregate_id)
    if row is None:
        return None
    request, _status = row
    category = _category_label(request)
    subject = f"Reconsideration asked · {request.display_number} {category}"
    text = (
        f"A requester has asked HAM to reconsider: {request.display_number} ({category}).\n\n"
        f"Open it: {_deep_link(request.id)}"
    )
    emails = [
        NotificationEmail(to=email, subject=subject, text_body=text, category="leader_update")
        for _user_id, email, notify_email in _addressed_recipients(reconsideration)
        if notify_email
    ]
    return emails or None


# ---------------------------------------------------------------------------------------
# L-E7: RequesterQuestionAnswered -- the asker only, in-app + email per preference.
# ---------------------------------------------------------------------------------------
def _asker_recipients(event: OutboxEvent):
    from .models import RequestQuestion

    question_id = event.payload.get("question_id")
    question = RequestQuestion.objects.filter(id=question_id).first()
    if question is None:
        return None, None
    return question, notification_recipients_for_users([question.asked_by_user_id])


def _build_question_answered_notices(event: OutboxEvent) -> list[InAppNotice] | None:
    question, recipients = _asker_recipients(event)
    if question is None or not recipients:
        return None
    row = _request_row(question.request_id)
    if row is None:
        return None
    request, _status = row
    title = f"Answer received · {request.display_number}"
    return [
        InAppNotice(
            recipient_user_id=user_id,
            kind="question_answered",
            subject_type="request",
            subject_id=request.id,
            title=title,
        )
        for user_id, _email, _notify_email in recipients
    ] or None


def _build_question_answered_emails(event: OutboxEvent) -> list[NotificationEmail] | None:
    question, recipients = _asker_recipients(event)
    if question is None or not recipients:
        return None
    row = _request_row(question.request_id)
    if row is None:
        return None
    request, _status = row
    subject = f"Answer received · {request.display_number}"
    text = (
        f"Your question on {request.display_number} has been answered.\n\n"
        f"Open it: {_deep_link(request.id)}"
    )
    emails = [
        NotificationEmail(to=email, subject=subject, text_body=text, category="leader_update")
        for _user_id, email, notify_email in recipients
        if notify_email
    ]
    return emails or None


def register() -> None:
    """Called once from `RequestsConfig.ready()`."""
    register_notification("RequestSubmitted", _build_needs_phone_check_emails)
    register_inapp("RequestSubmitted", _build_needs_phone_check_notices)
    register_notification("RequestAwaitingApproval", _build_awaiting_approval_emails)
    register_inapp("RequestAwaitingApproval", _build_awaiting_approval_notices)
    register_inapp("RequestCancelled", _build_cancelled_notices)

    # S3.5 (approvals.md §4, Q-168/Q-161/Q-176).
    register_inapp("RequestApproved", _build_decision_notices)
    register_notification("RequestApproved", _build_decision_emails)
    register_inapp("RequestRejected", _build_decision_notices)
    register_inapp("RequestUrgentApproval", _build_urgent_approval_notices)
    register_notification("RequestUrgentApproval", _build_urgent_approval_emails)
    register_inapp("RequestDecisionUndone", _build_decision_undone_notices)
    register_inapp("RequestUrgencyReviewUndone", _build_urgency_review_undone_notices)
    register_inapp("UrgencyCertified", _build_urgency_certified_notices)
    register_inapp("UrgencyNotCertified", _build_urgency_not_certified_notices)
    register_inapp("ReconsiderationRequested", _build_reconsideration_notices)
    register_notification("ReconsiderationRequested", _build_reconsideration_emails)
    register_inapp("RequesterQuestionAnswered", _build_question_answered_notices)
    register_notification("RequesterQuestionAnswered", _build_question_answered_emails)


__all__ = ["register"]
