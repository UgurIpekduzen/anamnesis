"""Integration tests for the db_backup CLI (dump/load/wipe/restore/verify)
against a real Firestore emulator."""

import json
from datetime import datetime, timezone

import pytest

from src.tools import db_backup
from src.core.firestore_client import get_client


@pytest.fixture
def own_project(monkeypatch):
    """Point GCP_PROJECT_ID at a dedicated emulator project, wipe it clean,
    and yield the Firestore client, wiping it again afterwards."""
    # The emulator keeps a project's data apart from the others', so wiping this
    # one can't touch what the other integration tests wrote.
    monkeypatch.setenv("GCP_PROJECT_ID", "db-backup-test")
    db_backup.wipe("db-backup-test")
    yield get_client()
    db_backup.wipe("db-backup-test")


def _write_sample(client):
    when = datetime(2026, 9, 26, 3, 11, 49, tzinfo=timezone.utc)
    client.document("tenants/alpha").set({"name": "Alpha", "created_at": when})
    client.document("tenants/alpha/facts/f1").set({"content": "a fact", "created_at": when})
    client.document("config/allowed_emails").set({"emails": ["a@example.com"]})
    # No fields of its own, only a subcollection: a plain stream() would miss it.
    client.document("tenants/ghost/facts/f2").set({"content": "under a parent without fields"})
    return when


def test_a_dump_can_be_loaded_back_and_gives_the_same_data(own_project, tmp_path):
    """A dump taken with db_backup.dump, loaded into a wiped project with
    db_backup.load, restores every document including one under a
    field-less parent."""
    when = _write_sample(own_project)
    path = str(tmp_path / "dump.json")

    assert db_backup.dump(path) == 4
    db_backup.wipe("db-backup-test")
    assert list(own_project.collections()) == []

    assert db_backup.load(path) == 4
    assert own_project.document("tenants/alpha").get().to_dict() == {
        "name": "Alpha",
        "created_at": when,
    }
    assert own_project.document("tenants/alpha/facts/f1").get().to_dict()["content"] == "a fact"
    assert own_project.document("config/allowed_emails").get().to_dict() == {
        "emails": ["a@example.com"]
    }
    assert (
        own_project.document("tenants/ghost/facts/f2").get().to_dict()["content"]
        == "under a parent without fields"
    )


def test_a_dump_says_which_project_and_when(own_project, tmp_path):
    """The dump file records the source project id, the backup format
    version, and a taken_at timestamp."""
    _write_sample(own_project)
    path = tmp_path / "dump.json"

    db_backup.dump(str(path))

    payload = json.loads(path.read_text())
    assert payload["project"] == "db-backup-test"
    assert payload["format"] == db_backup.FORMAT_VERSION
    assert payload["taken_at"]


def test_wipe_only_counts_until_the_project_is_confirmed(own_project):
    """db_backup.wipe with no confirming project id only counts documents
    and deletes nothing."""
    _write_sample(own_project)

    assert db_backup.wipe(None) == (4, False)
    assert own_project.document("tenants/alpha").get().exists


def test_wipe_with_the_wrong_project_deletes_nothing(own_project):
    """db_backup.wipe exits via SystemExit and deletes nothing when the
    confirming project id doesn't match the active one."""
    _write_sample(own_project)

    with pytest.raises(SystemExit):
        db_backup.wipe("some-other-project")

    assert own_project.document("tenants/alpha").get().exists


def test_wipe_with_the_right_project_deletes_everything_including_subcollections(own_project):
    """db_backup.wipe with the matching project id deletes every document,
    including those under a field-less parent."""
    _write_sample(own_project)

    assert db_backup.wipe("db-backup-test") == (4, True)

    assert list(own_project.collections()) == []


def _dump_of_sample(client, tmp_path):
    _write_sample(client)
    path = str(tmp_path / "dump.json")
    db_backup.dump(path)
    return path


def test_restore_only_reports_until_the_project_is_confirmed(own_project, tmp_path):
    """db_backup.restore with no confirming project id reports new/changed/
    unchanged counts but writes nothing back."""
    path = _dump_of_sample(own_project, tmp_path)
    own_project.document("tenants/alpha").update({"name": "Changed"})
    own_project.document("config/allowed_emails").delete()

    result = db_backup.restore(path, None)

    assert result == {"new": 1, "changed": 1, "unchanged": 2, "written": False}
    assert own_project.document("tenants/alpha").get().to_dict()["name"] == "Changed"
    assert not own_project.document("config/allowed_emails").get().exists


