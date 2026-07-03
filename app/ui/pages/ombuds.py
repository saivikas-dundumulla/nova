from __future__ import annotations

import streamlit as st

from app.ui.pages._chat import render_chat


def render_ombuds() -> None:
    st.title("Ombuds — investigate an incident")
    st.caption(
        "Provide the incident number and any additional context. The assistant will "
        "pull the incident, find related KB articles, and correlate log findings."
    )
    render_chat(role="ombuds", needs_incident_number=True)
