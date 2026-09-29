"""Liveness and the scheduler's entry point: the two routes that no signed-in
user calls."""

from fastapi import APIRouter, Depends

from api.internal_auth import verify_scheduler_token

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


def poll_all_tenants() -> dict:
    # Deferred: pulls in the GitHub fact-extraction LLM call chain, which
    # only /internal/poll-github needs — same reasoning as the lazy
    # ADK/Pub-Sub imports elsewhere in the API. A real
    # module-level name (not a local import inside the endpoint) so tests
    # can monkeypatch.setattr(internal, "poll_all_tenants", ...).
    from src.integrations.github.polling import poll_all_tenants as _poll_all_tenants

    return _poll_all_tenants()


@router.post("/internal/poll-github")
def poll_github(_: None = Depends(verify_scheduler_token)) -> dict:
    return poll_all_tenants()
