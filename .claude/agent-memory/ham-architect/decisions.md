# ham-architect decisions

- Step 3 plan: `docs/architecture/approvals.md`. Approvals, reconsideration, urgency and questions live in `ham/requests` (`Approval`, `Reconsideration`, `RequestQuestion`; append-only with Python guards; one reconsideration by UNIQUE(request_id)). No Project table in step 3.
- Step 4 adds `ham.projects` (layer between `requester_portal` and `media`): `Project.id` = request id, created by a data migration plus an idempotent subscriber on `RequestApproved`.
- The secure page composes its cards in `ham/requester_portal/page.py` by calling downward services directly (no provider registry needed; the portal sits above every module it reads).
