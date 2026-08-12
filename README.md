# attestify-langgraph

> Governed AI loop execution for [LangGraph](https://langchain-ai.github.io/langgraph/) — signed receipts, audit trails, and x402 payments on Base.

## Installation

```bash
pip install attestify-langgraph
```

## Usage — State Node

Drop a governed Attestify run directly into your graph as a node:

```python
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
```

## Usage — ToolNode

Use Attestify as tool-calling tools inside a LangGraph `ToolNode`:

```python
from attestify_langgraph import make_attestify_tools
from attestify_langgraph._http import _Client
from langgraph.prebuilt import ToolNode
import os

client = _Client(api_key=os.environ["ATTESTIFY_API_KEY"])
tools  = make_attestify_tools(client)

builder.add_node("tools", ToolNode(tools))
```

## State Fields

| Field | Direction | Type | Description |
|---|---|---|---|
| `task` | input | str | Natural-language task to execute |
| `lane_id` | input | str | Optional specific lane to invoke |
| `session_id` | input | str | Optional memory continuity ID |
| `max_cost_usdc` | input | float | Optional per-run spend cap |
| `loop_id` | output | str | Assigned loop identifier |
| `status` | output | str | `success` or `error` |
| `cost_usdc` | output | float | Actual cost charged |
| `output` | output | str | Agent output text |
| `receipt_url` | output | str | URL to the signed receipt |
| `error` | output | str \| None | Error message if status is `error` |

## Tools (ToolNode)

When using `make_attestify_tools`, the following are also available as graph-callable tools:

| Tool | Description |
|---|---|
| `attestify_run_loop` | Submit a governed task to the loop router |
| `attestify_get_receipt` | Fetch a single receipt by `loop_id` |
| `attestify_get_recent_loops` | List recent loop receipts for this tenant |
| `attestify_get_control_tower` | Live governance data (Enterprise only) |
| `attestify_query_governance_docs` | Semantic search over Attestify's governance docs |

## Links

- [Attestify OS](https://attestify-os.vercel.app)
- [Documentation](https://attestify-os.vercel.app/docs)
- [Get an API key](https://attestify-os.vercel.app/dashboard)
- [MCP Package](../../mcp-package/)
- [GitHub](https://github.com/attestifyagent/attestify-os)
