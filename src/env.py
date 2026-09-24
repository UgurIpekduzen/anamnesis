"""Where the process's settings come from when they aren't already exported."""

import os

from dotenv import load_dotenv


def load_env() -> None:
    """Read the dotenv file into the environment (existing variables win).

    It is `.env` unless DOTENV_PATH names another file. That is how a one-off
    script is pointed at real GCP instead of the local emulators:

        DOTENV_PATH=.env.production python seed_data.py

    (see .env.production.example), where the emulator host variables are
    deliberately absent.
    """
    load_dotenv(os.environ.get("DOTENV_PATH", ".env"))
