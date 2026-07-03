from __future__ import annotations

from typing import Any

import streamlit as st

from app.ui.sse_client import SSEEvent, iter_sse
from app.ui.state import api_base, append_message


def _render_source_status(status: dict[str, str]) -> None:
    if not status:
        return
    parts = []
    for src, st_ in status.items():
        icon = {"ok": "✅", "degraded": "⚠️", "down": "❌"}.get(st_, "•")
        parts.append(f"{icon} {src}: {st_}")
    st.caption(" · ".join(parts))


def _render_references(refs: list[dict[str, Any]]) -> None:
    if not refs:
        return
    with st.expander(f"References ({len(refs)})", expanded=False):
        for i, r in enumerate(refs, 1):
            title = r.get("title") or r.get("doc_key") or f"reference {r.get('id', i)}"
            url = r.get("url")
            src = r.get("type") or "source"
            st.markdown(f"{i}. [{title}]({url}) — _{src}_" if url else f"{i}. {title} — _{src}_")


def render_chat(role: str, needs_incident_number: bool) -> None:
    # Prior messages
    for msg in st.session_state.get("messages", []):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    _render_source_status(st.session_state.get("last_source_status") or {})

    incident_number: str | None = None
    if needs_incident_number:
        incident_number = st.text_input(
            "Incident number",
            value="",
            placeholder="INC0012345",
            key="incident_number_input",
        )

    user_message = st.chat_input("Type your question…")
    if not user_message:
        return
    if needs_incident_number and not incident_number:
        st.warning("Please enter an incident number first.")
        return

    # History = everything already in the transcript (before this new turn).
    history = list(st.session_state.get("messages", []))

    append_message("user", user_message)
    with st.chat_message("user"):
        st.markdown(user_message)

    token = st.session_state.get("token")
    if not token:
        st.error("Not authenticated.")
        return

    body = {
        "role": role,
        "message": user_message,
        "incident_number": incident_number,
        "history": history,
        "thread_id": st.session_state.get("thread_id"),
    }
    headers = {"Authorization": f"Bearer {token}"}

    with st.chat_message("assistant"):
        status_slot = st.empty()
        answer_slot = st.empty()
        status_events: list[str] = []
        source_status: dict[str, str] = dict(st.session_state.get("last_source_status") or {})
        answer_buf: list[str] = []
        references: list[dict[str, Any]] = []

        try:
            for evt in iter_sse(f"{api_base()}/chat/stream", json_body=body, headers=headers):
                evt: SSEEvent
                if evt.event == "token":
                    answer_buf.append(evt.data.get("delta", ""))
                    answer_slot.markdown("".join(answer_buf))
                elif evt.event == "tool_call_start":
                    status_events.append(f"⏳ {evt.data.get('tool', '?')} …")
                    status_slot.info(" · ".join(status_events[-3:]))
                elif evt.event == "tool_call_end":
                    tool = evt.data.get("tool", "?")
                    srcs = evt.data.get("sources_queried") or []
                    label = f"✔ {tool}" + (f" (sources: {', '.join(srcs)})" if srcs else "")
                    status_events.append(label)
                    status_slot.info(" · ".join(status_events[-3:]))
                elif evt.event == "source_status":
                    source_status[evt.data.get("source", "?")] = evt.data.get("status", "?")
                elif evt.event == "final":
                    if not answer_buf:  # fallback if no token frames were sent
                        answer_buf.append(evt.data.get("answer", ""))
                        answer_slot.markdown("".join(answer_buf))
                    references = evt.data.get("references") or []
                elif evt.event == "error":
                    st.error(f"Error: {evt.data.get('message', 'unknown')}")
        except Exception as e:
            st.error(f"Streaming failed: {e}")

        status_slot.empty()
        _render_source_status(source_status)
        _render_references(references)
        st.session_state["last_source_status"] = source_status

    final_answer = "".join(answer_buf).strip() or "(no response)"
    append_message("assistant", final_answer)
