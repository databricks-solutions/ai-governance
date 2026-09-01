# Workspace instructions (governed, manually applied)

**Workspace instructions** are org-wide context the Databricks Assistant / Genie Code injects
into *every* interaction in a workspace — conventions, governed data sources, safety rules. They
are the sibling of skills: skills load on description match; instructions are **always on**.

This directory holds the **canonical, PR-reviewed** instructions for each workspace. One file per
workspace, mapped to the URLs in [`../workspaces.json`](../workspaces.json):

| File | Workspace | Tiers served |
|------|-----------|--------------|
| `greenwood-dev.md` | `https://dbc-fb813e75-e5db.cloud.databricks.com` | Tier 1 sandbox + Tier 3 fan-out |
| `greenwood-staging.md` | `https://dbc-e1d9ab39-ffcf.cloud.databricks.com` | Tier 2 (all domains) + Tier 3 fan-out |
| `greenwood-prod.md` | `https://dbc-fbcbb704-ba3c.cloud.databricks.com` | Tier 3 (enterprise) fan-out |

## Why these are governed like a protected file

A workspace instruction shapes **every** Assistant response (far higher blast radius than any
single skill, which only loads on a description match). So changes here are **council-reviewed**
and routed by `CODEOWNERS`, the same as `governance.yaml` — propose by PR, merge only on
authorized review.

## How they are applied (manual — auto-push is out of scope)

Workspace instructions live at **`/Workspace/.assistant_workspace_instructions.md`** in the
workspace (per-user equivalent: `/Users/<email>/.assistant_instructions.md`). Only the **first
4,000 characters** are used — keep each file concise.

After a change merges to `main`, a workspace admin applies it manually:

1. In Genie Code → **Settings** → **Workspace instructions**, create/open the instructions file.
2. Paste the merged contents of this workspace's file.

> **Auto-push is out of scope by choice, not by limitation.** Because the target is just a
> workspace file, the same Workspace import API/CLI that `sync-skills.sh` uses could write it —
> e.g. `databricks workspace import workspace-instructions/greenwood-dev.md
> /Workspace/.assistant_workspace_instructions.md --format SOURCE --overwrite` (against that
> workspace's host). We keep it manual for now; wiring it into the sync stage is a future capability.
