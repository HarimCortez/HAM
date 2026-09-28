"""S2.2 note: once a domain module (e.g. `ham.requests`) registers a *real* attention
provider from its own `AppConfig.ready()`, that registration is permanent for the whole test
process (Django apps load once per session) -- `ham.notifications.attention`'s own registry
tests were written assuming a clean, empty `_providers` list, which stopped being true the
moment a real provider landed. This fixture isolates each test in this package from whatever
providers other apps have already registered, without touching their registration.
"""

from __future__ import annotations

import pytest

from ham.notifications import attention


@pytest.fixture(autouse=True)
def _isolated_attention_providers():
    original = list(attention._providers)
    attention._providers.clear()
    yield
    attention._providers.clear()
    attention._providers.extend(original)
