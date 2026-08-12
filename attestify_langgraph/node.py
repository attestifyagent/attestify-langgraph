"""
LangGraph nodes + TypedDict states for Attestify.

Two nodes are provided:

  attestify_node   — governed loop execution (existing)
  rag_node         — governance-docs semantic search (new)

─────────────────────────────────────────────────────────
attestify_node
─────────────────────────────────────────────────────────
State fields read:
  task (str)             — required: natural-language task to execute
  lane_id (str)          — optional: specific lane to invoke
  session_id (str)       — optional: memory continuity across turns
  max_cost_usdc (float)  — optional: per-run spend cap

State fields written:
  loop_id (str)          — assigned loop identifier
  status (str)            — 'success' or 'error'
  cost_usdc (float)      — actual cost charged
  output (str)           — agent output text
  receipt_url (str)      — URL to the signed receipt
  error (str | None)     — error message if status == 'error'

─────────────────────────────────────────────────────────
rag_node
─────────────────────────────────────────────────────────
State fields read:
  rag_query (str)        — required: natural-language question
  rag_source_type (str)  — optional: 'openapi' | 'policy' | 'runbook' |
                           'architecture' | 'sdk' | 'plan' | 'mcp'

State fields written:
  rag_answer (str)       — synthesised answer grounded in retrieved docs
  rag_sources (list)     — [{ref, sourceType, sourceId, title, similarity, metadata}]
  rag_error (str | None) — error message if the query failed
"""

from __future__ import annotations

from typing import List, Optional
try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict

from ._http import _Client, AttestifyError, DEFAULT_BASE_URL, DEFAULT_TIMEOUT, DEFAULT_RETRIES


# ── state schemas ─────────────────────────────────────────────────────────────

class AttestifyState(TypedDict, total=False):
    # inputs
    task:           str
    lane_id:        str
    session_id:     str
    max_cost_usdc:  float
    # outputs
    loop_id:        str
    status:         str
    cost_usdc:      float
    output:         str
    receipt_url:    str
    error:          Optional[str]


class AttestifyRagState(TypedDict, total=False):
    # inputs
    rag_query:       str
    rag_source_type: str
    # outputs
    rag_answer:      str
    rag_sources:     List[dict]
    rag_error:       Optional[str]


# ── node factories ────────────────────────────────────────────────────────────

def attestify_node(
    api_key:     str,
    base_url:    str   = DEFAULT_BASE_URL,
    timeout_s:   float = DEFAULT_TIMEOUT,
    max_retries: int   = DEFAULT_RETRIES,
):
    """
    Factory that returns a LangGraph node function bound to an Attestify tenant.

    Args:
        api_key:     Attestify API key (``att_live_...``).
        base_url:    Override the API base URL.
        timeout_s:   HTTP timeout in seconds.
        max_retries: Retries on 5xx errors.

    Returns:
        An async-compatible node callable ``(state: AttestifyState) -> dict``.

    Example::

        builder.add_node("governed_run", attestify_node(api_key=key))
    """
    client = _Client(api_key=api_key, base_url=base_url,
                     timeout_s=timeout_s, max_retries=max_retries)

    def node(state: AttestifyState) -> dict:
        task          = state.get("task", "")
        lane_id       = state.get("lane_id", "")
        session_id    = state.get("session_id", "")
        max_cost_usdc = state.get("max_cost_usdc", 0.0)

        if not task:
            return {"status": "error", "error": "task is required in state"}

        payload: dict = {"intent": task}
        if lane_id:       payload["lane_id"]     = lane_id
        if session_id:    payload["session_id"]  = session_id
        if max_cost_usdc: payload["constraints"] = {"max_cost_usdc": max_cost_usdc}

        try:
            res = client.post("/api/run", payload)
            loop_id = res.get("loop_id", "")
            return {
                "loop_id":     loop_id,
                "status":      res.get("status", "success"),
                "cost_usdc":   float(res.get("price_usdc") or 0),
                "output":      str(res.get("output") or ""),
                "receipt_url": f"{base_url.rstrip('/')}/api/receipts/{loop_id}" if loop_id else "",
                "error":       None,
            }
        except AttestifyError as exc:
            return {"status": "error", "error": str(exc), "loop_id": "", "output": "", "receipt_url": ""}

    return node


def rag_node(
    api_key:     str,
    base_url:    str   = DEFAULT_BASE_URL,
    timeout_s:   float = DEFAULT_TIMEOUT,
    max_retries: int   = DEFAULT_RETRIES,
):
    """
    Factory that returns a LangGraph node for governance-docs RAG search.

    The node reads ``rag_query`` from state, calls POST /api/rag/query on
    the AttestifyOS backend, and writes ``rag_answer``, ``rag_sources``,
    and ``rag_error`` back to state.

    Args:
        api_key:     Attestify API key (``att_live_...``).
        base_url:    Override the API base URL.
        timeout_s:   HTTP timeout in seconds.
        max_retries: Retries on 5xx errors.

    Returns:
        A node callable ``(state: AttestifyRagState) -> dict``.

    Example::

        builder.add_node("retrieve_docs", rag_node(api_key=key))
        builder.add_edge("retrieve_docs", "governed_run")

    Typical graph flow::

        START → retrieve_docs → governed_run → END

        # retrieve_docs populates rag_answer + rag_sources in state,
        # which governed_run can reference to ground its execution.
    """
    client = _Client(api_key=api_key, base_url=base_url,
                     timeout_s=timeout_s, max_retries=max_retries)

    def node(state: AttestifyRagState) -> dict:
        query       = state.get("rag_query", "")
        source_type = state.get("rag_source_type", "")

        if not query:
            return {"rag_answer": "", "rag_sources": [], "rag_error": "rag_query is required in state"}

        payload: dict = {"query": query}
        if source_type:
            payload["scope"] = source_type

        try:
            res = client.post("/api/rag/query", payload)
            return {
                "rag_answer":  res.get("answer", ""),
                "rag_sources": res.get("sources", []),
                "rag_error":   None,
            }
        except AttestifyError as exc:
            return {"rag_answer": "", "rag_sources": [], "rag_error": str(exc)}

    return node
