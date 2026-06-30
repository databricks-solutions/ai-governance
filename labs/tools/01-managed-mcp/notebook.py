# Databricks notebook source
# MAGIC %md
# MAGIC # Lab — Managed MCP servers
# MAGIC
# MAGIC Expose governed Unity Catalog assets to any MCP client, no server to run.
# MAGIC
# MAGIC See README.md for details.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-mcp databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md ### Publish a tool to Unity Catalog

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

# MAGIC %md ### Connect to the managed functions MCP server

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

# MAGIC %md ### Call a tool over MCP

# COMMAND ----------

tool_name = f"{CATALOG}__{SCHEMA}__lookup_order_status"
result = mcp.call_tool(tool_name, {"order_id": "A1001"})
print("result:", result.content[0].text if getattr(result, "content", None) else result)

# COMMAND ----------

# MAGIC %md ### The other managed servers
# MAGIC The same client targets the Vector Search and Genie servers — point `server_url` at the
# MAGIC relevant pattern (see README.md). For example:
# MAGIC
# MAGIC ```python
# MAGIC genie = DatabricksMCPClient(
# MAGIC     server_url=f"{HOST}/api/2.0/mcp/genie/<genie_space_id>",
# MAGIC     workspace_client=w,
# MAGIC )
# MAGIC genie.list_tools()
# MAGIC ```
