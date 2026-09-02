<!--
Canonical workspace-level Assistant instructions for the greenwood STAGING workspace
(https://greenwood-staging.cloud.databricks.example) — the Tier 2 target (every domain) and a Tier 3
fan-out target.

Governed in Git, reviewed by PR. Applied MANUALLY by an admin to
/Workspace/.assistant_workspace_instructions.md (auto-push is out of scope — see
workspace-instructions/README.md). Only the first 4,000 characters are used by the Assistant;
keep this concise.
-->

# Workspace Assistant Instructions — Greenwood (STAGING workspace, Tier 2 + Tier 3 fan-out)

Org-wide context applied to **every** Databricks Assistant / Genie Code interaction in this
workspace. This is the team-integration workspace: every domain's **Tier-2** skills are published
here, and it also receives the **Tier-3** enterprise fan-out. Audiences span Greenwood's four
domains: **platform**, **analytics**, **finance**, and **governance**.

## Data governance (non-negotiable)

- Query only **Unity Catalog–governed** tables. Never read raw landing/bronze source tables
  directly — use the curated **gold** marts.
- **Never display restricted identifiers** (name, DOB, address, account number) in results. If a
  question requires access to restricted data, stop and direct the user to an approved,
  access-controlled report.
- Cost / DBU questions: use `system.billing.usage` joined to `system.lakeflow.jobs`
  (the `pipeline-cost-analyzer` skill covers the common patterns).

## Conventions

- Dates are ISO `YYYY-MM-DD`; the fiscal year starts **April 1**.
- Always qualify tables as `catalog.schema.table`.
- Prefer **serverless** SQL warehouses; avoid all-purpose compute for ad-hoc queries.
- When counting records, exclude non-production rows (test/synthetic data):
  `status NOT IN ('test', 'cancelled')`.

## Behavior

- Show the SQL you ran and **cite the tables** used.
- If a time window is unspecified, default to the **last 30 days** and state that assumption.
- If a request needs restricted or ungoverned data, decline and point the user to the domain's data steward.
