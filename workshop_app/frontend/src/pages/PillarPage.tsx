import PageHeader from "@/components/PageHeader";
import StepCard from "@/components/StepCard";
import { groupCounts, type Pillar, type ProgressMap } from "@/lib/api";

export default function PillarPage({
  pillar,
  progress,
  onProgressChange,
}: {
  pillar: Pillar;
  progress: ProgressMap;
  onProgressChange: () => void;
}) {
  const { done, applicable } = groupCounts(pillar.steps, progress);
  const pct = applicable ? Math.round((100 * done) / applicable) : 0;

  return (
    <>
      <PageHeader title={pillar.title} lead={pillar.tagline}>
        <div className="mt-6 flex items-center gap-4">
          <div className="h-2 w-full max-w-md overflow-hidden rounded-full bg-navy/10">
            <div className="h-full bg-navy transition-all" style={{ width: `${pct}%` }} />
          </div>
          <span className="text-sm font-semibold tabular-nums text-navy">
            {done}/{applicable}
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
