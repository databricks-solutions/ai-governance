# Workshop prerequisites

Everything that must be true **before** the room sits down. Ordered by lead time, because the
items that stall a workshop are the ones needing an account admin, and those take days.

Send §1 and §2 to the customer at least **one week out**. Run §5 the **day before**.

> **The one-line test:** `GET /api/health` on the deployed app returns
> `{"status":"ok","config_problems":[]}`. If it names a problem, that is your blocker list.

---

## 1. Account admin — start here (days of lead time)

These cannot be fixed on the day. Nothing else matters if these are missing.

| # | Item | Why it's needed | Who |
|---|---|---|---|
| 1 | **Unity AI Gateway enabled** on the account and the workshop workspace | Nothing in the workshop works without it | Account admin |
| 2 | **`USE CATALOG` on `system` + `USE SCHEMA, SELECT` on `system.ai_gateway`** for the app's service principal | **6 steps** read this: spend by model, budget status, usage by project, coding-agent attribution, MCP telemetry, telemetry readiness | Account or metastore admin |
| 3 | **`USE SCHEMA, SELECT` on `system.access`** for the app's service principal | **2 steps**: the audit trail and the secret-leak scan | Account or metastore admin |
| 4 | **Service policies (Beta) enabled** — only if MCP policy steps are in scope | Attaching an ALLOW/DENY policy | Account admin |
| 5 | **Managed MCP preview enabled** — only if MCP steps are in scope | `/api/2.0/mcp/...` endpoints | Account admin |
| 6 | *Optional:* ability to **read grants on `system`** (MANAGE or metastore-admin) | `choice_default_access` reads them directly instead of asking an admin mid-session | Metastore admin |

On item 6: reading grants needs ownership, `MANAGE`, or metastore-admin, which the app's service
principal normally does **not** have on `system`. Without it the step reports "ask an admin" and
gives the statement to run — the finding still lands, it just costs a minute in the room. If you
can get it in advance, do; if not, have an admin ready to run:

```sql
SHOW GRANTS ON SCHEMA system.ai;   -- look for EXECUTE granted to `account users`
SHOW GRANTS ON CATALOG system;     -- the grant is inherited from here
```

`deploy.sh` prints the exact GRANT statements with the real service principal filled in:

```sql
GRANT USE CATALOG ON CATALOG system TO `<app-sp-client-id>`;
GRANT USE SCHEMA, SELECT ON SCHEMA system.ai_gateway TO `<app-sp-client-id>`;
GRANT USE SCHEMA, SELECT ON SCHEMA system.access     TO `<app-sp-client-id>`;
```

**Only these two schemas.** The app deliberately reads no others — `system.billing`,
`system.serving`, and `system.information_schema` were each removed once they proved
avoidable, precisely to keep this ask small.

### Why these grants, exactly

The Gateway records what it did in **system tables**, and the app reads them over the SQL
warehouse as its own service principal. Nothing else can answer "what did this cost?" or "who
called that?" — the control APIs report *configuration*, not *behaviour*. So without these two
grants the workshop can still prove a control **exists**; it cannot prove it **fired**.

Precisely which steps need which grant (8 of the 20 core steps):

| Grant | Steps that need it |
|---|---|
| `system.ai_gateway` | `cost_spend_by_model` · `cost_budgets` · `cost_usage` · `control_coding_agents` · `mcp_telemetry` (accelerator) · `telemetry_readiness` (accelerator) |
| `system.access` | `control_audit` · `pii_safety_readiness` (accelerator) |

`USE CATALOG ON CATALOG system` is needed as well: `USE SCHEMA` alone does not grant traversal
to the parent catalog, so the query fails before reaching the table.

**If the grants don't land in time, run the workshop anyway.** The routing ROI, endpoint
discovery, the `system.ai` default-access check, endpoint ACLs, asset inventory, rate limits,
guardrail tests, and MCP policy create/verify all use the serving and Unity Catalog APIs and
need **no `system` data access**. The telemetry steps report "action needed" instead of
passing. That is a visible, honest gap — not a failure. What you lose is every *number*: the
dollar figures, the attribution, and the audit evidence.

---

## 2. Platform / metastore (hours)

| # | Item | Detail |
|---|---|---|
| 6 | **A Unity Catalog catalog** the workshop can use | Must already exist — the bundle creates the *schema*, not the catalog. Passed as `-c`. |
| 7 | **A SQL warehouse**, running | Passed as `-w`. Serverless is fine and starts fastest. |
| 8 | **Deployer privileges** | Create Databricks Apps; `USE CATALOG` + `CREATE SCHEMA` on the target catalog; `CAN_USE` on the warehouse. |
| 9 | **An external-storage catalog** — only if guardrail/PII steps are in scope | Inference tables cannot be created in a default-storage catalog. |
| 10 | **Workshop group** for app access | Passed as `-g`; attendees get `CAN_USE`. Defaults to `users`. |

