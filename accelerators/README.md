# Accelerators — reference notebooks

Optional **~3-hour deep dives** that run after the core AI Governance Workshop (Choice · Cost ·
Control). Each accelerator is delivered in-app by the workshop app (defined in
[`../workshop_app/config/accelerators.yaml`](../workshop_app/config/accelerators.yaml)); the
folders here let you **reference and run the same checks without deploying the app**.

Every folder contains:

- **`README.md`** — what the accelerator proves, its steps, and prerequisites.
- **`reference_queries.py`** — a self-contained Databricks notebook that reproduces the app's
  SQL/API checks, one section per step. SQL runs through `spark.sql`; the rest uses the Databricks
  SDK / REST.
- **Ported deep-dive notebooks** — longer, hands-on notebooks for that topic.

| Accelerator | Folder | Deep-dive notebooks |
|---|---|---|
| 🔌 MCP Servers | [`mcp-servers/`](mcp-servers) | `managed_mcp.py`, `function_calling.py` |
| 🤖 Agent Registry | [`agent-registry/`](agent-registry) | `agent_framework.py`, `agent_evaluation.py` |
| 💻 Coding Agents | [`coding-agents/`](coding-agents) | `rate_limiting.py`, `usage_tracking_finops.py`, `openai_agents_sdk.py` |
| 🌐 External Providers | [`external-providers/`](external-providers) | `traffic_routing.py`, `fallbacks.py` |
| 🛡️ Policies & Guardrails | [`policies-and-guardrails/`](policies-and-guardrails) | `guardrail_benchmark.py`, `apply_guardrails.py` |

## Running any notebook

Clone this repo into Databricks (Repos or **Workspace → Import**), open a notebook, set the
widgets at the top to your workspace, and run top to bottom. No bundle and no app deploy are
required.

Most SQL steps read Unity Catalog `system` schemas (`system.ai_gateway`, `system.access`), which
need an account/metastore admin grant — each folder's README notes exactly which. Steps that send
prompts, burst the endpoint, or reconfigure a served entity are called out in the folder READMEs;
everything else is read-only.
