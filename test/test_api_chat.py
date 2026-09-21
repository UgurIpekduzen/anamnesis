import os
from types import SimpleNamespace

# api.deps reads these at import time.
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("ALLOWED_EMAILS", "test@example.com")

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

import api.main as api_main  # noqa: E402

OWNER = "test@example.com"
WS_URL = "/ws/chat/some_tenant?token=ignored"


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
        yield FakeEvent("hi")


@pytest.fixture
def chat(monkeypatch):
    runner = FakeRunner()
    recorded = []
    monkeypatch.setattr(api_main, "verify_token", lambda token: OWNER)
    monkeypatch.setattr(api_main, "get_owned_tenant", lambda tenant_id, owner_uid: {"name": "Some Tenant"})
    monkeypatch.setattr(api_main, "get_runner", lambda owner_uid: runner)
    monkeypatch.setattr(api_main, "record_message", lambda owner_uid: recorded.append(owner_uid))
    return TestClient(api_main.app), runner, recorded


def test_a_normal_message_reaches_the_agent_with_a_call_cap(chat):
    client, runner, recorded = chat
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"message": "hello"})
        assert ws.receive_json() == {"type": "final", "text": "hi"}

    assert len(runner.calls) == 1
    assert runner.calls[0]["run_config"].max_llm_calls == api_main.MAX_LLM_CALLS_PER_TURN
    assert recorded == [OWNER]


def test_an_oversized_message_is_rejected_before_the_agent_and_the_socket_survives(chat):
    client, runner, recorded = chat
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"message": "x" * (api_main.MAX_MESSAGE_CHARS + 1)})
        assert ws.receive_json()["type"] == "error"
        assert runner.calls == []
        assert recorded == []

        ws.send_json({"message": "hello"})
        assert ws.receive_json()["type"] == "final"


@pytest.mark.parametrize("payload", [["not", "a", "dict"], {"message": "   "}, {"message": 42}, {}])
def test_malformed_or_empty_messages_get_an_error_frame(chat, payload):
    client, runner, _ = chat
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json(payload)
        assert ws.receive_json()["type"] == "error"
    assert runner.calls == []


def test_an_agent_failure_becomes_an_error_frame_and_keeps_the_socket_open(chat):
    client, runner, _ = chat
    runner.fail = True
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"message": "hello"})
        assert ws.receive_json()["type"] == "error"

        runner.fail = False
        ws.send_json({"message": "hello again"})
        assert ws.receive_json() == {"type": "final", "text": "hi"}


def test_reset_deletes_the_server_side_session(chat):
    client, runner, _ = chat
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"type": "reset"})
        # reset has no reply frame — a follow-up round trip makes sure the
        # server has processed it before we look.
        ws.send_json({"message": "hello"})
        assert ws.receive_json()["type"] == "final"

    assert runner.session_service.deleted == [("anamnesis", OWNER, "session_some_tenant")]


def test_the_agent_is_told_which_project_the_ui_has_selected(chat):
    client, runner, _ = chat
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"message": "what do you know?"})
        assert ws.receive_json()["type"] == "final"

    assert runner.calls[0]["text"] == "[Project: Some Tenant] what do you know?"


def test_the_length_limit_applies_to_what_the_user_typed_not_the_project_prefix(chat):
    client, runner, _ = chat
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"message": "x" * api_main.MAX_MESSAGE_CHARS})
        assert ws.receive_json()["type"] == "final"


def test_connecting_to_a_project_the_user_does_not_own_is_refused(chat, monkeypatch):
    client, runner, _ = chat

    def not_owned(tenant_id, owner_uid):
        raise PermissionError("nope")

    monkeypatch.setattr(api_main, "get_owned_tenant", not_owned)

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(WS_URL):
            pass
    assert excinfo.value.code == 1008
    assert runner.calls == []