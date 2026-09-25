import pytest
from starlette.testclient import TestClient

import api.main as api_main

OWNER = "test@example.com"


@pytest.fixture
def api(monkeypatch, signed_in_owner):
    calls = []
    monkeypatch.setattr(api_main, "get_fact", lambda tenant_id, fact_id, owner_uid: {"fact_id": fact_id})
    monkeypatch.setattr(
        api_main,
        "update_fact",
        lambda tenant_id, fact_id, owner_uid, content=None, category=None: calls.append(
            ("update", tenant_id, fact_id, owner_uid, content, category)
        ),
    )
    monkeypatch.setattr(
        api_main, "delete_fact", lambda tenant_id, fact_id, owner_uid: calls.append(("delete", tenant_id, fact_id, owner_uid))
    )
    return TestClient(api_main.app), calls


def test_patch_updates_a_fact_for_the_authenticated_user(api):
    client, calls = api

    response = client.patch("/tenants/proj/facts/f1", json={"content": "Uses MySQL"})

    assert response.status_code == 200
    assert response.json() == {"status": "updated"}
    assert calls == [("update", "proj", "f1", OWNER, "Uses MySQL", None)]


def test_patch_can_change_only_the_category(api):
    client, calls = api

    assert client.patch("/tenants/proj/facts/f1", json={"category": "decision"}).status_code == 200
    assert calls == [("update", "proj", "f1", OWNER, None, "decision")]


@pytest.mark.parametrize("body", [{}, {"content": ""}, {"content": "x" * 2001}, {"content": "ok", "owner_uid": "x"}, {"content": 5}])
def test_patch_rejects_a_bad_body_and_changes_nothing(api, body):
    client, calls = api

    assert client.patch("/tenants/proj/facts/f1", json=body).status_code == 422
    assert calls == []


def test_patch_with_an_unknown_category_is_a_400_with_the_reason(api, monkeypatch):
    client, _ = api

    def refuse(*args, **kwargs):
        raise ValueError("Invalid category 'nope'")

    monkeypatch.setattr(api_main, "update_fact", refuse)

    response = client.patch("/tenants/proj/facts/f1", json={"category": "nope"})

    assert response.status_code == 400
    assert "nope" in response.json()["detail"]


def test_delete_removes_a_fact(api):
    client, calls = api

    response = client.delete("/tenants/proj/facts/f1")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}
    assert calls == [("delete", "proj", "f1", OWNER)]


@pytest.mark.parametrize("error", [PermissionError("not yours"), LookupError("no such fact")])
def test_someone_elses_project_or_a_missing_fact_is_a_404_and_nothing_changes(api, monkeypatch, error):
    client, calls = api

    def missing(*args, **kwargs):
        raise error

    monkeypatch.setattr(api_main, "get_fact", missing)

    assert client.patch("/tenants/proj/facts/f1", json={"content": "x"}).status_code == 404
    assert client.delete("/tenants/proj/facts/f1").status_code == 404
    assert calls == []


def test_fact_edits_require_authentication():
    client = TestClient(api_main.app)

    assert client.patch("/tenants/proj/facts/f1", json={"content": "x"}).status_code == 401
    assert client.delete("/tenants/proj/facts/f1").status_code == 401
