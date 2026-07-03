from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from app.tools.errors import SourceUnavailable
from app.tools.knowledge_base import KnowledgeBaseClient
from app.tools.schemas import ChatTurn


def _dump(obj: Any) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


def frame(event: str, data: dict[str, Any]) -> dict[str, str]:
    """Format a payload for sse-starlette's `EventSourceResponse`."""
    return {"event": event, "data": _dump(data)}


def _chunk_answer(text: str, size: int = 24) -> list[str]:
    """Split the synthesized answer into small chunks to stream a typing effect.

    The retrieve API returns the whole answer at once, so we simulate token streaming
    for the UI rather than blocking on the full response.
    """
    words = text.split(" ")
    chunks: list[str] = []
    buf = ""
    for w in words:
        buf = w if not buf else f"{buf} {w}"
        if len(buf) >= size:
            chunks.append(buf + " ")
            buf = ""
    if buf:
        chunks.append(buf)
    return chunks


async def stream_kb_answer(
    *,
    prompt: str,
    knowledge_base: str,
    history: list[ChatTurn],
    role: str,
    user_id: str,
    thread_id: str,
    client: KnowledgeBaseClient | None = None,
) -> AsyncIterator[dict[str, str]]:
    """Query the knowledge base and stream SSE frames (status, chunked answer, final)."""
    kb = client or KnowledgeBaseClient()
    yield frame("tool_call_start", {"tool": f"knowledge_base:{knowledge_base}"})
    try:
        result = await kb.retrieve(
            prompt,
            knowledge_base=knowledge_base,
            history=history,
            role=role,
            user_id=user_id,
            thread_id=thread_id,
        )
    except SourceUnavailable as e:
        yield frame("source_status", {"source": "azure_search", "status": "down"})
        yield frame("error", {"code": "source_unavailable", "message": str(e)})
        return
    except Exception as e:
        yield frame("error", {"code": "kb_error", "message": str(e)})
        return
    finally:
        if client is None:
            await kb.aclose()

    yield frame(
        "tool_call_end",
        {
            "tool": f"knowledge_base:{knowledge_base}",
            "status": "partial" if result.partial else "ok",
            "hit_count": len(result.references),
            "sources_queried": result.sources_queried,
        },
    )
    if result.partial:
        yield frame("source_status", {"source": "azure_search", "status": "degraded"})

    for chunk in _chunk_answer(result.answer):
        yield frame("token", {"delta": chunk})

    yield frame(
        "final",
        {
            "answer": result.answer,
            "references": [r.model_dump() for r in result.references],
            "sources_queried": result.sources_queried,
            "partial": result.partial,
        },
    )
