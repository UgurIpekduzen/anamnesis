import json
import os
import subprocess

from src.publisher import publish_fact
from src.tenants import list_tenants

CONFIG_PATH = "git_activity_config.json"
DAYS = int(os.environ.get("GIT_ACTIVITY_DAYS", 7))


def summarize_and_publish():
    with open(CONFIG_PATH) as f:
        repo_tenants = json.load(f)

    known_ids = {t["tenant_id"] for t in list_tenants()}

    for tenant_id, repo_path in repo_tenants.items():
        if tenant_id not in known_ids:
            print(f"Skipping unknown tenant_id: {tenant_id}")
            continue

        result = subprocess.run(
            ["git", "log", f"--since={DAYS} days ago", "--oneline"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        commit_count = len(result.stdout.strip().splitlines())
        if commit_count == 0:
            continue

        # Data minimization (APPCE-29): only a count, never raw commit
        # message text — commit messages could reference third parties.
        content = f"{commit_count} commits in the last {DAYS} days."
        publish_fact(tenant_id, content, category="status")
        print(f"{tenant_id}: {commit_count} commits -> published")


if __name__ == "__main__":
    summarize_and_publish()
