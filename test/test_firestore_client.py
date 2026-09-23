import pytest

from src import firestore_client


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    built = []

    def fake_client(project):
        built.append(project)
        return object()

    monkeypatch.setattr(firestore_client.firestore, "Client", fake_client)
    firestore_client._build_client.cache_clear()
    monkeypatch.setenv("GCP_PROJECT_ID", "proj-a")
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    yield built
    firestore_client._build_client.cache_clear()


def test_repeated_calls_share_one_client(fresh_cache):
    assert firestore_client.get_client() is firestore_client.get_client()
    assert fresh_cache == ["proj-a"]


def test_a_different_project_gets_its_own_client(fresh_cache, monkeypatch):
    first = firestore_client.get_client()
    monkeypatch.setenv("GCP_PROJECT_ID", "proj-b")
    assert firestore_client.get_client() is not first
    assert fresh_cache == ["proj-a", "proj-b"]


def test_switching_the_emulator_host_builds_a_new_client(fresh_cache, monkeypatch):
    first = firestore_client.get_client()
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "localhost:8080")
    assert firestore_client.get_client() is not first


def test_a_missing_project_id_is_an_error(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID")
    with pytest.raises(RuntimeError):
        firestore_client.get_client()
