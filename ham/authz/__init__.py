"""HAM authorization: deny-by-default action matrix, policy engine, route guard, nav
computation (foundation.md §1, §4, §7).

Only ``ham.identity`` reads auth tables (User, RoleAssignment, ImpersonationSession);
every other module receives an :class:`ham.authz.context.ActorContext` (foundation.md §1's
shared-identity seam). This package must never import ``ham.identity``.
"""
