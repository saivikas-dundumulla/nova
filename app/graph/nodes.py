from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.callbacks.manager import dispatch_custom_event
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from app.audit.logger import get_audit
from app.config.logging_config import get_app_logger
from app.config.settings import Settings, get_settings
from app.graph.prompts import ENDUSER_SYSTEM, OMBUDS_SYSTEM
from app.graph.state import OmbudsState
from app.tools.azure_search import run_search
from app.tools.errors import SourceUnavailable
from app.tools.kibana import run_kibana
from app.tools.schemas import SearchHit

_log = get_app_logger("graph.nodes")

_KIBANA_HINT_RE = re.compile(
    r"\b(error|exception|failed|failure|timeout|500|502|503|504|crash|log|logs|"
    r"traceback|stack ?trace|panic|denied)\b",
    re.IGNORECASE,
)
_DRAFT_BLOCK_RE = re.compile(r"<draft>\s*(\{.*?\})\s*</draft>", re.DOTALL)


def _emit_custom(name: str, payload: dict[str, Any]) -> None:
    """Emit a custom stream event so FastAPI can forward it as an SSE frame."""
    try:
        dispatch_custom_event(name, payload)
    except Exception:  # pragma: no cover — outside a streaming context
        pass


def _build_llm(settings: Settings) -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        azure_deployment=settings.azure_openai_deployment,
        temperature=settings.azure_openai_temperature,
        streaming=True,
    )


# ---------- nodes ----------

def router(state: OmbudsState) -> OmbudsState:
    role = state.get("role", "enduser")
    user_query = state.get("user_query") or ""
    # Enduser: heuristic-toggle kibana. Ombuds: always try Kibana.
    want_kibana = role == "ombuds" or bool(_KIBANA_HINT_RE.search(user_query))
    status: dict[str, str] = state.get("source_status", {}) or {}
    return {
        "source_status": {**status, "azure_search": "ok", "kibana": "ok" if want_kibana else "skipped"},
        "tool_results": state.get("tool_results") or {},
        "errors": state.get("errors") or [],
        "awaiting_confirmation": False,
        "draft_incident": None,
    }  # type: ignore[return-value]


def retrieve_search(state: OmbudsState) -> OmbudsState:
    role = state.get("role", "enduser")
    query = state.get("user_query") or ""
    incident_number = state.get("incident_number")
    user_id = state.get("user_id", "system")
    thread_id = state.get("thread_id")
    hits: list[SearchHit] = []
    kb_hits: list[SearchHit] = []
    source_status = dict(state.get("source_status") or {})

    _emit_custom("tool_call_start", {"tool": "azure_search_retrieval", "phase": "primary"})
    try:
        if role == "ombuds" and incident_number:
            # 1) exact-match on incident number
            hits = run_search(
                query=query or incident_number,
                incident_number=incident_number,
                user_id=user_id,
                role=role,
                thread_id=thread_id,
            )
            _emit_custom(
                "tool_call_end",
                {"tool": "azure_search_retrieval", "phase": "primary", "hit_count": len(hits)},
            )
            # 2) related KBs
            _emit_custom("tool_call_start", {"tool": "azure_search_retrieval", "phase": "kb"})
            kb_query = (hits[0].title or query) if hits else query
            kb_hits = run_search(
                query=kb_query or "",
                source_filter="confluence",
                user_id=user_id,
                role=role,
                thread_id=thread_id,
            )
            _emit_custom(
                "tool_call_end",
                {"tool": "azure_search_retrieval", "phase": "kb", "hit_count": len(kb_hits)},
            )
        else:
            hits = run_search(
                query=query,
                user_id=user_id,
                role=role,
                thread_id=thread_id,
            )
            _emit_custom(
                "tool_call_end",
                {"tool": "azure_search_retrieval", "phase": "primary", "hit_count": len(hits)},
            )
    except SourceUnavailable as e:
        _log.warning("azure_search_degraded", error=str(e))
        source_status["azure_search"] = "down"
        _emit_custom("source_status", {"source": "azure_search", "status": "down"})
    except Exception as e:
        _log.exception("azure_search_unexpected_error", error=str(e))
        source_status["azure_search"] = "down"
        _emit_custom("source_status", {"source": "azure_search", "status": "down"})

    tool_results = dict(state.get("tool_results") or {})
    tool_results["search"] = [h.model_dump() for h in hits]
    tool_results["kb"] = [h.model_dump() for h in kb_hits]
    return {"tool_results": tool_results, "source_status": source_status}  # type: ignore[return-value]


