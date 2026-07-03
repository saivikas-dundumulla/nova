from __future__ import annotations

import json
from pathlib import Path

from app.audit.logger import AuditLogger, hash_query


def test_hash_query_deterministic():
    assert hash_query("hello") == hash_query("hello")
    assert hash_query("hello") != hash_query("world")


def test_hash_query_none_returns_none():
    assert hash_query(None) is None


def test_audit_never_writes_raw_query(_isolate_audit_log: Path):
    audit = AuditLogger()
    secret_query = "employee-name says: personal grievance details"
    audit.emit(
        "tool_call",
        user_id="u1",
        role="enduser",
        thread_id="t1",
        tool="azure_search_retrieval",
        query=secret_query,
        status="ok",
        hit_count=3,
    )
    for h in audit._log.handlers:
        h.flush()
    text = _isolate_audit_log.read_text(encoding="utf-8")
    assert secret_query not in text
    record = json.loads(text.strip().splitlines()[-1])
    assert record["event_type"] == "tool_call"
    assert record["query_hash"] and len(record["query_hash"]) == 64
