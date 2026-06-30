# Databricks notebook source
# MAGIC %md
# MAGIC # Lab — Mosaic AI Agent Framework on a governed endpoint
# MAGIC
# MAGIC Build, log, and register a `ChatAgent` whose model calls run through the governed endpoint.
# MAGIC
# MAGIC See README.md for details.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade "mlflow[databricks]>=3.1" databricks-agents openai
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ../../../shared/setup

# COMMAND ----------

# MAGIC %md ### Define the agent (models-from-code)

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

# MAGIC %md ### Log the agent to MLflow

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

# MAGIC %md ### Load it back and test

# COMMAND ----------

agent = mlflow.pyfunc.load_model(logged.model_uri)
out = agent.predict(input_example)
show_json(out)

# COMMAND ----------

# MAGIC %md ### Register to Unity Catalog

# COMMAND ----------

uc_name = f"{CATALOG}.{SCHEMA}.support_agent"
registered = mlflow.register_model(model_uri=logged.model_uri, name=uc_name)
print(f"Registered {uc_name} version {registered.version}")

# COMMAND ----------

# MAGIC %md ### Deploy (optional next step)
# MAGIC
# MAGIC ```python
# MAGIC from databricks import agents
# MAGIC agents.deploy(uc_name, registered.version)
# MAGIC ```
