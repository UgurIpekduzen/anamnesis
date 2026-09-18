import streamlit as st

from app.auth import get_current_user_email
from app.chat import ask, clear_history
from app.facts import render_facts
from app.runner import get_runner
from app.tenant_selector import select_tenant
from src.usage import DAILY_MESSAGE_WARNING_THRESHOLD, get_today_count

st.set_page_config(page_title="Anamnesis")
st.title("Anamnesis")
st.caption("Personal Project Context Engine")

# Cloud Run forwards the caller's verified identity via the
# X-Serverless-Authorization header (see app/auth.py). Locally (docker
# compose), that header doesn't exist, so we fall back to a fixed dev
# identity — there's no real IAM check to satisfy there anyway.
user_email = get_current_user_email()
owner_uid = user_email or "local-dev@anamnesis.local"

if user_email is not None:
    st.caption(f"Signed in as {user_email}")
else:
    # TEMPORARY (APPCE-46 diagnosis, round 2): the header is present but
    # something about its value or decoding isn't matching what we
    # expect — show enough to tell what, without leaking the full token.
    raw = st.context.headers.get("X-Serverless-Authorization")
    st.caption(f"debug: raw prefix = {raw[:20]!r} len={len(raw) if raw else 0}")
    if raw:
        from app.auth import _decode_jwt_payload

        try:
            claims = _decode_jwt_payload(raw.removeprefix("Bearer "))
            st.caption(f"debug: decoded claim keys = {list(claims.keys())}")
        except Exception as exc:
            st.caption(f"debug: decode failed = {exc!r}")

runner = get_runner(owner_uid)
tenant = select_tenant(owner_uid)

with st.sidebar:
    today_count = get_today_count(owner_uid)
    st.caption(f"{today_count} messages today")
    if today_count >= DAILY_MESSAGE_WARNING_THRESHOLD:
        st.warning("You've sent a lot of messages today — just flagging it, nothing is blocked.")

    if st.button("🗑️ Clear chat"):
        clear_history(tenant["tenant_id"])
        st.rerun()

    trace_tab, facts_tab = st.tabs(["Agent trace", "Facts"])

with facts_tab:
    render_facts(tenant)

ask(runner, tenant, trace_tab, owner_uid)
