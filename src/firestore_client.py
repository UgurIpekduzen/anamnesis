import os

from dotenv import load_dotenv
from google.cloud import firestore

load_dotenv(os.environ.get("DOTENV_PATH", ".env"))


def get_client() -> firestore.Client:
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        raise RuntimeError("GCP_PROJECT_ID is not set (check your .env file)")

    # google-cloud-firestore automatically targets the emulator
    # when FIRESTORE_EMULATOR_HOST is set in the environment.
    return firestore.Client(project=project_id)
