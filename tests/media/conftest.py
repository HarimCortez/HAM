from __future__ import annotations

import pytest

from ham.requests.models import AssistanceRequest
from ham.requests.states import RequestStatus


@pytest.fixture
def local_storage(tmp_path, settings):
    settings.HAM_LOCAL_STORAGE_ROOT = str(tmp_path)
    settings.HAM_OBJECT_STORE_BACKEND = "ham.integrations.storage.local.LocalObjectStore"
    return tmp_path


@pytest.fixture
def make_request(db, local_storage):
    def _make(*, status: str = RequestStatus.SUBMITTED.value, closed_at=None) -> AssistanceRequest:
        return AssistanceRequest.objects.create(status=status, closed_at=closed_at)

    return _make


@pytest.fixture
def open_request(make_request) -> AssistanceRequest:
    return make_request()
