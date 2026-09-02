from datetime import datetime, timezone

from src.firestore_client import get_client

ALLOWED_CATEGORIES = ["architecture", "decision", "bug", "status", "todo"]


def seed():
    client = get_client()
    now = datetime.now(timezone.utc)

    # 1. Category config, read by src/categories.py at runtime.
    client.collection("config").document("categories").set(
        {"allowed": ALLOWED_CATEGORIES}
    )

    # 2. Sample tenant.
    tenant_ref = client.collection("tenants").document("recruiter_ai")
    tenant_ref.set(
        {
            "name": "Recruiter.AI",
            "status": "active",
            "created_at": now,
        }
    )

    # 3. Sample facts under that tenant.
    # Clear existing facts first so re-running this script stays idempotent
    # (facts use auto-generated IDs, so re-adding would otherwise duplicate them).
    for existing in tenant_ref.collection("facts").stream():
        existing.reference.delete()

    facts = [
        {
            "content": "Auth uses JWT with refresh tokens.",
            "category": "architecture",
        },
        {
            "content": "Decided to use PostgreSQL instead of MongoDB for structured candidate data.",
            "category": "decision",
        },
    ]
    for fact in facts:
        tenant_ref.collection("facts").add(
            {**fact, "created_at": now, "updated_at": now}
        )

    print("Seed data written.")


if __name__ == "__main__":
    seed()
