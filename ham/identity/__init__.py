"""User, SharedIdentityProfile, RoleAssignment, ImpersonationSession (foundation.md §3).

The only module that reads auth tables directly (foundation.md §1); every other module
receives an `ham.authz.context.ActorContext` instead.
"""
