"""S2.4a: concrete `ham.platform.storage.ObjectStore` implementations.

`ham.integrations.storage.s3.R2ObjectStore` (production, Cloudflare R2 / any S3-compatible
endpoint) and `ham.integrations.storage.local.LocalObjectStore` (dev/test). Domain code
(`ham.media`) never imports this package directly (pyproject.toml import-linter contract
"domain modules never import ham.integrations directly") — it loads whichever one is
configured through `ham.platform.storage.get_object_store()`, by dotted path
(`HAM_OBJECT_STORE_BACKEND`), same as the outbox pattern for every other third-party
integration (intake.md §2's one documented, explicit exception to that rule).
"""

from __future__ import annotations
