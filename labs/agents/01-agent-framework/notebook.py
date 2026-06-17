# Databricks notebook source
# MAGIC %md
# MAGIC # Lab — Mosaic AI Agent Framework on a governed endpoint
# MAGIC
# MAGIC **Unity AI Gateway for Agents**
# MAGIC
# MAGIC Here we build a first-class Databricks agent: a `ChatAgent` whose model calls run
# MAGIC through the **governed endpoint**, logged with MLflow and registered to **Unity
# MAGIC Catalog**. Because the agent uses the gateway, it inherits rate limits, guardrails,
# MAGIC usage tracking, and payload logging; because it's a UC model, it's versioned and
# MAGIC permissioned like any other governed asset. When deployed, its own serving endpoint is
# MAGIC governed too.
# MAGIC
# MAGIC In this lab you will:
# MAGIC 1. Define a `ChatAgent` (models-from-code).
# MAGIC 2. Log it to MLflow with a serving-endpoint resource dependency.
# MAGIC 3. Load it back and test it.
# MAGIC 4. Register it to Unity Catalog (deploy step included as an optional next move).

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade "mlflow[databricks]>=3.1" databricks-agents openai
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Define the agent (models-from-code)
# MAGIC The agent uses the Databricks deployments client, which auto-authenticates both in this
# MAGIC notebook and (via the declared resource) when deployed. We write it to a file so MLflow
# MAGIC can log the code as the model definition.

# COMMAND ----------

agent_code = f'''
import os
import uuid

import mlflow.deployments
from mlflow.models import set_model
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import ChatAgentMessage, ChatAgentResponse

GATEWAY_ENDPOINT = os.environ.get("GATEWAY_ENDPOINT", "{ENDPOINT_NAME}")


class SupportAgent(ChatAgent):
    """A minimal support agent that answers through the governed gateway endpoint."""

    def predict(self, messages, context=None, custom_inputs=None):
        client = mlflow.deployments.get_deploy_client("databricks")
        oai_messages = [{{"role": m.role, "content": m.content}} for m in messages]
        oai_messages.insert(
            0,
            {{"role": "system", "content": "You are a concise, professional support agent."}},
        )
        resp = client.predict(
            endpoint=GATEWAY_ENDPOINT,
            inputs={{"messages": oai_messages, "max_tokens": 256}},
        )
        content = resp["choices"][0]["message"]["content"]
        return ChatAgentResponse(
            messages=[ChatAgentMessage(role="assistant", content=content, id=str(uuid.uuid4()))]
        )


set_model(SupportAgent())
'''

agent_path = "/tmp/ai_governance_agent.py"
with open(agent_path, "w") as f:
    f.write(agent_code)
print("Wrote agent definition to", agent_path)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Log the agent to MLflow
# MAGIC We declare the governed endpoint as a **resource** so a future deployment is granted
# MAGIC access to it automatically (no embedded credentials).

# COMMAND ----------

import mlflow
from mlflow.models.resources import DatabricksServingEndpoint

mlflow.set_registry_uri("databricks-uc")

input_example = {"messages": [{"role": "user", "content": "What is an AI gateway?"}]}

with mlflow.start_run(run_name="support_agent"):
    logged = mlflow.pyfunc.log_model(
        name="support_agent",
        python_model=agent_path,
        input_example=input_example,
        resources=[DatabricksServingEndpoint(endpoint_name=ENDPOINT_NAME)],
        pip_requirements=["mlflow[databricks]>=3.1", "openai"],
    )

print("Logged model:", logged.model_uri)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Load it back and test
# MAGIC Loading the logged model and calling `predict` exercises the real artifact — the model
# MAGIC call goes through the governed endpoint.

# COMMAND ----------

agent = mlflow.pyfunc.load_model(logged.model_uri)
out = agent.predict(input_example)
show_json(out)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Register to Unity Catalog
# MAGIC The agent becomes a versioned, permissioned UC model.

# COMMAND ----------

uc_name = f"{CATALOG}.{SCHEMA}.support_agent"
registered = mlflow.register_model(model_uri=logged.model_uri, name=uc_name)
print(f"Registered {uc_name} version {registered.version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Deploy (optional next step)
# MAGIC Deploying creates a governed serving endpoint for the agent (with review app + feedback
# MAGIC logging). It provisions dedicated capacity and takes several minutes, so it's left as an
# MAGIC explicit step:
# MAGIC
# MAGIC ```python
# MAGIC from databricks import agents
# MAGIC agents.deploy(uc_name, registered.version)
# MAGIC ```
# MAGIC
# MAGIC Once deployed, evaluate it with `agents/02-agent-evaluation` by pointing `predict_fn` at
# MAGIC the agent's endpoint.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Takeaways
# MAGIC - The agent calls the **governed endpoint**, so it inherits every Gateway control —
# MAGIC   governance is centralized, not reimplemented per agent.
# MAGIC - Declaring the endpoint as a **resource** gives the deployed agent automatic, scoped
# MAGIC   access — no embedded tokens.
# MAGIC - Registered in **Unity Catalog**, the agent is versioned and permissioned like any
# MAGIC   other asset; its deployment endpoint is itself governable by the Gateway.
# MAGIC - Add governed tools (`tools/03-function-calling`, `tools/01-managed-mcp`) and quality
# MAGIC   gates (`agents/02-agent-evaluation`) to complete the loop.
