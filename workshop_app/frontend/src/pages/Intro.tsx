import { Layers, Lock, DollarSign, ArrowRight, Rocket, FileDown } from "lucide-react";
import PageHeader from "@/components/PageHeader";
import { Eyebrow, Pill } from "@/components/ui";
import Markdown, { inline } from "@/components/Markdown";
import ResetPanel from "@/components/ResetPanel";
import { api, groupCounts, type Pillar, type ProgressMap, type DeployGuide } from "@/lib/api";
import { cn } from "@/lib/cn";

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
  return (
    <>
      <PageHeader title={intro.title} />
      <div className="mx-auto max-w-4xl space-y-12 px-8 py-12 lg:px-14">
        {/* The invite artifact: a one-page overview to share with people BEFORE they open the
            app — hence it lives at the top of the landing page. */}
        <section className="flex flex-col gap-4 rounded-2xl border border-lava/20 bg-oat p-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-navy">Inviting people to the workshop?</h2>
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
              A one-pager on what the session covers, who to invite, and the optional
              accelerators — send it to anyone deciding whether to attend.
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

        <ResetPanel onReset={onProgressChange} />
      </div>
    </>
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

