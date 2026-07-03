from __future__ import annotations

import time
from typing import Any

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import AzureError, HttpResponseError
from azure.search.documents import SearchClient
from langchain_core.tools import tool

from app.audit.logger import get_audit
from app.config.logging_config import get_app_logger
from app.config.settings import Settings, get_settings
from app.tools.errors import SourceUnavailable
from app.tools.schemas import SearchHit, SearchQuery, SourceType

_log = get_app_logger("tools.azure_search")


def _escape_odata_literal(s: str) -> str:
    """OData string literals escape single quotes by doubling them."""
    return s.replace("'", "''")


def build_filter(
    settings: Settings,
    source_filter: SourceType | None,
    incident_number: str | None,
) -> str | None:
    clauses: list[str] = []
    if source_filter:
        field = settings.azure_search_field_source_type
        clauses.append(f"{field} eq '{_escape_odata_literal(source_filter)}'")
    if incident_number:
        field = settings.azure_search_field_incident_number
        clauses.append(f"{field} eq '{_escape_odata_literal(incident_number)}'")
    return " and ".join(clauses) if clauses else None


def _hit_from_doc(doc: dict[str, Any], settings: Settings, score: float | None) -> SearchHit:
    return SearchHit(
        id=str(doc.get("id") or doc.get("@search.documentKey") or ""),
        source_type=doc.get(settings.azure_search_field_source_type),
        incident_number=doc.get(settings.azure_search_field_incident_number),
        title=doc.get(settings.azure_search_field_title),
        content=doc.get(settings.azure_search_field_content),
        url=doc.get(settings.azure_search_field_url),
        score=score,
    )


def _make_client(settings: Settings) -> SearchClient:
    if not settings.azure_search_endpoint or not settings.azure_search_api_key:
        raise SourceUnavailable("azure_search", "endpoint or api key not configured")
    return SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name,
        credential=AzureKeyCredential(settings.azure_search_api_key),
    )


def run_search(
    query: str,
    source_filter: SourceType | None = None,
    incident_number: str | None = None,
    top_k: int | None = None,
    *,
    user_id: str = "system",
    role: str | None = None,
    thread_id: str | None = None,
    settings: Settings | None = None,
) -> list[SearchHit]:
    """Query the unified Azure AI Search index. Raises SourceUnavailable on failure."""
    s = settings or get_settings()
    k = top_k or s.azure_search_top_k
    filter_expr = build_filter(s, source_filter, incident_number)
    audit = get_audit()
    start = time.perf_counter()
    try:
        client = _make_client(s)
        results = client.search(
            search_text=query,
            filter=filter_expr,
            top=k,
            query_type="semantic",
            semantic_configuration_name=s.azure_search_semantic_config,
        )
        hits = [_hit_from_doc(dict(doc), s, doc.get("@search.score")) for doc in results]
    except (AzureError, HttpResponseError, OSError) as e:
        latency_ms = (time.perf_counter() - start) * 1000
        _log.warning("azure_search_failed", error=str(e), latency_ms=latency_ms)
        audit.emit(
            "tool_call",
            user_id=user_id,
            role=role,
            thread_id=thread_id,
            tool="azure_search_retrieval",
            query=query,
            filters={"source_filter": source_filter, "incident_number": incident_number},
            latency_ms=latency_ms,
            status="error",
            hit_count=0,
        )
        raise SourceUnavailable("azure_search", str(e)) from e

    latency_ms = (time.perf_counter() - start) * 1000
    audit.emit(
        "tool_call",
        user_id=user_id,
        role=role,
        thread_id=thread_id,
        tool="azure_search_retrieval",
        query=query,
        filters={"source_filter": source_filter, "incident_number": incident_number},
        latency_ms=latency_ms,
        status="ok",
        hit_count=len(hits),
    )
    return hits


@tool("azure_search_retrieval", args_schema=SearchQuery)
def azure_search_retrieval(
    query: str,
    source_filter: SourceType | None = None,
    incident_number: str | None = None,
    top_k: int = 8,
) -> list[dict]:
    """Search the unified ServiceNow + Confluence knowledge index.

    Use `source_filter='servicenow'` to restrict to incidents / known issues; use
    `source_filter='confluence'` for KB articles / runbooks. Pass `incident_number`
    to look up a specific incident by number.
    """
    hits = run_search(
        query=query,
        source_filter=source_filter,
        incident_number=incident_number,
        top_k=top_k,
    )
    return [h.model_dump() for h in hits]
