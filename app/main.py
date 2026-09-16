import streamlit as st

from app.chat import ask
from app.facts import render_facts
from app.runner import get_runner
from app.tenant_selector import select_tenant

st.set_page_config(page_title="Anamnesis")
st.title("Anamnesis")
st.caption("Personal Project Context Engine")

runner = get_runner()
tenant = select_tenant()

with st.sidebar:
    trace_tab, facts_tab = st.tabs(["Agent trace", "Facts"])

with facts_tab:
    render_facts(tenant)

ask(runner, tenant, trace_tab)
