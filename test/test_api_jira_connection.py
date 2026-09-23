import os

# api.deps reads these at import time.
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("ALLOWED_EMAILS", "test@example.com")

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import api.main as api_main  # noqa: E402
from api.deps import get_current_owner_uid  # noqa: E402

OWNER = "test@example.com"
VALID_BODY = {"email": "user@example.com", "token": "secret-token", "base_url": "https://example.atlassian.net"}


@pytest.fixture
def api(monkeypatch):
    saved = []
    deleted = []

    def fake_save(owner_uid, email, token, base_url):
        saved.append((owner_uid, email, token, base_url))

    def fake_delete(owner_uid):
        deleted.append(owner_uid)

    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER
    monkeypatch.setattr(api_main, "validate_jira_credentials", lambda email, token, base_url: None)
    monkeypatch.setattr(api_main, "save_jira_credentials", fake_save)
    monkeypatch.setattr(api_main, "delete_jira_connection", fake_delete)
    yield TestClient(api_main.app), saved, deleted
    api_main.app.dependency_overrides.clear()


def test_get_reports_connected_when_credentials_are_on_file(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(api_main, "has_jira_connection", lambda owner_uid: True)

    assert client.get("/jira/connection").json() == {"connected": True}


def test_get_reports_disconnected_when_no_credentials_are_on_file(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(api_main, "has_jira_connection", lambda owner_uid: False)

    assert client.get("/jira/connection").json() == {"connected": False}


def test_put_validates_then_saves_for_the_authenticated_user(api):
    client, saved, _ = api

    response = client.put("/jira/connection", json=VALID_BODY)

    assert response.status_code == 200
    assert response.json() == {"connected": True}
    assert saved == [(OWNER, "user@example.com", "secret-token", "https://example.atlassian.net")]


def test_put_rejects_credentials_validate_raises_on_and_saves_nothing(api, monkeypatch):
    client, saved, _ = api
    monkeypatch.setattr(
        api_main,
        "validate_jira_credentials",
        lambda email, token, base_url: (_ for _ in ()).throw(ValueError("nope")),
    )

    response = client.put("/jira/connection", json=VALID_BODY)

    assert response.status_code == 400
    assert saved == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**VALID_BODY, "email": ""},
        {**VALID_BODY, "token": ""},
        {**VALID_BODY, "base_url": ""},
        {**VALID_BODY, "owner_uid": "someone-else@example.com"},
    ],
)
def test_put_rejects_invalid_payloads_and_saves_nothing(api, payload):
    client, saved, _ = api
    assert client.put("/jira/connection", json=payload).status_code == 422
    assert saved == []


def test_delete_disconnects_the_authenticated_user(api):
    client, _, deleted = api

    response = client.delete("/jira/connection")

    assert response.status_code == 200
    assert response.json() == {"connected": False}
    assert deleted == [OWNER]


def test_jira_connection_requires_authentication():
    # No dependency override here: the real token check must run.
    client = TestClient(api_main.app)
    assert client.get("/jira/connection").status_code == 401
    assert client.put("/jira/connection", json=VALID_BODY).status_code == 401
    assert client.delete("/jira/connection").status_code == 401
