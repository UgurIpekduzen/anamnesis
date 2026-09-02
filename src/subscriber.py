import json

from src.facts import create_fact
from src.pubsub_client import get_subscriber_client, subscription_path

SUBSCRIPTION_ID = "fact-events-sub"


def _handle_message(message) -> None:
    payload = json.loads(message.data.decode("utf-8"))
    create_fact(
        tenant_id=payload["tenant_id"],
        content=payload["content"],
        category=payload["category"],
    )
    # Tell Pub/Sub the message was processed; an unacked message is
    # redelivered after the ack deadline elapses.
    message.ack()
    print(f"Wrote fact for tenant '{payload['tenant_id']}'")


def run():
    subscriber = get_subscriber_client()
    subscription = subscription_path(SUBSCRIPTION_ID)

    streaming_pull_future = subscriber.subscribe(subscription, callback=_handle_message)
    print(f"Listening on {subscription}... (Ctrl+C to stop)")

    with subscriber:
        try:
            streaming_pull_future.result()
        except KeyboardInterrupt:
            streaming_pull_future.cancel()
            streaming_pull_future.result()


if __name__ == "__main__":
    run()
