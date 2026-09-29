"""Periodic polling of every tenant's linked GitHub repo: fetches recent
PRs/issues, extracts candidate facts, and stages them for review. Meant to
be called by whatever schedules it (Cloud Scheduler, or by hand) — this
module only orchestrates, so it stays testable independent of that trigger.
"""

from datetime import datetime

from src.integrations.github.activity import fetch_recent_issues, fetch_recent_pull_requests
from src.integrations.github.alerts import is_github_poll_alert_muted
from src.integrations.github.fact_extraction import extract_facts
from src.core.log import log
from src.facts.pending_facts import create_pending_fact, has_pending_fact_for_source
from src.projects.tenants import (
    get_owned_tenant,
    list_tenants_with_github_repo,
    mark_github_poll_failed,
    mark_github_polled,
)

# Upper bound on LLM extractions per tenant per poll. Normal use
# is far below it: a fetch returns at most 2 x DEFAULT_LIMIT items.
MAX_EXTRACTIONS_PER_POLL = 10


def _parse_github_timestamp(value: str) -> datetime:
    # GitHub's timestamps are ISO 8601 with a "Z" suffix, which fromisoformat
    # only accepts once normalized to an explicit "+00:00" offset.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def poll_tenant_github_activity(
    owner_uid: str, tenant_id: str, max_extractions: int = MAX_EXTRACTIONS_PER_POLL
) -> int:
    """Fetch a tenant's recent GitHub PRs/issues, extract candidate facts
    from each, and stage them for review.

    Only items updated since the last poll are processed — otherwise every
    run would re-extract and re-stage the same pending facts for anything
    that hasn't changed. This function is meant to be called periodically
    (Cloud Scheduler once that periodic trigger is set up in Terraform;
    called by hand or a manual trigger until then).

    Each item costs one LLM call, and anyone with write access to the repo
    controls how many items exist — so at most `max_extractions` are
    processed per run. The rest are dropped (the poll is still marked done,
    so they aren't retried): a flood of issues shouldn't turn into an
    ever-growing bill, and this is a safety valve, not the normal path.
    Items that already have a pending fact are skipped before extraction so
    a retried or overlapping scheduler run doesn't stage them twice.

    Returns:
        How many pending facts were staged this run.
    """
    tenant = get_owned_tenant(tenant_id, owner_uid)
    last_polled_at = tenant.get("github_polled_at")

    created = 0
    extractions = 0
    skipped_over_cap = 0
    for kind, fetch in (("pull request", fetch_recent_pull_requests), ("issue", fetch_recent_issues)):
        for item in fetch(owner_uid, tenant_id):
            if last_polled_at is not None and _parse_github_timestamp(item["updated_at"]) <= last_polled_at:
                continue
            if has_pending_fact_for_source(tenant_id, item["url"]):
                continue
            if extractions >= max_extractions:
                skipped_over_cap += 1
                continue
            extractions += 1
            for fact in extract_facts(item["title"], item["body"], kind, owner_uid):
                create_pending_fact(
                    tenant_id, fact["content"], fact["category"], "github", item["url"], owner_uid
                )
                created += 1

    if skipped_over_cap:
        log("WARNING", "github_poll_cap_hit", tenant_id=tenant_id, cap=max_extractions, dropped=skipped_over_cap)

    mark_github_polled(tenant_id, owner_uid)
    return created


def _classify_poll_error(exc: Exception) -> str:
    """Coarsely classify a poll failure for Admin-panel display,
    without keeping the raw exception text anywhere (see poll_all_tenants).

    Only requests.HTTPError (raised by activity.py's raise_for_status())
    carries a status code to branch on; anything else — a network error, a
    bug, a test double — falls through to "other".
    """
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 403):
        return "auth"
    if status == 404:
        return "not_found"
    return "other"


def poll_all_tenants() -> dict:
    """Poll every tenant (any owner) with a linked GitHub repo.

    The actual periodic trigger (Cloud Scheduler calling an endpoint that
    calls this) is Terraform's responsibility — this is just
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
            mark_github_poll_failed(tenant["tenant_id"], _classify_poll_error(e))

    result = {"polled": polled, "created": created, "errors": errors}
    # One structured line per run so Cloud Logging can filter on it (and a
    # log-based alert can fire on a non-empty `errors`). The
    # error strings stay out of it in case they echo credentials.
    #
    # ERROR unless the owner muted this alert from the Admin window —
    # the Cloud Monitoring alert policy in
    # terraform/monitoring.tf only matches severity=ERROR, so WARNING here
    # is what actually silences the emails, without touching that policy or
    # needing any new GCP permission.
    severity = "INFO" if not errors else ("WARNING" if is_github_poll_alert_muted() else "ERROR")
    log(
        severity,
        "github_poll",
        polled=polled,
        created=created,
        error_count=len(errors),
        failed_tenants=[e["tenant_id"] for e in errors],
    )
    return result
