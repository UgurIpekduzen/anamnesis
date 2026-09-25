import pytest
from fastapi import HTTPException

import api.deps as deps


@pytest.fixture(autouse=True)
def no_extra_allowed_emails(monkeypatch):
    # verify_token also consults the runtime allowlist in Firestore
    # (APPCE-94) for any email outside the Terraform-configured owners —
    # a unit test mustn't reach real Firestore for that.
    monkeypatch.setattr(deps, "get_extra_allowed_emails", lambda: set())


def _verifier(claims=None, error=None):
    seen = {}

    def fake(token, request, audience, clock_skew_in_seconds):
        seen.update(token=token, audience=audience, skew=clock_skew_in_seconds)
        if error:
            raise error
        return claims

    return fake, seen


def test_a_valid_allowlisted_token_returns_its_email(monkeypatch):
    fake, seen = _verifier(claims={"email": "test@example.com", "email_verified": True})
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    assert deps.verify_token("tok") == "test@example.com"
    assert seen["audience"] == "test-client-id"


def test_verification_allows_a_small_clock_skew(monkeypatch):
    fake, seen = _verifier(claims={"email": "test@example.com", "email_verified": True})
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    deps.verify_token("tok")

    assert seen["skew"] == deps.CLOCK_SKEW_SECONDS > 0


def test_a_valid_token_for_an_account_off_the_allowlist_is_forbidden(monkeypatch):
    fake, _ = _verifier(claims={"email": "stranger@example.com", "email_verified": True})
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    with pytest.raises(HTTPException) as excinfo:
        deps.verify_token("tok")
    assert excinfo.value.status_code == 403


@pytest.mark.parametrize("verified", [False, "false", None, "true"])
def test_an_allowlisted_email_that_is_not_verified_is_forbidden(monkeypatch, verified):
    claims = {"email": "test@example.com"}
    if verified is not None:
        claims["email_verified"] = verified
    fake, _ = _verifier(claims=claims)
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
def test_the_rejection_log_names_the_reason_without_echoing_the_token(monkeypatch, capsys, message, expected, log_lines):
    secret = "SECRET-TOKEN-MATERIAL"
    fake, _ = _verifier(error=ValueError(f"{message} [{secret}]"))
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    with pytest.raises(HTTPException):
        deps.verify_token("tok")

    logged = capsys.readouterr().out
    (entry,) = log_lines(logged)
    assert (entry["severity"], entry["event"], entry["reason"]) == ("WARNING", "token_rejected", expected)
    assert secret not in logged


class FakeResponse:
    def __init__(self, status=200, headers=None):
        self.status = status
        self.headers = headers or {}
        self.data = b"{}"


class FakeTransport:
    def __init__(self, **response_kwargs):
        self.calls = []
        self.response_kwargs = response_kwargs

    def __call__(self, url, method="GET", body=None, headers=None, **kwargs):
        self.calls.append((url, method))
        return FakeResponse(**self.response_kwargs)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _cache(**response_kwargs):
    transport, clock = FakeTransport(**response_kwargs), Clock()
    return deps.CachedCertsRequest(transport, clock), transport, clock


def test_certificates_are_fetched_once_and_then_served_from_the_cache():
    request, transport, _ = _cache()

    first = request("https://certs")
    second = request("https://certs")

    assert first is second
    assert len(transport.calls) == 1


def test_the_cache_honours_the_servers_max_age_then_refetches():
    request, transport, clock = _cache(headers={"cache-control": "public, max-age=120"})

    request("https://certs")
    clock.now += 119
    request("https://certs")
    assert len(transport.calls) == 1

    clock.now += 2
    request("https://certs")
    assert len(transport.calls) == 2


def test_an_absurd_max_age_is_capped():
    request, transport, clock = _cache(headers={"cache-control": "max-age=99999999"})

    request("https://certs")
    clock.now += deps._CERTS_MAX_AGE_CAP_SECONDS + 1
    request("https://certs")

    assert len(transport.calls) == 2


def test_a_failed_fetch_is_not_cached():
    request, transport, _ = _cache(status=500)

    request("https://certs")
    request("https://certs")

    assert len(transport.calls) == 2


def test_different_urls_are_cached_separately():
    request, transport, _ = _cache()

    request("https://certs-a")
    request("https://certs-b")

    assert len(transport.calls) == 2


def test_a_forced_refresh_is_refused_while_the_cache_is_fresh():
    request, transport, clock = _cache()
    request("https://certs")

    assert request.drop_if_older_than(deps._CERTS_MIN_REFRESH_SECONDS) is False
    request("https://certs")
    assert len(transport.calls) == 1

    clock.now += deps._CERTS_MIN_REFRESH_SECONDS + 1
    assert request.drop_if_older_than(deps._CERTS_MIN_REFRESH_SECONDS) is True
    request("https://certs")
    assert len(transport.calls) == 2


def test_an_unknown_key_id_triggers_one_refetch_when_the_cache_is_old_enough(monkeypatch):
    request, transport, clock = _cache()
    monkeypatch.setattr(deps, "_request", request)
    request("https://certs")
    clock.now += deps._CERTS_MIN_REFRESH_SECONDS + 1

    attempts = []

    def fake(token, request_, audience, clock_skew_in_seconds):
        attempts.append(1)
        if len(attempts) == 1:
            raise ValueError("Certificate for key id abc not found.")
        return {"email": "test@example.com", "email_verified": True}

    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    assert deps.verify_token("tok") == "test@example.com"
    assert len(attempts) == 2


def test_an_unknown_key_id_is_not_retried_when_the_cache_is_fresh(monkeypatch):
    request, _, _ = _cache()
    monkeypatch.setattr(deps, "_request", request)
    request("https://certs")

    attempts = []

    def fake(token, request_, audience, clock_skew_in_seconds):
        attempts.append(1)
        raise ValueError("Certificate for key id abc not found.")

    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    with pytest.raises(HTTPException) as excinfo:
        deps.verify_token("tok")
    assert excinfo.value.status_code == 401
    assert len(attempts) == 1


def test_a_runtime_allowed_email_outside_the_owners_is_accepted(monkeypatch):
    fake, _ = _verifier(claims={"email": "invited@example.com", "email_verified": True})
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)
    monkeypatch.setattr(deps, "get_extra_allowed_emails", lambda: {"invited@example.com"})

    assert deps.verify_token("tok") == "invited@example.com"
