from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.api.main import create_app
from tests.conftest import TEST_PASSWORD


class _FakeAzureLLM:
    """Stand-in for `AzureChatOpenAI` used by the synthesize node."""

    def __init__(self, reply: str = "Here is the resolution.") -> None:
        self.reply = reply

    def invoke(self, messages):
        return AIMessage(content=self.reply)


def _sse_frames(response: httpx.Response) -> list[dict[str, Any]]:
    """Parse a raw SSE body into a list of {'event', 'data'} dicts."""
    frames: list[dict[str, Any]] = []
    for chunk in response.iter_lines():
        chunk_text = chunk if isinstance(chunk, str) else chunk.decode("utf-8")
        # httpx.iter_lines already strips newlines and yields per-line strings
        # We need to buffer until blank line for SSE semantics.
        frames.append({"line": chunk_text})
    # Rebuild proper SSE frames
    proper: list[dict[str, Any]] = []
    buf: list[str] = []
    for f in frames:
        line = f["line"]
        if line == "":
            if buf:
                event = "message"
                data = ""
                for L in buf:
                    if L.startswith("event:"):
                        event = L[len("event:"):].strip()
                    elif L.startswith("data:"):
                        data = L[len("data:"):].lstrip()
                if data:
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError:
                        payload = {"raw": data}
                    proper.append({"event": event, "data": payload})
                buf = []
        else:
            buf.append(line)
    return proper


def _login_as(client: TestClient, username: str) -> str:
    r = client.post("/login", json={"username": username, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@patch("app.graph.nodes._build_llm")
@patch("app.tools.azure_search._make_client")
def test_chat_stream_enduser_happy_path(mock_search_client, mock_build_llm, fake_search_hits):
    mock_client = MagicMock()
    mock_client.search.return_value = [
        {**h, "@search.score": h["score"]} for h in fake_search_hits
    ]
    mock_search_client.return_value = mock_client
    mock_build_llm.return_value = _FakeAzureLLM(
        reply="Try resetting your VPN password (see the linked KB). This resolves the issue."
    )

    app = create_app()
    with TestClient(app) as client:
        token = _login_as(client, "enduser1")
        r = client.post(
            "/chat/stream",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "enduser", "message": "vpn stopped working"},
        )
        assert r.status_code == 200
        events = _sse_frames(r)

    event_names = [e["event"] for e in events]
    # We expect at minimum a tool_call_start/end pair for azure_search and a final frame
    assert any(n == "tool_call_start" for n in event_names)
    assert any(n == "tool_call_end" for n in event_names)
    final = [e for e in events if e["event"] == "final"]
    assert final, f"expected a final event, got {event_names}"
    assert "resetting" in (final[-1]["data"].get("answer") or "").lower()


@patch("app.graph.nodes._build_llm")
@patch("app.tools.azure_search._make_client")
def test_chat_stream_role_mismatch_returns_error_frame(mock_search_client, mock_build_llm):
    mock_build_llm.return_value = _FakeAzureLLM()
    app = create_app()
    with TestClient(app) as client:
        token = _login_as(client, "enduser1")  # end user
        r = client.post(
            "/chat/stream",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "ombuds", "message": "INC0012345", "incident_number": "INC0012345"},
        )
        events = _sse_frames(r)
    err = [e for e in events if e["event"] == "error"]
    assert err, "expected an error frame for role mismatch"
    assert err[0]["data"]["code"] == "forbidden"


@patch("app.graph.nodes._build_llm")
@patch("app.tools.azure_search._make_client")
def test_chat_stream_kibana_down_still_finishes(mock_search_client, mock_build_llm, fake_search_hits):
    mock_client = MagicMock()
    mock_client.search.return_value = [
        {**h, "@search.score": h["score"]} for h in fake_search_hits
    ]
    mock_search_client.return_value = mock_client
    mock_build_llm.return_value = _FakeAzureLLM(reply="Investigation summary here.")

    # Force kibana to fail at network level
    def fail_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    with patch("app.tools.kibana.KibanaClient._search", side_effect=Exception("boom")):
        app = create_app()
        with TestClient(app) as client:
            token = _login_as(client, "ombuds1")
            r = client.post(
                "/chat/stream",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "role": "ombuds",
                    "message": "vpn issue",
                    "incident_number": "INC0012345",
                },
            )
            events = _sse_frames(r)

    # Even with Kibana broken, we get a final answer
    final = [e for e in events if e["event"] == "final"]
    assert final, f"expected a final event, got {[e['event'] for e in events]}"
    # And a source_status frame reflecting the degradation
    src = [e for e in events if e["event"] == "source_status"]
    assert any(e["data"].get("source") == "kibana" for e in src), (
        f"expected a kibana source_status event, got {[e['event'] for e in events]}"
    )
