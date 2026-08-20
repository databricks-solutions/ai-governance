# Databricks notebook source
# MAGIC %md
# MAGIC # MCP Servers — reference queries
# MAGIC
# MAGIC Standalone version of the checks the **MCP Servers** accelerator runs inside the AI
# MAGIC Governance Workshop app, so you can reference and run them without deploying the app.
# MAGIC Each section below mirrors one in-app step and its `test`. SQL runs through `spark.sql`;
# MAGIC everything else uses the Databricks SDK / REST. See `README.md` for the concepts.
# MAGIC
# MAGIC Set the widgets to match your workspace, then run top to bottom (or cell by cell).

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk databricks-mcp
# MAGIC %restart_python

# COMMAND ----------

import json
import re

import requests
from databricks.sdk import WorkspaceClient

dbutils.widgets.text("catalog", "main", "Unity Catalog catalog")
dbutils.widgets.text("schema", "ai_governance_workshop", "Workshop schema")
dbutils.widgets.text("mcp_service", "system.ai.github", "MCP Service FQN (an MCP_SERVICE securable)")
dbutils.widgets.text("policy_function", "mcp_read_only_policy", "Service-policy UDF name")
dbutils.widgets.text("deny_tools", "get_file_contents", "Tool names the policy DENYs (comma-separated)")
dbutils.widgets.text("identity_probe_tool", "get_me", "Read tool that echoes the caller (OBO probe)")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
MCP_SERVICE = dbutils.widgets.get("mcp_service")
POLICY_FN = dbutils.widgets.get("policy_function")
DENY_TOOLS = [t.strip() for t in dbutils.widgets.get("deny_tools").split(",") if t.strip()]
IDENTITY_PROBE_TOOL = dbutils.widgets.get("identity_probe_tool")
DENY_REASON = "Blocked by workshop policy: this tool is not permitted for the pilot group."

w = WorkspaceClient()
_ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
HOST = _ctx.apiUrl().get()

from databricks_mcp import DatabricksMCPClient

MANAGED_FUNCTIONS_URL = f"{HOST}/api/2.0/mcp/functions/{CATALOG}/{SCHEMA}"
SERVICE_URL = f"{HOST}/ai-gateway/mcp-services/{MCP_SERVICE}"

# Heuristic used to classify a tool as read vs write from its name (the app does the same).
_WRITE_HINTS = (
    "create", "update", "delete", "write", "put", "post", "insert", "remove", "set",
    "push", "merge", "add", "modify", "patch", "edit", "upload", "send", "run", "execute",
)


def classify_tool(name: str) -> str:
    return "write" if any(h in name.lower() for h in _WRITE_HINTS) else "read"


print("Managed functions endpoint:", MANAGED_FUNCTIONS_URL)
print("MCP Service URL           :", SERVICE_URL)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1 — Inventory MCP services (`mcp_inventory`)
# MAGIC Every `MCP_SERVICE` securable on the metastore — the Databricks-provided `system.ai.*`
# MAGIC services plus any external/custom server you registered. These are the ones that can
# MAGIC carry a service policy.

# COMMAND ----------

services = w.api_client.do("GET", "/api/2.1/unity-catalog/mcp-services")
print(json.dumps(services, indent=2, default=str))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2 — Managed MCP: UC functions as tools (`mcp_managed_tools`)
# MAGIC The managed UC-native endpoint turns the functions in a schema into MCP tools.
# MAGIC A caller without `USE CATALOG` + `USE SCHEMA` gets an **empty list**, not an error —
# MAGIC deny-by-absence, so an empty result is ambiguous.

# COMMAND ----------

managed = DatabricksMCPClient(server_url=MANAGED_FUNCTIONS_URL, workspace_client=w)
managed_tools = managed.list_tools()
print(f"{len(managed_tools)} tool(s) visible from the managed functions endpoint:")
for t in managed_tools:
    print(" -", t.name)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3 — MCP Service: the live tool surface (`mcp_service_tools`)
# MAGIC The configured MCP Service's tools over JSON-RPC. A `403` here means the caller is not
# MAGIC entitled or OAuth consent is incomplete — not that the service is broken.

# COMMAND ----------

