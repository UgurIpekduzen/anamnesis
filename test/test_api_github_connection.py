import pytest
from starlette.testclient import TestClient

import api.main as api_main

OWNER = "test@example.com"


@pytest.fixture
def api(monkeypatch, signed_in_owner):
    saved = []
    deleted = []

    def fake_save(owner_uid, token):
        saved.append((owner_uid, token))

    def fake_delete(owner_uid):
        deleted.append(owner_uid)

    monkeypatch.setattr(api_main, "validate_github_token", lambda token: None)
    monkeypatch.setattr(api_main, "save_github_token", fake_save)
    monkeypatch.setattr(api_main, "delete_github_connection", fake_delete)
    yield TestClient(api_main.app), saved, deleted


def test_get_reports_connected_when_a_token_is_on_file(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(api_main, "has_github_connection", lambda owner_uid: True)

    assert client.get("/github/connection").json() == {"connected": True}


def test_get_reports_disconnected_when_no_token_is_on_file(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(api_main, "has_github_connection", lambda owner_uid: False)

    assert client.get("/github/connection").json() == {"connected": False}


def test_put_validates_then_saves_for_the_authenticated_user(api):
    client, saved, _ = api

    response = client.put("/github/connection", json={"token": "github_pat_example"})

    assert response.status_code == 200
    assert response.json() == {"connected": True}
    assert saved == [(OWNER, "github_pat_example")]


def test_put_rejects_a_token_validate_raises_on_and_saves_nothing(api, monkeypatch):
    client, saved, _ = api
    monkeypatch.setattr(
        api_main,
        "validate_github_token",
        lambda token: (_ for _ in ()).throw(ValueError("nope")),
    )

    response = client.put("/github/connection", json={"token": "ghp_classic"})

    assert response.status_code == 400
    assert saved == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"token": ""},
        {"token": "x" * 256},
        {"token": "github_pat_example", "owner_uid": "someone-else@example.com"},
    ],
)
def test_put_rejects_invalid_payloads_and_saves_nothing(api, payload):
    client, saved, _ = api
    assert client.put("/github/connection", json=payload).status_code == 422
    assert saved == []


def test_delete_disconnects_the_authenticated_user(api):
    client, _, deleted = api

    response = client.delete("/github/connection")

    assert response.status_code == 200
    assert response.json() == {"connected": False}
    assert deleted == [OWNER]


def test_github_connection_requires_authentication():
    # No dependency override here: the real token check must run.
    client = TestClient(api_main.app)
    assert client.get("/github/connection").status_code == 401
    assert client.put("/github/connection", json={"token": "x"}).status_code == 401
    assert client.delete("/github/connection").status_code == 401
