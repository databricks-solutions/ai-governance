# Lab 01 — Managed MCP servers

**Category:** Unity AI Gateway for Tools · **Status:** 🟡 Planned

## Objective
Expose governed tools to agents through Databricks **managed MCP servers** — Unity Catalog
functions, Genie spaces, Vector Search, and Databricks SQL — with access controlled by UC.

## Databricks features
- Managed MCP servers (UC functions, Genie, Vector Search, SQL).
- Unity Catalog permissions governing which principals can call each tool.

## Outline
1. Register a Unity Catalog function as a tool.
2. Connect to the managed MCP server endpoint from an MCP client.
3. Grant/deny access via Unity Catalog and observe enforcement.
4. Call the tool from an agent.

> Status: planned — contributions welcome.
