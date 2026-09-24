"""Setup shared by every test (APPCE-106)."""

import json
import os
import sys

import pytest

# api.deps reads these when it is first imported, so they must be in place
# before any test module imports api.main; conftest.py is loaded before the
# test modules are collected.
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("ALLOWED_EMAILS", "test@example.com")
os.environ.setdefault("GITHUB_POLLER_SERVICE_ACCOUNT_EMAIL", "poller@test-project.iam.gserviceaccount.com")
os.environ.setdefault("GITHUB_POLLER_AUDIENCE", "https://anamnesis-app.example/internal/poll-github")

OWNER = "test@example.com"


@pytest.fixture
def log_lines():
    """Reads the structured log lines (src.log) out of what a test captured."""

    def read(captured_out: str) -> list[dict]:
        lines = []
        for line in captured_out.splitlines():
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return lines

    return read


@pytest.fixture
def signed_in_owner():
    """Make every authenticated endpoint treat the request as coming from OWNER,
    without a real Google token."""
    from api.deps import get_current_owner_uid
    from api.main import app

    app.dependency_overrides[get_current_owner_uid] = lambda: OWNER
    return OWNER


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    """Whatever a test overrode must not leak into the next one. api.main is
    only touched if the test already imported it, so tests that never use the
    API don't pay for loading it."""
    yield
    api_main = sys.modules.get("api.main")
    if api_main is not None:
        api_main.app.dependency_overrides.clear()
