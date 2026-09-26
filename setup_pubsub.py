import os

from google.api_core.exceptions import AlreadyExists

from src.pubsub_client import get_publisher_client, get_subscriber_client, subscription_path, topic_path

TOPIC_ID = "fact-events"
SUBSCRIPTION_ID = "fact-events-sub"
# A second subscription on the same topic that pushes to the dev subscriber
# service, like Cloud Pub/Sub does in production (APPCE-120). The pull one
# above stays as it is: the integration tests pull from it.
PUSH_SUBSCRIPTION_ID = "fact-events-push"


def setup():
    publisher = get_publisher_client()
    subscriber = get_subscriber_client()

    topic = topic_path(TOPIC_ID)
    subscription = subscription_path(SUBSCRIPTION_ID)

    try:
        publisher.create_topic(request={"name": topic})
        print(f"Created topic: {topic}")
    except AlreadyExists:
        print(f"Topic already exists: {topic}")

    try:
        subscriber.create_subscription(request={"name": subscription, "topic": topic})
        print(f"Created subscription: {subscription}")
    except AlreadyExists:
        print(f"Subscription already exists: {subscription}")

    push_endpoint = os.environ.get("PUSH_ENDPOINT")
    if push_endpoint:
        push_subscription = subscription_path(PUSH_SUBSCRIPTION_ID)
        try:
            subscriber.create_subscription(
                request={
                    "name": push_subscription,
                    "topic": topic,
                    "push_config": {"push_endpoint": push_endpoint},
                }
            )
            print(f"Created push subscription: {push_subscription} -> {push_endpoint}")
        except AlreadyExists:
            print(f"Push subscription already exists: {push_subscription}")


if __name__ == "__main__":
    setup()
