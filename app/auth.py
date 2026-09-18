import base64
import json

import streamlit as st


def _decode_jwt_payload(token: str) -> dict:
    """Decode a JWT's payload without verifying its signature.

    Cloud Run already verified this token's signature (and the caller's
    roles/run.invoker membership) before forwarding the request here — we
    only need to read the claims, not re-authenticate.
    """
    payload_segment = token.split(".")[1]
    padded = payload_segment + "=" * (-len(payload_segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def get_current_user_email() -> str | None:
    """Return the caller's email from the ID token Cloud Run forwards.

    Returns None when running outside Cloud Run's IAM auth (e.g. local
    docker compose), where no such header is present.
    """
    auth_header = st.context.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.removeprefix("Bearer ")
    try:
        claims = _decode_jwt_payload(token)
    except (IndexError, ValueError):
        return None

    return claims.get("email")
