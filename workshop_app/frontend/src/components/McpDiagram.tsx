import { cn } from "@/lib/cn";

/**
 * Static diagram of how an MCP tool call is governed.
 *
 * The point it has to land: there are TWO kinds of MCP, they travel different paths, and
 * only one of them can carry a service policy. Everything else is supporting detail. Built
 * as inline SVG + divs (no chart library) so it stays crisp, themeable, and printable in a
 * leave-behind.
 *
 * Content follows the three-plane model from the internal MCP field guide:
 *   Plane 1 Authenticate — OAuth scope picks the endpoint FAMILY
 *   Plane 2 Authorize    — UC grants pick the OBJECT
 *   Plane 3 Behavior     — service policies inspect the CALL (MCP Services only)
 */

const NAVY = "#1B3139";
const LAVA = "#FF3621";
const MUTED = "#5A676C";

function Arrow({ className, label }: { className?: string; label?: string }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <svg width="100%" height="10" viewBox="0 0 100 10" preserveAspectRatio="none" className="min-w-6 flex-1">
        <line x1="0" y1="5" x2="94" y2="5" stroke={NAVY} strokeOpacity="0.28" strokeWidth="1.5" />
        <path d="M94 1 L100 5 L94 9" fill="none" stroke={NAVY} strokeOpacity="0.45" strokeWidth="1.5" />
      </svg>
      {label && <span className="whitespace-nowrap text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</span>}
    </div>
  );
}

function PlaneBadge({ n, label, applies }: { n: number; label: string; applies: boolean }) {
  return (
    <div
      className={cn(
        "flex items-center gap-1.5 rounded-full border px-2.5 py-1",
        applies ? "border-navy/15 bg-white" : "border-navy/10 bg-navy/[0.02]",
      )}
      title={applies ? `${label} applies` : `${label} does not apply here`}
    >
      <span
        className={cn(
          "flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold",
          applies ? "bg-navy text-white" : "bg-navy/10 text-navy/35",
        )}
      >
        {n}
      </span>
      <span className={cn("text-[11px] font-semibold", applies ? "text-navy" : "text-navy/35 line-through")}>
        {label}
      </span>
    </div>
  );
}

