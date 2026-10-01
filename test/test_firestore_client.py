"""Tests for the cached Firestore client factory (get_client)."""

import pytest

from src.core import firestore_client


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    """Stub firestore.Client with a fake that records each project it was
    built for, clear the client cache before and after, and yield the list
    of built projects."""
    built = []

    def fake_client(project):
        """Record the project id a client was requested for and return a stand-in client."""
        built.append(project)
        return object()

    monkeypatch.setattr(firestore_client.firestore, "Client", fake_client)
    firestore_client._build_client.cache_clear()
    monkeypatch.setenv("GCP_PROJECT_ID", "proj-a")
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    yield built
    firestore_client._build_client.cache_clear()


def test_repeated_calls_share_one_client(fresh_cache):
    """Repeated get_client() calls for the same project return the same
    cached client instance."""
    assert firestore_client.get_client() is firestore_client.get_client()
    assert fresh_cache == ["proj-a"]


def test_a_different_project_gets_its_own_client(fresh_cache, monkeypatch):
    """Changing GCP_PROJECT_ID makes get_client() build and cache a new client."""
    first = firestore_client.get_client()
    monkeypatch.setenv("GCP_PROJECT_ID", "proj-b")
    assert firestore_client.get_client() is not first
    assert fresh_cache == ["proj-a", "proj-b"]


def test_switching_the_emulator_host_builds_a_new_client(fresh_cache, monkeypatch):
    """Setting FIRESTORE_EMULATOR_HOST makes get_client() build a new client
    instead of returning the cached one."""
    first = firestore_client.get_client()
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "localhost:8080")
    assert firestore_client.get_client() is not first


def test_a_missing_project_id_is_an_error(monkeypatch):
    """get_client() raises RuntimeError when GCP_PROJECT_ID isn't set."""
    monkeypatch.delenv("GCP_PROJECT_ID")
    with pytest.raises(RuntimeError):
        firestore_client.get_client()
