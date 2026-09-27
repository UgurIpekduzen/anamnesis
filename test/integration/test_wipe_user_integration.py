"""wipe_user (APPCE-123) against the real emulator — the boundary that
matters most for something permanent and irreversible: a dry run must never
write anything, a confirmed run must actually clear every collection it
claims to, the owner must never be a valid target, and a call that fails
partway through must leave things in a state a retry can finish cleanly.
"""

import uuid

import pytest

from src.accounts.allowed_emails import add_allowed_email, get_extra_allowed_emails, set_role
from src.accounts.settings import get_settings, save_settings
from src.accounts.usage import get_today_count, record_message
from src.facts.categories import get_categories, save_categories
from src.facts.facts import get_tenant_facts
from src.integrations.github.connections import has_github_connection, save_github_token
from src.integrations.jira.connections import has_jira_connection, save_jira_credentials
from src.projects.tenants import add_tenant, list_tenants
from src.tools import wipe_user as wipe_user_module
from src.tools.wipe_user import wipe_user


@pytest.fixture
def seeded_user():
    """An invited email with something in every collection wipe_user touches."""
    email = f"wipe-{uuid.uuid4().hex[:8]}@example.com"
    add_allowed_email(email)
    set_role(email, "user")
    # The tenant_id namespace is global (tenants.py derives it from the
    # name, not the owner), so the name must be unique per test run too.
    project_name = f"Wipe Test Project {uuid.uuid4().hex[:8]}"
    tenant_id = add_tenant(project_name, email)
    record_message(email)
    save_categories(email, ["bug"])
    save_settings(email, {"history_turns": 5, "daily_message_warning_threshold": 10})
    save_github_token(email, "ghp_fake")
    save_jira_credentials(email, "jira@example.com", "fake-token", "https://example.atlassian.net")
    yield email, tenant_id, project_name


def test_a_dry_run_reports_without_deleting_anything(seeded_user):
    email, tenant_id, project_name = seeded_user

    result = wipe_user(email)

    assert result["deleted"] is False
    assert result["tenants"] == [tenant_id]
    assert result["on_allowlist"] is True
    # Nothing touched: nobody's data is gone just from asking what's there.
    assert list_tenants(email) == [
        {"tenant_id": tenant_id, "name": project_name, "jira_project_key": None, "github_repo": None}
    ]
    assert email in get_extra_allowed_emails()
    assert has_github_connection(email) is True


def test_a_confirmed_wipe_clears_every_collection(seeded_user):
    email, tenant_id, _ = seeded_user

    result = wipe_user(email, confirm=True)

    assert result["deleted"] is True
    assert list_tenants(email) == []
    # The tenant doc itself is gone, so even asking for its facts now looks
    # like "never existed" (get_owned_tenant, APPCE-48) — the strongest
    # confirmation available that the facts really went with it.
    with pytest.raises(PermissionError):
        get_tenant_facts(tenant_id, email)
    assert has_github_connection(email) is False
    assert has_jira_connection(email) is False
    assert get_today_count(email) == 0
    assert get_categories(email) != ["bug"]  # back to the suggested default
    assert get_settings(email)["history_turns"] != 5  # back to the default
    assert email not in get_extra_allowed_emails()


def test_the_owner_cannot_be_wiped(monkeypatch):
    owner = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    # wipe_user.py imports OWNER_EMAILS into its own module namespace (`from
    # ... import OWNER_EMAILS`), a separate binding from
    # src.accounts.allowed_emails.OWNER_EMAILS — same pitfall as api.deps,
    # so it must be patched here too.
    monkeypatch.setattr(wipe_user_module, "OWNER_EMAILS", {owner})

    with pytest.raises(ValueError, match="owner"):
        wipe_user(owner, confirm=True)


def test_a_retry_after_a_partial_failure_finishes_the_job(seeded_user, monkeypatch):
    """Simulates the tenant delete failing partway through a confirmed wipe
    (e.g. a transient Firestore error) — the failure must propagate (not be
    swallowed into a misleadingly "successful" summary), and a second,
    ordinary call must be able to finish cleanly since every step here is
    independently idempotent."""
    email, tenant_id, project_name = seeded_user
    real_delete_tenant = wipe_user_module.delete_tenant
    calls = []

    def flaky_delete_tenant(tid, owner_uid):
        calls.append(tid)
        if len(calls) == 1:
            raise RuntimeError("simulated Firestore failure")
        return real_delete_tenant(tid, owner_uid)

    monkeypatch.setattr(wipe_user_module, "delete_tenant", flaky_delete_tenant)

    with pytest.raises(RuntimeError):
        wipe_user(email, confirm=True)

    # The tenant is still there (delete_tenant never got a chance to run
    # for it) — nothing was left half-deleted or silently skipped.
    assert list_tenants(email) == [
        {"tenant_id": tenant_id, "name": project_name, "jira_project_key": None, "github_repo": None}
    ]

    monkeypatch.setattr(wipe_user_module, "delete_tenant", real_delete_tenant)
    result = wipe_user(email, confirm=True)

    assert result["deleted"] is True
    assert list_tenants(email) == []
    assert email not in get_extra_allowed_emails()
