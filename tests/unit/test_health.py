from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_healthz_reports_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"


@pytest.mark.django_db
def test_healthz_is_public_and_has_no_pii(client):
    response = client.get("/healthz")
    text = response.content.decode()
    assert "@" not in text
