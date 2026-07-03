from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    """A single prior turn in the conversation, sent to the knowledge base for context."""

    role: str = Field(..., description="'user' or 'assistant'.")
    content: str


class KBReference(BaseModel):
    """A grounding reference returned by the knowledge base (citation)."""

    id: str | None = None
    type: str | None = None  # e.g. 'mcpServer', 'searchIndex', 'azureBlob'
    doc_key: str | None = None
    title: str | None = None
    url: str | None = None
    source_data: dict[str, Any] | None = None


class KBResult(BaseModel):
    """Parsed result of a knowledge base retrieve call."""

    answer: str
    references: list[KBReference] = Field(default_factory=list)
    # Which knowledge sources were actually queried (from the activity array).
    sources_queried: list[str] = Field(default_factory=list)
    activity_types: list[str] = Field(default_factory=list)
    partial: bool = False  # True when the service returned 206 Partial Content
