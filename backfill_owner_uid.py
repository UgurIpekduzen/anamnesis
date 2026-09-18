import sys

from src.firestore_client import get_client


def backfill(owner_uid: str) -> None:
    """One-off migration (APPCE-47): assign owner_uid to every existing
    tenant document that predates the multi-user change. Run this once,
    manually, before relying on list_tenants' owner_uid filter — tenants
    without owner_uid would otherwise become invisible to everyone.
    """
    client = get_client()
    updated = 0
    for doc in client.collection("tenants").stream():
        if doc.to_dict().get("owner_uid") is not None:
            continue
        doc.reference.update({"owner_uid": owner_uid})
        print(f"{doc.id}: owner_uid set to {owner_uid}")
        updated += 1

    print(f"Done. {updated} tenant(s) updated.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python backfill_owner_uid.py <owner_email>")
        sys.exit(1)
    backfill(sys.argv[1])
