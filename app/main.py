import streamlit as st

from app.chat import ask
from app.runner import get_runner
from app.tenant_selector import select_tenant

st.set_page_config(page_title="Anamnesis")
st.title("Anamnesis")
st.caption("Personal Project Context Engine")

runner = get_runner()
tenant = select_tenant()
ask(runner, tenant)
