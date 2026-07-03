from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class SSEEvent:
    event: str
    data: dict[str, Any]


def _parse_sse_line(buf: list[str]) -> SSEEvent | None:
    """Parse one SSE message from buffered lines. Returns None if no event data present."""
    event = "message"
    data_lines: list[str] = []
    for line in buf:
        if not line:
            continue
        if line.startswith(":"):
            continue  # comment/keepalive
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip())
    if not data_lines:
        return None
    raw = "\n".join(data_lines)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"raw": raw}
    if not isinstance(payload, dict):
        payload = {"value": payload}
    return SSEEvent(event=event, data=payload)


def iter_sse(
    url: str,
    *,
    json_body: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: float = 300.0,
) -> Iterator[SSEEvent]:
    """Blocking SSE consumer; yields typed events as they arrive.

    Streamlit runs synchronously, so a sync httpx client is fine here.
    """
    hdrs = {"Accept": "text/event-stream", **(headers or {})}
    with httpx.Client(timeout=httpx.Timeout(timeout, read=None)) as client:
        with client.stream("POST", url, json=json_body, headers=hdrs) as resp:
            resp.raise_for_status()
            buf: list[str] = []
            for line in resp.iter_lines():
                if line == "":
                    evt = _parse_sse_line(buf)
                    buf = []
                    if evt is not None:
                        yield evt
                else:
                    buf.append(line)
            if buf:
                evt = _parse_sse_line(buf)
                if evt is not None:
                    yield evt
