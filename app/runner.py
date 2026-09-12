import streamlit as st
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from agent.agent import root_agent


@st.cache_resource
def get_runner() -> Runner:
    # InMemorySessionService is fine here: Streamlit's own session_state
    # already ties a runner instance to one browser session, and we don't
    # need conversation history to survive a server restart.
    return Runner(
        agent=root_agent,
        app_name="anamnesis",
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )
