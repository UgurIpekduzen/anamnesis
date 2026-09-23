import streamlit as st
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from agent.agent import build_agent


@st.cache_resource
def get_runner(owner_uid: str, tenant_id: str) -> Runner:
    # Cached per (owner_uid, tenant_id) (st.cache_resource keys on its
    # arguments), so each project's chat gets its own Runner wrapping an
    # Agent whose tools are already scoped to just that project (see
    # agent/agent.py) — switching the tenant selectbox naturally builds
    # (and then reuses) a different cached Runner.
    #
    # InMemorySessionService is fine here: Streamlit's own session_state
    # already ties a runner instance to one browser session, and we don't
    # need conversation history to survive a server restart.
    return Runner(
        agent=build_agent(owner_uid, tenant_id),
        app_name="anamnesis",
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )
