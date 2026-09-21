import os
import re
from contextlib import contextmanager
import threading
import time
from types import SimpleNamespace

# api.deps reads these at import time.
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("ALLOWED_EMAILS", "test@example.com")

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

import api.main as api_main  # noqa: E402

OWNER = "test@example.com"
WS_URL = "/ws/chat/some_tenant"


class FakeEvent:
    def __init__(self, text):
        self.content = SimpleNamespace(parts=[SimpleNamespace(text=text)])

    def get_function_calls(self):
        return []

    def get_function_responses(self):
        return []

    def is_final_response(self):
        return True


class FakeSessionService:
    def __init__(self):
        self.deleted = []

    async def delete_session(self, *, app_name, user_id, session_id):
        self.deleted.append((app_name, user_id, session_id))


class FakeRunner:
    app_name = "anamnesis"

    def __init__(self):
        self.calls = []
        self.fail = False
        self.silent = False  # runs to completion without ever producing an answer
        self.session_service = FakeSessionService()

    def run(self, *, user_id, session_id, new_message, run_config):
        self.calls.append(
            {
                "session_id": session_id,
                "run_config": run_config,
                "text": new_message.parts[0].text,
            }
        )
        if self.fail:
            raise RuntimeError("boom")
        if not self.silent:
            yield FakeEvent("hi")


@contextmanager
def open_chat(client, token="a-token"):
    """Connect the way the UI does: open, authenticate, wait for "ready"."""
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"type": "auth", "token": token})
        assert ws.receive_json() == {"type": "ready"}
        yield ws


@pytest.fixture
def spies():
    """What the chat handler did with the persistence layer."""
    return SimpleNamespace(saved=[], restores=[], cleared=[], loads=[])


@pytest.fixture
def chat(monkeypatch, spies):
    runner = FakeRunner()
    recorded = []

    async def fake_restore(runner_, owner_uid, session_id, tenant_name, load_turns):
        spies.restores.append(
            {"owner": owner_uid, "session_id": session_id, "tenant_name": tenant_name, "load_turns": load_turns}
        )
        return False

    def fake_load(tenant_id, owner_uid, limit):
        spies.loads.append((tenant_id, owner_uid, limit))
        return []

    monkeypatch.setattr(api_main, "restore_session", fake_restore)
    monkeypatch.setattr(api_main, "load_recent_turns", fake_load)
    monkeypatch.setattr(api_main, "append_turn", lambda t, o, q, a: spies.saved.append((t, o, q, a)))
    monkeypatch.setattr(api_main, "clear_turns", lambda t, o: spies.cleared.append((t, o)))
    monkeypatch.setattr(
        api_main, "get_settings", lambda owner_uid: {"history_turns": 7, "daily_message_warning_threshold": 100}
    )
    monkeypatch.setattr(api_main, "verify_token", lambda token: OWNER)
    monkeypatch.setattr(api_main, "get_owned_tenant", lambda tenant_id, owner_uid: {"name": "Some Tenant"})
    monkeypatch.setattr(api_main, "get_runner", lambda owner_uid: runner)
    monkeypatch.setattr(api_main, "record_message", lambda owner_uid: recorded.append(owner_uid))
    return TestClient(api_main.app), runner, recorded


def test_a_normal_message_reaches_the_agent_with_a_call_cap(chat):
    client, runner, recorded = chat
    with open_chat(client) as ws:
        ws.send_json({"message": "hello"})
        assert ws.receive_json() == {"type": "final", "text": "hi"}

    assert len(runner.calls) == 1
    assert runner.calls[0]["run_config"].max_llm_calls == api_main.MAX_LLM_CALLS_PER_TURN
    assert recorded == [OWNER]


def test_an_oversized_message_is_rejected_before_the_agent_and_the_socket_survives(chat):
    client, runner, recorded = chat
    with open_chat(client) as ws:
        ws.send_json({"message": "x" * (api_main.MAX_MESSAGE_CHARS + 1)})
        assert ws.receive_json()["type"] == "error"
        assert runner.calls == []
        assert recorded == []

        ws.send_json({"message": "hello"})
        assert ws.receive_json()["type"] == "final"


