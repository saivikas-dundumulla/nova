from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.tools.errors import SourceUnavailable
from app.tools.schemas import KBReference, KBResult
from tests.conftest import TEST_PASSWORD


class _FakeKB:
    def __init__(self, result: KBResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls: list[dict[str, Any]] = []

    async def retrieve(self, prompt, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        if self._error:
            raise self._error
        return self._result

    async def aclose(self):
        pass


def _sse_frames(response: httpx.Response) -> list[dict[str, Any]]:
    proper: list[dict[str, Any]] = []
    buf: list[str] = []
    for raw in response.iter_lines():
        line = raw if isinstance(raw, str) else raw.decode("utf-8")
        if line == "":
            if buf:
                event, data = "message", ""
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


def _login(client: TestClient, username: str) -> str:
    r = client.post("/login", json={"username": username, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_chat_stream_enduser_happy_path():
    result = KBResult(
        answer="Try resetting your VPN password via Settings.",
        references=[KBReference(id="0", type="mcpServer", title="VPN reset", url="https://kb/vpn")],
        sources_queried=["nova-confluence-ks-ext"],
        activity_types=["modelQueryPlanning", "mcpServer", "modelAnswerSynthesis"],
    )
    fake = _FakeKB(result=result)
    with patch("app.api.sse.KnowledgeBaseClient", return_value=fake):
        app = create_app()
        with TestClient(app) as client:
            token = _login(client, "enduser1")
            r = client.post(
                "/chat/stream",
                headers={"Authorization": f"Bearer {token}"},
                json={"role": "enduser", "message": "vpn broke"},
            )
            assert r.status_code == 200
            events = _sse_frames(r)

    names = [e["event"] for e in events]
    assert "tool_call_start" in names
    assert "tool_call_end" in names
    assert "token" in names  # answer chunked into token frames
    final = [e for e in events if e["event"] == "final"]
    assert final
    assert "resetting" in final[-1]["data"]["answer"].lower()
    assert final[-1]["data"]["references"][0]["title"] == "VPN reset"


def test_chat_stream_ombuds_prompt_includes_incident_number():
    fake = _FakeKB(result=KBResult(answer="Investigation summary."))
    with patch("app.api.sse.KnowledgeBaseClient", return_value=fake):
        app = create_app()
        with TestClient(app) as client:
            token = _login(client, "ombuds1")
            r = client.post(
                "/chat/stream",
                headers={"Authorization": f"Bearer {token}"},
                json={"role": "ombuds", "message": "what happened", "incident_number": "INC0012345"},
            )
            assert r.status_code == 200
            _sse_frames(r)

    assert fake.calls, "KB was not called"
    assert "INC0012345" in fake.calls[0]["prompt"]


def test_chat_stream_role_mismatch_returns_error_frame():
    with patch("app.api.sse.KnowledgeBaseClient", return_value=_FakeKB(result=KBResult(answer="x"))):
        app = create_app()
        with TestClient(app) as client:
            token = _login(client, "enduser1")
            r = client.post(
                "/chat/stream",
                headers={"Authorization": f"Bearer {token}"},
                json={"role": "ombuds", "message": "INC1", "incident_number": "INC1"},
            )
            events = _sse_frames(r)
    err = [e for e in events if e["event"] == "error"]
    assert err and err[0]["data"]["code"] == "forbidden"


def test_chat_stream_source_unavailable_emits_error_not_500():
    fake = _FakeKB(error=SourceUnavailable("azure_search", "down"))
    with patch("app.api.sse.KnowledgeBaseClient", return_value=fake):
        app = create_app()
        with TestClient(app) as client:
            token = _login(client, "enduser1")
            r = client.post(
                "/chat/stream",
                headers={"Authorization": f"Bearer {token}"},
                json={"role": "enduser", "message": "hi"},
            )
            assert r.status_code == 200  # stream opened fine
            events = _sse_frames(r)

    names = [e["event"] for e in events]
    assert "source_status" in names
    assert "error" in names
