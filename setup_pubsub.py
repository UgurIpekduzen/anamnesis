from google.api_core.exceptions import AlreadyExists

from src.pubsub_client import get_publisher_client, get_subscriber_client, subscription_path, topic_path

TOPIC_ID = "fact-events"
SUBSCRIPTION_ID = "fact-events-sub"


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


if __name__ == "__main__":
    setup()
