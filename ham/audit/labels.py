"""Plain-language labels for audit event `action` codes (usability M5: "no raw error text,
internal action codes or IDs in the UI"; auth-and-access.md §H "ID-first, no requester names").

Pure presentation, no authorization here — this module only maps a code that already came
back from an authorized query to words a Director or Administrator would use. Every action
code actually written anywhere in the codebase (see the audit event `action=`/`audit_action=`
call sites) has an entry here; a test pins that.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActionGroup:
    label: str
    actions: tuple[str, ...]


# Grouped for the H1 filter bar's Action select (usability M7: "the grouped Action select").
ACTION_GROUPS: tuple[ActionGroup, ...] = (
    ActionGroup(
        "Signing in",
        (
            "auth.sign_in.succeeded",
            "auth.sign_in.locked",
            "auth.sign_out",
            "auth.step_up.succeeded",
            "auth.step_up.failed",
        ),
    ),
    ActionGroup(
        "Two-step sign-in",
        (
            "auth.mfa.enrolled",
            "auth.mfa.recovery_code_used",
            "auth.mfa.recovery_codes_regenerated",
            "auth.mfa.reset",
        ),
    ),
    ActionGroup(
        "People and roles",
        (
            "user.created",
            "user.identity_updated",
            "user.disabled",
            "user.enabled",
            "user.invitation_resent",
            "user.invitation_cancelled",
            "role.granted",
            "role.revoked",
        ),
    ),
    ActionGroup(
        "Projects and tasks",
        (
            "leader.project_assigned",
            "leader.project_revoked",
            "leader.task_assigned",
            "leader.task_revoked",
        ),
    ),
    ActionGroup(
        "Troubleshooting as someone else",
        (
            "impersonation.started",
            "impersonation.ended",
            "impersonation.action_blocked",
        ),
    ),
    ActionGroup(
        "Church settings",
        ("church_profile.updated", "outbox.retried"),
    ),
    ActionGroup(
        "Audit log",
        ("audit.exported",),
    ),
    # S2.0 (intake.md §6 "Audit actions", §10 "labels.py entries").
    ActionGroup(
        "Requests",
        (
            "request.submitted",
            "request.contact_verified",
            "request.status_changed",
            "request.duplicates_flagged",
            "request.cancelled",
            "request.created_assisted",
            "requester_pii.revealed",
        ),
    ),
    ActionGroup(
        "Requester links",
        (
            "requester_link.issued",
            "requester_link.regenerated",
            "requester_verification.locked",
        ),
    ),
    ActionGroup(
        "Request media",
        (
            "request_media.batch_opened",
            "request_media.uploaded",
            "request_media.rejected",
            "request_media.removed",
            "request_media.purged",
        ),
    ),
    ActionGroup(
        "Church-issued intake links",
        ("intake_source.created", "intake_source.deactivated"),
    ),
    # S2.5 (intake.md §5 notification.acknowledge, §10 "Urgent banner data").
    ActionGroup(
        "Notifications",
        ("notification.acknowledged",),
    ),
    ActionGroup(
        "Access denied",
        ("authz.denied",),
    ),
)

ACTION_LABELS: dict[str, str] = {
    "auth.sign_in.succeeded": "Signed in",
    "auth.sign_in.locked": "Sign-in locked (too many attempts)",
    "auth.sign_out": "Signed out",
    "auth.step_up.succeeded": "Confirmed it was them (step-up)",
    "auth.step_up.failed": "Step-up code didn't match",
    "auth.mfa.enrolled": "Set up two-step sign-in",
    "auth.mfa.recovery_code_used": "Used a recovery code",
    "auth.mfa.recovery_codes_regenerated": "Made new recovery codes",
    "auth.mfa.reset": "Two-step sign-in reset",
    "user.created": "Account created",
    "user.identity_updated": "Name or phone updated",
    "user.disabled": "Account turned off",
    "user.enabled": "Account turned on",
    "user.invitation_resent": "Invitation resent",
    "user.invitation_cancelled": "Invitation cancelled",
    "role.granted": "Role added",
    "role.revoked": "Role removed",
    "leader.project_assigned": "Assigned to lead a project",
    "leader.project_revoked": "Removed as project leader",
    "leader.task_assigned": "Assigned to lead a task",
    "leader.task_revoked": "Removed as task leader",
    "impersonation.started": "Started troubleshooting as someone else",
    "impersonation.ended": "Stopped troubleshooting as someone else",
    "impersonation.action_blocked": "Blocked action while troubleshooting",
    "church_profile.updated": "Church settings updated",
    "outbox.retried": "Integration delivery retried",
    "audit.exported": "Exported the audit log",
    "authz.denied": "Access denied",
    # S2.0 (intake.md §6).
    "request.submitted": "Request submitted",
    "request.contact_verified": "Contact verified",
    "request.status_changed": "Request status changed",
    "request.duplicates_flagged": "Possible earlier request flagged",
    "request.cancelled": "Request cancelled",
    "request.created_assisted": "Request entered on someone's behalf",
    "requester_pii.revealed": "Viewed requester contact details",
    "requester_link.issued": "Secure link sent",
    "requester_link.regenerated": "New secure link sent",
    "requester_verification.locked": "Verification locked (too many attempts)",
    "request_media.batch_opened": "Photo/video batch opened",
    "request_media.uploaded": "Photo/video uploaded",
    "request_media.rejected": "Photo/video rejected",
    "request_media.removed": "Photo/video removed",
    "request_media.purged": "Photo/video purged",
    "intake_source.created": "Church-issued link created",
    "intake_source.deactivated": "Church-issued link deactivated",
    "notification.acknowledged": "Acknowledged an urgent notification",
}


def action_label(action: str) -> str:
    """Plain-language label for an action code, falling back to the code itself so an
    unmapped action (a bug, not expected in production) never crashes the page."""
    return ACTION_LABELS.get(action, action)
