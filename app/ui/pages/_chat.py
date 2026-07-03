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
        icon = {"ok": "✅", "degraded": "⚠️", "down": "❌", "skipped": "⏭️"}.get(st_, "•")
        parts.append(f"{icon} {src}: {st_}")
    st.caption(" · ".join(parts))


def _render_draft(draft: dict[str, Any]) -> None:
    with st.container(border=True):
        st.subheader("Draft escalation")
        st.caption(
            "The assistant couldn't resolve the issue from the knowledge base. "
            "Copy this draft when opening a ticket."
        )
        st.text_input("Short description", value=draft.get("short_description", ""), key="draft_sd")
        cols = st.columns(2)
        cols[0].text_input("Category", value=draft.get("category", ""), key="draft_cat")
        cols[1].text_input(
            "Suggested priority",
            value=draft.get("suggested_priority", "medium"),
            key="draft_pri",
        )
        st.text_area("Description", value=draft.get("description", ""), height=200, key="draft_desc")
        evidence = draft.get("evidence") or []
        if evidence:
            st.markdown("**Evidence**")
            for e in evidence:
                title = e.get("title", "")
                url = e.get("url", "")
                st.markdown(f"- [{title}]({url})" if url else f"- {title}")


def render_chat(role: str, needs_incident_number: bool) -> None:
    # Prior messages
    for msg in st.session_state.get("messages", []):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if st.session_state.get("last_draft"):
        _render_draft(st.session_state["last_draft"])
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
        "thread_id": st.session_state.get("thread_id"),
    }
    headers = {"Authorization": f"Bearer {token}"}

    with st.chat_message("assistant"):
        status_slot = st.empty()
        answer_slot = st.empty()
        status_events: list[str] = []
        source_status: dict[str, str] = dict(st.session_state.get("last_source_status") or {})
        answer_buf: list[str] = []
        draft: dict[str, Any] | None = None

        try:
            for evt in iter_sse(
                f"{api_base()}/chat/stream", json_body=body, headers=headers
            ):
                evt: SSEEvent
                if evt.event == "token":
                    delta = evt.data.get("delta", "")
                    answer_buf.append(delta)
                    answer_slot.markdown("".join(answer_buf))
                elif evt.event == "tool_call_start":
                    status_events.append(f"⏳ {evt.data.get('tool', '?')} …")
                    status_slot.info(" · ".join(status_events[-3:]))
                elif evt.event == "tool_call_end":
                    tool = evt.data.get("tool", "?")
                    hits = evt.data.get("hit_count")
                    status_events.append(f"✔ {tool} ({hits} hits)")
                    status_slot.info(" · ".join(status_events[-3:]))
                elif evt.event == "source_status":
                    source_status[evt.data.get("source", "?")] = evt.data.get("status", "?")
                elif evt.event == "draft":
                    draft = evt.data.get("draft") or evt.data
                elif evt.event == "final":
                    if not answer_buf:  # non-streaming fallback
                        answer_buf.append(evt.data.get("answer", ""))
                        answer_slot.markdown("".join(answer_buf))
                    if evt.data.get("draft"):
                        draft = evt.data["draft"]
                    if evt.data.get("source_status"):
                        source_status.update(evt.data["source_status"])
                elif evt.event == "error":
                    st.error(f"Error: {evt.data.get('message', 'unknown')}")
        except Exception as e:
            st.error(f"Streaming failed: {e}")

        status_slot.empty()
        _render_source_status(source_status)
        st.session_state["last_source_status"] = source_status

    final_answer = "".join(answer_buf).strip() or "(no response)"
    append_message("assistant", final_answer)
    st.session_state["last_draft"] = draft
    if draft:
        _render_draft(draft)
