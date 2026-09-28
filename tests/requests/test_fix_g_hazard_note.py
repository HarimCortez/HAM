"""FIX-G UX minor: `hazard_labels`'s free-text note is always about the "Something else"
hazard (the only one the form collects a note for) -- attach it to that item specifically,
wherever it falls in the ticked list, instead of whichever hazard happened to be ticked first.
"""

from __future__ import annotations

from ham.requests.presentation import hazard_labels


class TestNoteAttachedToSomethingElse:
    def test_note_attaches_to_something_else_even_when_ticked_last(self):
        # Before the fix: the note landed on "mold" (the first-ticked code), not
        # "something_else" (the code the note is actually about).
        items = hazard_labels("mold, something_else (a mean dog next door)")
        by_code = {i["code"]: i["note"] for i in items}
        assert by_code["mold"] == ""
        assert by_code["something_else"] == "a mean dog next door"

    def test_note_attaches_to_something_else_when_ticked_first(self):
        items = hazard_labels("something_else, pests (a mean dog next door)")
        by_code = {i["code"]: i["note"] for i in items}
        assert by_code["something_else"] == "a mean dog next door"
        assert by_code["pests"] == ""

    def test_note_becomes_a_separate_line_when_something_else_is_not_ticked(self):
        # Defensive: the form itself requires "something_else" for a note to exist at all,
        # but if it somehow doesn't, the note is its own item (no label/icon) rather than
        # silently landing on an unrelated hazard.
        items = hazard_labels("mold, pests (seen in the kitchen)")
        assert [i["code"] for i in items] == ["mold", "pests", ""]
        assert items[0]["note"] == ""
        assert items[1]["note"] == ""
        assert items[2] == {"code": "", "label": "", "note": "seen in the kitchen"}
