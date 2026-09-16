import base64
import json
import time
import uuid

import pytest

from src.facts import get_tenant_facts
from src.publisher import publish_fact
from src.pubsub_client import get_subscriber_client, subscription_path
from src.subscriber import _process_push_message
from src.tenants import add_tenant, delete_tenant

SUBSCRIPTION_ID = "fact-events-sub"


def _pull_one(subscriber, subscription, timeout_seconds=5):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = subscriber.pull(request={"subscription": subscription, "max_messages": 1})
        if response.received_messages:
            return response.received_messages[0]
        time.sleep(0.2)
    raise TimeoutError("No message arrived on the subscription in time")


@pytest.fixture
def tenant_id():
    tenant_id = add_tenant(f"Integration Test Tenant {uuid.uuid4().hex[:8]}")
    yield tenant_id
    delete_tenant(tenant_id)


def test_publish_fact_is_delivered_and_written_by_the_subscriber(tenant_id):
    publish_fact(tenant_id, content="Published via the event-driven path", category="decision")

    subscriber = get_subscriber_client()
    subscription = subscription_path(SUBSCRIPTION_ID)
    received = _pull_one(subscriber, subscription)

    # The local emulator subscription stays pull-based regardless of
    # the real deployment's push_config (see setup_pubsub.py), so we
    # pull here and then hand the same bytes to _process_push_message
    # wrapped in a push envelope — exercising the same processing path
    # the deployed HTTP handler uses in production.
    envelope = json.dumps(
        {"message": {"data": base64.b64encode(received.message.data).decode("utf-8")}}
    ).encode("utf-8")
    status = _process_push_message(envelope)
    subscriber.acknowledge(request={"subscription": subscription, "ack_ids": [received.ack_id]})

    assert status == 200
    facts = get_tenant_facts(tenant_id)
    assert len(facts) == 1
    assert facts[0]["content"] == "Published via the event-driven path"
    assert facts[0]["category"] == "decision"
