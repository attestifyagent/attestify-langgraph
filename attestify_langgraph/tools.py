"""
make_attestify_tools — returns Attestify as LangChain BaseTool instances
for use in LangGraph tool-calling nodes (ToolNode).

This reuses the same tool logic as attestify-langchain but packaged
for the LangGraph ToolNode pattern without requiring the full
attestify-langchain package.
"""

from __future__ import annotations

import json
import os
from typing import Any, List

from langchain_core.tools import tool
from ._http import _Client, AttestifyError, AttestifyPermissionError
from ._trust import sign_trust_evidence


def _safe(val: Any) -> str:
    if isinstance(val, str): return val
    try: return json.dumps(val, default=str)
    except Exception: return str(val)


def make_attestify_tools(
    client: _Client,
    include_control_tower: bool = True,
    include_rag: bool = True,
    trust_agent_id: str = "",
    trust_private_key: str = "",
    include_trust: bool = True,
) -> List:
    """
    Return Attestify tools as LangChain @tool instances for use with
    LangGraph's ToolNode.

    Args:
        client:                Authenticated _Client instance.
        include_control_tower: Include the Enterprise-only Control Tower tool.
        include_rag:           Include the governance-docs RAG search tool.
        trust_agent_id:        Attestify Trust agent ID, from a one-time
                                provision_trust_agent() call -- falls back
                                to the TRUST_AGENT_ID env var if empty.
        trust_private_key:     That agent's Ed25519 private key -- falls
                                back to TRUST_PRIVATE_KEY. Never exposed as
                                a tool input.
        include_trust:          Include the Trust tools when both resolve.

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

    # ── Attestify Trust ── a separate concern from Router execution above
    # (/api/trust/v1/*, no x402, no lanes, no spend). agent_id/private_key
    # are closed over here, at tool-build time -- never a tool parameter,
    # so the private key never enters the graph's own state or a checkpoint.
    resolved_agent_id = trust_agent_id or os.environ.get("TRUST_AGENT_ID", "")
    resolved_private_key = trust_private_key or os.environ.get("TRUST_PRIVATE_KEY", "")
    if include_trust and resolved_agent_id and resolved_private_key:
        @tool
        def attestify_trust_submit_evidence(summary: str, evidence_schema: str = "work-completion/v1", action_basis: str = "explicit") -> str:
            """Sign and submit evidence that this agent completed real work.

            Produces a signed, timestamped, publicly verifiable receipt -- no wallet,
            no gas, no chain. Call after finishing something worth a permanent record.

            Args:
                summary: Plain-language description of the work done. Gets signed and
                    permanently recorded -- be specific and truthful.
                evidence_schema: Evidence schema version. Default 'work-completion/v1'.
                action_basis: 'explicit' if asked to do this, 'discretionary' if the
                    agent did it on its own initiative.
            """
            try:
                signed = sign_trust_evidence(
                    agent_id=resolved_agent_id, schema=evidence_schema,
                    payload={"summary": summary}, private_key=resolved_private_key,
                    action_basis=action_basis,
                )
                receipt = client.post("/api/trust/v1/evidence", signed)
                r = receipt.get("receipt", receipt)
                return _safe({
                    "receipt_id": r.get("id"),
                    "assurance_level": r.get("assurance_level"),
                    "issued_at": r.get("issued_at"),
                    "verify_url": f"https://attestifyos.com/trust/verify?receipt={r.get('id')}",
                })
            except AttestifyError as e:
                return json.dumps({"error": str(e), "status": e.status})
        tools.append(attestify_trust_submit_evidence)

        @tool
        def attestify_trust_verify(receipt_id: str) -> str:
            """Independently verify any Attestify Trust receipt by ID. Public, no API key needed."""
            if not receipt_id: return json.dumps({"error": "receipt_id is required"})
            try:    return _safe(client.get_public(f"/api/trust/v1/verify/{receipt_id}"))
            except AttestifyError as e: return json.dumps({"error": str(e), "status": e.status})
        tools.append(attestify_trust_verify)

    return tools
