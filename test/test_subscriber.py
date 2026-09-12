import json
from unittest.mock import MagicMock

from src.subscriber import _handle_message


def test_handle_message_nacks_on_invalid_json():
    message = MagicMock()
    message.data = b"not valid json"

    _handle_message(message)

    message.nack.assert_called_once()
    message.ack.assert_not_called()


def test_handle_message_nacks_on_missing_required_field():
    message = MagicMock()
    # Missing "category" — this used to crash the streaming-pull callback
    # and take down the whole subscriber process (APPCE-30).
    message.data = json.dumps({"tenant_id": "x", "content": "y"}).encode("utf-8")

    _handle_message(message)

    message.nack.assert_called_once()
    message.ack.assert_not_called()


def test_handle_message_acks_and_writes_fact_on_valid_payload(monkeypatch):
    message = MagicMock()
    message.data = json.dumps(
        {"tenant_id": "x", "content": "y", "category": "bug"}
    ).encode("utf-8")

    created = {}
    monkeypatch.setattr(
        "src.subscriber.create_fact",
        lambda tenant_id, content, category: created.update(
            tenant_id=tenant_id, content=content, category=category
        ),
    )

    _handle_message(message)

    assert created == {"tenant_id": "x", "content": "y", "category": "bug"}
    message.ack.assert_called_once()
    message.nack.assert_not_called()
