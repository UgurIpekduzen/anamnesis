"""Integration tests for tenant (project) lifecycle, ownership, and GitHub/Jira link management."""

from datetime import datetime, timezone
import uuid

import pytest

from src.facts.facts import create_fact, get_tenant_facts
from src.core.firestore_client import get_client
from src.projects.tenants import (
    add_tenant,
    clear_github_repo,
    clear_jira_project_key,
    delete_tenant,
    get_owned_tenant,
    list_broken_github_connections,
    list_tenants,
    mark_github_poll_failed,
    mark_github_polled,
    rename_tenant,
    set_github_repo,
    set_jira_project_key,
)

OWNER_UID = "test-owner@example.com"
OTHER_UID = "someone-else@example.com"


@pytest.fixture
def tenant_name():
    """Return a unique tenant name so repeated test runs don't collide in the persistent emulator."""
    # A random suffix keeps repeated test runs from colliding on the same
    # tenant_id in the emulator, which persists state across runs.
    return f"Integration Test Tenant {uuid.uuid4().hex[:8]}"


def test_add_tenant_creates_a_listed_tenant(tenant_name):
    """A newly added tenant appears in the owner's tenant list with its given name."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        tenants = list_tenants(OWNER_UID)
        assert any(t["tenant_id"] == tenant_id and t["name"] == tenant_name for t in tenants)
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_rename_tenant_updates_the_name(tenant_name):
    """Renaming a tenant updates the name shown in the owner's tenant list."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        rename_tenant(tenant_id, "Renamed Tenant", OWNER_UID)
        tenants = list_tenants(OWNER_UID)
        assert any(t["tenant_id"] == tenant_id and t["name"] == "Renamed Tenant" for t in tenants)
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_delete_tenant_removes_it_from_the_list(tenant_name):
    """Deleting a tenant removes it from the owner's tenant list."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    delete_tenant(tenant_id, OWNER_UID)

    tenants = list_tenants(OWNER_UID)
    assert not any(t["tenant_id"] == tenant_id for t in tenants)


def test_set_jira_project_key(tenant_name):
    """Setting a Jira project key on a tenant is reflected in the owner's tenant list."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        set_jira_project_key(tenant_id, "APPCE", OWNER_UID)

        tenants = list_tenants(OWNER_UID)
        tenant = next(t for t in tenants if t["tenant_id"] == tenant_id)
        assert tenant["jira_project_key"] == "APPCE"
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_set_github_repo(tenant_name):
    """Setting a GitHub repo on a tenant is reflected in the owner's tenant list."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        set_github_repo(tenant_id, "UgurIpekduzen/anamnesis", OWNER_UID)

        tenants = list_tenants(OWNER_UID)
        tenant = next(t for t in tenants if t["tenant_id"] == tenant_id)
        assert tenant["github_repo"] == "UgurIpekduzen/anamnesis"
    finally:
        delete_tenant(tenant_id, OWNER_UID)


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-repo",
        "https://github.com/owner/name",
        "owner/name/extra",
        "-owner/name",
        "owner/",
        "/name",
    ],
)
def test_set_github_repo_rejects_anything_that_is_not_owner_slash_name(tenant_name, bad):
    """Setting a GitHub repo value that isn't in owner/name form raises ValueError."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        with pytest.raises(ValueError):
            set_github_repo(tenant_id, bad, OWNER_UID)
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_list_tenants_excludes_other_owners_tenants(tenant_name):
    """Listing tenants for one owner does not include a tenant created by another owner."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        tenants = list_tenants("someone-else@example.com")
        assert not any(t["tenant_id"] == tenant_id for t in tenants)
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_delete_tenant_rejects_a_non_owner(tenant_name):
    """Deleting a tenant as a user who isn't its owner raises PermissionError."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        with pytest.raises(PermissionError):
            delete_tenant(tenant_id, "someone-else@example.com")
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def _tenant_doc(tenant_id):
    return get_client().collection("tenants").document(tenant_id).get().to_dict()


