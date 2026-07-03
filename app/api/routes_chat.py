from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.api.sse import stream_graph_events
from app.auth.base import User
from app.auth.deps import get_current_user
from app.graph.builder import get_graph

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    role: Literal["enduser", "ombuds"]
    message: str = Field(..., min_length=1, max_length=8000)
    incident_number: str | None = None
    thread_id: str | None = None


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> EventSourceResponse:
    # Auth check: enduser cannot use ombuds flow (role privilege)
    if body.role != user.role:
        # We deliberately don't 401 here — send an SSE error so the client
        # renders the message in-stream rather than dying opaquely.
        async def _err():
            yield {"event": "error", "data": '{"code":"forbidden","message":"role mismatch"}'}
        return EventSourceResponse(_err())

    graph = get_graph()
    thread_id = body.thread_id or str(uuid.uuid4())
    inputs = {
        "role": body.role,
        "user_id": user.id,
        "thread_id": thread_id,
        "user_query": body.message,
        "incident_number": body.incident_number,
        "messages": [],
        "tool_results": {},
        "source_status": {},
        "errors": [],
    }
    config = {"configurable": {"thread_id": thread_id}}

    async def event_gen():
        async for frame in stream_graph_events(graph, inputs, config):
            if await request.is_disconnected():
                break
            yield frame

    return EventSourceResponse(event_gen())
