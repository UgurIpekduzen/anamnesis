"""Tests for trimming ADK conversation history to a bounded number of turns."""

from types import SimpleNamespace

from google.genai import types

from agent.history import make_history_limiter, trim_to_last_turns


def _user(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part(text=text)])


def _model(text: str) -> types.Content:
    return types.Content(role="model", parts=[types.Part(text=text)])


def _tool_call(name: str) -> types.Content:
    return types.Content(
        role="model",
        parts=[types.Part(function_call=types.FunctionCall(name=name, args={}))],
    )


def _tool_result(name: str) -> types.Content:
    return types.Content(
        role="user",
        parts=[
            types.Part(function_response=types.FunctionResponse(name=name, response={"result": []}))
        ],
    )


def test_returns_history_unchanged_when_under_the_limit():
    """Content is returned unchanged when it has fewer user turns than the limit."""
    contents = [_user("one"), _model("a"), _user("two"), _model("b")]
    assert trim_to_last_turns(contents, max_turns=5) == contents


def test_keeps_only_the_last_n_user_turns():
    """Only the last `max_turns` user turns and their replies are kept."""
    contents = [_user("one"), _model("a"), _user("two"), _model("b"), _user("three"), _model("c")]
    trimmed = trim_to_last_turns(contents, max_turns=2)
    assert [c.parts[0].text for c in trimmed] == ["two", "b", "three", "c"]


def test_never_splits_a_tool_call_from_its_result():
    """The turn cut is pushed earlier when a naive cut would separate a tool call from its result."""
    contents = [
        _user("old question"),
        _model("old answer"),
        _user("question with tools"),
        _tool_call("list_tenants"),
        _tool_result("list_tenants"),
        _model("answer using tools"),
        _user("latest question"),
    ]
    trimmed = trim_to_last_turns(contents, max_turns=2)

    # Cut lands on the user turn that started the tool loop, so both
    # halves of the function_call/function_response pair survive.
    assert trimmed[0].parts[0].text == "question with tools"
    assert trimmed[1].parts[0].function_call is not None
    assert trimmed[2].parts[0].function_response is not None


def test_a_tool_result_is_not_counted_as_a_user_turn():
    """A function_response turn doesn't count toward the user-turn limit, so the cut still lands on the preceding real user turn."""
    contents = [
        _user("first"),
        _tool_call("get_tenant_facts"),
        _tool_result("get_tenant_facts"),
        _model("done"),
        _user("second"),
    ]
    trimmed = trim_to_last_turns(contents, max_turns=1)
    assert [c.parts[0].text for c in trimmed] == ["second"]


def test_returns_history_unchanged_when_there_are_no_user_turns():
    """Content with no user turns at all is returned unchanged."""
    contents = [_model("orphan")]
    assert trim_to_last_turns(contents, max_turns=1) == contents


def test_the_limiter_applies_the_shared_window_from_settings(monkeypatch):
    """The callback built by make_history_limiter trims the request's contents in place using the configured history_turns window."""
    monkeypatch.setattr("agent.history.get_settings", lambda: {"history_turns": 1})
    request = SimpleNamespace(contents=[_user("one"), _model("a"), _user("two")])

    make_history_limiter()(None, request)

    assert [c.parts[0].text for c in request.contents] == ["two"]


def test_the_limiter_picks_up_a_changed_setting_without_being_rebuilt(monkeypatch):
    """A single limiter instance re-reads history_turns on every call, so a later setting change takes effect without rebuilding it."""
    current = {"history_turns": 1}
    monkeypatch.setattr("agent.history.get_settings", lambda: dict(current))
    limiter = make_history_limiter()
    contents = [_user("one"), _model("a"), _user("two")]

    first = SimpleNamespace(contents=list(contents))
    limiter(None, first)
    assert len(first.contents) == 1

    current["history_turns"] = 5
    second = SimpleNamespace(contents=list(contents))
    limiter(None, second)
    assert len(second.contents) == 3
