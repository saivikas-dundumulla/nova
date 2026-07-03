from __future__ import annotations

import hashlib
from typing import Any

from app.audit.events import AuditEvent, EventType
from app.config.logging_config import get_audit_logger
from app.config.settings import get_settings


def hash_query(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _maybe_hash_user(user_id: str) -> str:
    s = get_settings()
    if not s.audit_hash_user_id:
        return user_id
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]


class AuditLogger:
    """Emit JSONL audit events. Never logs raw query text or incident bodies."""

    def __init__(self) -> None:
        self._log = get_audit_logger()

    def emit(
        self,
        event_type: EventType,
        *,
        user_id: str,
        role: str | None = None,
        thread_id: str | None = None,
        tool: str | None = None,
        query: str | None = None,
        filters: dict[str, Any] | None = None,
        latency_ms: float | None = None,
        status: str | None = None,
        hit_count: int | None = None,
        source_status: dict[str, str] | None = None,
        message: str | None = None,
    ) -> None:
        event = AuditEvent(
            event_type=event_type,
            user_id=_maybe_hash_user(user_id),
            role=role,
            thread_id=thread_id,
            tool=tool,
            query_hash=hash_query(query),
            filters=filters,
            latency_ms=latency_ms,
            status=status,
            hit_count=hit_count,
            source_status=source_status,
            message=message,
        )
        self._log.info(event.model_dump_json())


_singleton: AuditLogger | None = None


def get_audit() -> AuditLogger:
    global _singleton
    if _singleton is None:
        _singleton = AuditLogger()
    return _singleton
