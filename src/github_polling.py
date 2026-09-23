from datetime import datetime, timezone

from src.github_activity import fetch_recent_issues, fetch_recent_pull_requests
from src.github_fact_extraction import extract_facts
from src.pending_facts import create_pending_fact
from src.tenants import get_owned_tenant, mark_github_polled


def _parse_github_timestamp(value: str) -> datetime:
    # GitHub's timestamps are ISO 8601 with a "Z" suffix, which fromisoformat
    # only accepts once normalized to an explicit "+00:00" offset.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def poll_tenant_github_activity(owner_uid: str, tenant_id: str) -> int:
    """Fetch a tenant's recent GitHub PRs/issues, extract candidate facts
    from each, and stage them for review (see APPCE-81).

    Only items updated since the last poll are processed — otherwise every
    run would re-extract and re-stage the same pending facts for anything
    that hasn't changed. This function is meant to be called periodically
    (Cloud Scheduler once APPCE-56 lands; called by hand or a manual
    trigger until then, see APPCE-80).

    Returns:
        How many pending facts were staged this run.
    """
    tenant = get_owned_tenant(tenant_id, owner_uid)
    last_polled_at = tenant.get("github_polled_at")

    created = 0
    for kind, fetch in (("pull request", fetch_recent_pull_requests), ("issue", fetch_recent_issues)):
        for item in fetch(owner_uid, tenant_id):
            if last_polled_at is not None and _parse_github_timestamp(item["updated_at"]) <= last_polled_at:
                continue
            for fact in extract_facts(item["title"], item["body"], kind):
                create_pending_fact(
                    tenant_id, fact["content"], fact["category"], "github", item["url"], owner_uid
                )
                created += 1

    mark_github_polled(tenant_id, owner_uid)
    return created
