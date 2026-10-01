"""Tests for load_env's .env file loading and precedence rules."""

import os

from src.core.env import load_env


def test_dotenv_path_picks_which_file_is_loaded(tmp_path, monkeypatch):
    """load_env() reads the file named by DOTENV_PATH."""
    other = tmp_path / "other.env"
    other.write_text("ANAMNESIS_TEST_ONLY_VAR=from-the-other-file\n")
    monkeypatch.setenv("DOTENV_PATH", str(other))
    monkeypatch.delenv("ANAMNESIS_TEST_ONLY_VAR", raising=False)

    load_env()

    assert os.environ["ANAMNESIS_TEST_ONLY_VAR"] == "from-the-other-file"
    monkeypatch.delenv("ANAMNESIS_TEST_ONLY_VAR")


def test_a_variable_that_is_already_set_wins_over_the_file(tmp_path, monkeypatch):
    """An environment variable already set before load_env() keeps its value
    instead of being overwritten by the .env file."""
    other = tmp_path / "other.env"
    other.write_text("ANAMNESIS_TEST_ONLY_VAR=from-the-file\n")
    monkeypatch.setenv("DOTENV_PATH", str(other))
    monkeypatch.setenv("ANAMNESIS_TEST_ONLY_VAR", "already-exported")

    load_env()

    assert os.environ["ANAMNESIS_TEST_ONLY_VAR"] == "already-exported"


def test_a_missing_file_is_not_an_error(tmp_path, monkeypatch):
    """load_env() does nothing, without raising, when DOTENV_PATH points to a
    file that doesn't exist."""
    monkeypatch.setenv("DOTENV_PATH", str(tmp_path / "does-not-exist.env"))

    load_env()  # must simply do nothing
