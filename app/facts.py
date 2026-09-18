import streamlit as st

from src.facts import get_tenant_facts

# Mirrors seed_data.py's ALLOWED_CATEGORIES — not imported from there since
# seed_data.py is a one-off local setup script, not part of the deployed
# image.
CATEGORY_ORDER = ["architecture", "decision", "bug", "status", "todo"]


def render_facts(tenant: dict, owner_uid: str) -> None:
    facts = get_tenant_facts(tenant["tenant_id"], owner_uid)
    if not facts:
        st.caption("No facts recorded yet.")
        return

    by_category: dict[str, list[dict]] = {}
    for fact in facts:
        by_category.setdefault(fact["category"], []).append(fact)

    # Known categories first (in their defined order), then anything
    # unexpected so a stale/renamed category doesn't just get dropped.
    ordered_categories = [c for c in CATEGORY_ORDER if c in by_category]
    ordered_categories += [c for c in by_category if c not in CATEGORY_ORDER]

    for category in ordered_categories:
        label = f"{category.capitalize()} ({len(by_category[category])})"
        with st.expander(label, expanded=True):
            for fact in by_category[category]:
                with st.container(border=True):
                    st.write(fact["content"])
                    created_at = fact.get("created_at")
                    if created_at is not None:
                        st.caption(created_at.strftime("%b %d, %Y at %I:%M %p"))
