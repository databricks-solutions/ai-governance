import { useState } from "react";
import { Loader2, Target, Trash2 } from "lucide-react";
import { api, groupCounts, stepOutcome, type Pillar, type ProgressMap } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import OutcomeControls from "@/components/OutcomeControls";
import ExportPanel from "@/components/ExportPanel";
import { Pill } from "@/components/ui";
import { cn } from "@/lib/cn";

// The workshop outcomes checklist — every core and accelerator step in one place, checkable on
// its own so the workshop can guide activities even without the interactive Try-It flow. It
// shares the same backing state as the step cards, so ticks sync both ways and feed the export.
export default function Outcomes({
  pillars,
  accelerators,
  progress,
  onProgressChange,
}: {
  pillars?: Pillar[];
  accelerators?: Pillar[];
  progress: ProgressMap;
  onProgressChange: () => void;
}) {
  if (!pillars) {
    return (
      <div className="flex h-screen items-center justify-center text-muted">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading outcomes…
      </div>
    );
  }

  const groups = [...pillars, ...(accelerators ?? [])];
  let done = 0;
  let applicable = 0;
  let na = 0;
  let poc = 0;
  for (const g of groups) {
    for (const s of g.steps) {
      const o = stepOutcome(progress[s.id]);
      if (o.poc) poc++;
      if (o.na) {
        na++;
        continue;
      }
      applicable++;
      if (o.done) done++;
    }
  }
  const pct = applicable ? Math.round((100 * done) / applicable) : 0;

  return (
    <div>
      <PageHeader
        eyebrow="Track & follow up"
        title="Outcomes"
        lead="Every core and accelerator step in one checklist. Tick Done as you run each activity — you don't have to use the interactive Try-It buttons. Running a step's Try-It marks it Done here automatically, and these ticks sync with the step cards on each page and feed the exported outcomes."
      />
      <div className="mx-auto max-w-4xl px-8 py-12 lg:px-14">
        {/* Overall summary */}
        <div className="mb-8 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-navy/10 bg-oat p-5">
          <div>
            <div className="text-sm font-semibold text-navy">
              {done} of {applicable} applicable steps achieved ({pct}%)
            </div>
            <div className="mt-0.5 text-xs text-muted">
              A step is achieved when its Try-It test passed or you marked it Done. N/A steps are
              excluded from the count.
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {na > 0 && <Pill tone="muted">{na} N/A</Pill>}
            {poc > 0 && <Pill tone="lava">{poc} for POC</Pill>}
          </div>
        </div>

        {/* How to track toward a POC doc for production */}
        <div className="mb-8 rounded-2xl border border-navy/10 bg-white p-6">
          <div className="mb-2 flex items-center gap-2">
            <Target className="h-4.5 w-4.5 text-lava" strokeWidth={2} />
            <h2 className="font-semibold text-navy">Track each item toward a POC doc</h2>
          </div>
          <p className="mb-3 max-w-3xl text-sm leading-relaxed text-muted">
            The workshop proves each control live on your workspace. Getting to{" "}
            <span className="font-semibold text-navy">production</span> means turning whatever you
            couldn't finish in the room into a tracked punch list — a{" "}
            <span className="font-semibold text-navy">POC doc</span>. Mark every step as you go:
          </p>
          <ul className="mb-3 max-w-3xl space-y-1.5 text-sm leading-relaxed text-muted">
            <li>
              <span className="font-semibold text-[#1E7E34]">Done</span> — proven on this workspace;
              nothing more to do.
            </li>
            <li>
              <span className="font-semibold text-navy">N/A</span> — out of scope for this customer;
              drops from the count.
            </li>
            <li>
              <span className="font-semibold text-lava">Add to POC</span> — carry it into the POC doc
              as a production follow-up: something blocked in the room, waiting on an account admin,
              or needing a larger change to land.
            </li>
          </ul>
          <p className="max-w-3xl text-sm leading-relaxed text-muted">
            Export the report below as the POC-doc leave-behind — it lists every step with its
            status, the incomplete items as next steps, and everything flagged for POC. Work that
            list down to zero to reach production.
          </p>
        </div>

        <div className="flex flex-col gap-6">
          {groups.map((g) => {
            const c = groupCounts(g.steps, progress);
            return (
              <section key={g.id}>
                <div className="mb-2 flex flex-wrap items-baseline gap-x-3">
                  <h2 className="text-base font-semibold text-navy">{g.title}</h2>
                  <span className="text-xs text-navy-300">
                    {c.done}/{c.applicable}
                  </span>
                </div>
                <div className="overflow-hidden rounded-2xl border border-navy/10 bg-white">
                  {g.steps.map((step, idx) => (
                    <div
                      key={step.id}
                      className={cn(
                        "flex flex-wrap items-center justify-between gap-x-4 gap-y-2 p-4",
                        idx > 0 && "border-t border-navy/[0.07]",
                      )}
                    >
                      <span className="min-w-0 flex-1 text-sm font-medium text-navy">{step.title}</span>
                      <OutcomeControls
                        stepId={step.id}
                        pillarId={g.id}
                        saved={progress[step.id] ?? null}
                        onChange={onProgressChange}
                      />
                    </div>
                  ))}
                </div>
              </section>
            );
          })}
        </div>

        {/* Export — the POC-doc leave-behind and the machine-readable outcomes, relocated here
            from the Walkthrough so tracking and exporting live in one place. */}
        <div className="mt-10">
          <ExportPanel />
        </div>

        {/* Start over — clears all progress on this deployment. */}
        <ResetPanel onReset={onProgressChange} />
      </div>
    </div>
  );
}

/** Clear all workshop progress so the room can start fresh. Destructive — confirms first, and
 *  points the presenter at Export above to keep a record before wiping. */
function ResetPanel({ onReset }: { onReset: () => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function reset() {
    if (!window.confirm(
      "Clear ALL workshop progress on this deployment? Every step returns to not-started. " +
      "This cannot be undone — export the outcomes above first if you need the record.",
    )) return;
    setBusy(true);
    setMsg("");
    try {
      const res = await api.resetProgress();
      setMsg(`Cleared ${res.cleared} step(s). Starting fresh.`);
      onReset();
    } catch (e) {
      setMsg(`Reset failed: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-8 flex flex-wrap items-center gap-3 rounded-2xl border border-navy/10 bg-white p-5">
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-navy">Start over</div>
        <div className="mt-0.5 text-xs text-muted">
          Clears all progress on this deployment — for re-running the workshop or resetting a demo.
          Export above first; this can't be undone.
        </div>
      </div>
      <button
        onClick={reset}
        disabled={busy}
        className="inline-flex shrink-0 items-center gap-2 rounded-full border border-navy/20 px-4 py-2 text-sm font-semibold text-navy hover:border-lava hover:text-lava disabled:opacity-40"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
        Reset workshop progress
      </button>
      {msg && <span className="w-full text-xs text-muted">{msg}</span>}
    </div>
  );
}
