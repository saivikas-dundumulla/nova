from __future__ import annotations

import json
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config.settings import Settings, get_settings

# One lock per process is sufficient for a single-instance app; JSON files are small.
_LOCK = threading.Lock()
_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_filename(user_id: str) -> str:
    return _SAFE_ID.sub("_", user_id) or "unknown"


def _conversations_dir(settings: Settings | None = None) -> Path:
    s = settings or get_settings()
    d = Path(s.conversations_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _user_path(user_id: str, settings: Settings | None = None) -> Path:
    return _conversations_dir(settings) / f"{_safe_filename(user_id)}.json"


def _load(user_id: str, settings: Settings | None = None) -> dict[str, Any]:
    path = _user_path(user_id, settings)
    if not path.exists():
        return {"user_id": user_id, "threads": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"user_id": user_id, "threads": []}


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _title_from(text: str, limit: int = 60) -> str:
    t = " ".join((text or "").split())
    return t[:limit] + ("…" if len(t) > limit else "")


def append_turn(
    user_id: str,
    thread_id: str,
    question: str,
    answer: str,
    *,
    incident_number: str | None = None,
    references: list[dict[str, Any]] | None = None,
    cached: bool = False,
    settings: Settings | None = None,
) -> None:
    """Append a user question and its assistant answer to the user's thread (creating it)."""
    ts = _now()
    with _LOCK:
        data = _load(user_id, settings)
        threads: list[dict[str, Any]] = data.setdefault("threads", [])
        thread = next((t for t in threads if t.get("thread_id") == thread_id), None)
        if thread is None:
            thread = {"thread_id": thread_id, "created_at": ts, "updated_at": ts, "messages": []}
            threads.append(thread)
        thread["messages"].append(
            {"role": "user", "content": question, "ts": ts, "incident_number": incident_number}
        )
        thread["messages"].append(
            {"role": "assistant", "content": answer, "ts": ts, "references": references or [], "cached": cached}
        )
        thread["updated_at"] = ts
        _atomic_write(_user_path(user_id, settings), data)


def list_threads(user_id: str, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return thread summaries for a user, most-recently-updated first."""
    data = _load(user_id, settings)
    out: list[dict[str, Any]] = []
    for t in data.get("threads", []):
        msgs = t.get("messages", [])
        first_user = next((m for m in msgs if m.get("role") == "user"), None)
        out.append(
            {
                "thread_id": t.get("thread_id"),
                "title": _title_from(first_user["content"]) if first_user else "(empty)",
                "created_at": t.get("created_at"),
                "updated_at": t.get("updated_at"),
                "message_count": len(msgs),
            }
        )
    out.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return out


def get_thread(user_id: str, thread_id: str, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return the full message list for a thread (empty if not found)."""
    data = _load(user_id, settings)
    thread = next((t for t in data.get("threads", []) if t.get("thread_id") == thread_id), None)
    return thread.get("messages", []) if thread else []


def iter_qa_pairs(user_id: str, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Extract (question, answer) pairs across all of a user's threads for cache lookup."""
    data = _load(user_id, settings)
    pairs: list[dict[str, Any]] = []
    for t in data.get("threads", []):
        msgs = t.get("messages", [])
        for i in range(len(msgs) - 1):
            u, a = msgs[i], msgs[i + 1]
            if u.get("role") == "user" and a.get("role") == "assistant":
                pairs.append(
                    {
                        "question": u.get("content", ""),
                        "incident_number": u.get("incident_number"),
                        "answer": a.get("content", ""),
                        "references": a.get("references", []),
                        "thread_id": t.get("thread_id"),
                        "ts": a.get("ts"),
                    }
                )
    return pairs
