import base64
import json

from src.subscriber import _process_push_message


def _push_envelope(payload: dict) -> bytes:
    data = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    return json.dumps({"message": {"data": data}}).encode("utf-8")


def test_returns_400_on_invalid_json():
    status = _process_push_message(b"not valid json")
    assert status == 400


def test_returns_400_on_missing_required_field(monkeypatch):
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
        lambda tenant_id, content, category: created.update(
            tenant_id=tenant_id, content=content, category=category
        ),
    )
    body = _push_envelope({"tenant_id": "x", "content": "y", "category": "bug"})

    status = _process_push_message(body)

    assert status == 200
    assert created == {"tenant_id": "x", "content": "y", "category": "bug"}
