# AI Governance Workshop — FAQ

Common questions about the hands-on workshop. This file is readable directly in the repo
and is also rendered in the app under **FAQ**.

## What is this workshop?

A guided, hands-on session where the customer's platform team stands up a **governed AI
control plane** on their own workspace — organized around three pillars: **choice, cost,
and control**. Each step has a concept, a live "Try It" test against the workspace, and a
"Verify" check that proves the control fired.

## How long does it take?

Three phases, and the middle one is the only day in a room:

| Phase | Duration | What happens |
|---|---|---|
| **Prerequisites** | ~1 week | Entitlements, grants, previews, pilot users — mostly waiting on admins |
| **Workshop** | **3 hours hands-on + ~1 hour slides/discussion** | Test and validate live in your own workspace |
| **Follow-up** | 1–2 weeks | Close what didn't land on the day |

Each optional **accelerator** is a ~3-hour add-on on one customer need — run the one that
matches your priority, not all six.

## Why isn't <capability> in the workshop?

Four hours is about 19 steps including discussion, so the workshop proves a **governed path
works** rather than covering every Gateway feature. Some things are deliberately left out:
taking inventory of your current estate (pre-work over your own endpoints and spend), the
full migration sequence (run in parallel over weeks — there is no in-place rename), network
configuration like PrivateLink and egress policies (account-level infrastructure), and
passthrough mode (an escape hatch that loses cost tracking, rate limits, and policies).

None of that is lost — it's in the detailed field guides for adopting Unity AI Gateway fresh,
or migrating from a previous Databricks or external gateway:

- **Unity AI Gateway Adoption Guide** — target state, object model, Unity Catalog layout,
  telemetry, budgets, network.
- **Unity AI Gateway Migration Guide** — the phase-by-phase sequence off legacy Model Serving
  or a third-party gateway (LiteLLM, Portkey, Kong, APIM), plus production-readiness and
  rollback checklists.

Ask your Databricks team for both.

## Do I need admin access to the workspace?

Yes for the setup steps (creating the governed endpoint, configuring guardrails in the AI
Gateway UI, account-console budgets). The prerequisites list the exact entitlements; confirm
them before the day so the room isn't blocked.

## What are the prerequisites?

- Unity AI Gateway (Beta) enabled
- Workspace Unity Catalog enabled with foundation models
- Serverless compute enabled
- A SQL warehouse the app can use
- Unity Catalog groups ready for the pilot users

## How is my progress tracked?

Progress is stored in a JSON file on a Unity Catalog volume on the deployment — no database
required. The app is deployed once per workshop, so there is a single set of progress and
nothing to identify. You can pause and resume; nothing is lost between sessions.

A step can end in one of three states, and the distinction is deliberate: **done** (proved),
**action needed** (the step ran, but nothing is proven yet — a guided UI action, or a
telemetry query with no data yet), and **failed**. "Action needed" is never counted as
complete, so the progress bar and the exported report stay honest.

## What are the "Try It" and "Verify" actions actually doing?

They run real checks against the connected workspace — listing serving endpoints, creating a
governed endpoint, querying system/inference tables, creating an MCP policy function, etc.
They're read-mostly and safe; anything destructive is surfaced as a guided manual step instead.

## Why do some steps say "MANUAL (UI)"?

A few controls aren't yet available through the API (e.g. attaching a guardrail or a service
policy in the AI Gateway UI, or creating an account-console budget). Those are marked MANUAL
with a deep link to the exact place in the workspace to complete them.

## What are the six accelerators?

- **MCP Server Setup & Testing** — on-behalf-of auth to a managed/external MCP.
- **Agent Registry Setup & Testing** — register, version, and own a representative agent.
- **Coding Agent Setup & Testing** — govern dev-agent traffic with per-developer attribution
  and code-secret detection.
- **External Provider Setup & Testing** — route Bedrock/OpenAI/Anthropic through the Gateway.
- **Policies & Guardrails (PII & Safety)** — safety filter, custom PII-leakage judge, red-team dataset.
- **Skills** — build, govern, and deploy Agent Skills in Genie Code with a tiered registry.

## What do I get at the end?

Export the outcomes from the Walkthrough page:

- a per-step **report** (`.md`) — every step with its status and notes, grouped by pillar,
  with the incomplete items listed as next steps. This is the leave-behind.
- an **outcomes.json** — the same data machine-readable (`schema_version` 2), for follow-up.

Both include the accelerators. The incomplete items are
the follow-up list: they become the 1–2 weeks of work after the workshop, and they are the
reason the app distinguishes "action needed" from "done".

## Where do I report a bug or request a feature?

Use the links in the sidebar (Repository · Submit feature request · File an issue), or open an
issue on the repo directly.
