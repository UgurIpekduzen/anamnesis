import pytest

from src.integrations.github.alerts import is_github_poll_alert_muted, set_github_poll_alert_muted


@pytest.fixture(autouse=True)
def reset():
    yield
    set_github_poll_alert_muted(False)


def test_unmuted_by_default():
    assert is_github_poll_alert_muted() is False


def test_muting_sticks():
    set_github_poll_alert_muted(True)

    assert is_github_poll_alert_muted() is True


def test_unmuting_sticks():
    set_github_poll_alert_muted(True)
    set_github_poll_alert_muted(False)

    assert is_github_poll_alert_muted() is False
