"""Tests for token verification and Google certificate caching in api.deps."""

import pytest
from fastapi import HTTPException

import api.deps as deps


@pytest.fixture(autouse=True)
def no_extra_allowed_emails(monkeypatch):
    """Stub the runtime Firestore allowlist to an empty set so unit tests
    never need real Firestore access."""
    # verify_token also consults the runtime allowlist in Firestore
    # (APPCE-94) for any email outside the Terraform-configured owners —
    # a unit test mustn't reach real Firestore for that.
    monkeypatch.setattr(deps, "get_extra_allowed_emails", lambda: set())


def _verifier(claims=None, error=None):
    seen = {}

    def fake(token, request, audience, clock_skew_in_seconds):
        """Record the call's arguments, then return the given claims or raise the given error."""
        seen.update(token=token, audience=audience, skew=clock_skew_in_seconds)
        if error:
            raise error
        return claims

    return fake, seen


def test_a_valid_allowlisted_token_returns_its_email(monkeypatch):
    """A verified token for an allowlisted email returns that email, passing the configured client id as audience."""
    fake, seen = _verifier(claims={"email": "test@example.com", "email_verified": True})
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    assert deps.verify_token("tok") == "test@example.com"
    assert seen["audience"] == "test-client-id"


def test_verification_allows_a_small_clock_skew(monkeypatch):
    """Token verification is called with the configured positive clock skew tolerance."""
    fake, seen = _verifier(claims={"email": "test@example.com", "email_verified": True})
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    deps.verify_token("tok")

    assert seen["skew"] == deps.CLOCK_SKEW_SECONDS > 0


def test_a_valid_token_for_an_account_off_the_allowlist_is_forbidden(monkeypatch):
    """A valid token for an email outside the allowlist is rejected with 403."""
    fake, _ = _verifier(claims={"email": "stranger@example.com", "email_verified": True})
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    with pytest.raises(HTTPException) as excinfo:
        deps.verify_token("tok")
    assert excinfo.value.status_code == 403


@pytest.mark.parametrize("verified", [False, "false", None, "true"])
def test_an_allowlisted_email_that_is_not_verified_is_forbidden(monkeypatch, verified):
    """An allowlisted email is rejected with 403 unless email_verified is the boolean True."""
    claims = {"email": "test@example.com"}
    if verified is not None:
        claims["email_verified"] = verified
    fake, _ = _verifier(claims=claims)
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    with pytest.raises(HTTPException) as excinfo:
        deps.verify_token("tok")
    assert excinfo.value.status_code == 403


def test_a_token_google_rejects_is_a_401(monkeypatch):
    """A token that Google's verifier raises ValueError on is rejected with 401."""
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
    """A rejected token logs a WARNING with the classified reason, without leaking the token's own contents."""
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
    """A stand-in for the HTTP response returned by the certs transport."""

    def __init__(self, status=200, headers=None):
        """Store the given status and headers, with an empty JSON body."""
        self.status = status
        self.headers = headers or {}
        self.data = b"{}"


class FakeTransport:
    """A stand-in transport that records each call and always returns a configured FakeResponse."""

    def __init__(self, **response_kwargs):
        """Store the keyword arguments used to build the FakeResponse returned on every call."""
        self.calls = []
        self.response_kwargs = response_kwargs

    def __call__(self, url, method="GET", body=None, headers=None, **kwargs):
        """Record the requested url and method, then return the configured FakeResponse."""
        self.calls.append((url, method))
        return FakeResponse(**self.response_kwargs)


class Clock:
    """A manually advanceable fake clock, callable to read the current time."""

    def __init__(self):
        """Start the clock at a fixed timestamp."""
        self.now = 1000.0

    def __call__(self):
        """Return the current fake time."""
        return self.now


def _cache(**response_kwargs):
    transport, clock = FakeTransport(**response_kwargs), Clock()
    return deps.CachedCertsRequest(transport, clock), transport, clock


def test_certificates_are_fetched_once_and_then_served_from_the_cache():
    """A second request for the same URL is served from the cache instead of refetching."""
    request, transport, _ = _cache()

    first = request("https://certs")
    second = request("https://certs")

    assert first is second
    assert len(transport.calls) == 1


def test_the_cache_honours_the_servers_max_age_then_refetches():
    """The cache serves a cached response until the server's max-age elapses, then refetches."""
    request, transport, clock = _cache(headers={"cache-control": "public, max-age=120"})

    request("https://certs")
    clock.now += 119
    request("https://certs")
    assert len(transport.calls) == 1

    clock.now += 2
    request("https://certs")
    assert len(transport.calls) == 2


def test_an_absurd_max_age_is_capped():
    """A server-supplied max-age far beyond the cap is clamped, so the cache still expires and refetches."""
    request, transport, clock = _cache(headers={"cache-control": "max-age=99999999"})

    request("https://certs")
    clock.now += deps._CERTS_MAX_AGE_CAP_SECONDS + 1
    request("https://certs")

    assert len(transport.calls) == 2


def test_a_failed_fetch_is_not_cached():
    """A non-200 response is not cached, so the next request fetches again."""
    request, transport, _ = _cache(status=500)

    request("https://certs")
    request("https://certs")

    assert len(transport.calls) == 2


def test_different_urls_are_cached_separately():
    """Two different certificate URLs are each fetched and cached independently."""
    request, transport, _ = _cache()

    request("https://certs-a")
    request("https://certs-b")

    assert len(transport.calls) == 2


def test_a_forced_refresh_is_refused_while_the_cache_is_fresh():
    """drop_if_older_than refuses to drop a cache entry younger than the given age, then allows it once it's old enough."""
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
    """An unrecognized key id triggers exactly one certificate refetch and retry once the cache is old enough to drop."""
    request, transport, clock = _cache()
    monkeypatch.setattr(deps, "_request", request)
    request("https://certs")
    clock.now += deps._CERTS_MIN_REFRESH_SECONDS + 1

    attempts = []

    def fake(token, request_, audience, clock_skew_in_seconds):
        """Fail with an unknown-key-id error on the first call, then succeed."""
        attempts.append(1)
        if len(attempts) == 1:
            raise ValueError("Certificate for key id abc not found.")
        return {"email": "test@example.com", "email_verified": True}

    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    assert deps.verify_token("tok") == "test@example.com"
    assert len(attempts) == 2


def test_an_unknown_key_id_is_not_retried_when_the_cache_is_fresh(monkeypatch):
    """An unrecognized key id is not retried, and fails with 401, while the certificate cache is still fresh."""
    request, _, _ = _cache()
    monkeypatch.setattr(deps, "_request", request)
    request("https://certs")

    attempts = []

    def fake(token, request_, audience, clock_skew_in_seconds):
        """Always fail with an unknown-key-id error."""
        attempts.append(1)
        raise ValueError("Certificate for key id abc not found.")

    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)

    with pytest.raises(HTTPException) as excinfo:
        deps.verify_token("tok")
    assert excinfo.value.status_code == 401
    assert len(attempts) == 1


def test_a_runtime_allowed_email_outside_the_owners_is_accepted(monkeypatch):
    """An email not in the Terraform-configured owners is still accepted when it's in the runtime allowlist."""
    fake, _ = _verifier(claims={"email": "invited@example.com", "email_verified": True})
    monkeypatch.setattr(deps.id_token, "verify_oauth2_token", fake)
    monkeypatch.setattr(deps, "get_extra_allowed_emails", lambda: {"invited@example.com"})

    assert deps.verify_token("tok") == "invited@example.com"
