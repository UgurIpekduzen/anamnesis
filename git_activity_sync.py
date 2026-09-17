import os
import subprocess

from src.publisher import publish_fact
from src.tenants import list_tenants

DAYS = int(os.environ.get("GIT_ACTIVITY_DAYS", 7))
# This script runs locally, scoped to whoever's machine it's on — there's
# no Cloud Run identity to read here, so the owner is given explicitly
# instead of defaulting silently to the wrong person's projects.
OWNER_UID = os.environ["GIT_ACTIVITY_OWNER_UID"]


def summarize_and_publish():
    # git_repo_path is set per tenant via the agent (set_git_repo_path,
    # APPCE-34) rather than a local config file — machine-specific, so a
    # tenant with no repo on this machine simply has it unset here.
    tenants_with_repo = [t for t in list_tenants(OWNER_UID) if t.get("git_repo_path")]

    for tenant in tenants_with_repo:
        tenant_id = tenant["tenant_id"]
        repo_path = tenant["git_repo_path"]

        try:
            result = subprocess.run(
                ["git", "log", f"--since={DAYS} days ago", "--oneline"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
        except (FileNotFoundError, NotADirectoryError, subprocess.CalledProcessError):
            # git_repo_path is machine-specific (APPCE-34) — on a machine
            # where this path doesn't exist, skip instead of crashing the
            # whole sync over one tenant.
            print(f"{tenant_id}: repo path '{repo_path}' not usable on this machine, skipping")
            continue
        commit_count = len(result.stdout.strip().splitlines())
        if commit_count == 0:
            continue

        # Data minimization (APPCE-29): only a count, never raw commit
        # message text — commit messages could reference third parties.
        content = f"{commit_count} commits in the last {DAYS} days."
        publish_fact(tenant_id, content, category="status", owner_uid=OWNER_UID)
        print(f"{tenant_id}: {commit_count} commits -> published")


if __name__ == "__main__":
    summarize_and_publish()
