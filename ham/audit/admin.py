"""AuditEvent is NEVER registered in any Django admin (foundation.md §3, PRD §58).

Django admin bypasses HAM's authorization/audit layer (see `config/urls.py`), and an
append-only, IDs-only record must not gain an edit/delete UI through the back door. If you
are tempted to add `admin.site.register(AuditEvent, ...)` here — don't; use the audit viewer
service (`ham.audit.queries`) instead.
"""
