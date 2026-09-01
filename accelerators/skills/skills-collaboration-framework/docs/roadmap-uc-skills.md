# UC Skills Roadmap — From Folder Sync to Unity Catalog

## Three horizons — Databricks as the skill control plane

The same Git + CI authoring pipeline carries through all three; only the **publish target** moves.

1. **Today — Databricks is the central skill repository.** Git + CI publishes governed skills to
   `/Workspace/.assistant/skills/`; Genie Code auto-loads them. The repo is the single source of truth.
2. **Next — Unity AI Gateway becomes the serving layer.** The Git + CI pipeline becomes the
   Gateway's *supply chain*. Only the publish step changes; the governed library carries over with
   **zero rework**.
3. **Then — any model or agent requests governed skills from the Gateway.** External models/agents
   pull skills under Unity Catalog governance — one catalog of trusted skills serving every
   assistant, agent, and app.

> GTM one-liner: *"Build your governed skill library on Databricks now; when UC Gateway skills land,
> it becomes the serving source of truth for every model and agent — with zero rework."*
> (No external GA dates — roadmap-dependent; align with PM.)

## Today: Folder-Sync Model (what this repo builds)

The framework's authoring + governance layer — Git, PRs, CODEOWNERS, CI gates, `registry.yaml` —
is **publish-target agnostic**. Today it publishes via `databricks workspace import-dir` to
`/.assistant/skills/`. All governance (tier model, AI review, approval records,
deprecation enforcement) lives entirely in the Git + CI layer.

## Tomorrow: UC Skills Securable

Databricks is building a **UC Skills** securable — a first-class Unity Catalog object distributed
via AI Gateway MCP. When it ships, the only change in this framework is in `sync-skills.sh`:

| Today (folder sync) | Tomorrow (UC Skills) |
|---------------------|----------------------|
| `databricks workspace import-dir tier2/infrastructure /.assistant/skills` (skills land flat) | `databricks uc skills publish tier2/infrastructure/pipeline-cost-analyzer --catalog main --schema skills` |
| Tier isolation via separate workspaces (per-tier/domain sync targets) | Tier isolation via UC grant scopes |
| `users` group = CAN_READ on folder | `GRANT READ ON SKILL main.skills.pipeline-cost-analyzer TO infrastructure_users` |
| Genie Code reads from workspace folder | Genie Code + Claude Code + Cursor read from AI Gateway MCP |
| Deprecation = `workspace delete` | Deprecation = `DROP SKILL` or revoke grant |

## What survives the migration

Every layer except the sync step is preserved:

- **Tier model** — folder placement still signals reach; UC grant scopes map 1:1 to tier access rules
- **CI gates** — `lint-and-scan.sh`, `validate-meta.sh`, `ai-review.sh` are unchanged
- **Registry** — `registry.yaml` becomes the provisioning manifest for `uc skills publish`
- **CODEOWNERS** — review routing is unchanged; the same PR process governs publishing
- **Deprecation** — `prune-deprecated.sh` swaps `workspace delete` for `DROP SKILL`
- **Vendor-neutral CI** — Azure Pipelines calls the updated `sync-skills.sh`; the same scripts port to GitHub Actions or any CI unchanged

## Distribution via AI Gateway MCP

UC Skills exposed via MCP allow any MCP-compatible client (Genie Code, Claude Code, Cursor, VS Code
Copilot) to load enterprise-governed skills without workspace folder access. The `SKILL.md` name +
description continue to drive auto-load; the runtime changes, the authoring contract does not.

## Timeline

UC Skills is on the DAIS 2026 platform roadmap. This framework is architected to onboard on day
one — only `sync-skills.sh` needs updating; everything else is already aligned with the UC model.
