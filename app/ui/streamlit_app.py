from __future__ import annotations

import streamlit as st

from app.ui.api import fetch_thread_messages, fetch_threads
from app.ui.state import (
    api_base,
    init_session_state,
    is_logged_in,
    logout,
    set_api_base,
    user_role,
)
from app.ui.views.enduser import render_enduser
from app.ui.views.login import render_login
from app.ui.views.ombuds import render_ombuds


def _new_chat() -> None:
    st.session_state["messages"] = []
    st.session_state["thread_id"] = None
    st.session_state["last_source_status"] = {}


def _load_thread(thread_id: str) -> None:
    token = st.session_state.get("token")
    st.session_state["messages"] = fetch_thread_messages(token, thread_id) if token else []
    st.session_state["thread_id"] = thread_id
    st.session_state["last_source_status"] = {}


def _sidebar() -> None:
    with st.sidebar:
        st.header("Session")
        user = st.session_state.get("user") or {}
        st.write(f"**User:** {user.get('username', '-')}")
        st.write(f"**Role:** `{user.get('role', '-')}`")

        st.divider()
        if st.button("➕ New conversation", use_container_width=True):
            _new_chat()
            st.rerun()

        st.subheader("Past conversations")
        token = st.session_state.get("token")
        threads = fetch_threads(token) if token else []
        current = st.session_state.get("thread_id")
        if not threads:
            st.caption("No past conversations yet.")
        for t in threads:
            tid = t.get("thread_id")
            label = ("• " if tid == current else "") + (t.get("title") or "(untitled)")
            if st.button(label, key=f"thread_{tid}", use_container_width=True):
                _load_thread(tid)
                st.rerun()

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
