from __future__ import annotations

from app.ui.sse_client import _parse_sse_line


def test_parse_sse_event_and_data():
    evt = _parse_sse_line(["event: token", 'data: {"delta": "hi"}'])
    assert evt is not None
    assert evt.event == "token"
    assert evt.data == {"delta": "hi"}


def test_parse_sse_default_event_message():
    evt = _parse_sse_line(['data: {"x": 1}'])
    assert evt is not None
    assert evt.event == "message"


def test_parse_sse_skips_comments():
    evt = _parse_sse_line([":keepalive", "event: ping", "data: {}"])
    assert evt is not None
    assert evt.event == "ping"


def test_parse_sse_no_data_returns_none():
    assert _parse_sse_line(["event: token"]) is None
