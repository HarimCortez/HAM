"""Makes `{{ church.* }}` available in every template (design-system/README.md "How to use").
Never expose anything here beyond the church profile view's public fields."""

from __future__ import annotations

from ham.platform.church import church_profile


def church(request):
    return {"church": church_profile()}
