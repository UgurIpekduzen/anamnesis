from fastapi import Header, HTTPException


def get_current_owner_uid(x_owner_uid: str | None = Header(default=None)) -> str:
    """Return the caller's owner_uid.

    TEMPORARY (APPCE-53 scaffolding): trusts a client-supplied header
    with no verification. This is only acceptable because the API isn't
    exposed publicly yet — APPCE-54 replaces this with real Google
    Sign-In token verification before Cloud Run's IAM restriction comes
    off. Do not deploy this behind a public endpoint as-is.
    """
    if not x_owner_uid:
        raise HTTPException(status_code=401, detail="Missing X-Owner-Uid header")
    return x_owner_uid
