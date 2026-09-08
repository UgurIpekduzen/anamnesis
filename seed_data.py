from src.firestore_client import get_client

ALLOWED_CATEGORIES = ["architecture", "decision", "bug", "status", "todo"]


def seed():
    client = get_client()

    # Category config, read by src/categories.py at runtime. This is the
    # only thing seeded automatically — tenants are registered by hand via
    # src.tenants.add_tenant(), and facts are created through the
    # event-driven path (src.publisher.publish_fact), not seeded.
    client.collection("config").document("categories").set(
        {"allowed": ALLOWED_CATEGORIES}
    )

    print("Category config written.")


if __name__ == "__main__":
    seed()
