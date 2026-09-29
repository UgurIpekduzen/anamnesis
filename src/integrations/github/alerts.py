from src.core.firestore_client import get_client

# Whether poll_all_tenants should log a failed run at ERROR (which the
# Cloud Monitoring alert policy in terraform/monitoring.tf matches on) or
# WARNING (which it doesn't). Muting doesn't touch that policy or need any
# new GCP permission — it just changes which severity this app logs at.
# A single doc, not per-tenant: the alert itself fires on any
# tenant failing, not a specific one, so there's nothing to key by.
_DOC_PATH = ("config", "alerts")


def _doc_ref():
    collection, doc_id = _DOC_PATH
    return get_client().collection(collection).document(doc_id)


def is_github_poll_alert_muted() -> bool:
    doc = _doc_ref().get()
    return bool(doc.to_dict().get("github_poll_alert_muted", False)) if doc.exists else False


def set_github_poll_alert_muted(muted: bool) -> None:
    _doc_ref().set({"github_poll_alert_muted": muted}, merge=True)
