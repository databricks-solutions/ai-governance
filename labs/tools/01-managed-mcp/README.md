# Lab 01 — Managed MCP servers

**Category:** Unity AI Gateway for Tools · **Status:** ✅ Built

Expose governed Unity Catalog assets to any MCP client through Databricks **managed MCP servers** — no server to run.

## What you'll do
1. Publish a Unity Catalog function (the tool).
2. Connect to the managed **functions** MCP server with `DatabricksMCPClient`.
3. List and call the tool over MCP — with Unity Catalog enforcing access.
4. See how the same client targets the Vector Search and Genie MCP servers.

## Databricks features
- Managed MCP servers: `/api/2.0/mcp/functions|vector-search|genie/...`.
- Unity Catalog functions as MCP tools; UC permissions as the authorization layer.
- `databricks-mcp` client (`DatabricksMCPClient`).

## Prerequisites
- The bundle deployed so `${var.catalog}.${var.schema}` exists.
- Permission to create UC functions and call the managed MCP servers.

## Run it
Open `notebook.py` and run top-to-bottom. The same UC function is reusable as a direct
tool in `tools/03-function-calling`.
