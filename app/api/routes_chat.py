from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.api.sse import frame, stream_kb_answer
from app.auth.base import User
from app.auth.deps import get_current_user
from app.config.settings import get_settings
from app.tools.schemas import ChatTurn

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    role: Literal["enduser", "ombuds"]
    message: str = Field(..., min_length=1, max_length=8000)
    incident_number: str | None = None
    history: list[ChatTurn] = Field(default_factory=list)
    thread_id: str | None = None


def _compose_prompt(role: str, message: str, incident_number: str | None) -> str:
    """Frame the prompt for the knowledge base based on persona."""
    if role == "ombuds" and incident_number:
        return (
            f"I am an ombudsman investigating incident {incident_number}. "
            f"Pull the incident details and any related knowledge-base guidance. "
            f"Question: {message}"
        )
    return message


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> EventSourceResponse:
    # Role privilege: a user may only use their own persona's flow.
    if body.role != user.role:
        async def _err():
            yield frame("error", {"code": "forbidden", "message": "role mismatch"})
        return EventSourceResponse(_err())

    settings = get_settings()
    thread_id = body.thread_id or str(uuid.uuid4())
    prompt = _compose_prompt(body.role, body.message, body.incident_number)
    kb = settings.knowledge_base_for_role(body.role)

    async def event_gen():
        async for f in stream_kb_answer(
            prompt=prompt,
            knowledge_base=kb,
            history=body.history,
            role=body.role,
            user_id=user.id,
            thread_id=thread_id,
        ):
            if await request.is_disconnected():
                break
            yield f

    return EventSourceResponse(event_gen())
