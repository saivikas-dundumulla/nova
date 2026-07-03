from __future__ import annotations

import httpx
import streamlit as st

from app.ui.state import api_base, set_api_base


def render_login() -> None:
    st.title("Nova — Ombuds Assistant")
    st.caption("Sign in to continue.")

    with st.expander("API endpoint", expanded=False):
        cur = api_base()
        new_url = st.text_input("API base URL", value=cur)
        if new_url and new_url != cur:
            set_api_base(new_url)

    with st.form("login-form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    if not submitted:
        return

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"{api_base()}/login",
                json={"username": username, "password": password},
            )
        if resp.status_code != 200:
            detail = "invalid credentials"
            try:
                detail = resp.json().get("detail", detail)
            except Exception:
                pass
            st.error(f"Login failed: {detail}")
            return
        payload = resp.json()
    except httpx.HTTPError as e:
        st.error(f"Could not reach API: {e}")
        return

    st.session_state["token"] = payload["token"]
    st.session_state["user"] = payload["user"]
    st.session_state["messages"] = []
    st.session_state["thread_id"] = None
    st.rerun()
