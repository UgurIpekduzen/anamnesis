import os

# api.internal_auth reads these at import time.
os.environ.setdefault("GITHUB_POLLER_SERVICE_ACCOUNT_EMAIL", "poller@test-project.iam.gserviceaccount.com")
os.environ.setdefault("GITHUB_POLLER_AUDIENCE", "https://anamnesis-app.example/internal/poll-github")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import api.internal_auth as internal_auth  # noqa: E402

SCHEDULER_EMAIL = "poller@test-project.iam.gserviceaccount.com"


def _verifier(claims=None, error=None):
    def fake(token, request, audience):
        if error:
            raise error
        return claims

    return fake


def test_a_valid_scheduler_token_is_accepted(monkeypatch):
    monkeypatch.setattr(internal_auth.id_token, "verify_oauth2_token", _verifier(claims={"email": SCHEDULER_EMAIL}))

    internal_auth.verify_scheduler_token(authorization=f"Bearer tok")  # noqa: F541


def test_a_token_for_a_different_identity_is_rejected(monkeypatch):
    monkeypatch.setattr(
        internal_auth.id_token, "verify_oauth2_token", _verifier(claims={"email": "someone-else@example.com"})
    )

    with pytest.raises(HTTPException) as exc:
        internal_auth.verify_scheduler_token(authorization="Bearer tok")
    assert exc.value.status_code == 403


def test_an_invalid_token_is_rejected(monkeypatch):
    monkeypatch.setattr(
        internal_auth.id_token, "verify_oauth2_token", _verifier(error=ValueError("bad signature"))
    )

    with pytest.raises(HTTPException) as exc:
        internal_auth.verify_scheduler_token(authorization="Bearer tok")
    assert exc.value.status_code == 401


def test_a_missing_bearer_token_is_rejected():
    with pytest.raises(HTTPException) as exc:
        internal_auth.verify_scheduler_token(authorization=None)
    assert exc.value.status_code == 401


def test_misconfiguration_fails_closed(monkeypatch):
    monkeypatch.delenv("GITHUB_POLLER_SERVICE_ACCOUNT_EMAIL", raising=False)

    with pytest.raises(HTTPException) as exc:
        internal_auth.verify_scheduler_token(authorization="Bearer tok")
    assert exc.value.status_code == 503
