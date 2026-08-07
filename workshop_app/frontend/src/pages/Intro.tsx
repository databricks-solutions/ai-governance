import { Layers, Lock, DollarSign, ArrowRight, Rocket } from "lucide-react";
import PageHeader from "@/components/PageHeader";
import { Eyebrow, Pill } from "@/components/ui";
import ExportPanel from "@/components/ExportPanel";
import type { Pillar, ProgressMap } from "@/lib/api";
import { useAccount } from "@/lib/account";
import { cn } from "@/lib/cn";

const ICONS: Record<string, typeof Layers> = { choice: Layers, cost: DollarSign, control: Lock };

// Minimal, safe markdown: paragraphs, **bold**, and - bullets.
function Markdown({ text }: { text: string }) {
  const blocks = text.trim().split(/\n\n+/);
  return (
    <div className="space-y-3 text-[15px] leading-relaxed text-muted">
      {blocks.map((b, i) => {
        const lines = b.split("\n");
        if (lines.every((l) => l.trim().startsWith("- "))) {
          return (
            <ul key={i} className="ml-1 space-y-1.5">
              {lines.map((l, k) => (
                <li key={k} className="flex gap-2">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-lava" />
                  <span dangerouslySetInnerHTML={{ __html: inline(l.replace(/^- /, "")) }} />
                </li>
              ))}
            </ul>
          );
        }
        return <p key={i} dangerouslySetInnerHTML={{ __html: inline(b) }} />;
      })}
    </div>
  );
}

function inline(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong class='text-navy'>$1</strong>")
    .replace(/`(.+?)`/g, "<code class='rounded bg-navy/5 px-1 py-0.5 text-[13px] text-navy'>$1</code>");
}

