# Lab 01 — Managed MCP servers

**Expose governed Unity Catalog assets to any MCP client through Databricks managed MCP servers — no server to run.**

## What you'll do
1. Publish a Unity Catalog function (the tool).
2. Connect to the managed **functions** MCP server with `DatabricksMCPClient`.
3. List and call the tool over MCP — with Unity Catalog enforcing access.
4. See how the same client targets the Vector Search and Genie MCP servers.

## How it works
Databricks hosts managed MCP servers that expose governed assets to any MCP client (agents, Claude, Cursor, …) with no server to operate — each is a URL under your workspace:

| Server | URL pattern | Exposes |
|--------|-------------|---------|
| Unity Catalog functions | `/api/2.0/mcp/functions/{catalog}/{schema}` | UC functions as tools |
| Vector Search | `/api/2.0/mcp/vector-search/{catalog}/{schema}` | indexes as retrieval tools |
| Genie | `/api/2.0/mcp/genie/{space_id}` | a Genie space as a tool |

Access is governed by **Unity Catalog** — a caller only sees and runs what they're granted, and every call is audited. `DatabricksMCPClient` authenticates with the workspace client, so the same identity and UC grants apply. The same UC function is reusable as a direct tool (`tools/03-function-calling`) and an MCP tool. To host your own server, deploy it as a Databricks App; govern external-credential tools with UC connections and managed OAuth.

## Run it
Open `notebook.py` and run top-to-bottom, or run the `run_tools_labs` job. Requires the bundle deployed:
`databricks bundle deploy -t dev`.
