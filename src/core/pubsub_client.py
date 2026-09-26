import os

from google.cloud import pubsub_v1

from src.core.env import load_env

load_env()


def _project_id() -> str:
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        raise RuntimeError("GCP_PROJECT_ID is not set (check your .env file)")
    return project_id


def get_publisher_client() -> pubsub_v1.PublisherClient:
    # Targets the emulator automatically when PUBSUB_EMULATOR_HOST is set.
    return pubsub_v1.PublisherClient()


def get_subscriber_client() -> pubsub_v1.SubscriberClient:
    return pubsub_v1.SubscriberClient()


def topic_path(topic_id: str) -> str:
    return pubsub_v1.PublisherClient.topic_path(_project_id(), topic_id)


def subscription_path(subscription_id: str) -> str:
    return pubsub_v1.SubscriberClient.subscription_path(_project_id(), subscription_id)
