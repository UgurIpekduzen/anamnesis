import os

from fastapi import Header, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

_CLIENT_ID = os.environ["GOOGLE_OAUTH_CLIENT_ID"]
_ALLOWED_EMAILS = {e.strip() for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()}
_request = google_requests.Request()

# A token's iat/exp are checked against this host's clock, and a clock that
# lags Google's by even a second rejects a token issued moments ago ("Token
# used too early"). WSL2 clocks in particular drift behind after the host
# sleeps. A small allowance costs nothing security-wise — it only widens the
# iat/exp windows by this much.
CLOCK_SKEW_SECONDS = 10

_REASON_KEYWORDS = ("too early", "expired", "wrong recipient", "audience", "signature", "segments")


def _rejection_reason(exc: Exception) -> str:
    # google-auth's messages can echo (part of) the token itself, so log a
    # coarse category instead of the text.
    text = str(exc).lower()
    return next((keyword for keyword in _REASON_KEYWORDS if keyword in text), "other")


def verify_token(token: str) -> str:
    """Verify a Google ID token's signature and return its email claim.

    Cloud Run's IAM layer no longer does this for us once the service is
    public (see APPCE-54) — we verify against Google's own public keys
    and check the audience matches our OAuth client, then enforce the
    allowlist ourselves (replacing the Google Group membership check).
    """
    try:
        claims = id_token.verify_oauth2_token(
            token, _request, _CLIENT_ID, clock_skew_in_seconds=CLOCK_SKEW_SECONDS
        )
    except ValueError as exc:
        print(f"Token rejected ({_rejection_reason(exc)})")
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

    email = claims.get("email")
    if not email or email not in _ALLOWED_EMAILS:
        raise HTTPException(status_code=403, detail="This account isn't authorized")
    return email


def get_current_owner_uid(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return verify_token(authorization[len("Bearer "):])
