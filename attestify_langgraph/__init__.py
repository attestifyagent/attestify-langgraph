"""
attestify-langgraph
===================
LangGraph node integration for Attestify — governed AI loop execution
with receipts, audit trails, and plan-gated enterprise features.

Quick start::

    from attestify_langgraph import attestify_node, AttestifyState
    from langgraph.graph import StateGraph, END
    import os

    builder = StateGraph(AttestifyState)
    builder.add_node("run", attestify_node(api_key=os.environ["ATTESTIFY_API_KEY"]))
    builder.set_entry_point("run")
    builder.add_edge("run", END)

    graph = builder.compile()
    result = graph.invoke({"task": "Analyse Q2 revenue trends"})
    print(result["loop_id"], result["cost_usdc"], result["receipt_url"])

The node reads ``task``, ``lane_id``, ``session_id``, and ``max_cost_usdc``
from state and writes ``loop_id``, ``status``, ``cost_usdc``, ``output``,
``receipt_url``, and ``error`` back.
"""

from __future__ import annotations

from .node  import attestify_node, AttestifyState
from .tools import make_attestify_tools

__version__ = "0.1.0"

__all__ = ["attestify_node", "AttestifyState", "make_attestify_tools"]
