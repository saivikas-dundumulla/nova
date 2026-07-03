from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal["servicenow", "confluence"]


class SearchHit(BaseModel):
    id: str | None = None
    source_type: str | None = None
    incident_number: str | None = None
    title: str | None = None
    content: str | None = None
    url: str | None = None
    score: float | None = None


class SearchQuery(BaseModel):
    query: str = Field(..., description="Free-text semantic query.")
    source_filter: SourceType | None = Field(
        default=None,
        description="Restrict to 'servicenow' or 'confluence' records.",
    )
    incident_number: str | None = Field(
        default=None,
        description="Exact-match on ServiceNow incident number.",
    )
    top_k: int = Field(default=8, ge=1, le=50)


class LogHit(BaseModel):
    ts: str | None = None
    service: str | None = None
    level: str | None = None
    message: str | None = None
    trace_id: str | None = None
    raw: dict | None = None


class KibanaQuery(BaseModel):
    query: str = Field(..., description="Free-text log query.")
    service: str | None = Field(default=None, description="Optional service.name filter.")
    time_range: str = Field(
        default="24h",
        description="Time window ending now, e.g. '15m', '1h', '24h'.",
    )
    max_hits: int = Field(default=25, ge=1, le=200)
