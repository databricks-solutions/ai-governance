# AI Governance Workshop — FAQ

Common questions about the hands-on workshop. This file is readable directly in the repo
and is also rendered in the app under **FAQ**.

## What is this workshop?

A guided, hands-on session where the customer's platform team stands up a **governed AI
control plane** on their own workspace — organized around three pillars: **choice, cost,
and control**. Each step has a concept, a live "Try It" test against the workspace, and a
"Verify" check that proves the control fired.

## How long does it take?

The core workshop is a half-day. Each optional **accelerator** is a ~4-hour add-on focused
on one customer need — run the one that matches their priority, not all five.

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

Progress is stored per account (by Salesforce id) in a Lakebase table on the deployment. You
can pause and resume; nothing is lost between sessions.

## What are the "Try It" and "Verify" actions actually doing?

They run real checks against the connected workspace — listing serving endpoints, creating a
governed endpoint, querying system/inference tables, creating an MCP policy function, etc.
They're read-mostly and safe; anything destructive is surfaced as a guided manual step instead.

## Why do some steps say "MANUAL (UI)"?

A few controls aren't yet available through the API (e.g. attaching a guardrail or a service
policy in the AI Gateway UI, or creating an account-console budget). Those are marked MANUAL
with a deep link to the exact place in the workspace to complete them.

## What are the five accelerators?

- **MCP Server Setup & Testing** — on-behalf-of auth to a managed/external MCP.
- **Agent Registry Setup & Testing** — register, version, and own a representative agent.
- **Coding Agent Setup & Testing** — govern dev-agent traffic with per-developer attribution
  and code-secret detection.
- **External Provider Setup & Testing** — route Bedrock/OpenAI/Anthropic through the Gateway.
- **Policies & Guardrails (PII & Safety)** — safety filter, custom PII-leakage judge, red-team dataset.

## What do I get at the end?

Export the outcomes from the Introduction page: a per-step **report** (the customer
leave-behind) and an **outcomes.json** that the internal Databricks sales app ingests to track
the account and its next steps.

## Where do I report a bug or request a feature?

Use the links in the sidebar (Repository · Submit feature request · File an issue), or open an
issue on the repo directly.
