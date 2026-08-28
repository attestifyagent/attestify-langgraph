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

Attestify Trust — identity, signed evidence, free public verification.
No wallet, no gas, no chain::

    from attestify_langgraph import make_attestify_tools, provision_trust_agent
    from attestify_langgraph._http import _Client

    # ONE TIME, outside any graph run:
    creds = provision_trust_agent(
        api_key=os.environ["ATTESTIFY_API_KEY"],
        display_name="LangGraph Agent",
        framework="langgraph",
    )
    # Store creds["agent_id"] / creds["private_key"] as TRUST_AGENT_ID /
    # TRUST_PRIVATE_KEY -- make_attestify_tools() picks them up from those
    # env vars automatically and adds two more tools:

  attestify_trust_submit_evidence
      Sign and submit evidence of real work done. Returns a signed,
      immutable, publicly verifiable receipt.

  attestify_trust_verify
      Independently verify any Trust receipt by ID. Public, no API key.
"""

from __future__ import annotations

from .node  import attestify_node, AttestifyState
from .tools import make_attestify_tools
from ._trust import provision_trust_agent, generate_trust_keypair

__version__ = "0.2.0"

__all__ = [
    "attestify_node", "AttestifyState", "make_attestify_tools",
    "provision_trust_agent", "generate_trust_keypair",
]