@pytest.mark.parametrize("payload", [["not", "a", "dict"], {"message": "   "}, {"message": 42}, {}])
def test_malformed_or_empty_messages_get_an_error_frame(chat, payload):
    client, runner, _ = chat
    with open_chat(client) as ws:
        ws.send_json(payload)
        assert ws.receive_json()["type"] == "error"
    assert runner.calls == []


def test_an_agent_failure_becomes_an_error_frame_and_keeps_the_socket_open(chat):
    client, runner, _ = chat
    runner.fail = True
    with open_chat(client) as ws:
        ws.send_json({"message": "hello"})
        assert ws.receive_json()["type"] == "error"

        runner.fail = False
        ws.send_json({"message": "hello again"})
        assert ws.receive_json() == {"type": "final", "text": "hi"}


def test_reset_deletes_the_server_side_session(chat):
    client, runner, _ = chat
    with open_chat(client) as ws:
        ws.send_json({"type": "reset"})
        # reset has no reply frame — a follow-up round trip makes sure the
        # server has processed it before we look.
        ws.send_json({"message": "hello"})
        assert ws.receive_json()["type"] == "final"

    assert runner.session_service.deleted == [("anamnesis", OWNER, "session_some_tenant")]


def test_tool_events_carry_ids_so_results_can_be_paired_with_their_calls():
    call = SimpleNamespace(id="call-1", name="get_tenant_facts", args={"tenant_id": "t"})
    result = SimpleNamespace(id="call-1", name="get_tenant_facts", response={"result": []})
    event = SimpleNamespace(get_function_calls=lambda: [call], get_function_responses=lambda: [result])

    assert api_main._event_to_messages(event) == [
        {"type": "tool_call", "id": "call-1", "name": "get_tenant_facts", "args": {"tenant_id": "t"}},
        {"type": "tool_result", "id": "call-1", "name": "get_tenant_facts", "result": {"result": []}},
    ]


def test_the_agent_is_told_which_project_the_ui_has_selected(chat):
    client, runner, _ = chat
    with open_chat(client) as ws:
        ws.send_json({"message": "what do you know?"})
        assert ws.receive_json()["type"] == "final"

    assert runner.calls[0]["text"] == "[Project: Some Tenant] what do you know?"


def test_the_length_limit_applies_to_what_the_user_typed_not_the_project_prefix(chat):
    client, runner, _ = chat
    with open_chat(client) as ws:
        ws.send_json({"message": "x" * api_main.MAX_MESSAGE_CHARS})
        assert ws.receive_json()["type"] == "final"


def test_connecting_to_a_project_the_user_does_not_own_is_refused(chat, monkeypatch):
    client, runner, _ = chat

    def not_owned(tenant_id, owner_uid):
        raise PermissionError("nope")

    monkeypatch.setattr(api_main, "get_owned_tenant", not_owned)

    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"type": "auth", "token": "tok"})
        with pytest.raises(WebSocketDisconnect) as excinfo:
            ws.receive_json()
    assert excinfo.value.code == 1008
    assert runner.calls == []


def test_a_finished_turn_is_saved_as_plain_question_and_answer_text(chat, spies):
    client, _, _ = chat
    with open_chat(client) as ws:
        ws.send_json({"message": "what do you know?"})
        assert ws.receive_json()["type"] == "final"

    # The raw question — not the "[Project: ...]" form the model was shown.
    assert spies.saved == [("some_tenant", OWNER, "what do you know?", "hi")]


def test_a_turn_with_no_answer_is_not_saved(chat, spies):
    client, runner, _ = chat
    runner.silent = True
    with open_chat(client) as ws:
        ws.send_json({"message": "hello"})
        assert ws.receive_json() == {"type": "final", "text": "(no response)"}

    assert spies.saved == []


def test_a_failing_save_does_not_break_the_conversation(chat, monkeypatch):
    client, _, _ = chat

    def broken(*args):
        raise RuntimeError("firestore is down")

    monkeypatch.setattr(api_main, "append_turn", broken)

    with open_chat(client) as ws:
        ws.send_json({"message": "one"})
        assert ws.receive_json()["type"] == "final"
        ws.send_json({"message": "two"})
        assert ws.receive_json()["type"] == "final"


