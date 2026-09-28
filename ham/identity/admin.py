"""Identity models are not registered in Django admin.

Django's admin bypasses `ham.authz` (no deny-by-default matrix, no step-up, no audit event)
and is mounted only when `DEBUG` (config/urls.py) — a break-glass tool for the solo owner,
never a management surface for real user/role data. Manage users and roles through
`ham.identity.services` (which the eventual `ham.web` admin screens call), not here.
"""
