import { Layers, Lock, Eye, ArrowRight } from "lucide-react";
import PageHeader from "@/components/PageHeader";
import { Eyebrow, Pill } from "@/components/ui";
import type { Pillar, ProgressMap } from "@/lib/api";
import { cn } from "@/lib/cn";

const ICONS: Record<string, typeof Layers> = { choice: Layers, control: Lock, clarity: Eye };

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
  progress,
  go,
}: {
  intro: { title: string; body: string };
  pillars: Pillar[];
  progress: ProgressMap;
  go: (r: string) => void;
}) {
  return (
    <>
      <PageHeader part="00" title={intro.title} />
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
      </div>
    </>
  );
}
