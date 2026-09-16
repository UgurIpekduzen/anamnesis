import streamlit as st
from google.adk.runners import Runner
from google.genai import types


def _history_for(tenant_id: str) -> list[dict]:
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = {}
    return st.session_state.chat_history.setdefault(tenant_id, [])


def _render_message(role: str, content: str) -> None:
    with st.chat_message(role):
        st.write(content)


def _build_trace(events) -> list[dict]:
    trace: list[dict] = []
    for event in events:
        for call in event.get_function_calls():
            trace.append({"name": call.name, "args": call.args, "response": None})
        for response in event.get_function_responses():
            # Match against the most recent unresolved call with the same
            # name — calls/responses interleave across events rather than
            # arriving as neat 1:1 pairs within a single event.
            for entry in reversed(trace):
                if entry["name"] == response.name and entry["response"] is None:
                    entry["response"] = response.response
                    break
    return trace


def _render_args(args) -> None:
    if not isinstance(args, dict) or not args:
        st.caption("No arguments")
        return
    if all(not isinstance(value, (dict, list)) for value in args.values()):
        rows = [{"Argument": key, "Value": value} for key, value in args.items()]
        st.dataframe(rows, hide_index=True, use_container_width=True)
        return
    st.json(args)


def _render_result(response) -> None:
    if response is None:
        st.caption("No result")
        return
    if isinstance(response, dict) and "result" in response:
        value = response["result"]
        # Most tool responses here are {"result": [...]} — when that list
        # holds uniform dicts (list_tenants, get_tenant_facts, ...), a
        # table is far more scannable than a nested JSON tree.
        if isinstance(value, list):
            if not value:
                st.caption("Empty result")
                return
            if all(isinstance(row, dict) for row in value):
                st.dataframe(value, hide_index=True, use_container_width=True)
                return
        # A single plain value is usually an opaque id (publish_fact's
        # message id, a tenant_id) rather than something meant to be
        # read — lead with a plain confirmation and keep the raw value
        # available underneath, de-emphasized, instead of front and
        # center as a bare number.
        elif value is None or isinstance(value, (str, int, float, bool)):
            st.write("✅ Success")
            if value is not None:
                st.caption(str(value))
            return
    st.json(response)


def _render_trace_body(trace: list[dict] | None) -> None:
    if not trace:
        st.caption("No tool calls for the latest response.")
        return

    tool_names = list(dict.fromkeys(entry["name"] for entry in trace))

    if "selected_tool" not in st.session_state or st.session_state.selected_tool not in tool_names:
        st.session_state.selected_tool = tool_names[-1]

    st.radio(
        "Tool",
        tool_names,
        key="selected_tool",
        horizontal=True,
        label_visibility="collapsed",
    )

    for entry in trace:
        if entry["name"] != st.session_state.selected_tool:
            continue
        st.markdown("**Arguments**")
        _render_args(entry["args"])
        st.markdown("**Result**")
        _render_result(entry["response"])


def ask(runner: Runner, tenant: dict, trace_container) -> None:
    history = _history_for(tenant["tenant_id"])

    for turn in history:
        _render_message(turn["role"], turn["content"])

    question = st.chat_input("Ask or record something")
    if not question:
        # No new question this run (initial load, tenant switch, etc.) —
        # just show the most recent response's trace, since the live
        # per-event rendering below only happens while actually
        # processing a question.
        last_trace = next(
            (turn.get("trace") for turn in reversed(history) if turn.get("trace") is not None),
            None,
        )
        with trace_container:
            _render_trace_body(last_trace)
        return

    history.append({"role": "user", "content": question})
    _render_message("user", question)

    message = types.Content(
        role="user",
        parts=[types.Part(text=f"[Project: {tenant['name']}] {question}")],
    )

    live_trace = trace_container.empty()
    events = []
    try:
        with st.spinner("Thinking..."):
            for event in runner.run(
                user_id="streamlit_user",
                session_id=f"session_{tenant['tenant_id']}",
                new_message=message,
            ):
                events.append(event)
                # Redraw the trace tab after every event instead of only
                # once at the end, so tool calls appear one by one as
                # the agent actually makes them.
                tool_names_so_far = list(
                    dict.fromkeys(entry["name"] for entry in _build_trace(events))
                )
                with live_trace.container():
                    if tool_names_so_far:
                        for name in tool_names_so_far:
                            st.write(f"🔧 {name}")
                    else:
                        st.caption("No tool calls yet.")
    except Exception as exc:
        # Surface a friendly message to the user, but keep the real
        # exception in server logs (Cloud Run captures stdout) so it's
        # still debuggable — a bare traceback in the UI helps no one here.
        print(f"Agent call failed: {exc!r}")
        answer = "Something went wrong while talking to the agent. Please try again."
        history.append({"role": "assistant", "content": answer})
        _render_message("assistant", answer)
        return

    trace = _build_trace(events)
    final_events = [e for e in events if e.is_final_response()]
    answer = final_events[-1].content.parts[0].text if final_events else "(no response)"

    history.append({"role": "assistant", "content": answer, "trace": trace})
    _render_message("assistant", answer)

    with live_trace.container():
        _render_trace_body(trace)
