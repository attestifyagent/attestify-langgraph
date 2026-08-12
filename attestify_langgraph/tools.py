"""
make_attestify_tools — returns Attestify as LangChain BaseTool instances
for use in LangGraph tool-calling nodes (ToolNode).

This reuses the same tool logic as attestify-langchain but packaged
for the LangGraph ToolNode pattern without requiring the full
attestify-langchain package.
"""

from __future__ import annotations

import json
from typing import Any, List

from langchain_core.tools import tool
from ._http import _Client, AttestifyError, AttestifyPermissionError


def _safe(val: Any) -> str:
    if isinstance(val, str): return val
    try: return json.dumps(val, default=str)
    except Exception: return str(val)


def make_attestify_tools(
    client: _Client,
    include_control_tower: bool = True,
    include_rag: bool = True,
) -> List:
    """
    Return Attestify tools as LangChain @tool instances for use with
    LangGraph's ToolNode.

    Args:
        client:                Authenticated _Client instance.
        include_control_tower: Include the Enterprise-only Control Tower tool.
        include_rag:           Include the governance-docs RAG search tool.

    Example::

        from langgraph.prebuilt import ToolNode
        tools = make_attestify_tools(client)
        builder.add_node("tools", ToolNode(tools))
    """
    @tool
    def attestify_run_loop(task: str, lane_id: str = "", session_id: str = "", max_cost_usdc: float = 0.0) -> str:
        """Submit a task to the Attestify loop router. Returns loop_id, status, cost, output, receipt_url."""
        payload: dict = {"intent": task}
        if lane_id:       payload["lane_id"]     = lane_id
        if session_id:    payload["session_id"]  = session_id
        if max_cost_usdc: payload["constraints"] = {"max_cost_usdc": max_cost_usdc}
        try:    return _safe(client.post("/api/run", payload))
        except AttestifyError as e: return json.dumps({"error": str(e), "status": e.status})

    @tool
    def attestify_get_receipt(loop_id: str) -> str:
        """Retrieve a single verified loop receipt by its loop_id."""
        if not loop_id: return json.dumps({"error": "loop_id is required"})
        try:    return _safe(client.get(f"/api/receipts/{loop_id}"))
        except AttestifyError as e: return json.dumps({"error": str(e), "status": e.status})

    @tool
    def attestify_get_recent_loops(limit: int = 25) -> str:
        """List the most recent loop receipts for this tenant."""
        # /api/dashboard returns the tenant-scoped receipt history for the
        # caller's own API key. There is no separate per-tenant "list loops"
        # endpoint, so we reuse it and trim to `limit`.
        try:
            result = client.get("/api/dashboard")
            receipts = result.get("receipts", []) if isinstance(result, dict) else []
            return _safe({"loops": receipts[:max(1, min(limit, 100))]})
        except AttestifyError as e: return json.dumps({"error": str(e), "status": e.status})

    tools = [attestify_run_loop, attestify_get_receipt, attestify_get_recent_loops]

    if include_control_tower:
        @tool
        def attestify_get_control_tower() -> str:
            """Enterprise-only: live governance data and cross-tenant run visibility."""
            try:    return _safe(client.get("/api/control-tower"))
            except AttestifyPermissionError: return json.dumps({"error": "Enterprise plan required.", "status": 403})
            except AttestifyError as e: return json.dumps({"error": str(e), "status": e.status})
        tools.append(attestify_get_control_tower)

    if include_rag:
        @tool
        def attestify_query_governance_docs(query: str, source_type: str = "") -> str:
            """Search AttestifyOS governance docs, policies, runbooks, and API specs using semantic search.

            Use this tool whenever the agent needs to answer questions grounded in
            AttestifyOS documentation — policies, API endpoints, runbooks,
            architecture decisions, or SDK usage.

            Args:
                query:       The natural-language question or search phrase.
                source_type: Optional filter — one of 'openapi', 'policy', 'runbook',
                             'architecture', 'sdk', 'plan', 'mcp'. Omit to search all.

            Returns:
                JSON string with answer (synthesised) and sources[] list
                ({ref, sourceType, sourceId, title, similarity, metadata}).
            """
            if not query:
                return json.dumps({"error": "query is required"})
            payload: dict = {"query": query}
            if source_type:
                payload["scope"] = source_type
            try:    return _safe(client.post("/api/rag/query", payload))
            except AttestifyError as e: return json.dumps({"error": str(e), "status": e.status})
        tools.append(attestify_query_governance_docs)

    return tools
