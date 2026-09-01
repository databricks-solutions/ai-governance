# Accelerator — MCP Servers

Managed vs external MCP, UC permissions, on-behalf-of identity, and service policies. A ~3-hour
deep dive on the single most-requested MCP control: read-only enforcement for coding-agent users
while humans keep write.

Two different things are both called "MCP" on Databricks, and which one you use decides what you
can govern:

- **Managed (UC-native) endpoints** — `/api/2.0/mcp/functions|genie|sql|ai-search`. Expose Unity
  Catalog objects as tools; governed by authentication + UC grants. **Not** `MCP_SERVICE`
  securables, so service policies cannot attach.
- **MCP Services** — `/ai-gateway/mcp-services/<catalog>.<schema>.<name>`. Real UC securables (the
  provided `system.ai.*` services plus any external/custom server you register). These get UC
  grants **and** service policies (ALLOW / DENY / ASK).

## What you'll prove

Inventory MCP services · list managed-endpoint tools · list an MCP Service's tools · read who is
granted `EXECUTE` · prove on-behalf-of identity · confirm a policy can attach · write and verify a
DENY/ALLOW policy · classify tools read vs write for read-only enforcement · check external-MCP
readiness · scan tool metadata for poisoning · read MCP telemetry.

## Notebooks in this folder

| Notebook | What it is |
|---|---|
| [`reference_queries.py`](reference_queries.py) | The app's checks for all 11 steps, one section each — runnable without the app. |
| [`managed_mcp.py`](managed_mcp.py) | Deep dive: publish a UC function and call it as an MCP tool through the managed endpoint. |
| [`function_calling.py`](function_calling.py) | Deep dive: Unity Catalog functions as governed tools (function calling). |

## Prerequisites

- A SQL warehouse and an existing Unity Catalog catalog + schema (for the policy function).
- `SELECT` on `system.ai_gateway` (an account/metastore admin grant) for the telemetry step.
- An `MCP_SERVICE` securable to point the policy/OBO steps at — a provided `system.ai.*` service
  or an external one you register. Availability differs per workspace; run Step 1 to see what's
  registered. Some services (e.g. `system.ai.atlassian`) need per-user OAuth consent first.

## How to run

Clone this repo into Databricks (Repos or **Workspace → Import**), open a notebook, set the
widgets at the top to your workspace, and run top to bottom. Nothing here needs the workshop app
deployed.
