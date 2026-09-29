"""Permanently delete one invited user's data — everything the app knows
about a single email, as opposed to src.tools.db_backup's whole-database
wipe.

Removing access (src.accounts.allowed_emails.remove_allowed_email) only
stops a sign-in; it leaves the user's projects, facts, connections and usage
history in Firestore. wipe_user is the follow-up: same destructive-operation
family as db_backup's wipe/restore, so it follows the same shape — a dry run
by default, a deletion only when explicitly confirmed.
"""

from src.accounts.allowed_emails import OWNER_EMAILS, get_extra_allowed_emails, remove_allowed_email
from src.accounts.profiles import get_name, set_name
from src.accounts.usage import delete_usage
from src.core.firestore_client import get_client
from src.facts.categories import USER_COLLECTION as CATEGORIES_COLLECTION
from src.facts.categories import reset_categories
from src.integrations.github.connections import delete_github_connection, has_github_connection
from src.integrations.jira.connections import delete_jira_connection, has_jira_connection
from src.projects.tenants import delete_tenant, list_tenants


def wipe_user(email: str, confirm: bool = False) -> dict:
    """Report what belongs to email across every collection (and, with
    confirm=True, delete all of it): every tenant they own — cascading into
    its facts/chat_turns/pending_facts, same as delete_tenant — their GitHub
    and Jira connections, usage record, saved categories and owner-set
    display name, plus their entry in the allowlist (including
    any role).

    Deliberately doesn't touch src.accounts.settings — conversation memory
    and the daily warning threshold are shared, owner-set values,
    not this user's own data, so wiping a user must never reset them for
    everyone else.

    Never touches an owner: OWNER_EMAILS is the Terraform-configured
    identity that keeps this deployment from locking itself out, not
    invited-user data.

    Returns:
        {"tenants": [tenant_id, ...], "github_connection": bool,
         "jira_connection": bool, "usage_record": bool, "categories": bool,
         "name": str | None, "on_allowlist": bool, "deleted": bool}
        The booleans and the tenant list describe what's there (or, once
        confirm=True, what was there) — a dry run's report and a confirmed
        run's summary have the same shape.

    Raises:
        ValueError: email is an owner.
    """
    if email in OWNER_EMAILS:
        raise ValueError("The owner's data can't be wiped.")

    client = get_client()
    tenants = [t["tenant_id"] for t in list_tenants(email)]
    summary = {
        "tenants": tenants,
        "github_connection": has_github_connection(email),
        "jira_connection": has_jira_connection(email),
        "usage_record": client.collection("usage").document(email).get().exists,
        "categories": client.collection(CATEGORIES_COLLECTION).document(email).get().exists,
        "name": get_name(email),
        "on_allowlist": email in get_extra_allowed_emails(),
        "deleted": False,
    }
    if not confirm:
        return summary

    for tenant_id in tenants:
        delete_tenant(tenant_id, email)
    delete_github_connection(email)
    delete_jira_connection(email)
    delete_usage(email)
    # reset_categories, not a raw client.delete(): that module keeps a
    # short-lived in-process read cache, and only its own reset function
    # knows to drop it too — a direct Firestore delete would leave a stale
    # cached value behind.
    reset_categories(email)
    set_name(email, "")
    if summary["on_allowlist"]:
        remove_allowed_email(email)

    summary["deleted"] = True
    return summary
