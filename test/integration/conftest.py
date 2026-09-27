import os
import socket

import pytest

from src.tools.setup_pubsub import setup as setup_pubsub


def _emulator_reachable(host_env_var: str) -> bool:
    host_port = os.environ.get(host_env_var)
    if not host_port:
        return False
    host, _, port = host_port.partition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=True)
def _require_emulators():
    # .env always points these at localhost — that doesn't mean the
    # emulator containers are actually up, so check connectivity rather
    # than just env var presence (otherwise these tests fail with a
    # confusing connection error instead of a clear skip reason).
    if not _emulator_reachable("FIRESTORE_EMULATOR_HOST") or not _emulator_reachable(
        "PUBSUB_EMULATOR_HOST"
    ):
        pytest.skip("Emulators not reachable — start them with `task emulators:up`")


@pytest.fixture(scope="session", autouse=True)
def _setup_pubsub_topic(_require_emulators):
    # Same reasoning as _seed_categories: a fresh Pub/Sub emulator has no
    # topics/subscriptions, so publish_fact/pull would fail with NOT_FOUND.
    setup_pubsub()
