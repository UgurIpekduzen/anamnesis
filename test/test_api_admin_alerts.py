import pytest
from starlette.testclient import TestClient

import api.main as api_main
from api.deps import get_current_owner_uid
from api.routers import admin

OWNER = "test@example.com"
NON_OWNER = "someone-else@example.com"


@pytest.fixture
def api(monkeypatch):
    state = {"muted": False}
    monkeypatch.setattr(admin, "is_github_poll_alert_muted", lambda: state["muted"])

    def fake_set(muted):
        state["muted"] = muted

    monkeypatch.setattr(admin, "set_github_poll_alert_muted", fake_set)
    yield TestClient(api_main.app)


def test_owner_can_read_the_mute_state(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    response = api.get("/admin/alerts")

    assert response.status_code == 200
    assert response.json() == {"github_poll_alert_muted": False}


def test_owner_can_mute_and_unmute(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    muted = api.put("/admin/alerts", json={"github_poll_alert_muted": True})
    assert muted.status_code == 200
    assert muted.json() == {"github_poll_alert_muted": True}
    assert api.get("/admin/alerts").json() == {"github_poll_alert_muted": True}

    unmuted = api.put("/admin/alerts", json={"github_poll_alert_muted": False})
    assert unmuted.json() == {"github_poll_alert_muted": False}


def test_non_owner_cannot_read_or_write_alert_state(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: NON_OWNER

    assert api.get("/admin/alerts").status_code == 403
    assert api.put("/admin/alerts", json={"github_poll_alert_muted": True}).status_code == 403


def test_invalid_payloads_are_rejected(api):
    api_main.app.dependency_overrides[get_current_owner_uid] = lambda: OWNER

    assert api.put("/admin/alerts", json={"github_poll_alert_muted": "yes"}).status_code == 422
    assert api.put("/admin/alerts", json={}).status_code == 422
    assert api.put("/admin/alerts", json={"github_poll_alert_muted": True, "extra": 1}).status_code == 422
