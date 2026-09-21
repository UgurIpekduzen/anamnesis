import os

# api.deps reads these at import time.
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("ALLOWED_EMAILS", "test@example.com")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import api.deps as deps  # noqa: E402


def _verifier(claims=None, error=None):
    seen = {}

    def fake(token, request, audience, clock_skew_in_seconds):
        seen.update(token=token, audience=audience, skew=clock_skew_in_seconds)
        if error:
            raise error
        return claims

    return fake, seen


def test_a_valid_allowlisted_token_returns_its_email(monkeypatch):
    fake, seen = _verifier(claims={"email": "test@example.com"})
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    assert deps.verify_token("tok") == "test@example.com"
    assert seen["audience"] == "test-client-id"


def test_verification_allows_a_small_clock_skew(monkeypatch):
    fake, seen = _verifier(claims={"email": "test@example.com"})
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    deps.verify_token("tok")

    assert seen["skew"] == deps.CLOCK_SKEW_SECONDS > 0


def test_a_valid_token_for_an_account_off_the_allowlist_is_forbidden(monkeypatch):
    fake, _ = _verifier(claims={"email": "stranger@example.com"})
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    with pytest.raises(HTTPException) as excinfo:
        deps.verify_token("tok")
    assert excinfo.value.status_code == 403


def test_a_token_google_rejects_is_a_401(monkeypatch):
    fake, _ = _verifier(error=ValueError("Token used too early, 100 < 101"))
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    with pytest.raises(HTTPException) as excinfo:
        deps.verify_token("tok")
    assert excinfo.value.status_code == 401


@pytest.mark.parametrize(
    "message, expected",
    [
        ("Token used too early, 100 < 101", "too early"),
        ("Token expired, 100 < 200", "expired"),
        ("Token has wrong audience abc, expected one of ['x']", "audience"),
        ("Could not verify token signature.", "signature"),
        ("Something nobody anticipated", "other"),
    ],
)
def test_the_rejection_log_names_the_reason_without_echoing_the_token(monkeypatch, capsys, message, expected):
    secret = "SECRET-TOKEN-MATERIAL"
    fake, _ = _verifier(error=ValueError(f"{message} [{secret}]"))
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    with pytest.raises(HTTPException):
        deps.verify_token("tok")

    logged = capsys.readouterr().out
    assert f"Token rejected ({expected})" in logged
    assert secret not in logged
