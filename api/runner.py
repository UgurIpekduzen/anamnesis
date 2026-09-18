from functools import lru_cache

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from agent.agent import build_agent


@lru_cache
def get_runner(owner_uid: str) -> Runner:
    # Cached per owner_uid so each user gets one Runner wrapping an Agent
    # whose tools are already scoped to them (see agent/agent.py) — same
    # reasoning as app/runner.py's Streamlit equivalent.
    return Runner(
        agent=build_agent(owner_uid),
        app_name="anamnesis",
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )
