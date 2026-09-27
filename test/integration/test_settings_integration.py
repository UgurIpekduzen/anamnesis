import uuid

import pytest

from src.accounts import settings as settings_module
from src.core.firestore_client import get_client
from src.accounts.settings import BOUNDS, DEFAULTS, get_settings, reset_settings, save_settings


@pytest.fixture(autouse=True)
def fresh_cache():
    settings_module._cache.clear()
    yield
    settings_module._cache.clear()


@pytest.fixture
def owner():
    owner_uid = f"settings-{uuid.uuid4().hex[:8]}@example.com"
    yield owner_uid
    get_client().collection("user_settings").document(owner_uid).delete()


def _valid(**overrides):
    return {"history_turns": 10, "daily_message_warning_threshold": 50, **overrides}


def test_an_unseen_user_gets_the_defaults(owner):
    assert get_settings(owner) == DEFAULTS


def test_saved_settings_are_persisted_and_read_back(owner):
    save_settings(owner, _valid())

    # Drop the in-process cache so this really comes from Firestore.
    settings_module._cache.clear()
    assert get_settings(owner) == _valid()


def test_a_save_is_visible_immediately_despite_the_cache(owner):
    assert get_settings(owner) == DEFAULTS  # primes the cache with the defaults
    save_settings(owner, _valid(history_turns=7))
    assert get_settings(owner)["history_turns"] == 7


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
def test_invalid_settings_are_rejected_and_nothing_is_stored(owner, bad):
    with pytest.raises(ValueError):
        save_settings(owner, _valid(**bad))

    settings_module._cache.clear()
    assert get_settings(owner) == DEFAULTS


def test_a_missing_setting_is_rejected(owner):
    with pytest.raises(ValueError):
        save_settings(owner, {"history_turns": 10})


def test_out_of_bounds_stored_values_are_clamped_on_read(owner):
    # Simulates a value written under older/looser bounds (or by hand).
    get_client().collection("user_settings").document(owner).set(
        {"history_turns": 10_000, "daily_message_warning_threshold": -5}
    )
    settings = get_settings(owner)
    assert settings["history_turns"] == BOUNDS["history_turns"][1]
    assert settings["daily_message_warning_threshold"] == BOUNDS["daily_message_warning_threshold"][0]


def test_garbage_stored_values_fall_back_to_the_default(owner):
    get_client().collection("user_settings").document(owner).set(
        {"history_turns": "lots", "daily_message_warning_threshold": True}
    )
    assert get_settings(owner) == DEFAULTS


def test_one_users_settings_do_not_leak_to_another(owner):
    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    try:
        save_settings(owner, _valid(history_turns=3))
        assert get_settings(other) == DEFAULTS
    finally:
        get_client().collection("user_settings").document(other).delete()


def test_reset_returns_the_user_to_the_defaults_and_removes_the_stored_copy(owner):
    save_settings(owner, _valid(history_turns=3))

    assert reset_settings(owner) == DEFAULTS

    assert get_settings(owner) == DEFAULTS  # the cached value is gone too
    settings_module._cache.clear()
    assert get_settings(owner) == DEFAULTS  # and so is the Firestore document
    assert not get_client().collection("user_settings").document(owner).get().exists


def test_resetting_a_user_who_never_saved_anything_is_harmless(owner):
    assert reset_settings(owner) == DEFAULTS
