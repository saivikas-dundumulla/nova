from __future__ import annotations

import streamlit as st

from app.ui.pages.enduser import render_enduser
from app.ui.pages.login import render_login
from app.ui.pages.ombuds import render_ombuds
from app.ui.state import (
    api_base,
    init_session_state,
    is_logged_in,
    logout,
    set_api_base,
    user_role,
)


def _sidebar() -> None:
    with st.sidebar:
        st.header("Session")
        user = st.session_state.get("user") or {}
        st.write(f"**User:** {user.get('username', '-')}")
        st.write(f"**Role:** `{user.get('role', '-')}`")
        st.divider()
        st.write("API endpoint")
        new_url = st.text_input("URL", value=api_base(), key="sidebar_api_url")
        if new_url and new_url != api_base():
            set_api_base(new_url)
        if st.button("Log out"):
            logout()
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="Nova Ombuds Assistant", layout="wide")
    init_session_state()

    if not is_logged_in():
        render_login()
        return

    _sidebar()
    role = user_role()
    if role == "enduser":
        render_enduser()
    elif role == "ombuds":
        render_ombuds()
    else:
        st.error(f"Unsupported role: {role!r}. Contact your administrator.")


main()
