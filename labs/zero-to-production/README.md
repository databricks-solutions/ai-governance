# Zero to production

**Status:** ✅ Built

A capstone walkthrough that takes one endpoint from "returns text" to "production-ready,"
applying each Unity AI Gateway control in adoption order and leaving the endpoint in a
sensible governed state. It composes the individual Models/Tools labs into one narrative.

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

## Databricks features
- The full Unity AI Gateway control set on one endpoint, plus Unity Catalog functions and system-table observability.

## Prerequisites
- The bundle deployed (`scripts/deploy.sh deploy`).
- Permissions to update the endpoint's config + AI Gateway, and to create UC functions.

## Run it
Open `notebook.py` and run top-to-bottom. It's idempotent — safe to re-run. For depth on
any step, follow the linked lab in that section.
