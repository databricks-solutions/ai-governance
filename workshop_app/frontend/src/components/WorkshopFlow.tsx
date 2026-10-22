import { Fragment, type ReactNode } from "react";
import { Check, AlertCircle, ArrowRight } from "lucide-react";
import { stepOutcome, type Pillar, type ProgressMap } from "@/lib/api";
import { shortTitle } from "@/lib/text";
import { cn } from "@/lib/cn";

// A one-glance flow of the whole workshop: the pillars in order (Control -> Choice -> Cost) as
// phases, each listing its steps with a live status dot. Driven by the same progress store as the
// step cards, so it doubles as a progress map. Deliberately flat and on-brand (navy/oat/lava, line
// icons) - no gradients or 3D.

type Status = "done" | "setup" | "na" | "todo";

const DOT: Record<Status, string> = {
  done: "border-lava bg-lava text-white",
  setup: "border-[#B7791F] bg-[#FDF3E0] text-[#B7791F]",
  na: "border-navy/15 bg-navy/5 text-navy-300",
  todo: "border-navy/25 bg-white text-navy-300",
};

function stepStatus(saved: ProgressMap[string] | null | undefined): Status {
  const { done, na } = stepOutcome(saved);
  if (done) return "done";
  if (na) return "na";
  if (saved?.status === "action_required") return "setup";
  return "todo";
}

function Dot({ status }: { status: Status }) {
  return (
    <span className={cn("flex h-4 w-4 shrink-0 items-center justify-center rounded-full border", DOT[status])}>
      {status === "done" ? (
        <Check className="h-2.5 w-2.5" strokeWidth={3} />
      ) : status === "setup" ? (
        <AlertCircle className="h-2.5 w-2.5" />
      ) : null}
    </span>
  );
}

function LegendItem({ status, label }: { status: Status; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Dot status={status} /> {label}
    </span>
  );
}

export default function WorkshopFlow({
  pillars,
  progress,
}: {
  pillars: Pillar[];
  progress: ProgressMap;
}): ReactNode {
  return (
    <div className="rounded-2xl border border-navy/10 bg-white p-6">
      <div className="mb-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
        <LegendItem status="done" label="Done" />
        <LegendItem status="setup" label="Needs setup" />
        <LegendItem status="todo" label="Not started" />
      </div>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-stretch lg:gap-0">
        {pillars.map((p, i) => (
          <Fragment key={p.id}>
            <div className="flex-1 rounded-xl border border-navy/10 bg-oat p-4">
              <div className="mb-3 flex items-baseline gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-navy text-[11px] font-semibold text-white">
                  {i + 1}
                </span>
                <h4 className="text-sm font-semibold text-navy">{p.title}</h4>
              </div>
              <ol className="space-y-2">
                {p.steps.map((s) => (
                  <li key={s.id} className="flex items-start gap-2">
                    <span className="mt-0.5">
                      <Dot status={stepStatus(progress[s.id])} />
                    </span>
                    <span className="text-xs leading-snug text-navy">{shortTitle(s.title, p.title)}</span>
                  </li>
                ))}
              </ol>
            </div>
            {i < pillars.length - 1 && (
              <div className="flex items-center justify-center py-1 text-navy-300 lg:px-2">
                <ArrowRight className="hidden h-5 w-5 lg:block" />
                <ArrowRight className="h-4 w-4 rotate-90 lg:hidden" />
              </div>
            )}
          </Fragment>
        ))}
      </div>
    </div>
  );
}
