import os

# api.deps and api.internal_auth both read env vars at import time — kept
# in sync with test_internal_auth.py's values so whichever module gets
# imported first during collection doesn't leave the other with an unset
# (and therefore fail-closed-503) config.
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("ALLOWED_EMAILS", "test@example.com")
os.environ.setdefault("GITHUB_POLLER_SERVICE_ACCOUNT_EMAIL", "poller@test-project.iam.gserviceaccount.com")
os.environ.setdefault("GITHUB_POLLER_AUDIENCE", "https://anamnesis-app.example/internal/poll-github")

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import api.main as api_main  # noqa: E402
from api.internal_auth import verify_scheduler_token  # noqa: E402


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(api_main, "poll_all_tenants", lambda: {"polled": 2, "created": 5, "errors": []})
    yield TestClient(api_main.app)
    api_main.app.dependency_overrides.clear()


def test_a_valid_scheduler_identity_can_trigger_a_poll(api):
    api_main.app.dependency_overrides[verify_scheduler_token] = lambda: None

    response = api.post("/internal/poll-github")

    assert response.status_code == 200
    assert response.json() == {"polled": 2, "created": 5, "errors": []}


def test_a_request_without_scheduler_auth_is_refused(api):
    # No override — falls through to the real dependency, which requires a
    # bearer token that was never sent.
    assert api.post("/internal/poll-github").status_code == 401
