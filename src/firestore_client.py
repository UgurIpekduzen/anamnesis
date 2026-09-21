import os
from functools import lru_cache

from dotenv import load_dotenv
from google.cloud import firestore

load_dotenv(os.environ.get("DOTENV_PATH", ".env"))


@lru_cache(maxsize=None)
def _build_client(project_id: str, emulator_host: str | None) -> firestore.Client:
    # google-cloud-firestore automatically targets the emulator
    # when FIRESTORE_EMULATOR_HOST is set in the environment.
    # emulator_host is only a cache key: a client is bound to the endpoint
    # it was created for, so switching hosts must build a new one.
    return firestore.Client(project=project_id)


def get_client() -> firestore.Client:
    """One shared client per (project, endpoint).

    A new client pays channel setup and auth on its first call (~1 s), so
    building one per operation dominated every request's latency
    (APPCE-61). The client is thread-safe, so sharing it is fine.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        raise RuntimeError("GCP_PROJECT_ID is not set (check your .env file)")

    return _build_client(project_id, os.environ.get("FIRESTORE_EMULATOR_HOST"))
