"""The deny-by-default action matrix (foundation.md §4, PRD §67, §68; Q-038: fixed in code,
never Admin-editable).

Every consequential action HAM can perform is declared here once, with the roles that grant
it, its scope rule, whether it needs a fresh step-up (Q-010, Q-031, Q-046), and whether it is
refused while impersonating (§59, foundation.md owner-decisions box).

This is the single source of truth for ``docs/architecture/permission-matrix.md``
(``manage.py build_permission_matrix --check``) and for ``tests/authz/expected_matrix.csv``
(the test engineer's independent oracle).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from . import roles


class Scope(Enum):
    """Scope rules from foundation.md §4."""

    ANY = "any"
    SELF = "self"
    LEADS_PROJECT = "leads_project"
    LEADS_TASK = "leads_task"
    # Declared for later modules (foundation.md §4); no step-1 action uses them yet.
    ASSIGNED_PROJECT = "assigned_project"
    INVITED_PROJECT = "invited_project"
    # Special-cased in `authorize()`: only the Administrator currently impersonating.
    IMPERSONATING_ADMIN = "impersonating_admin"
    # S2.0 (intake.md §5): a `RequesterContext`'s own request only — compares
    # `ctx.request_id` to `resource.request_id`, never to a `user_id` (a requester has no
    # `User` row, intake.md §3 `Requester`).
    OWN_REQUEST = "own_request"


@dataclass(frozen=True, slots=True)
class ActionRule:
    allowed_roles: frozenset[str]
    scope: Scope = Scope.ANY
    step_up: bool = False
    blocked_while_impersonating: bool = False
    prd: tuple[str, ...] = ()


# Roles.ALL_ROLES minus the two scoped-only roles: any signed-in person with at least one
# standing (global) role reaches the shell and their own `Me` page. A person with genuinely no
# role (shouldn't normally exist) is denied, matching "deny if ... no role grants it".
ANY_STANDING_ROLE = roles.GLOBAL_ROLES | {roles.PROJECT_LEADER, roles.TASK_LEADER}

# ADM Administrator, DIR Director, AD Assistant Director, PAS Pastor, BRD Board rep.
_ADM = frozenset({roles.ADMINISTRATOR})
_ADM_DIR = frozenset({roles.ADMINISTRATOR, roles.HAM_DIRECTOR})
_ADM_DIR_AD = frozenset({roles.ADMINISTRATOR, roles.HAM_DIRECTOR, roles.ASSISTANT_DIRECTOR})
_DIR_AD = frozenset({roles.HAM_DIRECTOR, roles.ASSISTANT_DIRECTOR})  # Q-054: not Administrator

# S2.0 pseudo-roles (intake.md §5): never in `roles.GLOBAL_ROLES`/`ANY_STANDING_ROLE`, so they
# never reach `shell.use`/`me.*` by accident; declared here only for the handful of actions
# below that name them explicitly.
_REQUESTER = frozenset({"REQUESTER"})
_SYSTEM = frozenset({"SYSTEM"})

# Step 3 (approvals.md §3, amended by its owner-decisions box). PAS Pastor, BRD Board rep.
_PAS = frozenset({roles.PASTOR})
_PAS_BRD = frozenset({roles.PASTOR, roles.BOARD_REPRESENTATIVE})

# intake.md §1/§5: Director, Assistant Director, Pastor, Board representative see every
# request awaiting approval (§4.3, §8; Q-106/Q-125). Q-124 (decided): the Administrator gets
# view-only access to requests/media with contact details masked and no reveal, alongside this
# set but NOT `requester_pii.reveal` (a separate action below).
_DIR_AD_PAS_BRD = frozenset(
    {roles.HAM_DIRECTOR, roles.ASSISTANT_DIRECTOR, roles.PASTOR, roles.BOARD_REPRESENTATIVE}
)
_ADM_DIR_AD_PAS_BRD = _DIR_AD_PAS_BRD | _ADM

MATRIX: dict[str, ActionRule] = {
    "shell.use": ActionRule(ANY_STANDING_ROLE, prd=("§67",)),
    "me.view": ActionRule(ANY_STANDING_ROLE, scope=Scope.SELF, prd=("§67",)),
    # Blocked while impersonating (item 6, docs/ux/auth-and-access.md I3's "the target's own
    # ... consents/decisions" pattern): saving would apply to the *impersonated* identity
    # (`ctx.user_id`) while an unblocked view would display the real signed-in person's own
    # record, which is confusing and unsafe to let an Admin change on someone else's behalf.
    "me.update": ActionRule(
        ANY_STANDING_ROLE, scope=Scope.SELF, blocked_while_impersonating=True, prd=("§67", "§59")
    ),
    "me.security.manage": ActionRule(
        ANY_STANDING_ROLE, scope=Scope.SELF, blocked_while_impersonating=True, prd=("§60",)
    ),
    "me.recovery_codes.regenerate": ActionRule(
        ANY_STANDING_ROLE,
        scope=Scope.SELF,
        step_up=True,
        blocked_while_impersonating=True,
        prd=("§60.1", "Q-046"),
    ),
    # PRD-GAP Q-083: declared per foundation.md §4.11 owner-decisions box ("changing sign-in
    # email" needs step-up), but S3b did not build the "verify the new address by code" flow
    # (Q-051) in this slice — see docs/prd-open-questions.md Q-083. No route uses this action
    # yet (like `requester_pii.reveal`/`audit.view_deleted_comment` above it lands later).
    "me.sign_in_email.change": ActionRule(
        ANY_STANDING_ROLE,
        scope=Scope.SELF,
        step_up=True,
        blocked_while_impersonating=True,
        prd=("§60.2", "Q-051", "Q-046"),
    ),
    "church_profile.update": ActionRule(
        _ADM, blocked_while_impersonating=True, prd=("§4.11", "Q-007")
    ),
    "user.list": ActionRule(_ADM_DIR, prd=("§4.11", "Q-041")),
    "user.view": ActionRule(_ADM_DIR, prd=("§4.11", "Q-041")),
    # Q-037 (decided): Admin, Director and Assistant Director may invite. This is an admin
    # action on someone else's account, so it is blocked while impersonating, like disable
    # (Q-080, decided: matches docs/ux/auth-and-access.md §4 I3's expanded blocked-action list).
    "user.invite": ActionRule(
        _ADM_DIR_AD, blocked_while_impersonating=True, prd=("§4.11", "Q-037")
    ),
    # UX C5/B3: whoever may invite may also resend (new 7-day window, Q-071) or cancel a
    # still-Invited person's invitation.
    "user.invitation_resend": ActionRule(
        _ADM_DIR_AD, blocked_while_impersonating=True, prd=("§4.11", "Q-037", "Q-071")
    ),
    "user.invitation_cancel": ActionRule(
        _ADM_DIR_AD, blocked_while_impersonating=True, prd=("§4.11", "Q-037", "Q-052")
    ),
    "user.update_identity": ActionRule(_ADM, prd=("§4.11",)),
    # Q-079 (closed, answered by Q-052): the Director may disable/enable accounts that don't
    # hold Administrator — `disable_user`/`enable_user` (ham/identity/services.py) enforce the
    # finer-grained "not an Administrator" rule the matrix can't express (like
    # `_check_can_grant` does for role grants).
    # Q-080 (decided): blocked_while_impersonating=True follows docs/ux/auth-and-access.md §4 I3's
    # expanded blocked-action list ("user invites/turn-off"), which is more specific than
    # foundation.md's compressed owner-decisions summary.
    "user.disable": ActionRule(
        _ADM_DIR, blocked_while_impersonating=True, prd=("§4.11", "Q-035", "Q-052", "Q-079")
    ),
    "user.enable": ActionRule(
        _ADM_DIR, blocked_while_impersonating=True, prd=("§4.11", "Q-052", "Q-079")
    ),
    "user.mfa_reset": ActionRule(
        _ADM, step_up=True, blocked_while_impersonating=True, prd=("§60.1", "Q-035")
    ),
    "role.grant_global": ActionRule(
        _ADM_DIR, step_up=True, blocked_while_impersonating=True, prd=("§4.11", "§58", "Q-041")
    ),
    "role.revoke_global": ActionRule(
        _ADM_DIR, step_up=True, blocked_while_impersonating=True, prd=("§4.11", "§58", "Q-041")
    ),
    "leader.project.assign": ActionRule(
        _DIR_AD, blocked_while_impersonating=True, prd=("§16", "Q-031", "Q-054")
    ),
    "leader.project.revoke": ActionRule(
        _DIR_AD, blocked_while_impersonating=True, prd=("§16", "Q-031", "Q-054")
    ),
    "leader.task.assign": ActionRule(
        _DIR_AD, blocked_while_impersonating=True, prd=("§17", "Q-031", "Q-054")
    ),
    "leader.task.revoke": ActionRule(
        _DIR_AD, blocked_while_impersonating=True, prd=("§17", "Q-031", "Q-054")
    ),
    "audit.view": ActionRule(_ADM_DIR, prd=("§58", "§67", "Q-021")),
    "audit.export": ActionRule(
        _ADM_DIR, step_up=True, blocked_while_impersonating=True, prd=("§58", "Q-010")
    ),
    "audit.view_deleted_comment": ActionRule(
        _ADM_DIR, blocked_while_impersonating=True, prd=("§57",)
    ),
    "impersonation.start": ActionRule(
        _ADM, step_up=True, blocked_while_impersonating=True, prd=("§59", "Q-034")
    ),
    # Special-cased in authorize(): allowed only for the actor currently impersonating,
    # regardless of role (foundation.md §4: "the impersonating Admin").
    "impersonation.stop": ActionRule(frozenset(), scope=Scope.IMPERSONATING_ADMIN, prd=("§59",)),
    "integrations.view_status": ActionRule(_ADM, prd=("§4.11",)),
    "rules.view": ActionRule(_ADM_DIR, prd=("§4.11",)),
    "outbox.retry": ActionRule(_ADM, blocked_while_impersonating=True, prd=("§70.3",)),
    # --- S2.0 (intake.md §5, §10 "S2.0 contents"): step-2 (Intake) actions ------------------
    # Requester (public) actions: `RequesterContext`, `Scope.OWN_REQUEST`. `request.submit`
    # itself has no request yet to scope to (the draft becomes the request inside the
    # service), so it stays `Scope.ANY` — the service layer is what actually checks the draft
    # carries a consumed verification challenge (intake.md §4 "REQUESTER after a verified code
    # or link").
    "request.submit": ActionRule(_REQUESTER, prd=("§6", "§7.1", "Q-100")),
    "requester.request.view": ActionRule(
        _REQUESTER, scope=Scope.OWN_REQUEST, prd=("§7.2", "§67", "Q-101")
    ),
    "requester.media.upload": ActionRule(
        _REQUESTER, scope=Scope.OWN_REQUEST, prd=("§7.1", "§45", "Q-118")
    ),
    "requester.media.remove": ActionRule(_REQUESTER, scope=Scope.OWN_REQUEST, prd=("§45", "Q-118")),
    "requester_link.regenerate": ActionRule(
        _REQUESTER, scope=Scope.OWN_REQUEST, prd=("§7.3", "§58", "Q-116", "Q-117")
    ),
    # Leadership actions: Director, Assistant Director, Pastor, Board representative see every
    # request (intake.md §5, Q-106/Q-125); the Administrator is added to the view-only rows
    # only (Q-124 decided: masked contact details, no reveal).
    "request.list": ActionRule(_ADM_DIR_AD_PAS_BRD, prd=("§8", "§64", "Q-106")),
    "request.view": ActionRule(_ADM_DIR_AD_PAS_BRD, prd=("§8", "§67", "Q-124")),
    # Kept separate from `request.view` so a later Project/Task Leader `request.view` grant
    # (steps 4-5, via `LEADS_PROJECT`/`LEADS_TASK`) never implicitly includes the duplicate
    # panel (intake.md §5 "kept separate so later PL/TL request.view never includes it"). Not
    # granted to the Administrator: Q-124 is "requests", not the duplicate-history detail.
    "request.history.view": ActionRule(_DIR_AD_PAS_BRD, prd=("§5", "§9")),
    # Q-081/Q-122/Q-125 (closed for step 2): Director, Assistant Director, Pastor and Board
    # representative may reveal on any request; every reveal is logged except a *non*-
    # impersonating Director's (Q-024) — that exemption is applied in
    # `ham.requests.services.reveal_requester_pii`, not here (the matrix only decides who may
    # ask; §68's "was it logged" nuance is finer-grained than a matrix flag). Denied attempts
    # are always audited (`_AUDITED_ON_DENIAL` below) regardless of who denies.
    "requester_pii.reveal": ActionRule(
        _DIR_AD_PAS_BRD, prd=("§67", "§68", "Q-009", "Q-024", "Q-081", "Q-122", "Q-125")
    ),
    "request_media.view": ActionRule(_ADM_DIR_AD_PAS_BRD, prd=("§69", "Q-124")),
    "request_media.reopen": ActionRule(_DIR_AD_PAS_BRD, prd=("§46",)),
    "request.cancel": ActionRule(
        _DIR_AD, blocked_while_impersonating=True, prd=("§52", "Q-107", "Q-111")
    ),
    # PRD-guardian N2: `request.create_assisted` (staff-entered request over the phone) was
    # never wired to a real service in step 2 — it only granted Pastors an unused, unaudited
    # staff-entry power. Removed rather than left dormant; Q-025's actual no-email path is
    # `request.contact_verify_phone` below (the requester still submits the form themselves;
    # a Director/AD only confirms the phone call).
    # intake.md owner-decisions box: no-email requests wait in a Director/AD-only "Needs a
    # phone check" list until verified by phone.
    "request.needs_phone_check.list": ActionRule(_DIR_AD, prd=("Q-025",)),
    # The consequential "verified by phone call" action itself (intake.md owner-decisions box:
    # "audited, blocked while impersonating").
    "request.contact_verify_phone": ActionRule(
        _DIR_AD, blocked_while_impersonating=True, prd=("Q-025",)
    ),
    "intake_source.manage": ActionRule(_DIR_AD, prd=("§6", "Q-106")),
    "notification.acknowledge": ActionRule(
        ANY_STANDING_ROLE, scope=Scope.SELF, blocked_while_impersonating=True, prd=("§10", "§35")
    ),
    # --- S3.0 (approvals.md §3, amended by its owner-decisions box): step-3 (Approvals)
    # actions. Q-172 (decided, amended): every decision, undo and question action, and every
    # phone record, is blocked while impersonating; `request.category.change` is the one
    # exception (Q-109 -- "an operational correction, not a decision", §59). ---
    "request.approve": ActionRule(
        _PAS_BRD,
        blocked_while_impersonating=True,
        prd=("§4.2", "§4.3", "§8", "§10", "§67", "Q-048", "Q-153"),
    ),
    "request.reject": ActionRule(
        _PAS_BRD, blocked_while_impersonating=True, prd=("§8.3", "Q-048", "Q-154")
    ),
    # Undo (Q-156/Q-176): only the person who recorded the decision may undo -- a
    # finer-grained check the matrix can't express, enforced by the service
    # (`ham.requests.services.undo_decision`) and tested there, same shape as reconsideration
    # routing below. Same actor set as the actions it undoes (PAS approve/reject/certify, BRD
    # approve/reject).
    "request.decision.undo": ActionRule(
        _PAS_BRD, blocked_while_impersonating=True, prd=("§8", "§3.3", "§58", "Q-156", "Q-176")
    ),
    "request.urgency.review": ActionRule(
        _PAS, blocked_while_impersonating=True, prd=("§10", "§67", "Q-048", "Q-160")
    ),
    "request.reconsideration.decide": ActionRule(
        _PAS_BRD, blocked_while_impersonating=True, prd=("§8.4", "Q-048", "Q-157")
    ),
    "request.reconsideration.record_phone": ActionRule(
        _DIR_AD, blocked_while_impersonating=True, prd=("§8.4", "Q-025", "Q-159")
    ),
    "request.decision.record_phoned": ActionRule(
        _DIR_AD, blocked_while_impersonating=True, prd=("§8.3", "Q-025", "Q-159")
    ),
    "request.question.ask": ActionRule(
        _DIR_AD_PAS_BRD, blocked_while_impersonating=True, prd=("§7.2", "Q-162")
    ),
    "request.question.record_answer": ActionRule(
        _DIR_AD_PAS_BRD, blocked_while_impersonating=True, prd=("§7.2", "Q-162")
    ),
    "request.question.withdraw": ActionRule(
        _DIR_AD_PAS_BRD, blocked_while_impersonating=True, prd=("§7.2", "Q-162")
    ),
    # Owner box reconciliation ("Change category: Director and AD only. Not blocked while
    # impersonating."): Director/AD only, NOT Pastor/Board rep -- narrower than
    # approvals.md §2.6/§3's own table, which the box explicitly overrides.
    "request.category.change": ActionRule(_DIR_AD, prd=("Q-109",)),
    "requester.question.answer": ActionRule(
        _REQUESTER, scope=Scope.OWN_REQUEST, prd=("§7.2", "Q-162")
    ),
    "requester.reconsideration.request": ActionRule(
        _REQUESTER, scope=Scope.OWN_REQUEST, prd=("§8.3", "§8.4", "Q-155", "Q-158")
    ),
    "system.request.finalize_rejection": ActionRule(_SYSTEM, prd=("§8.4", "Q-155")),
    # System (background job) actions: `SystemContext`, no human behind them.
    "system.request.complete_intake_checks": ActionRule(_SYSTEM, prd=("§9",)),
    "system.media.process": ActionRule(_SYSTEM, prd=("§45",)),
    "system.media.purge": ActionRule(_SYSTEM, prd=("§47",)),
    "system.intake.purge": ActionRule(_SYSTEM, prd=("§76",)),
}


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    reason: str
    step_up_required: bool = False
    blocked_by_impersonation: bool = False


def _self_scope_ok(ctx, resource) -> bool:
    if resource is None:
        return True
    target = getattr(resource, "user_id", resource)
    return target == ctx.user_id


def _scoped_role_ok(ctx, resource, *, role: str, scope_attr: str) -> bool:
    if resource is None:
        return False
    scope_id = getattr(resource, scope_attr, resource)
    return any(sr.role == role and sr.scope_id == scope_id for sr in ctx.scoped_roles)


def _check_scope(scope: Scope, ctx, resource) -> bool:
    if scope is Scope.ANY:
        return True
    if scope is Scope.SELF:
        return _self_scope_ok(ctx, resource)
    if scope is Scope.LEADS_PROJECT:
        return _scoped_role_ok(ctx, resource, role=roles.PROJECT_LEADER, scope_attr="project_id")
    if scope is Scope.LEADS_TASK:
        return _scoped_role_ok(ctx, resource, role=roles.TASK_LEADER, scope_attr="task_id")
    if scope in (Scope.ASSIGNED_PROJECT, Scope.INVITED_PROJECT):
        # foundation.md §4: "come from later modules through the scope-provider registry".
        from .scopes import check_scope_provider

        return check_scope_provider(scope, ctx, resource)
    if scope is Scope.IMPERSONATING_ADMIN:
        return ctx.is_impersonating
    if scope is Scope.OWN_REQUEST:
        if resource is None:
            return False
        target = getattr(resource, "request_id", resource)
        return target == getattr(ctx, "request_id", None)
    return False  # pragma: no cover - exhaustive over Scope


def authorize(ctx, action: str, resource: object | None = None) -> Decision:
    """The one authorization entry point (foundation.md §4).

    Deny if the action is unknown, the actor is unauthenticated/inactive, or no held role
    grants it. Roles are a union (§4.11): any one held role that grants the action is enough.
    """
    rule = MATRIX.get(action)
    if rule is None:
        return Decision(False, "unknown action")
    if not ctx.is_authenticated or not ctx.is_active:
        return Decision(False, "not signed in")

    if action == "impersonation.start" and ctx.is_impersonating:
        # Q-034: no nesting. Modeled as an impersonation block, not a plain denial, so the
        # command pipeline audits it as `impersonation.action_blocked` like other blocked
        # actions, not as a silent `authz.denied`.
        return Decision(True, "no nesting while impersonating", blocked_by_impersonation=True)

    if rule.scope is Scope.IMPERSONATING_ADMIN:
        allowed = _check_scope(rule.scope, ctx, resource)
        return Decision(allowed, "" if allowed else "not currently impersonating")

    if not (ctx.effective_roles & rule.allowed_roles):
        return Decision(False, "no held role grants this action")

    if not _check_scope(rule.scope, ctx, resource):
        return Decision(False, "out of scope")

    blocked = ctx.is_impersonating and rule.blocked_while_impersonating
    return Decision(True, "", step_up_required=rule.step_up, blocked_by_impersonation=blocked)
