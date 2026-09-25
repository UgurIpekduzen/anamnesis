from datetime import datetime, timezone
import uuid

import pytest

from src.firestore_client import get_client
from src.tenants import (
    add_tenant,
    clear_github_repo,
    clear_jira_project_key,
    delete_tenant,
    list_tenants,
    rename_tenant,
    set_github_repo,
    set_jira_project_key,
)

OWNER_UID = "test-owner@example.com"


@pytest.fixture
def tenant_name():
    # A random suffix keeps repeated test runs from colliding on the same
    # tenant_id in the emulator, which persists state across runs.
    return f"Integration Test Tenant {uuid.uuid4().hex[:8]}"


def test_add_tenant_creates_a_listed_tenant(tenant_name):
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        tenants = list_tenants(OWNER_UID)
        assert any(t["tenant_id"] == tenant_id and t["name"] == tenant_name for t in tenants)
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_rename_tenant_updates_the_name(tenant_name):
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        rename_tenant(tenant_id, "Renamed Tenant", OWNER_UID)
        tenants = list_tenants(OWNER_UID)
        assert any(t["tenant_id"] == tenant_id and t["name"] == "Renamed Tenant" for t in tenants)
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_delete_tenant_removes_it_from_the_list(tenant_name):
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    delete_tenant(tenant_id, OWNER_UID)

    tenants = list_tenants(OWNER_UID)
    assert not any(t["tenant_id"] == tenant_id for t in tenants)


def test_set_jira_project_key(tenant_name):
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        set_jira_project_key(tenant_id, "APPCE", OWNER_UID)

        tenants = list_tenants(OWNER_UID)
        tenant = next(t for t in tenants if t["tenant_id"] == tenant_id)
        assert tenant["jira_project_key"] == "APPCE"
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_set_github_repo(tenant_name):
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
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        with pytest.raises(ValueError):
            set_github_repo(tenant_id, bad, OWNER_UID)
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_list_tenants_excludes_other_owners_tenants(tenant_name):
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        tenants = list_tenants("someone-else@example.com")
        assert not any(t["tenant_id"] == tenant_id for t in tenants)
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_delete_tenant_rejects_a_non_owner(tenant_name):
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        with pytest.raises(PermissionError):
            delete_tenant(tenant_id, "someone-else@example.com")
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def _tenant_doc(tenant_id):
    return get_client().collection("tenants").document(tenant_id).get().to_dict()


def test_set_jira_project_key_rejects_an_invalid_key_and_saves_nothing(tenant_name):
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        with pytest.raises(ValueError):
            set_jira_project_key(tenant_id, 'X" OR project != "', OWNER_UID)

        assert "jira_project_key" not in _tenant_doc(tenant_id)
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_a_jira_project_key_can_be_set_and_cleared(tenant_name):
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
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        set_github_repo(tenant_id, "owner/repo", OWNER_UID)
        get_client().collection("tenants").document(tenant_id).update({"github_polled_at": datetime(2026, 1, 1, tzinfo=timezone.utc)})

        clear_github_repo(tenant_id, OWNER_UID)

        doc = _tenant_doc(tenant_id)
        assert "github_repo" not in doc
        assert "github_polled_at" not in doc
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_switching_to_another_repo_resets_the_poll_cut_off(tenant_name):
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        set_github_repo(tenant_id, "owner/old-repo", OWNER_UID)
        get_client().collection("tenants").document(tenant_id).update({"github_polled_at": datetime(2026, 1, 1, tzinfo=timezone.utc)})

        set_github_repo(tenant_id, "owner/new-repo", OWNER_UID)

        doc = _tenant_doc(tenant_id)
        assert doc["github_repo"] == "owner/new-repo"
        # Kept, the old repo's cut-off would hide the new repo's existing items.
        assert "github_polled_at" not in doc
    finally:
        delete_tenant(tenant_id, OWNER_UID)


def test_saving_the_same_repo_again_keeps_the_poll_cut_off(tenant_name):
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
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        with pytest.raises(PermissionError):
            clear(tenant_id, "someone-else@example.com")
    finally:
        delete_tenant(tenant_id, OWNER_UID)
