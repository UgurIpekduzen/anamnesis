"""Provides the Pub/Sub publisher and subscriber clients, and the topic/
subscription path helpers built from GCP_PROJECT_ID, shared by the fact
publisher and its subscriber so both target the same project and topic
naming.
"""

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
    """Build a new Pub/Sub publisher client for GCP_PROJECT_ID."""
    # Targets the emulator automatically when PUBSUB_EMULATOR_HOST is set.
    return pubsub_v1.PublisherClient()


def get_subscriber_client() -> pubsub_v1.SubscriberClient:
    """Build a new Pub/Sub subscriber client for GCP_PROJECT_ID."""
    return pubsub_v1.SubscriberClient()


def topic_path(topic_id: str) -> str:
    """Build the fully-qualified path for a topic in GCP_PROJECT_ID.

    Args:
        topic_id: The topic's short name, e.g. "facts".
    """
    return pubsub_v1.PublisherClient.topic_path(_project_id(), topic_id)


def subscription_path(subscription_id: str) -> str:
    """Build the fully-qualified path for a subscription in GCP_PROJECT_ID.

    Args:
        subscription_id: The subscription's short name, e.g. "facts-sub".
    """
    return pubsub_v1.SubscriberClient.subscription_path(_project_id(), subscription_id)
