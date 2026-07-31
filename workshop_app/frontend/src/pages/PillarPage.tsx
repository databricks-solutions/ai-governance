import PageHeader from "@/components/PageHeader";
import StepCard from "@/components/StepCard";
import type { Pillar, ProgressMap } from "@/lib/api";

export default function PillarPage({
  pillar,
  progress,
  onProgressChange,
}: {
  pillar: Pillar;
  progress: ProgressMap;
  onProgressChange: () => void;
}) {
  const done = pillar.steps.filter((s) => progress[s.id]?.status === "done").length;
  const pct = pillar.steps.length ? Math.round((100 * done) / pillar.steps.length) : 0;

  return (
    <>
      <PageHeader part={pillar.title} title={pillar.title} lead={pillar.tagline}>
        <div className="mt-6 flex items-center gap-4">
          <div className="h-2 w-full max-w-md overflow-hidden rounded-full bg-navy/10">
            <div className="h-full bg-navy transition-all" style={{ width: `${pct}%` }} />
          </div>
          <span className="text-sm font-semibold tabular-nums text-navy">
            {done}/{pillar.steps.length}
          </span>
        </div>
      </PageHeader>

      <div className="mx-auto max-w-4xl space-y-6 px-8 py-12 lg:px-14">
        {pillar.steps.map((step, i) => (
          <StepCard
            key={step.id}
            index={i + 1}
            pillarId={pillar.id}
            step={step}
            saved={progress[step.id] ?? null}
            onProgressChange={onProgressChange}
          />
        ))}
      </div>
    </>
  );
}
