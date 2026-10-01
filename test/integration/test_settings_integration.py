"""Integration tests for reading, saving, and validating the app-wide message settings document."""

import pytest

from src.accounts import settings as settings_module
from src.accounts.settings import BOUNDS, DEFAULTS, get_settings, save_settings
from src.core.firestore_client import get_client


@pytest.fixture(autouse=True)
def fresh_settings():
    """Clear the in-process settings cache before each test and delete the settings document afterwards."""
    settings_module._cache = None
    yield
    settings_module._doc_ref().delete()
    settings_module._cache = None


def _valid(**overrides):
    return {"history_turns": 10, "daily_message_warning_threshold": 50, **overrides}


def test_unset_settings_are_the_defaults():
    """When no settings document exists, get_settings returns the default values."""
    assert get_settings() == DEFAULTS


def test_saved_settings_are_persisted_and_read_back():
    """Settings saved via save_settings are persisted to Firestore and read back unchanged."""
    save_settings(_valid())

    # Drop the in-process cache so this really comes from Firestore.
    settings_module._cache = None
    assert get_settings() == _valid()


def test_a_save_is_visible_immediately_despite_the_cache():
    """A saved setting is visible on the next read even though a prior read had primed the cache."""
    assert get_settings() == DEFAULTS  # primes the cache with the defaults
    save_settings(_valid(history_turns=7))
    assert get_settings()["history_turns"] == 7


@pytest.mark.parametrize(
    "bad",
    [
        {"history_turns": BOUNDS["history_turns"][0] - 1},
        {"history_turns": BOUNDS["history_turns"][1] + 1},
        {"daily_message_warning_threshold": 0},
        {"daily_message_warning_threshold": BOUNDS["daily_message_warning_threshold"][1] + 1},
        {"history_turns": True},
        {"history_turns": "10"},
        {"unknown_setting": 1},
    ],
)
def test_invalid_settings_are_rejected_and_nothing_is_stored(bad):
    """Each out-of-bounds, wrong-typed, or unknown setting is rejected and leaves the stored defaults untouched."""
    with pytest.raises(ValueError):
        save_settings(_valid(**bad))

    settings_module._cache = None
    assert get_settings() == DEFAULTS


def test_a_missing_setting_is_rejected():
    """Saving a settings payload that omits a required key raises ValueError."""
    with pytest.raises(ValueError):
        save_settings({"history_turns": 10})


def test_out_of_bounds_stored_values_are_clamped_on_read():
    """Values stored outside the current bounds are clamped to the nearest bound when read back."""
    # Simulates a value written under older/looser bounds (or by hand).
    get_client().collection("config").document("message_settings").set(
        {"history_turns": 10_000, "daily_message_warning_threshold": -5}
    )
    settings = get_settings()
    assert settings["history_turns"] == BOUNDS["history_turns"][1]
    assert (
        settings["daily_message_warning_threshold"] == BOUNDS["daily_message_warning_threshold"][0]
    )


def test_garbage_stored_values_fall_back_to_the_default():
    """Stored values of the wrong type fall back to the defaults when read back."""
    get_client().collection("config").document("message_settings").set(
        {"history_turns": "lots", "daily_message_warning_threshold": True}
    )
    assert get_settings() == DEFAULTS
