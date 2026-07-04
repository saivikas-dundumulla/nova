from __future__ import annotations

from typing import Any

import httpx

from app.ui.state import api_base


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def fetch_threads(token: str) -> list[dict[str, Any]]:
    """List the user's past conversation threads (most recent first)."""
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{api_base()}/conversations", headers=_headers(token))
            r.raise_for_status()
            return r.json().get("threads", [])
    except httpx.HTTPError:
        return []


def fetch_thread_messages(token: str, thread_id: str) -> list[dict[str, str]]:
    """Return [{'role','content'}] for a past thread, ready to load into the transcript."""
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{api_base()}/conversations/{thread_id}", headers=_headers(token))
            r.raise_for_status()
            raw = r.json().get("messages", [])
    except httpx.HTTPError:
        return []
    return [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in raw]