def test_set_jira_project_key_rejects_an_invalid_key_and_saves_nothing(tenant_name):
    """Setting a Jira project key with invalid characters raises ValueError and stores nothing."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        with pytest.raises(ValueError):
            set_jira_project_key(tenant_id, 'X" OR project != "', OWNER_UID)

        assert "jira_project_key" not in _tenant_doc(tenant_id)
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_a_jira_project_key_can_be_set_and_cleared(tenant_name):
    """A Jira project key can be set, then cleared, leaving the tenant document and listing without it."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        set_jira_project_key(tenant_id, "APPCE", OWNER_UID)
        assert _tenant_doc(tenant_id)["jira_project_key"] == "APPCE"

        clear_jira_project_key(tenant_id, OWNER_UID)

        assert "jira_project_key" not in _tenant_doc(tenant_id)
        listed = next(t for t in list_tenants(OWNER_UID) if t["tenant_id"] == tenant_id)
        assert listed["jira_project_key"] is None
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_a_github_repo_can_be_cleared_and_its_poll_cut_off_goes_with_it(tenant_name):
    """Clearing a tenant's GitHub repo also removes its recorded poll cut-off timestamp."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        set_github_repo(tenant_id, "owner/repo", OWNER_UID)
        get_client().collection("tenants").document(tenant_id).update(
            {"github_polled_at": datetime(2026, 1, 1, tzinfo=timezone.utc)}
        )

        clear_github_repo(tenant_id, OWNER_UID)

        doc = _tenant_doc(tenant_id)
        assert "github_repo" not in doc
        assert "github_polled_at" not in doc
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_switching_to_another_repo_resets_the_poll_cut_off(tenant_name):
    """Switching a tenant to a different GitHub repo drops the previous repo's poll cut-off timestamp."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        set_github_repo(tenant_id, "owner/old-repo", OWNER_UID)
        get_client().collection("tenants").document(tenant_id).update(
            {"github_polled_at": datetime(2026, 1, 1, tzinfo=timezone.utc)}
        )

        set_github_repo(tenant_id, "owner/new-repo", OWNER_UID)

        doc = _tenant_doc(tenant_id)
        assert doc["github_repo"] == "owner/new-repo"
        # Kept, the old repo's cut-off would hide the new repo's existing items.
        assert "github_polled_at" not in doc
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_mark_github_poll_failed_records_the_failure(tenant_name):
    """Marking a GitHub poll as failed records the failure kind and a failure timestamp on the tenant."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        mark_github_poll_failed(tenant_id, "auth")

        doc = _tenant_doc(tenant_id)
        assert doc["github_poll_failure_kind"] == "auth"
        assert "github_poll_failed_at" in doc
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_a_successful_poll_clears_a_previously_recorded_failure(tenant_name):
    """Recording a successful poll clears a previously recorded GitHub poll failure."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        mark_github_poll_failed(tenant_id, "auth")

        mark_github_polled(tenant_id, OWNER_UID)

        doc = _tenant_doc(tenant_id)
        assert "github_poll_failed_at" not in doc
        assert "github_poll_failure_kind" not in doc
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_list_broken_github_connections_includes_a_failed_tenant(tenant_name):
    """A tenant with a recorded GitHub poll failure appears in the list of broken connections with its details."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        mark_github_poll_failed(tenant_id, "not_found")

        broken = list_broken_github_connections()

        entry = next(c for c in broken if c["tenant_id"] == tenant_id)
        assert entry["owner_uid"] == OWNER_UID
        assert entry["name"] == tenant_name
        assert entry["kind"] == "not_found"
        assert entry["failed_at"] is not None
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_list_broken_github_connections_excludes_a_healthy_tenant(tenant_name):
    """A tenant with no recorded GitHub poll failure does not appear in the list of broken connections."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        assert tenant_id not in {c["tenant_id"] for c in list_broken_github_connections()}
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_saving_the_same_repo_again_keeps_the_poll_cut_off(tenant_name):
    """Setting a tenant's GitHub repo to the same value it already has keeps the existing poll cut-off."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        set_github_repo(tenant_id, "owner/repo", OWNER_UID)
        cut_off = datetime(2026, 1, 1, tzinfo=timezone.utc)
        get_client().collection("tenants").document(tenant_id).update({"github_polled_at": cut_off})

        set_github_repo(tenant_id, "owner/repo", OWNER_UID)

        assert _tenant_doc(tenant_id)["github_polled_at"] == cut_off
    finally:
        delete_tenant(tenant_id, OWNER_UID)


@pytest.mark.parametrize("clear", [clear_github_repo, clear_jira_project_key])
def test_clearing_a_link_rejects_a_non_owner(tenant_name, clear):
    """Clearing a tenant's GitHub repo or Jira project key as a non-owner raises PermissionError."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        with pytest.raises(PermissionError):
            clear(tenant_id, "someone-else@example.com")
    finally:
        delete_tenant(tenant_id, OWNER_UID)


# The project id comes from the name and is shared by every user, so
# creating a project must never take over one that already exists.
def test_a_second_user_cannot_take_over_a_project_with_the_same_name(tenant_name):
    """A second user cannot create a project whose name slugifies to an existing tenant's id, and the original is unaffected."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        create_fact(tenant_id, "the first user's note", "note")

        # Same slug, different spelling: still the same project id.
        with pytest.raises(ValueError):
            add_tenant(tenant_name.upper(), OTHER_UID)

        assert get_owned_tenant(tenant_id, OWNER_UID)["name"] == tenant_name
        assert [f["content"] for f in get_tenant_facts(tenant_id, OWNER_UID)] == [
            "the first user's note"
        ]
        with pytest.raises(PermissionError):
            get_owned_tenant(tenant_id, OTHER_UID)
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_creating_the_same_name_twice_keeps_the_first_project_as_it_was(tenant_name):
    """Creating a tenant with a name that already exists for the same owner fails without overwriting the original tenant's data."""
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        set_github_repo(tenant_id, "some-org/some-repo", OWNER_UID)

        with pytest.raises(ValueError):
            add_tenant(tenant_name, OWNER_UID)

        # It used to be written over: the repo link and the creation time were lost.
        assert get_owned_tenant(tenant_id, OWNER_UID)["github_repo"] == "some-org/some-repo"
    finally:
        delete_tenant(tenant_id, OWNER_UID)
