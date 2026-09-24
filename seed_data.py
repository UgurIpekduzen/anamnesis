from src.categories import DEFAULT_CATEGORIES
from src.firestore_client import get_client


def seed():
    client = get_client()

    # Category config, read by src/categories.py at runtime. Kept here as
    # a manual/reset option — the API now seeds this automatically on
    # startup if it's missing (APPCE-93), so running this script by hand
    # is no longer required for a fresh deployment, only for resetting
    # categories back to the defaults. Tenants are registered by hand via
    # src.tenants.add_tenant(), and facts are created through the
    # event-driven path (src.publisher.publish_fact), not seeded.
    client.collection("config").document("categories").set(
        {"allowed": DEFAULT_CATEGORIES}
    )

    print("Category config written.")


if __name__ == "__main__":
    seed()