export default function McpDiagram() {
  return (
    <figure className="my-2 overflow-hidden rounded-2xl border border-navy/10 bg-oat">
      {/* ---------------------------------------------------------------- header */}
      <figcaption className="border-b border-navy/10 bg-white px-6 py-4">
        <h4 className="text-sm font-semibold text-navy">How an MCP tool call is governed</h4>
        <p className="mt-0.5 text-xs leading-relaxed text-muted">
          Both routes are called “MCP”. They are governed differently — and only one of them can
          carry a service policy.
        </p>
      </figcaption>

      <div className="space-y-4 p-5 sm:p-6">
        {/* -------------------------------------------------------------- caller */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="rounded-xl border border-navy/15 bg-white px-4 py-2.5">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">Coding agent</div>
            <div className="text-sm font-semibold text-navy">Claude Code · Cursor · Codex</div>
          </div>
          <Arrow className="min-w-16 flex-1" label="OAuth token" />
          <div className="rounded-xl border-2 px-4 py-2.5" style={{ borderColor: LAVA }}>
            <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: LAVA }}>
              Unity AI Gateway
            </div>
            <div className="text-sm font-semibold text-navy">One governed entry point</div>
          </div>
        </div>

        {/* ------------------------------------------------- plane 1 annotation */}
        <div className="rounded-xl border border-navy/10 bg-white/70 px-4 py-2.5">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <PlaneBadge n={1} label="Authenticate" applies />
            <span className="text-xs text-muted">
              The scope picks the endpoint <strong className="text-navy">family</strong> —{" "}
              <code className="rounded bg-navy/5 px-1 text-[11px] text-navy">unity-catalog</code>,{" "}
              <code className="rounded bg-navy/5 px-1 text-[11px] text-navy">genie</code>,{" "}
              <code className="rounded bg-navy/5 px-1 text-[11px] text-navy">ai-search</code>,{" "}
              <code className="rounded bg-navy/5 px-1 text-[11px] text-navy">sql</code>. It grants no
              per-object access.
            </span>
          </div>
        </div>

        {/* ------------------------------------------------------- the two paths */}
        <div className="grid gap-4 md:grid-cols-2">
          {/* ---- managed / UC-native ---- */}
          <div className="flex flex-col rounded-xl border border-navy/15 bg-white p-4">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-navy">Managed (UC-native)</span>
              <span className="rounded-full bg-navy/5 px-2 py-0.5 text-[10px] font-semibold text-muted">
                not a securable
              </span>
            </div>
            <code className="mb-3 block break-all text-[11px] leading-relaxed text-muted">
              /api/2.0/mcp/functions|genie|sql|ai-search
            </code>

            <div className="mb-3 space-y-1.5">
              <PlaneBadge n={2} label="Authorize — UC grants" applies />
              <PlaneBadge n={3} label="Behavior — service policy" applies={false} />
            </div>

            <div className="mt-auto space-y-2 text-xs leading-relaxed text-muted">
              <p>
                <strong className="text-navy">Deny by absence.</strong> Without{" "}
                <code className="rounded bg-navy/5 px-1 text-[11px] text-navy">USE CATALOG</code> +{" "}
                <code className="rounded bg-navy/5 px-1 text-[11px] text-navy">USE SCHEMA</code> the tool
                is simply <em>missing</em> from the list — not an error. So an empty list is ambiguous.
              </p>
              <p>
                Content risk is handled by column masks / ABAC on the underlying data, not guardrails.
              </p>
              <p className="rounded-lg bg-navy/[0.03] px-2.5 py-1.5 text-[11px]">
                Telemetry: <strong className="text-navy">none</strong> MCP-specific.
              </p>
            </div>
          </div>

          {/* ---- MCP Services ---- */}
          <div className="flex flex-col rounded-xl border-2 bg-white p-4" style={{ borderColor: `${LAVA}55` }}>
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-navy">MCP Services</span>
              <span
                className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                style={{ backgroundColor: `${LAVA}14`, color: LAVA }}
              >
                MCP_SERVICE securable
              </span>
            </div>
            <code className="mb-3 block break-all text-[11px] leading-relaxed text-muted">
              /ai-gateway/mcp-services/&lt;catalog&gt;.&lt;schema&gt;.&lt;name&gt;
            </code>

            <div className="mb-3 space-y-1.5">
              <PlaneBadge n={2} label="Authorize — UC grants" applies />
              <PlaneBadge n={3} label="Behavior — service policy" applies />
            </div>

            <div className="mt-auto space-y-2 text-xs leading-relaxed text-muted">
              <p>
                <strong className="text-navy">Provided:</strong>{" "}
                <code className="rounded bg-navy/5 px-1 text-[11px] text-navy">system.ai.github</code>,{" "}
                <code className="rounded bg-navy/5 px-1 text-[11px] text-navy">slack</code>,{" "}
                <code className="rounded bg-navy/5 px-1 text-[11px] text-navy">atlassian</code>, …
                <br />
                <strong className="text-navy">External / custom:</strong> your own server, behind an HTTP
                connection.
              </p>
              <p>
                Policy returns <strong className="text-navy">ALLOW</strong> /{" "}
                <strong style={{ color: LAVA }}>DENY</strong> / <strong className="text-navy">ASK</strong>,
                on request and on response. Fail-closed.
              </p>
              <p className="rounded-lg bg-navy/[0.03] px-2.5 py-1.5 text-[11px]">
                Telemetry: usage row + <code className="text-navy">mcpCall</code> audit —{" "}
                <strong className="text-navy">no payloads</strong>.
              </p>
            </div>
          </div>
        </div>

        {/* --------------------------------------------------------- downstream */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="rounded-xl border border-navy/10 bg-white px-4 py-2 text-xs text-muted">
            UC functions · Genie · SQL · Vector Search
          </div>
          <Arrow className="min-w-12 flex-1" label="on behalf of the caller" />
          <div className="rounded-xl border border-navy/10 bg-white px-4 py-2 text-xs text-muted">
            GitHub · Slack · Jira · your API
          </div>
        </div>

        {/* ------------------------------------------------------------- payoff */}
        <div className="rounded-xl border-l-2 bg-white px-4 py-3" style={{ borderLeftColor: LAVA }}>
          <p className="text-xs leading-relaxed text-muted">
            <strong className="text-navy">On-behalf-of, in one line:</strong> the tool runs as the{" "}
            <strong className="text-navy">calling user</strong>, never a shared service account — so if a
            person cannot see a record, neither can their agent. The honest limit: nothing today expresses
            “the analyst may, but her agent may not”. Separating them means giving the agent its own
            identity, usually a service principal.
          </p>
        </div>

        {/* -------------------------------------------------------- debug hints */}
        <details className="group rounded-xl border border-navy/10 bg-white px-4 py-3">
          <summary className="cursor-pointer text-xs font-semibold text-navy marker:text-lava">
            Debugging: “tools/list works but tools/call fails”
          </summary>
          <ul className="mt-2.5 space-y-1.5 text-xs leading-relaxed text-muted">
            <li>
              <strong className="text-navy">JSON-RPC errors ride inside HTTP 200.</strong> Never infer
              success from the status code — look for a <code className="text-navy">result</code> key.
            </li>
            <li>
              <strong className="text-navy">Plane 1:</strong> consent never completed, or the wrong scope
              for the endpoint family. A PAT cannot be scope-limited and needs{" "}
              <code className="text-navy">all-apis</code>.
            </li>
            <li>
              <strong className="text-navy">Plane 2:</strong> holding{" "}
              <code className="text-navy">EXECUTE</code> without{" "}
              <code className="text-navy">USE CATALOG</code> + <code className="text-navy">USE SCHEMA</code>{" "}
              is the most common silent failure.
            </li>
            <li>
              <strong className="text-navy">Plane 3:</strong> a policy returned DENY, or ASK is waiting on
              an approval nobody clicked.
            </li>
            <li>
              <strong className="text-navy">Self-hosted:</strong> the server must be{" "}
              <strong className="text-navy">stateless</strong> — a stateful one behind the replicated proxy
              can fail the first call even after list succeeded.
            </li>
          </ul>
        </details>

        <p className="text-[11px] leading-relaxed" style={{ color: MUTED }}>
          Service policies are Beta and attach from the AI Gateway UI only — there is no DDL or
          control-API path yet. MCP payload logging is not in Beta.
        </p>
      </div>
    </figure>
  );
}
