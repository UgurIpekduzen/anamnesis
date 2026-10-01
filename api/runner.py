"""Builds and caches the per-(owner, project) ADK Runner that the chat
WebSocket endpoint (api/routers/chat.py) drives."""

from functools import lru_cache

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from agent.agent import build_agent


@lru_cache
def get_runner(owner_uid: str, tenant_id: str) -> Runner:
    """Return the cached Runner for this owner and project, building one on first use.

    Args:
        owner_uid (str): The signed-in user's identity.
        tenant_id (str): The project this Runner's agent is scoped to.
    """
    # Cached per (owner_uid, tenant_id) so each project's chat gets its own
    # Runner wrapping an Agent whose tools are already scoped to just that
    # project (see agent/agent.py) — full isolation, not just per-user.
    return Runner(
        agent=build_agent(owner_uid, tenant_id),
        app_name="anamnesis",
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )
