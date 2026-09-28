"""FIX-D: guards against a subtle Django template bug found while regenerating the step-2
screenshots -- `{# ... #}` is Django's *single-line* comment tag (the tokenizer regex is
`{#.*?#}` without `re.DOTALL`, so `.` never matches a newline). A `{# #}` comment that spans
more than one line is never recognized as a comment at all: Django can't find a matching `#}`
before hitting the newline, so the literal `{#...#}` text (including the developer's own
internal notes) is emitted straight into the rendered page instead of being stripped.

Several existing templates had exactly this bug (visible, for example, as a stray "M6: the
request title is always the h1 ..." paragraph right above R10's real heading). The fix is
always the same: use the block form, `{% comment %}...{% endcomment %}`, for anything that
doesn't fit on one line. This test scans every shipped template for the single-line form
spanning multiple lines, so a future multi-line `{# #}` regresses in CI, not on a real screen.
"""

from __future__ import annotations

import re
from pathlib import Path

_TEMPLATES_ROOT = Path(__file__).resolve().parents[2] / "ham"
_MULTILINE_HASH_COMMENT = re.compile(r"\{#(?:(?!#\}).)*\n(?:(?!#\}).)*#\}", re.DOTALL)


def test_no_multiline_hash_comments_in_any_shipped_template():
    offenders = []
    for path in _TEMPLATES_ROOT.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for match in _MULTILINE_HASH_COMMENT.finditer(text):
            offenders.append(f"{path}: {match.group(0)[:60]!r}...")
    assert not offenders, (
        "Found `{# ... #}` comment(s) spanning more than one line -- Django's single-line "
        "comment tag can't close across a newline, so this text renders verbatim on the page. "
        "Use `{% comment %}...{% endcomment %}` instead:\n" + "\n".join(offenders)
    )
