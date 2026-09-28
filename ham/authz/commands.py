"""The one write path (foundation.md §1 "One write path (the command pattern)").

``@command("action.code")`` wraps a service function so every consequential action:
1. is authorized (deny-by-default matrix);
2. has step-up freshness enforced if the action requires it (Q-010, Q-031, Q-046);
3. is refused if blocked while impersonating (§59);
4. runs its change, then ``audit.record(...)``, then ``outbox.emit(...)``, all inside one
   ``transaction.atomic()`` — if anything raises, nothing is written (§79 flow for humans).

The wrapped function receives the ``ActorContext`` as its first argument and returns a
``CommandResult`` describing what to audit/emit; ``command()`` returns ``result.value`` to the
caller.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any
from uuid import UUID

from django.db import transaction

from ham.platform.clock import now as clock_now
from ham.rules import RULES

from .context import ActorContext
from .matrix import authorize


class PermissionDenied(Exception):
    """The action's matrix rule refused this actor (foundation.md §4 "deny by default")."""


class ImpersonationBlocked(Exception):
    """Action is flagged ``blocked_while_impersonating`` and the actor is impersonating."""


class StepUpRequired(Exception):
    """Action needs a step-up not fresh in this session (Q-010, Q-031, Q-046)."""

    def __init__(self, action: str, kind: str) -> None:
        super().__init__(f"{action} requires a fresh step-up ({kind})")
        self.action = action
        self.kind = kind


# `ham.authz` sits above `ham.audit` and `ham.outbox` in the dependency order (foundation.md
# §1: "web -> domain modules -> {authz, audit, outbox, rules, platform}"), so this module
# records/emits through them. But `ham.audit`'s own viewer/export services need to *check*
# authorization (`ham.authz`), which would create a cycle if this module imported them at
# module scope. `AuthzConfig.ready()` (apps.py) registers the concrete callables once at
# Django startup instead, so neither package has a static import of the other's internals.
AuditRecorder = Callable[..., Any]
OutboxEmitter = Callable[..., None]

_audit_record: AuditRecorder | None = None
_outbox_emit: OutboxEmitter | None = None


def _register_audit_recorder(fn: AuditRecorder) -> None:
    global _audit_record
    _audit_record = fn


def _register_outbox_emitter(fn: OutboxEmitter) -> None:
    global _outbox_emit
    _outbox_emit = fn


@dataclass(frozen=True, slots=True)
class OutboxSpec:
    event_type: str
    aggregate_type: str
    aggregate_id: UUID | str
    payload: dict[str, Any]
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class CommandResult:
    """What a ``@command``-wrapped function returns: its value plus the one audit event to
    record and (optionally) the one outbox event to emit, all inside the same transaction."""

    value: Any
    audit_action: str
    target_type: str
    target_id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    project_id: UUID | None = None
    reason: str = ""
    context: dict[str, Any] | None = None
    outbox: OutboxSpec | None = None


# Denied attempts at privileged actions are audited (foundation.md §4 "Denied privileged
# actions ... write `authz.denied`. Ordinary denials are not logged, to avoid noise").
_AUDITED_ON_DENIAL: frozenset[str] = frozenset(
    {
        "user.mfa_reset",
        "role.grant_global",
        "role.revoke_global",
        "impersonation.start",
        "audit.export",
        "user.disable",
        "user.enable",
        "user.invite",
        "church_profile.update",
        "outbox.retry",
    }
)

_STEP_UP_KIND_BY_ACTION: dict[str, str] = dict(RULES.auth.STEP_UP_ACTIONS)


def _step_up_kind(action: str) -> str:
    kind = _STEP_UP_KIND_BY_ACTION.get(action)
    if kind is None:  # pragma: no cover - defensive; matrix/rules are kept in sync by a test
        raise AssertionError(f"{action!r} requires step-up but has no rules.STEP_UP_ACTIONS kind")
    return kind


def command(
    action: str, *, resource_from: Callable[..., Any] | None = None
) -> Callable[[Callable], Callable]:
    def decorator(fn: Callable[..., CommandResult]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(ctx: ActorContext, *args: Any, **kwargs: Any) -> Any:
            if _audit_record is None or _outbox_emit is None:  # pragma: no cover - defensive
                raise RuntimeError(
                    "ham.authz.commands used before Django app startup registered the audit "
                    "recorder / outbox emitter (see AuthzConfig.ready())."
                )
            audit_record = _audit_record
            outbox_emit = _outbox_emit

            resource = resource_from(ctx, *args, **kwargs) if resource_from else None
            decision = authorize(ctx, action, resource)

            if not decision.allowed:
                if action in _AUDITED_ON_DENIAL:
                    audit_record(
                        ctx=ctx,
                        action="authz.denied",
                        target_type="action",
                        target_id=action,
                        reason=decision.reason,
                    )
                raise PermissionDenied(f"{action}: {decision.reason}")

            if decision.blocked_by_impersonation:
                audit_record(
                    ctx=ctx,
                    action="impersonation.action_blocked",
                    target_type="action",
                    target_id=action,
                    reason="blocked while impersonating (§59)",
                )
                raise ImpersonationBlocked(action)

            if decision.step_up_required:
                kind = _step_up_kind(action)
                if not ctx.has_fresh_step_up(
                    kind, now=clock_now(), freshness=RULES.auth.STEP_UP_WINDOW
                ):
                    raise StepUpRequired(action, kind)

            try:
                with transaction.atomic():
                    result = fn(ctx, *args, **kwargs)
                    audit_record(
                        ctx=ctx,
                        action=result.audit_action,
                        target_type=result.target_type,
                        target_id=result.target_id,
                        project_id=result.project_id,
                        before=result.before,
                        after=result.after,
                        reason=result.reason,
                        context=result.context,
                    )
                    if result.outbox is not None:
                        outbox_emit(
                            result.outbox.event_type,
                            aggregate_type=result.outbox.aggregate_type,
                            aggregate_id=result.outbox.aggregate_id,
                            payload=result.outbox.payload,
                            schema_version=result.outbox.schema_version,
                        )
            except PermissionDenied as exc:
                # A finer-grained rule inside the service body (e.g. "a Director may not grant
                # Administrator", `ham.identity.services._check_can_grant`) raised this from
                # *inside* the atomic block the matrix-level check above already passed. The
                # `with transaction.atomic()` block above already rolled the change back; audit
                # it here, outside (after) that rollback, same as the matrix-level denial above.
                if action in _AUDITED_ON_DENIAL:
                    audit_record(
                        ctx=ctx,
                        action="authz.denied",
                        target_type="action",
                        target_id=action,
                        reason=str(exc),
                    )
                raise
            return result.value

        return wrapper

    return decorator


__all__ = [
    "CommandResult",
    "ImpersonationBlocked",
    "OutboxSpec",
    "PermissionDenied",
    "StepUpRequired",
    "command",
]
