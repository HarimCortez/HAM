from __future__ import annotations

from ham.audit.export import build_csv
from ham.audit.services import record


def test_csv_has_utf8_bom_and_header(db):
    event = record(
        ctx=None, actor_type="system", action="user.created", target_type="user", target_id="u1"
    )
    data = build_csv([event])
    assert data.startswith("﻿".encode())
    text = data.decode("utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0].split(",")[0] == "event_id"
    assert str(event.id) in lines[1]


def test_csv_never_contains_an_at_sign(db):
    # Defense-in-depth: even if a caller passed an email into `reason`, we don't expect it;
    # this pins that our own columns never carry PII by construction (Q-050).
    event = record(
        ctx=None,
        actor_type="system",
        action="user.created",
        target_type="user",
        target_id="u1",
        reason="no email here",
    )
    data = build_csv([event])
    assert "@" not in data.decode("utf-8-sig")
