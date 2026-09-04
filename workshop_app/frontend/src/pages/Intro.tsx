import { useEffect, useRef, useState } from "react";
import { Layers, Lock, DollarSign, ArrowRight, Rocket, FileDown, Upload, Loader2 } from "lucide-react";
import PageHeader from "@/components/PageHeader";
import { Eyebrow, Pill } from "@/components/ui";
import Markdown, { inline } from "@/components/Markdown";
import { api, groupCounts, type Pillar, type ProgressMap, type DeployGuide,
  type WorkshopRecommendations, type PlanAction } from "@/lib/api";
import { cn } from "@/lib/cn";

// The four canonical decisions — the same vocabulary as the internal app + the Score & plan sheet.
const ACTION_META: Record<PlanAction, { label: string; icon: string; cls: string }> = {
  blocking_prerequisite: { label: "Blocking Prerequisite", icon: "⛔", cls: "border-lava/40 bg-lava/[0.06] text-lava" },
  prove_in_workshop: { label: "Prove in Workshop", icon: "🎯", cls: "border-navy/25 bg-navy/[0.04] text-navy" },
  explore_in_accelerator: { label: "Explore in Accelerator", icon: "🔍", cls: "border-[#6B4FBB]/40 bg-[#6B4FBB]/[0.07] text-[#6B4FBB]" },
  validate_in_poc: { label: "Validate in POC", icon: "✅", cls: "border-[#1E7E34]/30 bg-[#E6F4EA] text-[#1E7E34]" },
};
const scoreCls = (s: number) =>
  s <= 2 ? "bg-lava/10 text-lava" : s <= 4 ? "bg-[#FDF3E0] text-[#B7791F]" : "bg-[#E6F4EA] text-[#1E7E34]";

const ICONS: Record<string, typeof Layers> = { choice: Layers, cost: DollarSign, control: Lock };

