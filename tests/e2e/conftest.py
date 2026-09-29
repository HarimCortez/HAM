"""Shared fixtures for every test under `tests/e2e/` (Playwright + `live_server`).

The "sweep leaked Procrastinate `todo` jobs after a `django_db(transaction=True)` test" fixture
that used to live only here has been generalized to every test in the suite --
`tests/conftest.py::_sweep_leaked_procrastinate_todo_jobs` (test-engineer pass, step 3: the
same leak was found crossing `tests/web/` files too, not just this directory). Nothing
`tests/e2e/`-specific remains to add here; kept as an explicit, documented empty module rather
than deleted outright, since other docs/agent memory may still point at "the shared
`tests/e2e/conftest.py` fixture" by name.
"""

from __future__ import annotations
