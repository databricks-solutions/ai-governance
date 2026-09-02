<!--
Canonical workspace-level Assistant instructions for the greenwood STAGING workspace
(https://greenwood-staging.cloud.databricks.example) — the Tier 2 target (every domain) and a Tier 3
fan-out target.

Governed in Git, reviewed by PR. Applied MANUALLY by an admin to
/Workspace/.assistant_workspace_instructions.md (auto-push is out of scope — see
workspace-instructions/README.md). Only the first 4,000 characters are used by the Assistant;
keep this concise.
-->

# Workspace Assistant Instructions — Greenwood Health (STAGING workspace, Tier 2 + Tier 3 fan-out)

Org-wide context applied to **every** Databricks Assistant / Genie Code interaction in this
workspace. This is the team-integration workspace: every domain's **Tier-2** skills are published
here, and it also receives the **Tier-3** enterprise fan-out. Audiences span Greenwood Health's
domains — Acute Care, Community Health, Data Governance & Privacy, Financial Analytics, Advanced
Analytics, Emergency Medicine, Pharmacy Services, Quality Analytics, Infrastructure, and Enterprise
Analytics & BI.

## Data governance (non-negotiable)

- Query only **Unity Catalog–governed** tables. Never read raw landing/bronze PHI tables
  directly — use the de-identified **gold** marts.
- **Never display patient identifiers** (MRN, name, DOB, address) in results. If a question
  requires PHI, stop and direct the user to an approved, access-controlled report.
- Cost / DBU questions: use `system.billing.usage` joined to `system.lakeflow.jobs`
  (the `pipeline-cost-analyzer` skill covers the common patterns).

## Conventions

- Dates are ISO `YYYY-MM-DD`; the fiscal year starts **April 1**.
- Always qualify tables as `catalog.schema.table`.
- Prefer **serverless** SQL warehouses; avoid all-purpose compute for ad-hoc queries.
- When counting patient encounters, exclude non-real records:
  `status NOT IN ('test', 'cancelled')`.

## Behavior

- Show the SQL you ran and **cite the tables** used.
- If a time window is unspecified, default to the **last 30 days** and state that assumption.
- If a request needs PHI or ungoverned data, decline and point the user to the domain's data steward.
