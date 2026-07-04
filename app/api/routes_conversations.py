from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.auth.base import User
from app.auth.deps import get_current_user
from app.memory import store

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """List the current user's past conversation threads (most recent first)."""
    return {"threads": store.list_threads(user.id)}


@router.get("/{thread_id}")
async def get_conversation(
    thread_id: str, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """Return the full message transcript for one of the current user's threads."""
    return {"thread_id": thread_id, "messages": store.get_thread(user.id, thread_id)}
