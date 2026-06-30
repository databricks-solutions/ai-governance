# Zero to production

**A capstone that takes one endpoint from "returns text" to "production-ready," applying each Unity AI Gateway control in adoption order.**

## What you'll do
1. Confirm the governed endpoint.
2. Turn on observability (usage tracking + payload logging).
3. Apply safety + PII guardrails.
4. Apply production rate limits.
5. Add a fallback for resilience.
6. Publish a governed Unity Catalog tool.
7. Smoke-test the fully governed endpoint.
8. Point at the usage/cost telemetry (FinOps).
9. Review a production checklist (access control, budgets, evaluation, networking, change management).

## How it works
This capstone composes the individual Models and Tools labs into one narrative, applying each
control in the order you'd actually adopt it and leaving the endpoint in a sensible, governed
state. Observability goes on first so you can always answer "who called what, and what did it
cost?"; then guardrails, rate limits, and a fallback model; then governed tools published as
Unity Catalog functions. Everything configures one endpoint that every caller (apps, agents,
notebooks) goes through, and the notebook is idempotent so it's safe to re-run. For depth on any
step, follow the linked lab in that section.

## Run it
Open `notebook.py` and run top-to-bottom, or run the `[AI Governance] Zero to production capstone` job. Requires the bundle deployed:
`databricks bundle deploy -t dev`.
