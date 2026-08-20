# Accelerator build plan — from box-checking to compelling

The core workshop proves the control plane across choice / cost / control. The **accelerators**
are optional ~4-hour deep dives. One of them (**MCP Servers**, 10 steps) is strong; the other
four are thin — mostly `list` / `manual` / `readiness` steps that don't *prove* anything a
customer couldn't already assume. This plan deepens them.

## What makes an accelerator compelling

The bar is set by the MCP accelerator: **every step pairs a concept with a live "prove-it" test
and teaches one non-obvious thing.** The strongest steps prove a *silent failure* — a control
the customer would otherwise believe is in place. Thin steps lean on `manual:` deep-links and
`list`/`readiness` checks that only confirm a thing exists.

Design rules for every new step:
- A backend test in `server/tests_registry.py` that runs against the live workspace and returns
  a real result (not a link).
- `action_required` (not a false green) whenever the step ran but proved nothing yet.
- Honest about Beta features and known limitations — say what it can and cannot prove, and bake
  a "confirm on this account" state into anything that rides a preview.

## Where the demand is (field + community signal)

Prioritization is driven by where questions and pain concentrate, cross-checked against the
public state of practice. In rough order:

1. **Governing *managed* MCP** (DBSQL / Genie) — read-only enforcement for coding-agent users
   while UI users keep write. The single most-requested control.
2. **Coding agents through the gateway** — routing config-drift (traffic silently hitting a
   legacy endpoint while limits sit on the new model service), 429 / rate-limit behavior,
   per-developer attribution, OAuth vs PAT.
3. **Silent path-coverage gaps** — controls fire on the OpenAI-compatible chat path but may not
   on provider-native paths (`/ai-gateway/anthropic/v1/...`) that coding agents actually use.
4. **Guardrail *effectiveness*** — measuring whether guardrails work (PII redact/block, unsafe,
   jailbreak, hallucination), MASK vs BLOCK, policy rank + fail-closed, and custom guardrails.
5. **FinOps** — budgets, hard caps, per-user limits, smart routing, policies-as-code.
6. **Identity gap** — rate limits / guardrails on agent service principals; OBO attribution.

Market themes that reinforce these: gateway-as-enforcement-point, **MCP tool poisoning** as the
top MCP security worry, smart routing for large cost savings, privileged-execution governance
for coding agents, and observability-as-control-plane.

## Assessment of the current accelerators

| Accelerator | Steps | Verdict |
|---|---|---|
| MCP Servers | 10 | Solid — the model to match. |
| Coding Agents | 3 | Thin — route (manual) / attribution / secret scan. |
| Policies & Guardrails | 3 | Thin — effectiveness is only a "readiness" check. |
| External Providers | 3 | Thin — two manual/verify + one list. |
| Agent Registry | 3 | Thinnest — no agent actually built, versioned, or evaluated. |

## Build plan

### Tier 1 — highest demand, assets exist

**A. Coding Agents — rebuild into the "governance in one call" flow** *(in progress)*
- [x] Route coding agents at the governed model service; add OAuth-relay vs PAT.
- [x] **NEW — "is it actually routed?"** — detect coding-agent traffic on a legacy endpoint vs
  the governed model service. Test: `coding_agent_route_check`.
- [x] Per-developer attribution. Test: `coding_agent_usage` (existing).
- [x] **NEW — path coverage** — probe whether governance fires on the OpenAI-compatible path
  vs the provider-native path coding agents use. Test: `path_coverage_check`.
- [x] **NEW — live 429** — send a burst and observe the rate limit (honest about propagation
  lag and calling identity). Test: `rate_limit_429_demo`.
- [x] Per-user budget + hard cap. Test: `budget_status` (existing) + account-budgets deep link.
- [x] Code-secret detection. Test: `audit_scan` (existing).

**B. Policies & Guardrails — rebuild around effectiveness** *(done — 3 → 6 steps)*
- [x] PII **MASK vs BLOCK** — probe an SSN-echo prompt and classify block / mask / passthrough.
  Test: `pii_mask_vs_block`.
- [x] **Block shape + fail-closed** — report whether a block is a 4xx error or HTTP 200 + reason
  (the coding-agent "sticky block" gotcha), and state the fail-closed rule. Test:
  `guardrail_block_shape`.
- [x] **Path coverage** — does the guardrail fire on the provider-native path too? Reuses
  `path_coverage_check`.
- [x] **Effectiveness** — references the in-repo `labs/guardrails/02-guardrail-benchmark`
  (labeled scoring across PII/unsafe/jailbreak/hallucination, online vs offline judge, DSPy
  false-positive tuning) and confirms the payloads/telemetry a judge reads from. Custom/in-house
  guardrails plug in at the same layer. Test: `pii_safety_readiness`.
- [~] Policy **rank + fail-closed** — fail-closed is covered in the block-shape step; policy
  *rank ordering* is service-policy semantics, so it moves to the MCP accelerator (Tier 1C).

**C. MCP — extend the strong accelerator with the top gap** *(done — 9 → 11 steps)*
- [x] **Read-only enforcement** — classify the service's tools read vs write, and spell out the
  enforcement recipe for MCP Services (deny-writes policy + no `USE CONNECTION`) vs managed
  endpoints (read functions only + UC grants). Test: `mcp_readonly_enforcement`.
- [x] **Tool-poisoning scan** — heuristic scan of tool name/description for prompt-injection
  smuggled into metadata (the top MCP supply-chain risk). Test: `mcp_tool_metadata_scan`.

### Tier 2 — deepen after Tier 1
**D. External Providers** *(done — 3 → 5 steps)* — added credentials-in-secrets check
(`provider_secret_readiness`), `ISOLATED` catalog/workspace-binding check
(`workspace_binding_check`), and the Anthropic OAuth-relay path in the route step's concept.
**E. Agent Registry** *(done — 3 → 5 steps)* — added versioning + ownership check
(`agent_versions`) and the agent-endpoint identity gap (`agent_sp_attribution`:
limits/guardrails/usage-tracking on custom agent endpoints). An eval-scorer step is a good
future add (needs an eval run, not just a readiness check).

### Optional net-new accelerator
A dedicated **FinOps / cost-control** accelerator (budgets, hard caps, per-user limits, smart
routing, token-saving config, policies-as-code via the gateway API). Cost is already in the core
workshop, so this is only worth splitting out for a FinOps-led engagement — otherwise folded
into Coding Agents.

## New backend tests
`coding_agent_route_check`, `path_coverage_check`, `rate_limit_429_demo` *(Tier 1A — done)*;
then `guardrail_benchmark`, `pii_mask_vs_block`, `mcp_readonly_enforcement`,
`mcp_tool_metadata_scan`, and `agent_register_version` / `agent_eval_scorer` /
`agent_sp_attribution`.

## Caveats
Several items ride Beta features and known behaviors (managed-MCP policy coverage, provider-path
coverage, the sticky-block fix, Sensitive Data Detection, hard budget caps). Verify each on the
target account before promising — every new step reports `action_required` with a
"confirm on this account" message rather than a false green.
