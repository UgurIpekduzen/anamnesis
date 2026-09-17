import uuid

import pytest

from src.tenants import (
    add_tenant,
    delete_tenant,
    list_tenants,
    rename_tenant,
    set_git_repo_path,
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


def test_set_jira_project_key_and_git_repo_path(tenant_name):
    tenant_id = add_tenant(tenant_name, OWNER_UID)
    try:
        set_jira_project_key(tenant_id, "APPCE", OWNER_UID)
        set_git_repo_path(tenant_id, "/home/user/repos/anamnesis", OWNER_UID)

        tenants = list_tenants(OWNER_UID)
        tenant = next(t for t in tenants if t["tenant_id"] == tenant_id)
        assert tenant["jira_project_key"] == "APPCE"
        assert tenant["git_repo_path"] == "/home/user/repos/anamnesis"
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
