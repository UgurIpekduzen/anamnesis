"""Auth for the scheduler-only endpoint: verifies Cloud Scheduler's own
OIDC identity, kept separate from api/deps.py's user-facing allowlist
check since it authenticates a service account, not a signed-in user."""

import os

from fastapi import Header, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

_request = google_requests.Request()


def verify_scheduler_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency gating /internal/poll-github.

    Raises 401/403 unless the request carries a valid Google-signed OIDC
    token whose audience and email match the scheduler job's identity —
    never the user-facing GOOGLE_OAUTH_CLIENT_ID/ALLOWED_EMAILS check.

    Reads its config from the environment on every call rather than
    freezing it into a module-level constant at import time: several
    test files import api.main (and transitively this module) with
    different env vars set, and whichever one runs first in a shared
    test process would otherwise "win" for the rest of the session.

    Args:
        authorization (str | None): The raw Authorization header value,
            expected as "Bearer <token>"; None if the header was absent.
    """
    # The service account Cloud Scheduler signs its OIDC token as when it
    # calls this endpoint — set once the Terraform-side service
    # account + scheduler job exist. Deliberately a *different* check from
    # api.deps's user-facing ALLOWED_EMAILS: this endpoint is never meant
    # to be reachable by a signed-in user, only by the scheduler itself.
    scheduler_service_account_email = os.environ.get("GITHUB_POLLER_SERVICE_ACCOUNT_EMAIL", "")
    # Must match exactly what Cloud Scheduler is configured to put in the
    # OIDC token's "aud" claim (the job's http_target.uri in Terraform).
    expected_audience = os.environ.get("GITHUB_POLLER_AUDIENCE", "")

    if not scheduler_service_account_email or not expected_audience:
        # Misconfiguration, not a caller problem — fail closed either way.
        raise HTTPException(status_code=503, detail="Scheduler auth not configured")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization[len("Bearer ") :]
    try:
        claims = id_token.verify_oauth2_token(token, _request, expected_audience)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

    if claims.get("email") != scheduler_service_account_email:
        raise HTTPException(status_code=403, detail="Not the expected scheduler identity")
