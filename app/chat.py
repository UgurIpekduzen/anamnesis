import streamlit as st
from google.adk.runners import Runner
from google.genai import types


def ask(runner: Runner, tenant: dict) -> None:
    question = st.text_input("Ask or record something")

    if st.button("Send") and question:
        message = types.Content(
            role="user",
            parts=[types.Part(text=f"[Project: {tenant['name']}] {question}")],
        )

        events = list(
            runner.run(
                user_id="streamlit_user",
                session_id=f"session_{tenant['tenant_id']}",
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
