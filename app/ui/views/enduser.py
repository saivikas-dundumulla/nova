from __future__ import annotations

import streamlit as st

from app.ui.views._chat import render_chat


def render_enduser() -> None:
    st.title("Self-service — describe your issue")
    st.caption(
        "Describe what's happening in your own words. The assistant searches the "
        "knowledge base (ServiceNow incidents + Confluence articles) and returns a "
        "grounded resolution."
    )
    render_chat(role="enduser", needs_incident_number=False)
