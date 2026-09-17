import streamlit as st
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from agent.agent import build_agent


@st.cache_resource
def get_runner(owner_uid: str) -> Runner:
    # Cached per owner_uid (st.cache_resource keys on its arguments), so
    # each user gets their own Runner wrapping an Agent whose tools are
    # already scoped to them (see agent/agent.py) — sharing one Runner
    # across all users would mean sharing one owner_uid too.
    #
    # InMemorySessionService is fine here: Streamlit's own session_state
    # already ties a runner instance to one browser session, and we don't
    # need conversation history to survive a server restart.
    return Runner(
        agent=build_agent(owner_uid),
        app_name="anamnesis",
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )
