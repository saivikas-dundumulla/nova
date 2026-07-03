from __future__ import annotations

import httpx
import pytest

from app.config.settings import Settings, get_settings
from app.tools.errors import SourceUnavailable
from app.tools.knowledge_base import KnowledgeBaseClient, build_messages
from app.tools.schemas import ChatTurn


def _client_with(handler, settings: Settings | None = None) -> KnowledgeBaseClient:
    transport = httpx.MockTransport(handler)
    ac = httpx.AsyncClient(
        base_url="https://fake.search.windows.net",
        headers={"api-key": "fake-key"},
        transport=transport,
    )
    return KnowledgeBaseClient(settings=settings or get_settings(), client=ac)


def test_build_messages_includes_history_then_prompt():
    history = [ChatTurn(role="user", content="hi"), ChatTurn(role="assistant", content="hello")]
    msgs = build_messages("my question", history)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[-1]["content"][0]["text"] == "my question"


async def test_retrieve_parses_answer_references_and_sources(fake_kb_response):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=fake_kb_response)

    kb = _client_with(handler)
    result = await kb.retrieve("reset vpn", role="enduser", user_id="u1")

    assert "resetting" in result.answer.lower() or "reset" in result.answer.lower()
    assert result.partial is False
    assert result.sources_queried == ["nova-confluence-ks-ext"]
    assert "modelAnswerSynthesis" in result.activity_types
    assert len(result.references) == 1
    assert result.references[0].title == "Reset your VPN password"
    assert result.references[0].url == "https://kb/vpn-reset"
    # Correct endpoint + api-version
    assert "/knowledgebases/nova-kb/retrieve" in captured["url"]
    assert "api-version=2026-05-01-preview" in captured["url"]


async def test_retrieve_marks_partial_on_206(fake_kb_response):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(206, json=fake_kb_response)

    kb = _client_with(handler)
    result = await kb.retrieve("q", role="ombuds", user_id="o1")
    assert result.partial is True


async def test_retrieve_wraps_network_error_as_source_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    # max_retries=0 so the test doesn't wait on backoff
    settings = get_settings().model_copy(update={"azure_search_max_retries": 0})
    kb = _client_with(handler, settings=settings)
    with pytest.raises(SourceUnavailable) as exc:
        await kb.retrieve("q", user_id="u1")
    assert exc.value.source == "azure_search"


async def test_retrieve_wraps_http_500_as_source_unavailable(fake_kb_response):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    settings = get_settings().model_copy(update={"azure_search_max_retries": 0})
    kb = _client_with(handler, settings=settings)
    with pytest.raises(SourceUnavailable):
        await kb.retrieve("q", user_id="u1")
