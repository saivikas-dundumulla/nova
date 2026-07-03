from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "login",
    "login_failed",
    "logout",
    "tool_call",
    "graph_run",
    "graph_error",
    "draft_created",
    "draft_confirmed",
]


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


class AuditEvent(BaseModel):
    ts: str = Field(default_factory=_utcnow_iso)
    event_type: EventType
    user_id: str
    role: str | None = None
    thread_id: str | None = None
    tool: str | None = None
    query_hash: str | None = None
    filters: dict[str, Any] | None = None
    latency_ms: float | None = None
    status: str | None = None
    hit_count: int | None = None
    source_status: dict[str, str] | None = None
    message: str | None = None  # short, non-PII (e.g. "kibana degraded")
