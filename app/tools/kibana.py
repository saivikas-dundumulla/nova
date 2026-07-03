from __future__ import annotations

import re
import time
from typing import Any

import httpx
from langchain_core.tools import tool
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.audit.logger import get_audit
from app.config.logging_config import get_app_logger
from app.config.settings import Settings, get_settings
from app.tools.errors import SourceUnavailable
from app.tools.schemas import KibanaQuery, LogHit

_log = get_app_logger("tools.kibana")
_TIME_RANGE_RE = re.compile(r"^\d+[smhdw]$")


def _normalize_time_range(tr: str) -> str:
    tr = tr.strip().lower()
    if not _TIME_RANGE_RE.match(tr):
        raise ValueError(f"invalid time_range {tr!r}, expected like '15m', '1h', '24h'")
    return tr


def build_es_query(query: str, service: str | None, time_range: str, max_hits: int) -> dict:
    tr = _normalize_time_range(time_range)
    must: list[dict[str, Any]] = [{"query_string": {"query": query, "default_field": "message"}}]
    if service:
        must.append({"term": {"service.name": service}})
    return {
        "size": max_hits,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "query": {
            "bool": {
                "must": must,
                "filter": [{"range": {"@timestamp": {"gte": f"now-{tr}", "lte": "now"}}}],
            }
        },
    }


def _hit_from_source(src: dict[str, Any]) -> LogHit:
    service = src.get("service", {})
    return LogHit(
        ts=src.get("@timestamp"),
        service=service.get("name") if isinstance(service, dict) else str(service or ""),
        level=src.get("log", {}).get("level") if isinstance(src.get("log"), dict) else src.get("level"),
        message=src.get("message"),
        trace_id=src.get("trace", {}).get("id") if isinstance(src.get("trace"), dict) else src.get("trace_id"),
        raw=src,
    )


class KibanaClient:
    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self._s = settings or get_settings()
        if not self._s.kibana_url:
            raise SourceUnavailable("kibana", "url not configured")
        headers = {
            "kbn-xsrf": "true",
            "Content-Type": "application/json",
        }
        if self._s.kibana_api_key:
            headers["Authorization"] = f"ApiKey {self._s.kibana_api_key}"
        self._client = client or httpx.Client(
            base_url=self._s.kibana_url.rstrip("/"),
            headers=headers,
            timeout=self._s.kibana_timeout_seconds,
        )

    def close(self) -> None:  # pragma: no cover
        self._client.close()

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.3, min=0.3, max=2.0),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    )
    def _search(self, body: dict) -> dict:
        # Direct ES `_search` via Kibana's proxy path. Adjust if your Kibana disallows the proxy.
        path = f"/api/console/proxy?path=/{self._s.kibana_index_pattern}/_search&method=POST"
        resp = self._client.post(path, json=body)
        resp.raise_for_status()
        return resp.json()

    def search(self, query: str, service: str | None, time_range: str, max_hits: int) -> list[LogHit]:
        body = build_es_query(query, service, time_range, max_hits)
        try:
            data = self._search(body)
        except (httpx.HTTPError, RetryError) as e:
            raise SourceUnavailable("kibana", str(e)) from e
        hits_raw = data.get("hits", {}).get("hits", [])
        return [_hit_from_source(h.get("_source", {})) for h in hits_raw]


def run_kibana(
    query: str,
    service: str | None = None,
    time_range: str | None = None,
    max_hits: int | None = None,
    *,
    user_id: str = "system",
    role: str | None = None,
    thread_id: str | None = None,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> list[LogHit]:
    s = settings or get_settings()
    tr = time_range or s.kibana_default_time_range
    mh = max_hits or s.kibana_max_hits
    audit = get_audit()
    start = time.perf_counter()
    try:
        kibana = KibanaClient(settings=s, client=client)
        hits = kibana.search(query=query, service=service, time_range=tr, max_hits=mh)
    except SourceUnavailable:
        latency_ms = (time.perf_counter() - start) * 1000
        audit.emit(
            "tool_call",
            user_id=user_id,
            role=role,
            thread_id=thread_id,
            tool="kibana_search",
            query=query,
            filters={"service": service, "time_range": tr},
            latency_ms=latency_ms,
            status="error",
            hit_count=0,
        )
        raise

    latency_ms = (time.perf_counter() - start) * 1000
    audit.emit(
        "tool_call",
        user_id=user_id,
        role=role,
        thread_id=thread_id,
        tool="kibana_search",
        query=query,
        filters={"service": service, "time_range": tr},
        latency_ms=latency_ms,
        status="ok",
        hit_count=len(hits),
    )
    return hits


@tool("kibana_search", args_schema=KibanaQuery)
def kibana_search(
    query: str,
    service: str | None = None,
    time_range: str = "24h",
    max_hits: int = 25,
) -> list[dict]:
    """Search Kibana / Elasticsearch application logs.

    `service` is an optional service.name filter. `time_range` is a window ending now
    (e.g. '15m', '1h', '24h'). Returns recent log hits sorted newest-first.
    """
    hits = run_kibana(query=query, service=service, time_range=time_range, max_hits=max_hits)
    return [h.model_dump() for h in hits]
