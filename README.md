# attestify-langgraph

> Governed AI loop execution for [LangGraph](https://langchain-ai.github.io/langgraph/) — signed receipts, audit trails, x402 payments on Base, and [Attestify Trust](https://attestifyos.com/trust) (no-wallet agent identity + signed evidence).

## Installation

```bash
pip install attestify-langgraph
```

Trust tools additionally need `cryptography` — install with `pip install attestify-langgraph[trust]`; everything else works without it.

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
| `attestify_trust_submit_evidence` | Sign and submit evidence of real work — free, no wallet (Trust configured) |
| `attestify_trust_verify` | Independently verify any Trust receipt by ID — public, no key |

## Attestify Trust — no-wallet agent identity + signed evidence

A separate concern from the Router tools above: no x402, no lanes, no spend. Register once, then the graph can sign proof of what it actually did.

```python
from attestify_langgraph import provision_trust_agent, make_attestify_tools
from attestify_langgraph._http import _Client
import os

# ONE TIME, outside any graph run — never let the graph call this itself.
# A fresh identity per run breaks the agent's own verified-active streak
# and adds noise to Attestify's public census instead of a real number.
creds = provision_trust_agent(
    api_key=os.environ["ATTESTIFY_API_KEY"],
    display_name="LangGraph Agent",
    framework="langgraph",
)
print(f"Store these — TRUST_AGENT_ID={creds['agent_id']}  TRUST_PRIVATE_KEY={creds['private_key']}")

# From then on, with those two env vars set, make_attestify_tools() picks
# them up automatically and adds attestify_trust_submit_evidence and
# attestify_trust_verify to the returned tool list.
client = _Client(api_key=os.environ["ATTESTIFY_API_KEY"])
tools  = make_attestify_tools(client)
```

The private key is bound once at tool-build time — it's never a tool parameter, so it never enters the graph's own state or a checkpoint.

## Getting Your API Key

Subscribe at [attestifyos.com/pricing](https://attestifyos.com/pricing) for Router access, or register free for Trust-only use at [attestifyos.com/trust](https://attestifyos.com/trust) — no card required.

## Links

- [Attestify OS](https://attestifyos.com)
- [Attestify Trust](https://attestifyos.com/trust)
- [Documentation](https://attestifyos.com/docs)
- [Get an API key](https://attestifyos.com/dashboard)
- [GitHub](https://github.com/attestifyagent/attestify-langgraph)
