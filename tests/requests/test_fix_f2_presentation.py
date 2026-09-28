"""FIX-F2 item 5 (UX M1 leftovers): `hazard_labels` renders a bare "none_known" as the
neutral empty state (no warning triangle) and is robust to a note containing " (". New file
per wave brief.
"""

from __future__ import annotations

from ham.requests.presentation import hazard_labels


class TestNoneKnownRendersAsNeutral:
    def test_bare_none_known_returns_no_hazard_items(self):
        # Before the fix: this returned one item with label="None that I know of" and no
        # "note" -- rendered by `_request_detail.html` with a warning-triangle icon, even
        # though "none known" is the *absence* of a hazard.
        assert hazard_labels("none_known") == []

    def test_none_known_with_a_stray_note_keeps_the_note_as_plain_text(self):
        # A note somehow present alongside "none known" (e.g. leftover draft data) is not
        # itself a hazard warning either -- shown as plain text (`label=""`), never a
        # triangle-icon item.
        items = hazard_labels("none_known (told us anyway)")
        assert items == [{"code": "", "label": "", "note": "told us anyway"}]


class TestNoteParsingRobustToParens:
    def test_note_containing_open_paren_is_not_truncated(self):
        # Before the fix: `rpartition(" (")` split on the *last* " (" in the string, so a note
        # like "help (please)" chopped the codes/note boundary in the wrong place.
        items = hazard_labels("dogs_or_other_animals (friendly but loud (a bit))")
        assert items == [
            {
                "code": "dogs_or_other_animals",
                "label": "Dogs or other animals",
                "note": "friendly but loud (a bit)",
            }
        ]

    def test_note_with_a_comma_still_works(self):
        items = hazard_labels("mold (in the bathroom, near the tub)")
        assert items == [{"code": "mold", "label": "Mold", "note": "in the bathroom, near the tub"}]

    def test_multiple_codes_with_a_parenthetical_note(self):
        items = hazard_labels("mold, pests (seen in the kitchen (twice))")
        assert [i["code"] for i in items] == ["mold", "pests"]
        assert items[0]["note"] == "seen in the kitchen (twice)"
        assert items[1]["note"] == ""
