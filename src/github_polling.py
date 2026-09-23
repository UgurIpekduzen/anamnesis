from datetime import datetime, timezone

from src.github_activity import fetch_recent_issues, fetch_recent_pull_requests
from src.github_fact_extraction import extract_facts
from src.pending_facts import create_pending_fact
from src.tenants import get_owned_tenant, list_tenants_with_github_repo, mark_github_polled


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


def poll_all_tenants() -> dict:
    """Poll every tenant (any owner) with a linked GitHub repo.

    The actual periodic trigger (Cloud Scheduler calling an endpoint that
    calls this) is Terraform's responsibility (APPCE-80) — this is just
    the orchestration, so it's testable and callable independently of how
    it ends up scheduled.

    One tenant's failure (a revoked token, a deleted repo, a transient
    GitHub API error) doesn't stop the others — each is caught and
    reported instead of letting one bad tenant block every later one in
    the same run.

    Returns:
        {"polled": int, "created": int, "errors": [{"tenant_id": str, "error": str}]}
    """
    polled = 0
    created = 0
    errors = []
    for tenant in list_tenants_with_github_repo():
        try:
            created += poll_tenant_github_activity(tenant["owner_uid"], tenant["tenant_id"])
            polled += 1
        except Exception as e:
            errors.append({"tenant_id": tenant["tenant_id"], "error": str(e)})

    return {"polled": polled, "created": created, "errors": errors}
