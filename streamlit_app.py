import streamlit as st
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent.agent import root_agent
from src.tenants import list_tenants

st.set_page_config(page_title="Anamnesis")
st.title("Anamnesis")
st.caption("Personal Project Context Engine")


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


runner = get_runner()

tenants = list_tenants()
if not tenants:
    st.warning("No projects found. Run seed_data.py first.")
    st.stop()

tenant_names = [t["name"] for t in tenants]
selected_name = st.selectbox("Project", tenant_names)
selected_tenant = next(t for t in tenants if t["name"] == selected_name)

question = st.text_input("Ask or record something")

if st.button("Send") and question:
    message = types.Content(
        role="user",
        parts=[types.Part(text=f"[Project: {selected_tenant['name']}] {question}")],
    )

    events = list(
        runner.run(
            user_id="streamlit_user",
            session_id=f"session_{selected_tenant['tenant_id']}",
            new_message=message,
        )
    )

    with st.expander("Agent trace", expanded=True):
        for event in events:
            for call in event.get_function_calls():
                st.write(f"🔧 **{call.name}**", call.args)
            for response in event.get_function_responses():
                st.write(f"✅ **{response.name}** returned", response.response)

    final_events = [e for e in events if e.is_final_response()]
    if final_events:
        st.markdown("### Answer")
        st.write(final_events[-1].content.parts[0].text)
