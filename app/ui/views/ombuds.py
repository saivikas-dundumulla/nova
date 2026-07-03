from __future__ import annotations

import streamlit as st

from app.ui.views._chat import render_chat


def render_ombuds() -> None:
    st.title("Ombuds — investigate an incident")
    st.caption(
        "Provide the incident number and your question. The assistant pulls the "
        "incident and related knowledge-base guidance and returns an investigation summary."
    )
    render_chat(role="ombuds", needs_incident_number=True)
