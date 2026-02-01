import streamlit as st

from admin.components.auth import check_auth, render_auth_sidebar

st.set_page_config(page_title="Vartalaap Admin", layout="wide")

if not check_auth():
    st.stop()

render_auth_sidebar()

st.title("Vartalaap Admin")
st.caption("Use the sidebar to navigate between pages.")
st.info(
    "This admin panel manages reservations, call logs, and business configuration "
    "for the Vartalaap voice assistant."
)
