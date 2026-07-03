from __future__ import annotations

import httpx
import pytest

from app.tools.errors import SourceUnavailable
from app.tools.kibana import KibanaClient, build_es_query, run_kibana


def test_build_es_query_basic():
    body = build_es_query("error", service=None, time_range="1h", max_hits=10)
    assert body["size"] == 10
    assert body["query"]["bool"]["must"][0]["query_string"]["query"] == "error"
    assert body["query"]["bool"]["filter"][0]["range"]["@timestamp"]["gte"] == "now-1h"


def test_build_es_query_with_service():
    body = build_es_query("error", service="vpn-gateway", time_range="24h", max_hits=5)
    must = body["query"]["bool"]["must"]
    assert {"term": {"service.name": "vpn-gateway"}} in must


def test_build_es_query_rejects_bad_time_range():
    with pytest.raises(ValueError):
        build_es_query("q", None, "yesterday", 5)


def test_run_kibana_returns_hits(monkeypatch):
    def transport_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-07-03T09:15:22Z",
                                "service": {"name": "vpn-gateway"},
                                "log": {"level": "ERROR"},
                                "message": "TLS handshake failed",
                            }
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(transport_handler)
    client = httpx.Client(base_url="https://kibana.example.com", transport=transport)

    # Inject client directly via KibanaClient to avoid our internal client construction path
    # (run_kibana wraps client construction, so we call the KibanaClient manually here).
    kc = KibanaClient(client=client)
    hits = kc.search("tls", service=None, time_range="1h", max_hits=5)
    assert len(hits) == 1
    assert hits[0].service == "vpn-gateway"
    assert hits[0].level == "ERROR"


def test_run_kibana_wraps_network_error_as_source_unavailable():
    def transport_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    transport = httpx.MockTransport(transport_handler)
    client = httpx.Client(base_url="https://kibana.example.com", transport=transport)
    with pytest.raises(SourceUnavailable):
        run_kibana(query="q", client=client)