service = DatabricksMCPClient(server_url=SERVICE_URL, workspace_client=w)
service_tools = service.list_tools()
print(f"{len(service_tools)} tool(s) on {MCP_SERVICE}:")
for t in service_tools:
    print(f"  [{classify_tool(t.name)}] {t.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4 — Who is allowed to call it (`mcp_grants`, Plane 2)
# MAGIC UC grants decide callability. By default `system.ai` grants `EXECUTE` to **all account
# MAGIC users** — a broad grant here is the signal to scope the service (deny-by-absence in a
# MAGIC customer-owned catalog).

# COMMAND ----------

grants = w.api_client.do("GET", f"/api/2.1/unity-catalog/permissions/mcp_service/{MCP_SERVICE}")
print(json.dumps(grants, indent=2, default=str))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5 — Prove on-behalf-of identity (`mcp_obo`)
# MAGIC The tool runs as the **calling user**. Call a read tool that echoes the upstream
# MAGIC identity — two participants running this should see different names. That difference is
# MAGIC the proof, versus taking OBO on trust.

# COMMAND ----------

tool_names = {t.name for t in service_tools}
probe = IDENTITY_PROBE_TOOL if IDENTITY_PROBE_TOOL in tool_names else next(
    (c for c in ("get_me", "get_my_user_profile", "whoami") if c in tool_names), None
)
if probe:
    print("Identity probe tool:", probe)
    print(json.dumps(service.call_tool(probe, {}), indent=2, default=str))
else:
    print("No identity-echo tool on this service — action required.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6 — Confirm a policy can attach here (`mcp_policy_target`, Plane 3)
# MAGIC Service policies attach **only** to `MCP_SERVICE` securables. Verify the configured
# MAGIC service is one before writing a policy — managed UC-native endpoints are not securables
# MAGIC and have nothing to attach to.

# COMMAND ----------

names = [s.get("name") or s.get("full_name") for s in services.get("mcp_services", services.get("services", []))]
print("Configured service :", MCP_SERVICE)
print("Is an MCP_SERVICE securable:", MCP_SERVICE in names)
print("Registered services:", names)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7 — Write the contextual policy (`create_mcp_policy`, Plane 3)
# MAGIC A service policy is a UC SQL function taking `event VARIANT` and returning ALLOW / DENY
# MAGIC / ASK. Note `to_variant_object(...)` (not `to_variant`) and the VARIANT path cast
# MAGIC `event:context.tool.name::STRING`.

# COMMAND ----------

deny_sql = ", ".join("'" + t.replace("'", "''") + "'" for t in DENY_TOOLS)
reason_sql = "'" + DENY_REASON.replace("'", "''") + "'"
create_policy = f"""
CREATE OR REPLACE FUNCTION {CATALOG}.{SCHEMA}.{POLICY_FN}(event VARIANT)
RETURNS VARIANT
RETURN CASE
  WHEN event:context.tool.name::STRING IN ({deny_sql})
  THEN to_variant_object(named_struct('result','DENY','reason',{reason_sql}))
  ELSE to_variant_object(named_struct('result','ALLOW','reason',''))
END
"""
print(create_policy)
spark.sql(create_policy)
print("Created", f"{CATALOG}.{SCHEMA}.{POLICY_FN}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8 — Verify DENY / ALLOW logic (`mcp_policy_enforcement`)
# MAGIC Evaluate the policy function against synthetic events before attaching it. A write tool
# MAGIC should return DENY; a read tool should return ALLOW. (Attaching the policy to the
# MAGIC service itself is a manual step in the AI Gateway UI.)

# COMMAND ----------

def eval_policy(tool_name: str):
    event = json.dumps({"type": "request", "context": {"tool": {"name": tool_name}}})
    event_sql = "'" + event.replace("'", "''") + "'"
    fqn = f"{CATALOG}.{SCHEMA}.{POLICY_FN}"
    row = spark.sql(
        f"SELECT {fqn}(parse_json({event_sql})):result::STRING AS decision, "
        f"{fqn}(parse_json({event_sql})):reason::STRING AS reason"
    ).first()
    return row["decision"], row["reason"]

for probe_tool in (DENY_TOOLS[0] if DENY_TOOLS else "push_files", "get_commit"):
    print(probe_tool, "->", eval_policy(probe_tool))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 9 — Read-only enforcement (`mcp_readonly_enforcement`)
# MAGIC Classify the service's tools read vs write, so you see exactly what a read-only policy
# MAGIC would need to deny (keep coding-agent users to reads; humans keep write).

# COMMAND ----------

read_tools = [t.name for t in service_tools if classify_tool(t.name) == "read"]
write_tools = [t.name for t in service_tools if classify_tool(t.name) == "write"]
print("READ  tools:", read_tools)
print("WRITE tools (a read-only policy would DENY these):", write_tools or "(none exposed)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 10 — External-MCP readiness (`mcp_external_readiness`)
# MAGIC For a customer not yet running MCP on Databricks, an HTTP connection is the prerequisite
# MAGIC for registering an external server (which is what enables service policies).

# COMMAND ----------

connections = list(w.connections.list())
print(f"{len(connections)} connection(s):")
for c in connections:
    print(f"  {c.name}  ({c.connection_type})")
external = [n for n in names if n and not n.startswith("system.ai")]
print("Already-registered external MCP services:", external or "(none yet)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 11 — Scan tools for poisoning (`mcp_tool_metadata_scan`)
# MAGIC A tool's name/description is sent to the model, so a malicious server can smuggle
# MAGIC instructions into them. Scan the advertised metadata for injection-shaped phrases.
# MAGIC A flag is a prompt to review the tool and its source, not proof of compromise.

# COMMAND ----------

INJECTION = re.compile(
    r"ignore (all |the |previous |prior )*(instructions|prompt)"
    r"|disregard (the |all )*(above|previous)"
    r"|system prompt|you are now|do not (tell|mention|reveal)|without (telling|informing)"
    r"|exfiltrat|<\s*system|begin system|api[_-]?key|secret key|password",
    re.IGNORECASE,
)
flagged = []
for t in service_tools:
    blob = f"{t.name} {getattr(t, 'description', '') or ''}"
    if INJECTION.search(blob):
        flagged.append(t.name)
print("Flagged tools:", flagged or "(none — no injection-shaped phrases found)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 12 — What was actually recorded (`mcp_telemetry`)
# MAGIC MCP Service calls write a usage row (identity, service, tool, latency, cost); managed
# MAGIC UC-native endpoints write no MCP-specific telemetry. Arguments and results are **not**
# MAGIC captured in the current Beta.

# COMMAND ----------

display(spark.sql("""
    SELECT service_name, requester,
           COUNT(*) AS calls,
           SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS errors,
           ROUND(AVG(latency_ms)) AS avg_latency_ms
    FROM system.ai_gateway.usage
    WHERE event_time > current_timestamp() - INTERVAL 7 DAYS
      AND service_type = 'MCP_SERVICE'
    GROUP BY 1, 2 ORDER BY calls DESC LIMIT 20
"""))
