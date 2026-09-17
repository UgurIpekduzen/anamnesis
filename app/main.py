import streamlit as st

from app.auth import get_current_user_email
from app.chat import ask, clear_history
from app.facts import render_facts
from app.runner import get_runner
from app.tenant_selector import select_tenant

st.set_page_config(page_title="Anamnesis")
st.title("Anamnesis")
st.caption("Personal Project Context Engine")

# Cloud Run forwards the caller's verified identity via the Authorization
# header (see app/auth.py). Locally (docker compose), that header doesn't
# exist, so we fall back to a fixed dev identity — there's no real IAM
# check to satisfy there anyway.
user_email = get_current_user_email()
owner_uid = user_email or "local-dev@anamnesis.local"

runner = get_runner(owner_uid)
tenant = select_tenant(owner_uid)

with st.sidebar:
    if user_email is not None:
        st.caption(f"Signed in as {user_email}")

    if st.button("🗑️ Clear chat"):
        clear_history(tenant["tenant_id"])
        st.rerun()

    trace_tab, facts_tab = st.tabs(["Agent trace", "Facts"])

with facts_tab:
    render_facts(tenant)

ask(runner, tenant, trace_tab)