def retrieve_kibana(state: OmbudsState) -> OmbudsState:
    source_status = dict(state.get("source_status") or {})
    if source_status.get("kibana") == "skipped":
        return {"source_status": source_status}  # type: ignore[return-value]

    query = state.get("user_query") or ""
    user_id = state.get("user_id", "system")
    thread_id = state.get("thread_id")
    role = state.get("role")
    tool_results = dict(state.get("tool_results") or {})

    _emit_custom("tool_call_start", {"tool": "kibana_search"})
    try:
        logs = run_kibana(query=query, user_id=user_id, role=role, thread_id=thread_id)
        tool_results["kibana"] = [h.model_dump() for h in logs]
        _emit_custom("tool_call_end", {"tool": "kibana_search", "hit_count": len(logs)})
    except SourceUnavailable as e:
        _log.warning("kibana_degraded", error=str(e))
        source_status["kibana"] = "down"
        tool_results["kibana"] = []
        _emit_custom("source_status", {"source": "kibana", "status": "down"})
    except Exception as e:
        _log.exception("kibana_unexpected_error", error=str(e))
        source_status["kibana"] = "down"
        tool_results["kibana"] = []
        _emit_custom("source_status", {"source": "kibana", "status": "down"})

    return {"tool_results": tool_results, "source_status": source_status}  # type: ignore[return-value]


def _render_hits(hits: list[dict], limit: int = 5) -> str:
    if not hits:
        return "(no results)"
    lines: list[str] = []
    for i, h in enumerate(hits[:limit], 1):
        title = h.get("title") or "(untitled)"
        url = h.get("url") or ""
        src = h.get("source_type") or "?"
        snippet = (h.get("content") or "")[:400]
        lines.append(f"{i}. [{src}] {title} — {url}\n   {snippet}")
    return "\n".join(lines)


def _render_logs(logs: list[dict], limit: int = 5) -> str:
    if not logs:
        return "(no log hits)"
    lines: list[str] = []
    for i, h in enumerate(logs[:limit], 1):
        lines.append(
            f"{i}. {h.get('ts', '')} [{h.get('service', '?')}] {h.get('level', '?')}: "
            f"{(h.get('message') or '')[:300]}"
        )
    return "\n".join(lines)


def synthesize(state: OmbudsState, settings: Settings | None = None) -> OmbudsState:
    s = settings or get_settings()
    role = state.get("role", "enduser")
    query = state.get("user_query") or ""
    incident_number = state.get("incident_number")
    tool_results = state.get("tool_results") or {}
    source_status = state.get("source_status") or {}

    search_hits = tool_results.get("search", [])
    kb_hits = tool_results.get("kb", [])
    kibana_hits = tool_results.get("kibana", [])

    system_prompt = OMBUDS_SYSTEM if role == "ombuds" else ENDUSER_SYSTEM

    parts = [
        f"User query: {query or '(none)'}",
        f"Incident number: {incident_number or '(none)'}",
        f"Source status: {json.dumps(source_status)}",
        "",
        "== Azure Search primary results ==",
        _render_hits(search_hits),
    ]
    if kb_hits:
        parts += ["", "== Related KB (Confluence) ==", _render_hits(kb_hits)]
    if kibana_hits:
        parts += ["", "== Kibana log hits ==", _render_logs(kibana_hits)]
    if role == "enduser":
        parts += [
            "",
            "If you cannot resolve the issue from the evidence above, end your response "
            "with a draft block in this exact form (JSON on one line, no markdown fences):",
            "<draft>{\"short_description\": \"...\", \"category\": \"...\", "
            "\"description\": \"...\", \"evidence\": [{\"title\": \"...\", \"url\": \"...\"}], "
            "\"suggested_priority\": \"low|medium|high\"}</draft>",
        ]

    user_msg = "\n".join(parts)
    llm = _build_llm(s)
    ai: AIMessage = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_msg)])  # type: ignore[assignment]
    answer_text = ai.content if isinstance(ai.content, str) else str(ai.content)

    draft: dict[str, Any] | None = None
    m = _DRAFT_BLOCK_RE.search(answer_text)
    if m:
        try:
            draft = json.loads(m.group(1))
        except json.JSONDecodeError:
            draft = None
        # Strip the draft block from the visible answer
        answer_text = _DRAFT_BLOCK_RE.sub("", answer_text).strip()

    messages_out: list[Any] = [AIMessage(content=answer_text)]
    return {  # type: ignore[return-value]
        "messages": messages_out,
        "draft_incident": draft,
    }


def finalize(state: OmbudsState) -> OmbudsState:
    audit = get_audit()
    audit.emit(
        "graph_run",
        user_id=state.get("user_id", "system"),
        role=state.get("role"),
        thread_id=state.get("thread_id"),
        query=state.get("user_query"),
        status="ok",
        source_status=dict(state.get("source_status") or {}),
        message="draft_created" if state.get("draft_incident") else None,
    )
    if state.get("draft_incident"):
        _emit_custom("draft", {"draft": state["draft_incident"]})
    return {}  # type: ignore[return-value]
