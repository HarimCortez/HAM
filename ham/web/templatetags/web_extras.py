"""Template helpers for the app shell. Never hard-code a church name, logo path or color here
(CLAUDE.md "Design"; design-system/README.md) — everything comes from `church_profile()` or
settings, resolved once here so templates stay declarative.
"""

from __future__ import annotations

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse

from ham.platform.church import format_church_time
from ham.platform.tokens import token_hex

register = template.Library()


@register.filter
def action_label(action: str) -> str:
    """`{{ event.action|action_label }}` — plain-language audit action name (usability M5)."""
    from ham.audit.labels import action_label as _action_label

    return _action_label(action)


@register.filter
def target_display(value, names) -> str:
    """`{{ event.target_type }} {{ event.target_id|target_display:names }}` — resolves a
    user-type audit target to its display name instead of a raw UUID (usability M5: "show
    subjects ID-first ... rather than a raw UUID"). `names` is the `names` dict already built
    by `display_names_for`, keyed by `uuid.UUID`; anything that isn't a resolvable user UUID
    (a project ID, say) is shown as-is."""
    import uuid as _uuid

    try:
        key = _uuid.UUID(str(value))
    except (ValueError, TypeError):
        return value
    return names.get(key, value)


@register.filter
def church_time(moment) -> str:
    """`{{ event.occurred_at|church_time }}` — local time with the zone abbreviation
    (PRD §70.5), instead of a bare UTC timestamp (usability M6)."""
    if moment is None:
        return ""
    return format_church_time(moment)


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
