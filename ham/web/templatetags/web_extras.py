"""Template helpers for the app shell. Never hard-code a church name, logo path or color here
(CLAUDE.md "Design"; design-system/README.md) — everything comes from `church_profile()` or
settings, resolved once here so templates stay declarative.
"""

from __future__ import annotations

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse

from ham.platform.tokens import token_hex

register = template.Library()


@register.simple_tag
def maybe_url(name: str, *args: object) -> str:
    """Like `{% url %}`, but returns `""` instead of raising when `name` doesn't resolve yet
    (S5 build note: "a link to /me/security ... guarded so the page doesn't crash if the URL
    doesn't exist yet in your worktree" — used for S3b routes not merged here, e.g.
    `web:me_security`, `web:user_mfa_reset`, `web:impersonation_start`)."""
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return ""


@register.simple_tag
def theme_color_hex() -> str:
    """The literal hex for `<meta name="theme-color">` (S5 build note item 4), resolved from
    `tokens.css` instead of hard-coded (CLAUDE.md "Design")."""
    return token_hex("ham-color-neutral-950")


@register.filter
def get_item(mapping: dict, key: str) -> str:
    """`{{ some_dict|get_item:key }}` — Django templates have no `dict[key]` syntax."""
    return mapping.get(key, key)


@register.filter
def brand_static(filename: str) -> str:
    """Build the static URL for a file inside the active brand's folder
    (`design-system/brands/<HAM_BRAND>/<filename>`, e.g. `{{ church.logo_mark|brand_static }}`).
    `design-system/` is on `STATICFILES_DIRS` (config/settings/base.py), so this is a normal
    static URL, not a special view.
    """
    return static(f"brands/{settings.HAM_BRAND}/{filename}")