export default function Intro({
  intro,
  pillars,
  accelOverview,
  accelerators,
  progress,
  go,
  onProgressChange,
}: {
  intro: { title: string; body: string; deploy?: DeployGuide };
  pillars: Pillar[];
  accelOverview?: { title: string; body: string };
  accelerators?: Pillar[];
  progress: ProgressMap;
  go: (r: string) => void;
  onProgressChange: () => void;
}) {
  const [rec, setRec] = useState<WorkshopRecommendations | null>(null);
  const loadRecs = () => { api.recommendations().then(setRec).catch(() => setRec(null)); };
  useEffect(() => { loadRecs(); }, []);

  return (
    <>
      <PageHeader title={intro.title} />
      <div className="mx-auto max-w-4xl space-y-12 px-8 py-12 lg:px-14">
        <ScopeImport onImported={() => { onProgressChange(); loadRecs(); }} />
        {rec && rec.plan && rec.plan.length > 0 && <RecommendationsPanel rec={rec} />}

        {/* The invite artifact: a one-page overview to share with people BEFORE they open the
            app — hence it lives at the top of the landing page. */}
        <section className="flex flex-col gap-4 rounded-2xl border border-lava/20 bg-oat p-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-navy">Inviting people to the workshop?</h2>
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
              Share the one-page overview — what the four-hour session covers (choice, cost,
              control), who should be in the room, and the optional accelerators. Send it to
              anyone deciding whether to attend.
            </p>
          </div>
          <a
            href={api.brochurePdfUrl()}
            className="inline-flex shrink-0 items-center gap-2 rounded-full bg-navy px-4 py-2 text-sm font-semibold text-white hover:bg-navy-700"
          >
            <FileDown className="h-4 w-4" /> Download one-pager (PDF)
          </a>
        </section>

        <Markdown text={intro.body} />

        <section>
          <Eyebrow>The three pillars</Eyebrow>
          <div className="grid gap-4 md:grid-cols-3">
            {pillars.map((p) => {
              const Icon = ICONS[p.id] ?? Layers;
              const { done, applicable } = groupCounts(p.steps, progress);
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
                    <Pill tone={applicable > 0 && done === applicable ? "lava" : "muted"}>
                      {done}/{applicable}
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
                const { done, applicable } = groupCounts(a.steps, progress);
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
                      <Pill tone={applicable > 0 && done === applicable ? "lava" : "muted"}>
                        {done}/{applicable}
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

        {intro.deploy && (
          <section>
            <Eyebrow>Deploy</Eyebrow>
            <DeploySection guide={intro.deploy} />
          </section>
        )}

        <section>
          <Eyebrow>What the app needs from your workspace</Eyebrow>
          <GrantsExplainer go={go} />
        </section>
      </div>
    </>
  );
}

// Import the scope.json exported by the internal sales-play app: it pre-marks out-of-scope
// accelerators N/A so the room opens focused on the core + the recommended add-on. Lives at the
// top of the Walkthrough because scope is the first thing to set before working the steps.
function ScopeImport({ onImported }: { onImported: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setToast("");
    try {
      const scope = JSON.parse(await file.text());
      const res = await api.importScope(scope);
      const focus = res.focus_pillars?.length ? ` Focus: ${res.focus_pillars.join(", ")}.` : "";
      const blk = res.blocking_prerequisites ? ` ${res.blocking_prerequisites} blocking prerequisite(s).` : "";
      setToast(
        `Recommendations applied — ${res.na_marked} out-of-scope + ${res.validated_marked} mature step(s) marked N/A.${focus}${blk}`,
      );
      onImported();
    } catch (err) {
      setToast(`Import failed: ${err}`);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-navy/10 bg-white p-6 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h2 className="text-lg font-semibold text-navy">Start from a recommended scope</h2>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
          Import the <code className="rounded bg-navy/5 px-1">scope.json</code> from the account's
          maturity assessment to pre-mark out-of-scope accelerators N/A — the room opens focused on
          the core and the recommended accelerator. Optional; you can also scope by hand.
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-start gap-1">
        <button
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-full border border-navy/20 px-4 py-2 text-sm font-semibold text-navy hover:border-navy/50 disabled:opacity-40"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          Import scope.json
        </button>
        <input ref={fileRef} type="file" accept="application/json,.json" onChange={onFile} className="hidden" />
        {toast && <span className="text-xs text-muted">{toast}</span>}
      </div>
    </section>
  );
}

/** Group the flat plan rows by pillar, preserving first-seen order. */
function planGroups(plan: NonNullable<WorkshopRecommendations["plan"]>) {
  const groups: { id: string; title: string; items: typeof plan }[] = [];
  for (const row of plan) {
    let g = groups.find((x) => x.id === row.pillar_id);
    if (!g) {
      g = { id: row.pillar_id, title: row.pillar_title, items: [] };
      groups.push(g);
    }
    g.items.push(row);
  }
  return groups;
}

// The imported workshop recommendations, read-only: the four-decision summary, blocking
// prerequisites, the recommended accelerator, and the statement-by-statement plan. Mirrors the
// internal app's Recommended Scope so both sides tell the same story.
function RecommendationsPanel({ rec }: { rec: WorkshopRecommendations }) {
  const s = rec.plan_summary;
  const blockers = rec.blocking_prerequisites ?? [];
  const order: PlanAction[] = ["blocking_prerequisite", "prove_in_workshop", "explore_in_accelerator", "validate_in_poc"];
  return (
    <section className="rounded-2xl border border-navy/10 bg-white p-6">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold text-navy">Workshop recommendations</h2>
        {rec.overall?.level && <Pill tone="navy">L{rec.overall.level.level} · {rec.overall.level.label}</Pill>}
        {rec.source && <span className="text-[11px] uppercase tracking-wide text-navy-300">from {rec.source}</span>}
      </div>
      <p className="mb-4 max-w-2xl text-sm leading-relaxed text-muted">
        Imported from the maturity assessment. Out-of-scope accelerators and proven-mature outcomes are
        already marked N/A — the room focuses on what to prove live.
      </p>

      {s && (
        <div className="mb-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {order.map((a) => (
            <div key={a} className={cn("rounded-xl border bg-white p-3", ACTION_META[a].cls.split(" ")[0])}>
              <div className="text-xl font-semibold tabular-nums text-navy">{s[a]}</div>
              <div className="text-[11px] leading-tight text-muted">{ACTION_META[a].icon} {ACTION_META[a].label}</div>
            </div>
          ))}
        </div>
      )}

      {blockers.length > 0 && (
        <div className="mb-5 rounded-xl border border-lava/30 bg-lava/[0.04] p-4">
          <div className="mb-2 text-sm font-semibold text-lava">⛔ Establish before the workshop</div>
          <ul className="space-y-2">
            {blockers.map((b) => (
              <li key={b.id} className="text-xs leading-relaxed text-navy/80">
                <span className="font-semibold text-navy">{b.prereq}</span>
                {b.scoped ? <span className="text-navy-300"> · only if {b.scoped} in scope</span> : null}
                <div className="text-[11px] text-muted">{b.prompt}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {rec.recommended_accelerator && (
        <div className="mb-5 flex items-start gap-2 rounded-xl border border-[#6B4FBB]/30 bg-[#6B4FBB]/[0.05] p-3">
          <span className="mt-0.5">🔍</span>
          <div>
            <div className="text-sm font-semibold text-navy">Explore accelerator: {rec.recommended_accelerator.title}</div>
            <div className="text-xs leading-relaxed text-muted">{rec.recommended_accelerator.outcome}</div>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-4">
        {planGroups(rec.plan ?? []).map((g) => (
          <div key={g.id}>
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-navy-300">{g.title}</div>
            <div className="overflow-hidden rounded-xl border border-navy/10">
              {g.items.map((row, i) => {
                const meta = ACTION_META[row.action];
                return (
                  <div key={row.id} className={cn("flex flex-wrap items-start gap-x-3 gap-y-1 p-3", i > 0 && "border-t border-navy/[0.07]")}>
                    <span className={cn("mt-0.5 shrink-0 rounded px-1.5 font-semibold tabular-nums", scoreCls(row.score))}>{row.score}</span>
                    <span className={cn("mt-0.5 shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold", meta.cls)}>
                      {meta.icon} {meta.label}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs leading-relaxed text-navy/80">{row.prompt}</div>
                      {row.detail && <div className="mt-0.5 text-[11px] leading-relaxed text-muted">{row.detail}</div>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// The deploy guide: a numbered "do this / ensure this" walkthrough driven by config
// (steps.yaml → intro.deploy). `do` and `ensure` render inline markdown; `cmd` is verbatim.
function DeploySection({ guide }: { guide: DeployGuide }) {
  return (
    <div className="rounded-2xl border border-navy/10 bg-white p-6">
      <h3 className="font-semibold text-navy">{guide.title}</h3>
      {guide.intro && (
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">{guide.intro}</p>
      )}
      <ol className="mt-5 space-y-5">
        {guide.steps.map((s, i) => (
          <li key={i} className="flex gap-3.5">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-navy text-xs font-semibold text-white">
              {i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <div
                className="text-sm leading-relaxed text-navy"
                dangerouslySetInnerHTML={{ __html: inline(s.do) }}
              />
              {s.cmd && (
                <pre className="mt-2 overflow-x-auto rounded-lg bg-navy/[0.04] p-3 text-[11.5px] leading-relaxed text-navy/85">
                  {s.cmd.trimEnd()}
                </pre>
              )}
              {s.ensure && (
                <p className="mt-2 text-xs leading-relaxed text-muted">
                  <span className="font-semibold text-navy">Ensure: </span>
                  <span dangerouslySetInnerHTML={{ __html: inline(s.ensure) }} />
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
      {guide.footer && <p className="mt-5 text-xs leading-relaxed text-muted">{guide.footer}</p>}
    </div>
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
        traversal to the parent catalog, so the query fails before it reaches the table. Get the
        app's service principal with{" "}
        <code className="rounded bg-navy/5 px-1 py-0.5">databricks apps get ai-governance-workshop</code>{" "}
        and fill it in above. Needs an account or metastore admin, so{" "}
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
