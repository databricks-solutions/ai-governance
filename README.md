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
**Tools**, **Agents**, and **Developer tools**.

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

See [`docs/architecture.md`](docs/architecture.md) for detail.

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
Self-contained guardrail track — apply, deploy a custom safety model, benchmark. See [`labs/guardrails`](labs/guardrails).

| # | Lab | What it shows |
|---|-----|---------------|
| 01 | [Apply guardrails](labs/guardrails/01-apply-guardrails) | PII masking, safety, topic moderation, keyword filtering at the gateway |
| 02 | [Deploy `gpt-oss-safeguard-20b`](labs/guardrails/02-deploy-oss-safeguard) | Custom policy-driven safety model + head-to-head vs Claude Haiku |
| 03 | [Guardrail benchmark](labs/guardrails/03-guardrail-benchmark) | Precision / recall / **FPR** across PII redaction, PII blocking, unsafe content, jailbreak, hallucination; online vs two judges + DSPy/GEPA alignment |

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

```bash
# 1. Install the Databricks CLI and authenticate (host + token, or a profile).
export DATABRICKS_HOST=https://<your-workspace>.cloud.databricks.com
export DATABRICKS_TOKEN=<token>

# 2. Deploy the governed endpoint, schema, and job.
scripts/deploy.sh validate
scripts/deploy.sh deploy

# 3. Open labs/models/01-rate-limiting/notebook.py in the workspace and run it,
#    or run all core labs as a job:
scripts/deploy.sh run
```

Full prerequisites and walkthrough: [`docs/getting-started.md`](docs/getting-started.md).
Architecture and where governance data lands: [`docs/architecture.md`](docs/architecture.md).

## Repository layout

```
databricks.yml          Asset Bundle root (endpoint + schema + job)
resources/              Bundle resource definitions
shared/setup.py         %run helper used by the labs
labs/                   models / tools / agents / zero-to-production
docs/                   getting started, architecture
scripts/deploy.sh       CLI wrapper (validate / deploy / run / destroy)
```

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
