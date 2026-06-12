# Lab 02 — MCP client authorization

**Category:** Unity AI Gateway for Tools · **Status:** 🟡 Planned

## Objective
Authorize MCP clients to external/third-party tools using Unity Catalog **connections** with
managed OAuth, so credentials are never exposed to end users or agents.

## Databricks features
- Unity Catalog connections + managed OAuth.
- On-behalf-of authorization and service principals.

## Outline
1. Create a Unity Catalog connection with managed OAuth to an external service.
2. Front the external tool through a Databricks-managed MCP proxy.
3. Authorize a client and call the tool without handling raw credentials.
4. Review access via Unity Catalog audit logs.

> Status: planned — contributions welcome.