def test_connecting_restores_the_models_memory_using_the_users_window_setting(chat, spies):
    client, _, _ = chat
    with open_chat(client):
        pass

    assert len(spies.restores) == 1
    restore = spies.restores[0]
    assert (restore["owner"], restore["session_id"], restore["tenant_name"]) == (
        OWNER,
        "session_some_tenant",
        "Some Tenant",
    )

    # The loader the handler hands over reads exactly the user's window.
    restore["load_turns"]()
    assert spies.loads == [("some_tenant", OWNER, 7)]


def test_a_failing_restore_does_not_stop_the_user_from_chatting(chat, monkeypatch):
    client, _, _ = chat

    async def broken_restore(*args):
        raise RuntimeError("firestore is down")

    monkeypatch.setattr(api_main, "restore_session", broken_restore)

    with open_chat(client) as ws:
        ws.send_json({"message": "hello"})
        assert ws.receive_json() == {"type": "final", "text": "hi"}


def test_clear_chat_also_deletes_the_saved_turns(chat, spies):
    client, _, _ = chat
    with open_chat(client) as ws:
        ws.send_json({"type": "reset"})
        ws.send_json({"message": "hello"})
        assert ws.receive_json()["type"] == "final"

    assert spies.cleared == [("some_tenant", OWNER)]


def test_a_failing_clear_does_not_break_the_conversation(chat, monkeypatch):
    client, _, _ = chat

    def broken(*args):
        raise RuntimeError("firestore is down")

    monkeypatch.setattr(api_main, "clear_turns", broken)

    with open_chat(client) as ws:
        ws.send_json({"type": "reset"})
        ws.send_json({"message": "hello"})
        assert ws.receive_json()["type"] == "final"


def test_a_running_turn_does_not_block_other_requests(chat, monkeypatch):
    client, runner, _ = chat

    original_run = runner.run

    def slow_run(**kwargs):
        time.sleep(1.0)  # stands in for the model + Firestore-backed tools
        yield from original_run(**kwargs)

    monkeypatch.setattr(runner, "run", slow_run)

    with client as running:  # one shared event loop, like the real server
        with open_chat(running) as ws:
            ws.send_json({"message": "hello"})
            time.sleep(0.2)  # the turn is now mid-flight

            started = time.perf_counter()
            assert running.get("/health").status_code == 200
            elapsed = time.perf_counter() - started

            assert ws.receive_json()["type"] == "final"

    # Blocked, this waits out the remaining ~0.8 s of the turn.
    assert elapsed < 0.4


def test_the_model_call_does_not_wait_for_the_usage_write(chat, monkeypatch):
    client, runner, _ = chat
    agent_started = threading.Event()
    waited_for_agent = []

    def slow_usage(owner_uid):
        # Only returns True if the agent started while this was still
        # running — i.e. the two ran side by side, not one after the other.
        waited_for_agent.append(agent_started.wait(2))

    original_run = runner.run

    def run(**kwargs):
        agent_started.set()
        yield from original_run(**kwargs)

    monkeypatch.setattr(api_main, "record_message", slow_usage)
    monkeypatch.setattr(runner, "run", run)

    with open_chat(client) as ws:
        ws.send_json({"message": "hello"})
        assert ws.receive_json()["type"] == "final"

    assert waited_for_agent == [True]


def test_a_failing_usage_write_does_not_break_the_conversation(chat, monkeypatch):
    client, _, _ = chat

    def broken(owner_uid):
        raise RuntimeError("firestore is down")

    monkeypatch.setattr(api_main, "record_message", broken)

    with open_chat(client) as ws:
        ws.send_json({"message": "one"})
        assert ws.receive_json()["type"] == "final"
        ws.send_json({"message": "two"})
        assert ws.receive_json()["type"] == "final"