export default function Intro({
  intro,
  pillars,
  accelOverview,
  accelerators,
  progress,
  go,
}: {
  intro: { title: string; body: string };
  pillars: Pillar[];
  accelOverview?: { title: string; body: string };
  accelerators?: Pillar[];
  progress: ProgressMap;
  go: (r: string) => void;
}) {
  const { sfid, setSfid } = useAccount();
  return (
    <>
      <PageHeader title={intro.title}>
        <div className="mt-6">
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">Account ID</span>
            <input
              value={sfid}
              onChange={(e) => setSfid(e.target.value)}
              placeholder="0016100001Qcv4uAAB"
              className="mt-1.5 block w-72 rounded-xl border border-navy/15 bg-white px-3.5 py-2.5 text-sm text-navy outline-none focus:border-navy"
            />
          </label>
          <p className="mt-2 max-w-xl text-xs text-muted">
            The whole workshop is tracked against this account, and progress and the outcomes export are keyed
            to it. {!sfid && <span className="text-lava">Set it before running steps.</span>}
          </p>
        </div>
      </PageHeader>
      <div className="mx-auto max-w-4xl space-y-12 px-8 py-12 lg:px-14">
        <Markdown text={intro.body} />

        <section>
          <Eyebrow>The three pillars</Eyebrow>
          <div className="grid gap-4 md:grid-cols-3">
            {pillars.map((p) => {
              const Icon = ICONS[p.id] ?? Layers;
              const done = p.steps.filter((s) => progress[s.id]?.status === "done").length;
              return (
                <button
                  key={p.id}
                  onClick={() => go(p.id)}
                  className={cn(
                    "group flex flex-col items-start rounded-2xl border border-navy/10 bg-white p-6 text-left transition-all",
                    "hover:-translate-y-0.5 hover:border-navy/30",
                  )}
                >
                  <div className="mb-4 flex w-full items-center justify-between">
                    <Icon className="h-6 w-6 text-navy" strokeWidth={2} />
                    <Pill tone={done === p.steps.length ? "lava" : "muted"}>
                      {done}/{p.steps.length}
                    </Pill>
                  </div>
                  <h3 className="text-xl font-semibold text-navy">{p.title}</h3>
                  <p className="mt-1.5 text-sm leading-snug text-muted">{p.tagline}</p>
                  <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-navy opacity-0 transition-opacity group-hover:opacity-100">
                    Start <ArrowRight className="h-4 w-4" />
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        {accelerators && accelerators.length > 0 && (
          <section>
            <Eyebrow>Accelerators</Eyebrow>
            {accelOverview && (
              <>
                <h2 className="mb-3 text-xl font-semibold text-navy">{accelOverview.title}</h2>
                <Markdown text={accelOverview.body} />
              </>
            )}
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              {accelerators.map((a) => {
                const done = a.steps.filter((s) => progress[s.id]?.status === "done").length;
                return (
                  <button
                    key={a.id}
                    onClick={() => go(a.id)}
                    className={cn(
                      "group flex flex-col items-start rounded-2xl border border-navy/10 bg-white p-6 text-left transition-all",
                      "hover:-translate-y-0.5 hover:border-navy/30",
                    )}
                  >
                    <div className="mb-4 flex w-full items-center justify-between">
                      <Rocket className="h-6 w-6 text-navy" strokeWidth={2} />
                      <Pill tone={done === a.steps.length && a.steps.length > 0 ? "lava" : "muted"}>
                        {done}/{a.steps.length}
                      </Pill>
                    </div>
                    <h3 className="text-lg font-semibold text-navy">{a.title}</h3>
                    <p className="mt-1.5 text-sm leading-snug text-muted">{a.tagline}</p>
                    <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-navy opacity-0 transition-opacity group-hover:opacity-100">
                      Open <ArrowRight className="h-4 w-4" />
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        )}

        <section>
          <Eyebrow>What the app needs from your workspace</Eyebrow>
          <GrantsExplainer go={go} />
        </section>

        <section>
          <Eyebrow>Wrap up</Eyebrow>
          <ExportPanel />
        </section>
      </div>
    </>
  );
}

// Why the app needs two `system` grants, stated where a platform team will actually read it.
// The distinction that matters: control APIs report CONFIGURATION, system tables report
// BEHAVIOUR. Without these grants the workshop proves a control exists but never that it fired.
function GrantsExplainer({ go }: { go: (route: string) => void }) {
  return (
    <div className="rounded-2xl border border-navy/10 bg-white p-6">
      <h3 className="font-semibold text-navy">Two Unity Catalog grants, and what they buy</h3>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        This app reads Gateway telemetry from <strong>system tables</strong> as its own service
        principal. That is the only place the platform records what actually happened — the
        control APIs report <em>configuration</em>, not <em>behaviour</em>. So without these two
        grants the workshop can still prove a control <strong>exists</strong>; it cannot prove
        it <strong>fired</strong>, and you lose every dollar figure and every attribution.
      </p>
      <div className="mt-4 overflow-hidden rounded-xl border border-navy/10">
        <table className="w-full text-left text-sm">
          <thead className="bg-oat text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-2 font-semibold">Grant</th>
              <th className="px-4 py-2 font-semibold">Unlocks</th>
            </tr>
          </thead>
          <tbody className="text-muted">
            <tr className="border-t border-navy/[0.07]">
              <td className="px-4 py-2.5 align-top">
                <code className="rounded bg-navy/5 px-1.5 py-0.5 text-[12px] text-navy">system.ai_gateway</code>
              </td>
              <td className="px-4 py-2.5">
                <span className="font-semibold text-navy">6 steps</span> — spend by model, budget
                status, usage by project, coding-agent attribution, MCP telemetry, telemetry readiness
              </td>
            </tr>
            <tr className="border-t border-navy/[0.07]">
              <td className="px-4 py-2.5 align-top">
                <code className="rounded bg-navy/5 px-1.5 py-0.5 text-[12px] text-navy">system.access</code>
              </td>
              <td className="px-4 py-2.5">
                <span className="font-semibold text-navy">2 steps</span> — the audit trail and the
                secret-leak scan
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <pre className="mt-4 overflow-x-auto rounded-xl bg-navy/[0.03] p-3.5 text-[11.5px] leading-relaxed text-navy/80">{`GRANT USE CATALOG ON CATALOG system TO \`<app-service-principal>\`;
GRANT USE SCHEMA, SELECT ON SCHEMA system.ai_gateway TO \`<app-service-principal>\`;
GRANT USE SCHEMA, SELECT ON SCHEMA system.access     TO \`<app-service-principal>\`;`}</pre>
      <p className="mt-3 text-xs leading-relaxed text-muted">
        <code className="rounded bg-navy/5 px-1 py-0.5">USE CATALOG</code> on{" "}
        <code className="rounded bg-navy/5 px-1 py-0.5">system</code> is required too —{" "}
        <code className="rounded bg-navy/5 px-1 py-0.5">USE SCHEMA</code> alone does not grant
        traversal to the parent catalog, so the query fails before it reaches the table.{" "}
        <code className="rounded bg-navy/5 px-1 py-0.5">deploy.sh</code> prints these with the real
        principal filled in. Needs an account or metastore admin, so{" "}
        <button onClick={() => go("prereqs")} className="font-semibold text-navy underline decoration-lava decoration-2 underline-offset-2 hover:text-lava">
          start it early
        </button>
        .
      </p>
      <p className="mt-3 text-xs leading-relaxed text-muted">
        <strong className="text-navy">If the grants are not ready, run the workshop anyway.</strong>{" "}
        Everything else — the routing ROI, the default-access check, endpoint ACLs, rate limits,
        guardrails, and MCP policies — uses the serving and Unity Catalog APIs and needs no{" "}
        <code className="rounded bg-navy/5 px-1 py-0.5">system</code> data access. The telemetry
        steps report <em>action needed</em> rather than failing.
      </p>
    </div>
  );
}