---

## 3. Identity, network, and agents (hours to days)

| # | Item | Detail |
|---|---|---|
| 11 | **Pilot users from the customer IdP** | Per-user attribution is only meaningful with real identities, not shared logins. |
| 12 | **Egress allowlisted** — only if external providers or external MCP are in scope | The serving layer must reach the provider. |
| 13 | **Coding agent chosen** | Claude Code, Cursor, or Codex. `ucode` is the fastest path: `uv tool install git+https://github.com/databricks/ucode` then `ucode <agent>`. Needs Python 3.12+. |
| 14 | **Participants can install locally** | If laptops are locked down, the coding-agent steps become a demo rather than hands-on. Worth knowing in advance. |

---

## 4. Content decisions (minutes, but make them beforehand)

These are small and they materially change how well the workshop lands.

| # | Decision | Why it matters |
|---|---|---|
| 15 | **A representative prompt** for the routing ROI step | `cost.routing.sample_prompt`. The savings number only persuades if it's *their* kind of work. |
| 16 | **Negotiated `$/DBU` rate** | `cost.routing.dbu_to_usd`. Until set, dollars are list-price illustrative — token counts are always real. |
| 17 | **Which accelerator** (if any) | Pick the one matching their priority. Don't run all five. |
| 18 | **Which MCP service** to govern | `mcp.builtin_service`. Availability differs per workspace — see the caveat below. |
| 19 | **Who owns the AI budget** | Determines whether the FinOps owner needs to be in the room. |

### MCP caveats worth knowing before you promise a demo

Verified on a live workspace, 2026-08-06:

- **`system.ai.github` is already filtered to read-only** — 26 tools, no `push_files`. A
  "deny the write tool" demo needs an **external** MCP that actually exposes one.
- **`system.ai.atlassian` returned 403** pending per-user OAuth consent. Complete consent
  (service page → Login) before the session, or pick another service.
- **`system.ai.*` grants `EXECUTE` to `account users`** by default. Good finding to *show* a
  security team; don't be surprised by it live.
- **Service policies attach to MCP Services only**, not the managed `/api/2.0/mcp/...`
  endpoints — those aren't securables.

---

## 5. Day-before check (10 minutes)

Run these in order. Each has an unambiguous pass condition.

```bash
# 1. Deploy (idempotent — safe to re-run)
./deploy.sh -p <profile> -w <warehouse-id> -c <catalog> -g <workshop-group>

# 2. Health: must be {"status":"ok","config_problems":[]}
curl -s -H "Authorization: Bearer $(databricks auth token -p <profile> | jq -r .access_token)" \
  https://ai-governance-workshop-<workspace-id>.<region>.databricksapps.com/api/health
```

Then, in the app itself:

- [ ] Walkthrough page loads; set an **Account ID**
- [ ] **Choice → Test connection** passes
- [ ] **Cost → Show the model panel** lists three models that exist on this workspace
- [ ] **Cost → Route a prompt** returns a real saving (this is the ROI moment — never
      demo it untested)
- [ ] **Control → Create the policy function** succeeds (proves `CREATE FUNCTION`)
- [ ] At least one telemetry step returns data (proves the `system` grants landed)
- [ ] A second person can open the app (proves the group grant)

Anything red here is a prerequisite that didn't land — resolve it before the room, not during.

---

## 6. Scope guard

The workshop is 4 hours and deliberately does **not** try to prove every Gateway feature.
Resist adding boxes; the goal is a governed path that demonstrably works, not exhaustive
coverage.

**In scope — the 20 core steps:** the open-by-default posture on `system.ai`, one governed
endpoint and who may call it, model/tool/agent inventory, a policy that visibly denies
something, a guardrail that blocks a prompt, a rate limit, spend visible in dollars,
per-developer coding-agent attribution, a measured routing saving, cost attribution by tag,
and an audit trail.

**Deferred to accelerators or follow-up:** exhaustive per-agent parity, enterprise-wide role
design, whole-agent runtime guardrails, budget hard-blocking (still rolling out), MCP payload
logging (not in Beta), and Lakewatch (not enabled on most accounts, so it is not a step).

If a customer wants more, that's an accelerator (~4h) or a follow-up item in the exported
outcomes — not extra steps crammed into the core session. For adopting UAIG fresh or
migrating from a previous Databricks or external gateway, point them at the Adoption and
Migration field guides rather than growing the workshop.
