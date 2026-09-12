import time
import uuid

import pytest

from src.facts import get_tenant_facts
from src.publisher import publish_fact
from src.pubsub_client import get_subscriber_client, subscription_path
from src.subscriber import SUBSCRIPTION_ID, _handle_message
from src.tenants import add_tenant, delete_tenant


class _PulledMessage:
    """Adapts a synchronously-pulled Pub/Sub message to the small
    .data/.ack()/.nack() interface _handle_message expects — that
    interface is normally provided by the streaming-pull callback
    wrapper, which we bypass here in favor of a one-shot pull so the
    test doesn't need to run subscriber.run()'s infinite loop.
    """

    def __init__(self, subscriber, subscription, received_message):
        self.data = received_message.message.data
        self._subscriber = subscriber
        self._subscription = subscription
        self._ack_id = received_message.ack_id

    def ack(self):
        self._subscriber.acknowledge(
            request={"subscription": self._subscription, "ack_ids": [self._ack_id]}
        )

    def nack(self):
        self._subscriber.modify_ack_deadline(
            request={
                "subscription": self._subscription,
                "ack_ids": [self._ack_id],
                "ack_deadline_seconds": 0,
            }
        )


def _pull_one(subscriber, subscription, timeout_seconds=5):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = subscriber.pull(
            request={"subscription": subscription, "max_messages": 1}
        )
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

    _handle_message(_PulledMessage(subscriber, subscription, received))

    facts = get_tenant_facts(tenant_id)
    assert len(facts) == 1
    assert facts[0]["content"] == "Published via the event-driven path"
    assert facts[0]["category"] == "decision"