def test_restore_adds_what_is_missing_and_overwrites_what_differs_but_deletes_nothing(
    own_project, tmp_path
):
    """db_backup.restore with the matching project id recreates a deleted
    document, overwrites a changed one, and leaves a document written after
    the dump untouched."""
    path = _dump_of_sample(own_project, tmp_path)
    own_project.document("tenants/alpha").update({"name": "Changed"})
    own_project.document("config/allowed_emails").delete()
    own_project.document("tenants/alpha/facts/added-later").set(
        {"content": "written after the backup"}
    )

    result = db_backup.restore(path, "db-backup-test")

    assert result == {"new": 1, "changed": 1, "unchanged": 2, "written": True}
    assert own_project.document("tenants/alpha").get().to_dict()["name"] == "Alpha"
    assert own_project.document("config/allowed_emails").get().exists
    # Not in the dump, so left alone.
    assert own_project.document("tenants/alpha/facts/added-later").get().exists


def test_restore_with_the_wrong_project_writes_nothing(own_project, tmp_path):
    """db_backup.restore exits via SystemExit and writes nothing when the
    confirming project id doesn't match the active one."""
    path = _dump_of_sample(own_project, tmp_path)
    own_project.document("config/allowed_emails").delete()

    with pytest.raises(SystemExit):
        db_backup.restore(path, "some-other-project")

    assert not own_project.document("config/allowed_emails").get().exists


def test_restore_refuses_a_dump_from_another_project(own_project, tmp_path, monkeypatch):
    """db_backup.restore exits via SystemExit, naming the dump's source
    project, when asked to restore it into a different active project."""
    path = _dump_of_sample(own_project, tmp_path)

    # Only inside the block: the fixture's clean-up must still see the test project.
    with monkeypatch.context() as other:
        other.setenv("GCP_PROJECT_ID", "another-project")
        with pytest.raises(SystemExit, match="db-backup-test"):
            db_backup.restore(path, "another-project")


def test_verify_says_the_database_matches_the_dump_it_was_loaded_from(own_project, tmp_path):
    """db_backup.verify reports every document as matching right after the
    dump was taken."""
    path = _dump_of_sample(own_project, tmp_path)

    assert db_backup.verify(path) == {"same": 4, "different": 0, "missing": 0, "extra": 0}


def test_verify_finds_what_differs_what_is_missing_and_what_is_extra(own_project, tmp_path):
    """db_backup.verify separately reports a changed, a deleted, and an
    extra document against the dump."""
    path = _dump_of_sample(own_project, tmp_path)
    own_project.document("tenants/alpha").update({"name": "Changed"})
    own_project.document("config/allowed_emails").delete()
    own_project.document("tenants/alpha/facts/added-later").set({"content": "not in the dump"})

    assert db_backup.verify(path) == {"same": 2, "different": 1, "missing": 1, "extra": 1}


def test_verify_changes_nothing(own_project, tmp_path):
    """db_backup.verify is read-only: a document changed before the call
    stays changed afterwards."""
    path = _dump_of_sample(own_project, tmp_path)
    own_project.document("tenants/alpha").update({"name": "Changed"})

    db_backup.verify(path)

    assert own_project.document("tenants/alpha").get().to_dict()["name"] == "Changed"


def test_verify_works_on_a_dump_taken_from_another_project(own_project, tmp_path, monkeypatch):
    """db_backup.verify matches a dump against a different project's data
    loaded from it, since verify doesn't check the dump's project id."""
    # A dump of the real project checked against the emulator's copy of it.
    path = _dump_of_sample(own_project, tmp_path)
    with monkeypatch.context() as other:
        other.setenv("GCP_PROJECT_ID", "the-copy")
        db_backup.load(path)
        try:
            assert db_backup.verify(path) == {"same": 4, "different": 0, "missing": 0, "extra": 0}
        finally:
            db_backup.wipe("the-copy")


def test_the_verify_command_exits_non_zero_when_the_database_differs(own_project, tmp_path):
    """db_backup.main("verify", ...) exits 0 while the database matches the
    dump, and 1 once a document diverges from it."""
    path = _dump_of_sample(own_project, tmp_path)

    assert db_backup.main(["verify", path]) == 0

    own_project.document("tenants/alpha").update({"name": "Changed"})
    assert db_backup.main(["verify", path]) == 1
