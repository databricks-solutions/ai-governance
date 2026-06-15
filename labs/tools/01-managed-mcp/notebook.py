# Databricks notebook source
# MAGIC %md
# MAGIC # Lab — Managed MCP servers
# MAGIC
# MAGIC **Unity AI Gateway for Tools**
# MAGIC
# MAGIC Databricks hosts **managed MCP servers** that expose governed assets to any MCP client
# MAGIC (agents, Claude, Cursor, …) with no server to run. Each is a URL under your workspace:
# MAGIC
# MAGIC | Server | URL pattern | Exposes |
# MAGIC |--------|-------------|---------|
# MAGIC | Unity Catalog functions | `/api/2.0/mcp/functions/{catalog}/{schema}` | UC functions as tools |
# MAGIC | Vector Search | `/api/2.0/mcp/vector-search/{catalog}/{schema}` | indexes as retrieval tools |
# MAGIC | Genie | `/api/2.0/mcp/genie/{space_id}` | a Genie space as a tool |
# MAGIC
# MAGIC Access is governed by **Unity Catalog** — a caller only sees and runs what they're
# MAGIC granted. In this lab you connect to the functions server and list + call a tool.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-mcp databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Publish a tool to Unity Catalog
# MAGIC Any UC function in the schema is automatically exposed by the managed functions MCP
# MAGIC server. (If you ran the function-calling lab, this already exists.)

# COMMAND ----------

spark.sql(
    f"""
    CREATE OR REPLACE FUNCTION {CATALOG}.{SCHEMA}.lookup_order_status(order_id STRING)
    RETURNS STRING
    COMMENT 'Look up the fulfillment status of an order by its ID.'
    RETURN
      CASE
        WHEN order_id = 'A1001' THEN 'shipped'
        WHEN order_id = 'A1002' THEN 'processing on line 3'
        ELSE 'unknown order'
      END
    """
)
print(f"Tool published to UC: {CATALOG}.{SCHEMA}.lookup_order_status")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Connect to the managed functions MCP server
# MAGIC `DatabricksMCPClient` authenticates with the workspace client — the same identity and
# MAGIC Unity Catalog grants govern what tools are visible.

# COMMAND ----------

from databricks_mcp import DatabricksMCPClient

functions_server = f"{HOST}/api/2.0/mcp/functions/{CATALOG}/{SCHEMA}"
print("MCP server:", functions_server)

mcp = DatabricksMCPClient(server_url=functions_server, workspace_client=w)
tools = mcp.list_tools()
print(f"\n{len(tools)} tool(s) visible over MCP:")
for t in tools:
    print(" -", t.name)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Call a tool over MCP
# MAGIC The MCP server executes the UC function and returns the result. UC permissions are
# MAGIC enforced on the call.

# COMMAND ----------

tool_name = f"{CATALOG}__{SCHEMA}__lookup_order_status"
result = mcp.call_tool(tool_name, {"order_id": "A1001"})
print("result:", result.content[0].text if getattr(result, "content", None) else result)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. The other managed servers
# MAGIC The same client works against the Vector Search and Genie servers — point `server_url`
# MAGIC at the relevant pattern. For example, to expose a Genie space as a tool:
# MAGIC
# MAGIC ```python
# MAGIC genie = DatabricksMCPClient(
# MAGIC     server_url=f"{HOST}/api/2.0/mcp/genie/<genie_space_id>",
# MAGIC     workspace_client=w,
# MAGIC )
# MAGIC genie.list_tools()
# MAGIC ```
# MAGIC
# MAGIC An agent (see `agents/01-agent-framework`) registers these MCP servers and the model
# MAGIC calls their tools; every model turn still flows through the governed endpoint.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Takeaways
# MAGIC - **No server to operate**: managed MCP servers are hosted by Databricks and addressed
# MAGIC   by URL.
# MAGIC - **Unity Catalog is the authorization layer**: callers only see/run granted assets, and
# MAGIC   every call is audited.
# MAGIC - One UC function is reusable as a **direct tool** (`tools/03-function-calling`) *and* an
# MAGIC   **MCP tool** — same governance, two access paths.
# MAGIC - For tools that need external credentials, govern them with Unity Catalog connections
# MAGIC   and managed OAuth (`tools/02-mcp-authorization`); to host your own server, see
# MAGIC   `tools/04-custom-mcp-app`.
