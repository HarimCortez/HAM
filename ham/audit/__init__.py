"""HAM's append-only audit trail (foundation.md §3 "AuditEvent", PRD §58, §59, §70.6).

Never registered in any Django admin (see `admin.py`). No service exposes update/delete;
the DB refuses UPDATE always and DELETE unless the retention purge job sets
`ham.audit_purge = 'on'` for its transaction.
"""
