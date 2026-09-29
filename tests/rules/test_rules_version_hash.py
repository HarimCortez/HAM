"""A rule value cannot change without a version bump, a changelog entry and a new pin.

How to change a rule (see ham/rules/v1.py):
  1. edit the value, 2. bump RULES_VERSION, 3. add a docs/rules-changelog.md entry,
  4. add ``"<new version>": "<new hash>"`` to PINNED_HASHES below (keep old entries).
"""

import dataclasses
import re
import unittest
from datetime import timedelta
from pathlib import Path

from ham.rules import RULES, RULES_HASH, RULES_VERSION, CalendarYears, Pending, content_hash
from ham.rules.fingerprint import canonical_document, encode_value
from ham.rules.v1 import iter_rules

REPO_ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = REPO_ROOT / "docs" / "rules-changelog.md"

# version -> content hash. Append only; never edit an existing line.
PINNED_HASHES = {
    "2026.09.27-1": "sha256:e13eb47656eceb028c495b3f5e918fb4274d9fdc7b752fce3ba1b434ee77188a",
    "2026.09.28-1": "sha256:84f96591b6cae641b20e83cc70ea0eff466990850f31c207d6f0249ccd3983d7",
    "2026.09.28-2": "sha256:870301de1d7d500763632d339a9bc9cf0eeabf7c8b117d32466bb2e17f3de9da",
    "2026.09.28-3": "sha256:2635dba3e86d2066f3a3069d9191682b4c293e3702b3dccefa6b71dc67ea011e",
    "2026.09.28-4": "sha256:77c70f3c4751ab55b2fb106b369f6f34bb6e74bc5ed41374de8cc06aad4d4068",
    "2026.09.28-5": "sha256:66abce06bc3b003b2ec564dc7a763c7a3d062afb4a7a0a017349b60c31f20ce3",
    "2026.09.28-6": "sha256:da176a0734d061ccc65edf97000c4cf458fe4c76b4d4c0f8de241d6c22d455e5",
    "2026.09.28-7": "sha256:83e16dbc64c47bd4991c89843fe32949154818f9f6d91a9aac6807319bd3f756",
    "2026.09.28-8": "sha256:cc7ba9d2eeb15fbf5736b16f9456de3f8e4408f8e8cd8aa8a572674f221b14ed",
    "2026.09.28-9": "sha256:4d782eeafd8e307d3a1e4e61c92226c2c9adbd7c6849aaa496b7001da28eb880",
}


def _mutated(value: object) -> object:
    """A different value of the same shape, to prove the hash covers it."""
    if isinstance(value, Pending):
        return 1
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, timedelta):
        return value + timedelta(seconds=1)
    if isinstance(value, CalendarYears):
        return CalendarYears(value.years + 1)
    if isinstance(value, tuple):
        return value + (value[-1],)
    raise TypeError(type(value))


class VersionHashTest(unittest.TestCase):
    def test_version_format(self) -> None:
        self.assertRegex(RULES_VERSION, r"^\d{4}\.\d{2}\.\d{2}-\d+$")

    def test_current_version_is_pinned(self) -> None:
        self.assertIn(
            RULES_VERSION,
            PINNED_HASHES,
            "RULES_VERSION was bumped: pin its hash in PINNED_HASHES and add a changelog entry",
        )

    def test_values_match_the_pinned_hash_for_this_version(self) -> None:
        self.assertEqual(
            content_hash(RULES),
            PINNED_HASHES[RULES_VERSION],
            "A rule value changed without a version bump. Bump RULES_VERSION in "
            "ham/rules/v1.py, add a docs/rules-changelog.md entry, and pin the new hash.",
        )
        self.assertEqual(RULES_HASH, content_hash(RULES))

    def test_every_version_has_a_distinct_hash(self) -> None:
        hashes = list(PINNED_HASHES.values())
        self.assertEqual(len(hashes), len(set(hashes)), "a version bump must change values")

    def test_hash_is_deterministic(self) -> None:
        self.assertEqual(content_hash(RULES), content_hash(type(RULES)()))

    def test_changing_any_single_value_changes_the_hash(self) -> None:
        base = content_hash(RULES)
        for gf, rf, value in iter_rules(RULES):
            with self.subTest(rule=f"{gf.name}.{rf.name}"):
                group = getattr(RULES, gf.name)
                changed = dataclasses.replace(
                    RULES, **{gf.name: dataclasses.replace(group, **{rf.name: _mutated(value)})}
                )
                self.assertNotEqual(content_hash(changed), base)

    def test_bool_int_and_types_are_distinguished(self) -> None:
        self.assertNotEqual(encode_value(True), encode_value(1))
        self.assertNotEqual(encode_value(1), encode_value(CalendarYears(1)))
        self.assertNotEqual(encode_value(timedelta(days=1)), encode_value(1))
        self.assertNotEqual(encode_value(Pending("Q-001", "")), encode_value(Pending("Q-027", "")))

    def test_canonical_document_covers_every_rule(self) -> None:
        doc = canonical_document(RULES)
        count = sum(len(v) for v in doc.values())
        self.assertEqual(count, len(list(iter_rules(RULES))))

    def test_changelog_documents_current_version_and_hash(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        heading = re.search(rf"^## {re.escape(RULES_VERSION)}\b.*$", text, re.MULTILINE)
        self.assertIsNotNone(heading, f"docs/rules-changelog.md needs '## {RULES_VERSION}'")
        self.assertIn(PINNED_HASHES[RULES_VERSION], text)

    def test_changelog_lists_every_pinned_version(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        for version in PINNED_HASHES:
            with self.subTest(version=version):
                self.assertRegex(text, rf"(?m)^## {re.escape(version)}\b")


if __name__ == "__main__":
    unittest.main()
