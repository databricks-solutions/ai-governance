# Governance principles

A useful way to scope an AI governance POC is to evaluate it against the same pillars you
use for any production platform. Each pillar below maps to concrete Unity AI Gateway
capabilities and the labs that demonstrate them.

## Security & compliance
- **Guardrails** — PII masking/blocking, safety filtering, topic moderation, keyword
  filtering on inputs and outputs. → [Lab 02](../labs/models/02-ai-guardrails)
- **Access control** — Unity Catalog permissions on endpoints, MCP servers, and functions.
  → Tools / Agents labs
- **Auditability** — payload logging to Unity Catalog inference tables.
  → [Lab 03](../labs/models/03-usage-tracking-finops)

## Reliability
- **Fallbacks** — automatic failover across served entities/providers.
  → [Lab 04](../labs/models/04-fallbacks)
- **Traffic routing** — load balancing and safe canary/A-B rollouts.
  → [Lab 05](../labs/models/05-traffic-routing)

## Performance efficiency
- **Traffic routing** — balance load across backends.
- **Semantic caching** — serve similar prompts from cache. → [Lab 07](../labs/models/07-semantic-caching)
- **Streaming** — responsive token-by-token delivery. → [dev-tools/streaming](../labs/dev-tools/streaming)

## Operational excellence
- **Usage tracking & observability** — system tables + AI/BI dashboard.
  → [Lab 03](../labs/models/03-usage-tracking-finops)
- **Tracing** — step-level visibility for agents/pipelines. → [dev-tools/tracing](../labs/dev-tools/tracing)
- **Evaluation & monitoring** — continuous quality/safety checks. → [agents/02](../labs/agents/02-agent-evaluation)

## Cost optimization (FinOps)
- **Rate limits** — cap consumption per endpoint and per user. → [Lab 01](../labs/models/01-rate-limiting)
- **Usage & cost rollups + budget alerts** — attribute spend and act on it.
  → [Lab 03](../labs/models/03-usage-tracking-finops)
- **Semantic caching** — avoid paying twice for equivalent prompts. → [Lab 07](../labs/models/07-semantic-caching)

## Suggested POC flow
1. Deploy the governed endpoint (`scripts/deploy.sh deploy`).
2. Establish guardrails and rate limits (Labs 02, 01) — the baseline safety/cost controls.
3. Add reliability (Labs 04, 05).
4. Turn on the FinOps view (Lab 03) and review real consumption.
5. Extend into Tools and Agents once the model layer is governed.
