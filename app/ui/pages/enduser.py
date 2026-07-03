from __future__ import annotations

import streamlit as st

from app.ui.pages._chat import render_chat


def render_enduser() -> None:
    st.title("Self-service — describe your issue")
    st.caption(
        "Describe what's happening in your own words. The assistant will search "
        "knowledge articles and, if it's a technical issue, application logs."
    )
    render_chat(role="enduser", needs_incident_number=False)
