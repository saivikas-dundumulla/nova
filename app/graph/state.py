from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

Role = Literal["enduser", "ombuds"]
SourceStatus = Literal["ok", "degraded", "down"]


class OmbudsState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    role: Role
    user_id: str
    thread_id: str
    incident_number: str | None
    user_query: str
    tool_results: dict[str, Any]  # {"search": [...], "kibana": [...]}
    source_status: dict[str, SourceStatus]
    draft_incident: dict[str, Any] | None
    awaiting_confirmation: bool
    errors: list[str]