def test_usage_save_and_clear_run_off_the_event_loop_thread(chat, monkeypatch):
    client, _, _ = chat
    threads = {}

    async def fake_restore(*args):
        # Runs on the event loop, so this is the loop's thread.
        threads["loop"] = threading.get_ident()
        return False

    def note(name):
        def fake(*args):
            threads[name] = threading.get_ident()

        return fake

    monkeypatch.setattr(api_main, "restore_session", fake_restore)
    monkeypatch.setattr(api_main, "record_message", note("usage"))
    monkeypatch.setattr(api_main, "append_turn", note("save"))
    monkeypatch.setattr(api_main, "clear_turns", note("clear"))

    with open_chat(client) as ws:
        ws.send_json({"type": "reset"})
        ws.send_json({"message": "hello"})
        assert ws.receive_json()["type"] == "final"
        # The save runs after the final frame; one more round trip makes
        # sure the handler has got past it.
        ws.send_json({"message": "again"})
        assert ws.receive_json()["type"] == "final"

    # A blocking call made straight from the handler would report the
    # loop's own thread; asyncio.to_thread reports a worker's.
    assert {"usage", "save", "clear"} <= threads.keys()
    for name in ("usage", "save", "clear"):
        assert threads[name] != threads["loop"], name


# --- Authentication happens in the first frame, never in the URL (APPCE-67)


def _assert_closed_with_policy_violation(ws):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        ws.receive_json()
    assert excinfo.value.code == 1008


def test_the_token_is_read_from_the_auth_frame_not_the_url(chat, monkeypatch):
    client, _, _ = chat
    seen = []

    def verify(token):
        seen.append(token)
        return OWNER

    monkeypatch.setattr(api_main, "verify_token", verify)

    with open_chat(client, token="the-real-token"):
        pass

    assert seen == ["the-real-token"]
    assert "token" not in WS_URL


def test_an_invalid_token_is_refused_and_never_reaches_the_agent(chat, monkeypatch):
    client, runner, _ = chat

    def reject(token):
        raise api_main.HTTPException(status_code=401, detail="Invalid token")

    monkeypatch.setattr(api_main, "verify_token", reject)

    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"type": "auth", "token": "bad"})
        _assert_closed_with_policy_violation(ws)
    assert runner.calls == []


def test_a_chat_message_before_authenticating_is_refused(chat):
    client, runner, recorded = chat
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"message": "hello"})
        _assert_closed_with_policy_violation(ws)
    assert runner.calls == []
    assert recorded == []


@pytest.mark.parametrize("frame", [{"type": "auth"}, {"type": "auth", "token": ""}, {"type": "auth", "token": 5}, ["x"]])
def test_a_malformed_auth_frame_is_refused(chat, frame):
    client, runner, _ = chat
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json(frame)
        _assert_closed_with_policy_violation(ws)
    assert runner.calls == []


def test_a_first_frame_that_is_not_json_is_refused(chat):
    client, _, _ = chat
    with client.websocket_connect(WS_URL) as ws:
        ws.send_text("not json at all")
        _assert_closed_with_policy_violation(ws)


def test_an_oversized_first_frame_is_refused_without_verifying_it(chat, monkeypatch):
    client, _, _ = chat
    verified = []
    monkeypatch.setattr(api_main, "verify_token", lambda token: verified.append(token) or OWNER)

    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"type": "auth", "token": "x" * api_main.MAX_AUTH_FRAME_CHARS})
        _assert_closed_with_policy_violation(ws)
    assert verified == []


def test_a_connection_that_never_authenticates_is_dropped(chat, monkeypatch):
    client, _, _ = chat
    monkeypatch.setattr(api_main, "AUTH_TIMEOUT_SECONDS", 0.2)

    with client.websocket_connect(WS_URL) as ws:
        _assert_closed_with_policy_violation(ws)


# --- Request duration log (APPCE-68)


def test_each_rest_call_logs_its_duration(chat, capsys):
    client, _, _ = chat
    assert client.get("/health").status_code == 200

    out = capsys.readouterr().out
    assert re.search(r"^GET /health -> 200 in \d+ ms$", out, re.MULTILINE)


def test_the_duration_log_never_includes_the_query_string(chat, capsys):
    client, _, _ = chat
    client.get("/health?token=super-secret&x=1")

    out = capsys.readouterr().out
    assert "GET /health -> 200" in out
    assert "super-secret" not in out
    assert "?" not in out


def test_cors_preflights_are_not_logged(chat, capsys):
    client, _, _ = chat
    client.options(
        "/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )

    assert "OPTIONS" not in capsys.readouterr().out
