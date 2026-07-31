import { Rocket, ArrowRight } from "lucide-react";
import PageHeader from "@/components/PageHeader";
import { Eyebrow, Pill } from "@/components/ui";
import type { Pillar, ProgressMap } from "@/lib/api";
import { cn } from "@/lib/cn";

// Minimal, safe markdown: paragraphs, **bold**, `code`, and - bullets (matches Intro).
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

export default function AcceleratorsOverview({
  overview,
  accelerators,
  progress,
  go,
}: {
  overview: { title: string; body: string };
  accelerators: Pillar[];
  progress: ProgressMap;
  go: (r: string) => void;
}) {
  return (
    <>
      <PageHeader
        part="Accelerators"
        title={overview.title}
        lead="Optional ~4-hour add-ons, each focused on one customer need. Run the one that matches the customer's priority — not all five."
      />
      <div className="mx-auto max-w-4xl space-y-12 px-8 py-12 lg:px-14">
        <Markdown text={overview.body} />

        <section>
          <Eyebrow>The five accelerators</Eyebrow>
          <div className="grid gap-4 sm:grid-cols-2">
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
      </div>
    </>
  );
}
