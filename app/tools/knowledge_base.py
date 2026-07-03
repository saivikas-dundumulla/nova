from __future__ import annotations

import time
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.audit.logger import get_audit
from app.config.logging_config import get_app_logger
from app.config.settings import Settings, get_settings
from app.tools.errors import SourceUnavailable
from app.tools.schemas import ChatTurn, KBReference, KBResult

_log = get_app_logger("tools.knowledge_base")


def build_messages(prompt: str, history: list[ChatTurn] | None = None) -> list[dict[str, Any]]:
    """Build the retrieve `messages` array (prior turns + current user prompt)."""
    messages: list[dict[str, Any]] = []
    for turn in history or []:
        role = turn.role if turn.role in ("user", "assistant") else "user"
        messages.append({"role": role, "content": [{"type": "text", "text": turn.content}]})
    messages.append({"role": "user", "content": [{"type": "text", "text": prompt}]})
    return messages


def _parse_answer(data: dict[str, Any]) -> str:
    for msg in data.get("response", []) or []:
        for part in msg.get("content", []) or []:
            if part.get("type") == "text" and part.get("text"):
                return str(part["text"]).strip()
    return ""


def _parse_references(data: dict[str, Any]) -> list[KBReference]:
    refs: list[KBReference] = []
    for r in data.get("references", []) or []:
        src = r.get("sourceData") if isinstance(r.get("sourceData"), dict) else None
        title = url = None
        if src:
            title = src.get("title") or src.get("name")
            url = src.get("url") or src.get("link")
        refs.append(
            KBReference(
                id=str(r.get("id")) if r.get("id") is not None else None,
                type=r.get("type"),
                doc_key=r.get("docKey"),
                title=title,
                url=url,
                source_data=src,
            )
        )
    return refs


def _parse_activity(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    activity_types: list[str] = []
    sources: list[str] = []
    for a in data.get("activity", []) or []:
        t = a.get("type")
        if t:
            activity_types.append(t)
        name = a.get("knowledgeSourceName")
        if name and name not in sources:
            sources.append(name)
    return activity_types, sources


class KnowledgeBaseClient:
    """Thin async client over the Azure AI Search knowledge base `retrieve` endpoint.

    The knowledge base performs retrieval (over its configured MCP knowledge sources)
    *and* answer synthesis internally, so this app sends a prompt and receives a
    finished, grounded answer — no separate LLM call.
    """

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self._s = settings or get_settings()
        if not self._s.azure_search_endpoint or not self._s.azure_search_api_key:
            raise SourceUnavailable("azure_search", "endpoint or api key not configured")
        self._external_client = client is not None
        self._client = client or httpx.AsyncClient(
            base_url=self._s.azure_search_endpoint.rstrip("/"),
            headers={
                "api-key": self._s.azure_search_api_key,
                "Content-Type": "application/json",
            },
            timeout=self._s.azure_search_timeout_seconds,
        )

    async def aclose(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def _post(self, kb: str, body: dict[str, Any]) -> httpx.Response:
        path = f"/knowledgebases/{kb}/retrieve?api-version={self._s.azure_search_api_version}"
        resp = await self._client.post(path, json=body)
        resp.raise_for_status()  # 206 Partial Content is NOT an error
        return resp

    async def retrieve(
        self,
        prompt: str,
        *,
        knowledge_base: str | None = None,
        history: list[ChatTurn] | None = None,
        role: str | None = None,
        user_id: str = "system",
        thread_id: str | None = None,
    ) -> KBResult:
        kb = knowledge_base or self._s.azure_search_knowledge_base
        body = {"messages": build_messages(prompt, history)}
        audit = get_audit()
        start = time.perf_counter()
        try:
            async for attempt in AsyncRetrying(
                reraise=True,
                stop=stop_after_attempt(self._s.azure_search_max_retries + 1),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
                retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
            ):
                with attempt:
                    resp = await self._post(kb, body)
        except httpx.HTTPError as e:
            latency_ms = (time.perf_counter() - start) * 1000
            _log.warning("kb_retrieve_failed", kb=kb, error=str(e), latency_ms=latency_ms)
            audit.emit(
                "tool_call",
                user_id=user_id,
                role=role,
                thread_id=thread_id,
                tool="knowledge_base",
                query=prompt,
                filters={"knowledge_base": kb},
                latency_ms=latency_ms,
                status="error",
                hit_count=0,
            )
            raise SourceUnavailable("azure_search", str(e)) from e

        data = resp.json()
        answer = _parse_answer(data)
        references = _parse_references(data)
        activity_types, sources = _parse_activity(data)
        partial = resp.status_code == 206
        latency_ms = (time.perf_counter() - start) * 1000

        audit.emit(
            "tool_call",
            user_id=user_id,
            role=role,
            thread_id=thread_id,
            tool="knowledge_base",
            query=prompt,
            filters={"knowledge_base": kb, "sources_queried": sources},
            latency_ms=latency_ms,
            status="partial" if partial else "ok",
            hit_count=len(references),
        )
        return KBResult(
            answer=answer,
            references=references,
            sources_queried=sources,
            activity_types=activity_types,
            partial=partial,
        )
