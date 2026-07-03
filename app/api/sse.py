from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any


def _dump(obj: Any) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


def frame(event: str, data: dict[str, Any]) -> dict[str, str]:
    """Format a payload for sse-starlette's `EventSourceResponse`."""
    return {"event": event, "data": _dump(data)}


async def stream_graph_events(
    graph: Any,
    inputs: dict[str, Any],
    config: dict[str, Any],
) -> AsyncIterator[dict[str, str]]:
    """Consume `graph.astream_events(v='v2')` and yield sse-starlette frame dicts."""
    try:
        async for event in graph.astream_events(inputs, config=config, version="v2"):
            evt = event.get("event")
            data = event.get("data", {})
            name = event.get("name", "")

            if evt == "on_chat_model_stream":
                chunk = data.get("chunk")
                delta = getattr(chunk, "content", None) if chunk is not None else None
                if delta:
                    yield frame("token", {"delta": delta})

            elif evt == "on_custom_event":
                # Emitted from nodes via langchain_core.callbacks.dispatch_custom_event(name, payload)
                payload = data if isinstance(data, dict) else {"data": data}
                yield frame(name or "custom", payload)

            elif evt == "on_tool_start":
                yield frame("tool_call_start", {"tool": name})
            elif evt == "on_tool_end":
                out = data.get("output")
                hit_count = len(out) if isinstance(out, list) else None
                yield frame(
                    "tool_call_end",
                    {"tool": name, "hit_count": hit_count, "status": "ok"},
                )
            elif evt == "on_chain_end" and name == "LangGraph":
                final_state = data.get("output") or {}
                messages = final_state.get("messages") or []
                answer = ""
                if messages:
                    last = messages[-1]
                    answer = getattr(last, "content", "") or ""
                yield frame(
                    "final",
                    {
                        "answer": answer,
                        "draft": final_state.get("draft_incident"),
                        "source_status": final_state.get("source_status"),
                    },
                )
    except Exception as e:
        yield frame("error", {"code": "graph_error", "message": str(e)})
