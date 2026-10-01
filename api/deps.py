"""FastAPI auth dependencies: verify a caller's Google ID token against
Google's public keys and this app's allowlist, and expose the verified
email as owner_uid to route handlers."""

import os
import re
import threading
import time

from fastapi import Depends, Header, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from src.accounts.allowed_emails import OWNER_EMAILS, get_extra_allowed_emails
from src.core.log import log

_CLIENT_ID = os.environ["GOOGLE_OAUTH_CLIENT_ID"]

# Google rotates its signing keys rarely and publishes them with a
# Cache-Control max-age, but google-auth refetches the certificates on every
# verification (~140 ms, and it blocks whoever is waiting). Keep them for as
# long as Google says, within sane bounds.
_CERTS_MAX_AGE_DEFAULT_SECONDS = 300
_CERTS_MAX_AGE_CAP_SECONDS = 3600
# A token naming a key we don't have may mean a rotation, so refetch once —
# but never more often than this, or a stream of made-up key ids would turn
# every request into a certificate fetch.
_CERTS_MIN_REFRESH_SECONDS = 60
_KEY_NOT_FOUND = "not found"


class CachedCertsRequest:
    """A google-auth transport that remembers successful GET responses.

    Only the certificate downloads go through it, so caching every 200 GET
    by URL is enough. Thread-safe: verify_token runs in worker threads.
    """

    def __init__(self, inner=None, clock=time.monotonic):
        """Wrap a transport (or build a default one) with an empty cache.

        Args:
            inner (unannotated): The transport to delegate actual requests
                to; defaults to a fresh google.auth Request.
            clock (unannotated): Time source used to judge cache freshness;
                overridable so tests can control expiry without sleeping.
        """
        self._inner = inner or google_requests.Request()
        self._clock = clock
        self._lock = threading.Lock()
        self._entries = {}  # url -> (response, fetched_at, expires_at)

    def __call__(self, url, method="GET", body=None, headers=None, **kwargs):
        """Serve a cached GET response if it hasn't expired, else fetch and cache it.

        Any method other than GET is passed straight through to the inner
        transport, uncached.

        Args:
            url (unannotated): The URL to request; also the cache key for
                GET responses.
            method (unannotated): The HTTP method; only "GET" responses are
                cached, anything else is passed straight through.
            body (unannotated): The request body, passed through to the
                inner transport.
            headers (unannotated): The request headers, passed through to
                the inner transport.
        """
        if method != "GET":
            return self._inner(url, method=method, body=body, headers=headers, **kwargs)

        now = self._clock()
        with self._lock:
            entry = self._entries.get(url)
        if entry and now < entry[2]:
            return entry[0]

        response = self._inner(url, method=method, body=body, headers=headers, **kwargs)
        if response.status == 200:
            with self._lock:
                self._entries[url] = (response, now, now + self._max_age(response))
        return response

    @staticmethod
    def _max_age(response) -> int:
        match = re.search(
            r"max-age=(\d+)", (response.headers or {}).get("cache-control", ""), re.IGNORECASE
        )
        seconds = int(match.group(1)) if match else _CERTS_MAX_AGE_DEFAULT_SECONDS
        return min(seconds, _CERTS_MAX_AGE_CAP_SECONDS)

    def drop_if_older_than(self, seconds: float) -> bool:
        """Forget cached responses fetched more than `seconds` ago.

        Returns whether anything was dropped, i.e. whether a retry can see
        fresher data than the attempt that just failed.

        Args:
            seconds (float): The age threshold, in seconds — entries
                fetched at or before this many seconds ago are dropped.
        """
        cutoff = self._clock() - seconds
        with self._lock:
            stale = [
                url for url, (_, fetched_at, _) in self._entries.items() if fetched_at <= cutoff
            ]
            for url in stale:
                del self._entries[url]
        return bool(stale)


_request = CachedCertsRequest()

# A token's iat/exp are checked against this host's clock, and a clock that
# lags Google's by even a second rejects a token issued moments ago ("Token
# used too early"). WSL2 clocks in particular drift behind after the host
# sleeps. A small allowance costs nothing security-wise — it only widens the
# iat/exp windows by this much.
CLOCK_SKEW_SECONDS = 10

_REASON_KEYWORDS = (
    "too early",
    "expired",
    "wrong recipient",
    "audience",
    "signature",
    "segments",
    "key id",
)


def _rejection_reason(exc: Exception) -> str:
    # google-auth's messages can echo (part of) the token itself, so log a
    # coarse category instead of the text.
    text = str(exc).lower()
    return next((keyword for keyword in _REASON_KEYWORDS if keyword in text), "other")


def verify_token(token: str) -> str:
    """Verify a Google ID token's signature and return its email claim.

    Cloud Run's IAM layer no longer does this for us once the service is
    public — we verify against Google's own public keys
    and check the audience matches our OAuth client, then enforce the
    allowlist ourselves (replacing the Google Group membership check).

    Args:
        token (str): The bearer token's raw JWT, as sent in the
            Authorization header (without the "Bearer " prefix).
    """

    def verify():
        """Call Google's verifier with this module's client id and clock skew allowance."""
        return id_token.verify_oauth2_token(
            token, _request, _CLIENT_ID, clock_skew_in_seconds=CLOCK_SKEW_SECONDS
        )

    try:
        try:
            claims = verify()
        except ValueError as exc:
            # An unknown key id can mean Google rotated its keys since we
            # cached them — refetch once, at most once a minute.
            if _KEY_NOT_FOUND in str(exc) and _request.drop_if_older_than(
                _CERTS_MIN_REFRESH_SECONDS
            ):
                claims = verify()
            else:
                raise
    except ValueError as exc:
        log("WARNING", "token_rejected", reason=_rejection_reason(exc))
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

    # Anyone can put an address they don't control in a Google Workspace or
    # third-party-linked account; only a verified one proves ownership. The
    # allowlist is editable at runtime, so this check matters.
    # Compared with `is not True` so a missing or string "false" claim fails.
    if claims.get("email_verified") is not True:
        raise HTTPException(status_code=403, detail="This account's email isn't verified")

    # Identity stays the email rather than the immutable `sub` claim:
    # every Firestore document is keyed by it, so switching needs
    # a data migration. Deliberate for personal scale, where the allowlist is
    # curated by hand and a reassigned address is an unlikely risk.
    email = claims.get("email")
    if not email or (email not in OWNER_EMAILS and email not in get_extra_allowed_emails()):
        raise HTTPException(status_code=403, detail="This account isn't authorized")
    return email


def get_current_owner_uid(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: verify the caller's bearer token and return their email.

    Args:
        authorization (str | None): The raw Authorization header value,
            expected as "Bearer <token>"; None if the header was absent.

    Raises:
        HTTPException: 401 if the Authorization header is missing or isn't
            a bearer token (verify_token raises its own 401/403 for a
            token that's invalid or not on the allowlist).
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return verify_token(authorization[len("Bearer ") :])


def require_owner(owner_uid: str = Depends(get_current_owner_uid)) -> str:
    """Like get_current_owner_uid, but only for the Terraform-configured
    owner(s) — gates managing who else is allowed in, since
    letting any allowed user grant access to others would defeat the
    allowlist entirely.
    """
    if owner_uid not in OWNER_EMAILS:
        raise HTTPException(status_code=403, detail="Owner access required")
    return owner_uid
