"""Tests for the Pub/Sub push subscriber that writes incoming facts."""

import base64
import http.client
import json
import threading
from http.server import HTTPServer

import pytest

import src.subscriber as subscriber
from src.subscriber import _process_push_message


def _push_envelope(payload: dict) -> bytes:
    data = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    return json.dumps({"message": {"data": data}}).encode("utf-8")


def test_returns_400_on_invalid_json():
    """A push body that isn't valid JSON is rejected with a 400."""
    status = _process_push_message(b"not valid json")
    assert status == 400


def test_returns_400_on_missing_required_field(monkeypatch):
    """A decoded message missing a required field is rejected with a 400 instead of crashing, and create_fact is never called."""
    monkeypatch.setattr("src.subscriber.create_fact", lambda **_: (_ for _ in ()).throw(AssertionError))
    # Missing "category" — this used to crash the streaming-pull callback
    # and take down the whole subscriber process (APPCE-30).
    body = _push_envelope({"tenant_id": "x", "content": "y"})

    status = _process_push_message(body)

    assert status == 400


def test_returns_200_and_writes_fact_on_valid_payload(monkeypatch):
    created = {}
    monkeypatch.setattr(
        "src.subscriber.create_fact",
        lambda tenant_id, content, category, source: created.update(
            tenant_id=tenant_id, content=content, category=category, source=source
        ),
    )
    body = _push_envelope({"tenant_id": "x", "content": "y", "category": "bug", "source": "github"})

    status = _process_push_message(body)

    assert status == 200
    assert created == {"tenant_id": "x", "content": "y", "category": "bug", "source": "github"}


def test_a_message_published_before_source_existed_defaults_to_chat(monkeypatch):
    created = {}
    monkeypatch.setattr(
        "src.subscriber.create_fact",
        lambda tenant_id, content, category, source: created.update(source=source),
    )
    body = _push_envelope({"tenant_id": "x", "content": "y", "category": "bug"})

    status = _process_push_message(body)

    assert status == 200
    assert created == {"source": "chat"}


# APPCE-119: what the push endpoint does with a request that is not a normal
# Pub/Sub delivery. It runs behind IAM, so this is depth, not the front door.
@pytest.fixture
def server(monkeypatch):
    seen = []
    monkeypatch.setattr(subscriber, "_process_push_message", lambda body: seen.append(body) or 200)
    httpd = HTTPServer(("127.0.0.1", 0), subscriber._Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1], seen
    httpd.shutdown()
    httpd.server_close()


def _post(port, headers, body=b""):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", "/")
    for name, value in headers.items():
        conn.putheader(name, value)
    conn.endheaders(body)
    status = conn.getresponse().status
    conn.close()
    return status


def test_a_normal_push_is_handled(server):
    port, seen = server
    assert _post(port, {"Content-Length": "2"}, b"{}") == 200
    assert seen == [b"{}"]


@pytest.mark.parametrize("value", ["abc", "-5", "1.5", ""])
def test_an_invalid_content_length_is_a_400_and_nothing_is_processed(server, value):
    port, seen = server
    assert _post(port, {"Content-Length": value}) == 400
    assert seen == []


def test_a_body_over_the_limit_is_a_413_and_is_never_read(server):
    port, seen = server
    assert _post(port, {"Content-Length": str(subscriber.MAX_BODY_BYTES + 1)}) == 413
    assert seen == []


def test_a_malformed_message_is_logged_without_its_content(monkeypatch):
    logged = []
    monkeypatch.setattr(subscriber, "log", lambda severity, event, **fields: logged.append((event, fields)))

    body = b'{"message": {"data": "not base64 at all, a private fact"}}'
    assert subscriber._process_push_message(body) == 400

    assert logged and logged[0][0] == "malformed_push_message"
    assert "private fact" not in repr(logged)
    assert logged[0][1]["size"] == len(body)
