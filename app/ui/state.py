from __future__ import annotations

from typing import Any

import streamlit as st


def init_session_state() -> None:
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("token", None)
    st.session_state.setdefault("messages", [])  # list[{"role":"user|assistant","content":str}]
    st.session_state.setdefault("thread_id", None)
    st.session_state.setdefault("last_source_status", {})


def is_logged_in() -> bool:
    return bool(st.session_state.get("token")) and bool(st.session_state.get("user"))


def logout() -> None:
    for k in ("user", "token", "messages", "thread_id", "last_source_status"):
        st.session_state.pop(k, None)
    init_session_state()


def append_message(role: str, content: str) -> None:
    st.session_state["messages"].append({"role": role, "content": content})


def api_base() -> str:
    import os

    return (
        st.session_state.get("api_base")
        or os.environ.get("NOVA_API_BASE")
        or "http://127.0.0.1:8000"
    )


def set_api_base(url: str) -> None:
    st.session_state["api_base"] = url


def user_role() -> str | None:
    u: Any = st.session_state.get("user")
    if isinstance(u, dict):
        return u.get("role")
    return None
