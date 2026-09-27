import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.internal_auth import verify_scheduler_token
from api.routers import internal


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(internal, "poll_all_tenants", lambda: {"polled": 2, "created": 5, "errors": []})
    yield TestClient(api_main.app)


def test_a_valid_scheduler_identity_can_trigger_a_poll(api):
    api_main.app.dependency_overrides[verify_scheduler_token] = lambda: None

    response = api.post("/internal/poll-github")

    assert response.status_code == 200
    assert response.json() == {"polled": 2, "created": 5, "errors": []}


def test_a_request_without_scheduler_auth_is_refused(api):
    # No override — falls through to the real dependency, which requires a
    # bearer token that was never sent.
    assert api.post("/internal/poll-github").status_code == 401
