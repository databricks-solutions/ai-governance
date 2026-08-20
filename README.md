# Databricks Unity AI Gateway — POC Labs

```
Hands-on labs for running a proof of concept with the Databricks Unity AI Gateway.
Each lab is a self-contained Databricks notebook that applies one production
governance control — rate limiting, guardrails, usage/cost tracking, fallbacks,
traffic routing — to a real Model Serving endpoint, and proves it works.
```

The Unity AI Gateway puts a single, governed control plane in front of the models,
tools, and agents your organization uses. This repo shows how to stand that up as a
proof of concept: deploy one endpoint, then layer on each control and watch it take
effect. Labs are organized exactly the way you'd evaluate the platform — **Models**,
**Guardrails**, **Tools**, and **Agents** — and the whole workshop deploys from a single
Databricks Asset Bundle.

> The Unity AI Gateway is in Beta. Feature availability and API shapes may change; the
> labs use the documented REST/SDK surfaces and are easy to adjust.

## Architecture

```
        clients / agents / apps
                  │
                  ▼
        ┌────────────────────────┐
        │   Unity AI Gateway      │  rate limits · guardrails · usage tracking
        │  (governed endpoint)    │  payload logging · fallbacks · traffic routing
        └───────────┬────────────┘
                    │
      ┌─────────────┼──────────────┐
      ▼             ▼              ▼
 Foundation     External      Custom / fine-
 Models         models        tuned models
      │
      ▼
 Unity Catalog: inference tables, system tables, permissions, lineage
```

**Where governance data lands:** per-request token usage in `system.serving.endpoint_usage`; DBU cost
in `system.billing.usage`; full request/response payloads in Unity Catalog **inference tables**
(`<catalog>.<schema>.gateway_*`) for audit, eval, and guardrail review.

## Labs

### 🧠 Unity AI Gateway for Models
General platform governance — setup, cost control, tagging, resilience.

| # | Lab | What it shows |
|---|-----|---------------|
| 01 | [Rate limiting](labs/models/01-rate-limiting) | Per-endpoint & per-user token/request limits; observe `429` |
| 02 | [Usage tracking & FinOps](labs/models/02-usage-tracking-finops) | Tokens & cost via system tables + budget alert + AI/BI dashboard |
| 03 | [Fallbacks](labs/models/03-fallbacks) | Automatic failover across served entities |
| 04 | [Traffic routing](labs/models/04-traffic-routing) | Load balancing + A/B/canary across backends |

### 🛡️ Guardrails
Self-contained guardrail track — apply, then benchmark. See [`labs/guardrails`](labs/guardrails).

| Part | Lab | What it shows |
|------|-----|---------------|
| 1 | [Apply guardrails](labs/guardrails/01-apply-guardrails) | PII masking, safety, topic moderation, keyword filtering at the gateway |
| 2 | [Guardrail benchmark](labs/guardrails/02-guardrail-benchmark) | Precision / recall / **FPR** across PII redaction, PII blocking, unsafe content, jailbreak, hallucination; online vs two managed judges + DSPy/GEPA alignment |

### 🔧 Unity AI Gateway for Tools
| Lab | What it shows |
|-----|---------------|
| [Managed MCP servers](labs/tools/01-managed-mcp) | UC functions, Genie, Vector Search as governed MCP tools |
| [Function calling](labs/tools/03-function-calling) | Unity Catalog functions as governed tools |

### 🤖 Unity AI Gateway for Agents
| Lab | What it shows |
|-----|---------------|
| [Agent Framework](labs/agents/01-agent-framework) | Mosaic AI agent on governed endpoints, logged + registered to UC |
| [Agent evaluation](labs/agents/02-agent-evaluation) | Evaluate & monitor governed agents with MLflow judges |
| [OpenAI Agents SDK](labs/agents/03-openai-agents-sdk) | Existing agent stack on the OpenAI-compatible endpoint |

### 🏁 Capstone
| Lab | What it shows |
|-----|---------------|
| [Zero to production](labs/zero-to-production) | One endpoint, end to end: observability → guardrails → limits → fallback → governed tools → validate → checklist |

Every lab above is built, deployable, and verified end-to-end in a workspace.

### Roadmap
Planned additions: external-model providers, semantic caching (Vector Search), MCP client
authorization, custom MCP on Databricks Apps, multi-agent orchestration, and developer
utilities (tracing, streaming, rate-limit tester, mock server).

## Getting started

The whole workshop deploys from **one Databricks Asset Bundle**.

```bash
# 1. Authenticate the Databricks CLI to your workspace (a profile, or host + token).
# 2. Point the bundle at your workspace: set targets.dev.workspace.host in databricks.yml.
# 3. Create the endpoint's backing secret (one time):
databricks secrets create-scope ai_governance
databricks secrets put-secret  ai_governance api_token      # paste a PAT

# 4. Deploy the gateway endpoint, schema, jobs, and every lab notebook:
databricks bundle deploy -t dev

# 5. Run a lab group as a job — or just open a notebook and run it:
databricks bundle run run_core_labs          -t dev    # rate limit · usage/FinOps · fallbacks · routing
databricks bundle run run_guardrail_labs     -t dev    # apply guardrails
databricks bundle run run_tools_labs         -t dev    # managed MCP · function calling
databricks bundle run run_agent_labs         -t dev    # agent framework · evaluation
databricks bundle run run_zero_to_production  -t dev    # capstone
```

**Prerequisites:** a workspace with Model Serving + Foundation Model APIs, the Databricks CLI, and
permission to create a serving endpoint, a Unity Catalog schema, and jobs. The guardrail **benchmark**
(Part 2) is interactive — it streams datasets and calls models — so open it and set the `n_examples`
widget rather than running it as a job.

## Repository layout

```
databricks.yml          Asset Bundle root — one bundle for the whole workshop
resources/              Bundle resources (endpoint + schema + jobs)
shared/setup.py         %run helper used by every lab
labs/                   models · guardrails · tools · agents · zero-to-production
                        (each lab folder = README.md + notebook.py)
```

## Maintainers

Maintained by the Databricks Field Engineering team. For questions or issues, open a GitHub
issue (below) or reach a maintainer:

- Scott McKean — scott.mckean@databricks.com
- Tim Lortz — tim.lortz@databricks.com

## How to get help

Databricks support doesn't cover this content. For questions or bugs, please open a
GitHub issue and the team will help on a best effort basis.

## License

&copy; 2025 Databricks, Inc. All rights reserved. The source in this repository is
provided subject to the Databricks License [https://databricks.com/db-license-source].
All included or referenced third party libraries are subject to their respective licenses.

| library | description | license | source |
|---------|-------------|---------|--------|
| databricks-sdk | Databricks SDK for Python | Apache 2.0 | https://github.com/databricks/databricks-sdk-py |
| mlflow | ML lifecycle platform | Apache 2.0 | https://github.com/mlflow/mlflow |
| openai | OpenAI Python client | Apache 2.0 | https://github.com/openai/openai-python |
| requests | HTTP client | Apache 2.0 | https://github.com/psf/requests |
| polars | DataFrame library | MIT | https://github.com/pola-rs/polars |

A full third-party dependency audit for the workshop app and labs — versions, licenses,
and purpose — is in [DEPENDENCIES.md](DEPENDENCIES.md).
