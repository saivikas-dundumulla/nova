from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    finalize,
    retrieve_kibana,
    retrieve_search,
    router,
    synthesize,
)
from app.graph.state import OmbudsState


def build_graph():
    g: StateGraph = StateGraph(OmbudsState)
    g.add_node("router", router)
    g.add_node("retrieve_search", retrieve_search)
    g.add_node("retrieve_kibana", retrieve_kibana)
    g.add_node("synthesize", synthesize)
    g.add_node("finalize", finalize)

    g.add_edge(START, "router")
    # Sequenced retrieval — kibana no-ops when the router marks it "skipped".
    # (Parallel fan-out requires reducer-annotated state channels; v1 keeps this simple.)
    g.add_edge("router", "retrieve_search")
    g.add_edge("retrieve_search", "retrieve_kibana")
    g.add_edge("retrieve_kibana", "synthesize")
    g.add_edge("synthesize", "finalize")
    g.add_edge("finalize", END)

    checkpointer = MemorySaver()
    return g.compile(checkpointer=checkpointer)


@lru_cache(maxsize=1)
def get_graph():
    return build_graph()
