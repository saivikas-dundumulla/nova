from __future__ import annotations


class ToolError(Exception):
    """Base for tool-level failures."""


class SourceUnavailable(ToolError):
    """A backing data source (Azure Search, Kibana) is unreachable or returned an error.

    Callers should catch this and update state.source_status; the graph continues with a caveat.
    """

    def __init__(self, source: str, detail: str = "") -> None:
        super().__init__(f"{source} unavailable: {detail}" if detail else f"{source} unavailable")
        self.source = source
        self.detail = detail
