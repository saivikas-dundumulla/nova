from __future__ import annotations

from app.graph.nodes import router


def test_router_enduser_no_kibana_hint():
    out = router({"role": "enduser", "user_query": "how do I request vacation days"})
    assert out["source_status"]["kibana"] == "skipped"
    assert out["source_status"]["azure_search"] == "ok"


def test_router_enduser_with_kibana_hint():
    out = router({"role": "enduser", "user_query": "getting 500 errors on checkout"})
    assert out["source_status"]["kibana"] == "ok"


def test_router_ombuds_always_kibana():
    out = router({"role": "ombuds", "user_query": "policy interpretation question"})
    assert out["source_status"]["kibana"] == "ok"
