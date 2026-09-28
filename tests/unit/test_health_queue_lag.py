"""GET /healthz degrades when the job queue lag passes the rules threshold (Q-056, proposed
default in use: 5 minutes)."""

from __future__ import annotations

import pytest

from ham.rules import RULES

LIMIT = RULES.operations.HEALTH_MAX_QUEUE_LAG.total_seconds()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("lag", "status", "http"),
    [
        (None, "ok", 200),  # nothing due
        (LIMIT - 1, "ok", 200),
        (LIMIT, "ok", 200),  # exactly at the threshold is still healthy
        (LIMIT + 1, "degraded", 503),
    ],
    ids=["none", "under", "exactly", "over"],
)
def test_healthz_queue_lag_threshold(client, monkeypatch, lag, status, http):
    monkeypatch.setattr("ham.web.views.queue_lag_seconds", lambda: lag)
    response = client.get("/healthz")
    assert response.status_code == http
    assert response.json()["status"] == status
