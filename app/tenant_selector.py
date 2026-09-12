import streamlit as st

from src.tenants import list_tenants


def select_tenant() -> dict:
    tenants = list_tenants()
    if not tenants:
        st.warning("No projects found. Run seed_data.py first.")
        st.stop()

    tenant_names = [t["name"] for t in tenants]
    selected_name = st.selectbox("Project", tenant_names)
    return next(t for t in tenants if t["name"] == selected_name)
