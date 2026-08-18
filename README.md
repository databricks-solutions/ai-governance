# Databricks Unity AI Gateway Ã¢ÂÂ POC Labs

```
Hands-on labs for running a proof of concept with the Databricks Unity AI Gateway.
Each lab is a self-contained Databricks notebook that applies one production
governance control Ã¢ÂÂ rate limiting, guardrails, usage/cost tracking, fallbacks,
traffic routing Ã¢ÂÂ to a real Model Serving endpoint, and proves it works.
```

The Unity AI Gateway puts a single, governed control plane in front of the models,
tools, and agents your organization uses. This repo shows how to stand that up as a
proof of concept: deploy one endpoint, then layer on each control and watch it take
effect. Labs are organized exactly the way you'd evaluate the platform Ã¢ÂÂ **Models**,
**Guardrails**, **Tools**, and **Agents** Ã¢ÂÂ and the whole workshop deploys from a single
Databricks Asset Bundle.

> The Unity AI Gateway is in Beta. Feature availability and API shapes may change; the
> labs use the documented REST/SDK surfaces and are easy to adjust.

## Architecture

```
        clients / agents / apps
                  Ã¢ÂÂ
                  Ã¢ÂÂ¼
        Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
        Ã¢ÂÂ   Unity AI Gateway      Ã¢ÂÂ  rate limits ÃÂ· guardrails ÃÂ· usage tracking
        Ã¢ÂÂ  (governed endpoint)    Ã¢ÂÂ  payload logging ÃÂ· fallbacks ÃÂ· traffic routing
        Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ¬Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
                    Ã¢ÂÂ
      Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ¼Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
      Ã¢ÂÂ¼             Ã¢ÂÂ¼              Ã¢ÂÂ¼
 Foundation     External      Custom / fine-
 Models         models        tuned models
      Ã¢ÂÂ
      Ã¢ÂÂ¼
 Unity Catalog: inference tables, system tables, permissions, lineage
```

**Where governance data lands:** per-request token usage in `system.serving.endpoint_usage`; DBU cost
in `system.billing.usage`; full request/response payloads in Unity Catalog **inference tables**
(`<catalog>.<schema>.gateway_*`) for audit, eval, and guardrail review.

## Labs

### Ã°ÂÂ§Â  Unity AI Gateway for Models
General platform governance Ã¢ÂÂ setup, cost control, tagging, resilience.

| # | Lab | What it shows |
|---|-----|---------------|
| 01 | [Rate limiting](labs/models/01-rate-limiting) | Per-endpoint & per-user token/request limits; observe `429` |
| 02 | [Usage tracking & FinOps](labs/models/02-usage-tracking-finops) | Tokens & cost via system tables + budget alert + AI/BI dashboard |
| 03 | [Fallbacks](labs/models/03-fallbacks) | Automatic failover across served entities |
| 04 | [Traffic routing](labs/models/04-traffic-routing) | Load balancing + A/B/canary across backends |

### Ã°ÂÂÂ¡Ã¯Â¸Â Guardrails
Self-contained guardrail track Ã¢ÂÂ apply, then benchmark. See [`labs/guardrails`](labs/guardrails).

| Part | Lab | What it shows |
|------|-----|---------------|
| 1 | [Apply guardrails](labs/guardrails/01-apply-guardrails) | PII masking, safety, topic moderation, keyword filtering at the gateway |
| 2 | [Guardrail benchmark](labs/guardrails/02-guardrail-benchmark) | Precision / recall / **FPR** across PII redaction, PII blocking, unsafe content, jailbreak, hallucination; online vs two managed judges + DSPy/GEPA alignment |

### Ã°ÂÂÂ§ Unity AI Gateway for Tools
| Lab | What it shows |
|-----|---------------|
| [Managed MCP servers](labs/tools/01-managed-mcp) | UC functions, Genie, Vector Search as governed MCP tools |
| [Function calling](labs/tools/03-function-calling) | Unity Catalog functions as governed tools |

### Ã°ÂÂ¤Â Unity AI Gateway for Agents
| Lab | What it shows |
|-----|---------------|
| [Agent Framework](labs/agents/01-agent-framework) | Mosaic AI agent on governed endpoints, logged + registered to UC |
| [Agent evaluation](labs/agents/02-agent-evaluation) | Evaluate & monitor governed agents with MLflow judges |
| [OpenAI Agents SDK](labs/agents/03-openai-agents-sdk) | Existing agent stack on the OpenAI-compatible endpoint |

### Ã°ÂÂÂ Capstone
| Lab | What it shows |
|-----|---------------|
| [Zero to production](labs/zero-to-production) | One endpoint, end to end: observability Ã¢ÂÂ guardrails Ã¢ÂÂ limits Ã¢ÂÂ fallback Ã¢ÂÂ governed tools Ã¢ÂÂ validate Ã¢ÂÂ checklist |

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

# 5. Run a lab group as a job Ã¢ÂÂ or just open a notebook and run it:
databricks bundle run run_core_labs          -t dev    # rate limit ÃÂ· usage/FinOps ÃÂ· fallbacks ÃÂ· routing
databricks bundle run run_guardrail_labs     -t dev    # apply guardrails
databricks bundle run run_tools_labs         -t dev    # managed MCP ÃÂ· function calling
databricks bundle run run_agent_labs         -t dev    # agent framework ÃÂ· evaluation
databricks bundle run run_zero_to_production  -t dev    # capstone
```

**Prerequisites:** a workspace with Model Serving + Foundation Model APIs, the Databricks CLI, and
permission to create a serving endpoint, a Unity Catalog schema, and jobs. The guardrail **benchmark**
(Part 2) is interactive Ã¢ÂÂ it streams datasets and calls models Ã¢ÂÂ so open it and set the `n_examples`
widget rather than running it as a job.

## Repository layout

```
databricks.yml          Asset Bundle root Ã¢ÂÂ one bundle for the whole workshop
resources/              Bundle resources (endpoint + schema + jobs)
shared/setup.py         %run helper used by every lab
labs/                   models ÃÂ· guardrails ÃÂ· tools ÃÂ· agents ÃÂ· zero-to-production
                        (each lab folder = README.md + notebook.py)
```

## Maintainers

Maintained by the Databricks Field Engineering team. For questions or issues, open a GitHub
issue (below) or reach a maintainer:

- Scott McKean â scott.mckean@databricks.com
- Tim Lortz â tim.lortz@databricks.com

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

A full third-party dependency audit for the workshop app and labs — versions, licenses, and purpose — is in [DEPENDENCIES.md](DEPENDENCIES.md).
