"""Integration tests for the GitHub poll alert mute flag against a real
Firestore emulator."""

import pytest

from src.integrations.github.alerts import is_github_poll_alert_muted, set_github_poll_alert_muted


@pytest.fixture(autouse=True)
def reset():
    """Reset the GitHub poll alert mute flag to unmuted after each test."""
    yield
    set_github_poll_alert_muted(False)


def test_unmuted_by_default():
    """The GitHub poll alert is unmuted when no mute flag has been set."""
    assert is_github_poll_alert_muted() is False


def test_muting_sticks():
    """Setting the GitHub poll alert mute flag to True persists so a
    subsequent read reports it as muted."""
    set_github_poll_alert_muted(True)

    assert is_github_poll_alert_muted() is True


def test_unmuting_sticks():
    """Setting the GitHub poll alert mute flag back to False persists so a
    subsequent read reports it as unmuted."""
    set_github_poll_alert_muted(True)
    set_github_poll_alert_muted(False)

    assert is_github_poll_alert_muted() is False
