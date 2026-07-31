import { useEffect, useState } from "react";
import { Loader2, ExternalLink } from "lucide-react";
import PageHeader from "@/components/PageHeader";
import { api } from "@/lib/api";

const REPO_FAQ = "https://github.com/databricks-solutions/ai-governance/blob/main/workshop_app/FAQ.md";

// Small markdown renderer: #/## headings, **bold**, `code`, and - bullet lists.
function inline(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong class='text-navy'>$1</strong>")
    .replace(/`(.+?)`/g, "<code class='rounded bg-navy/5 px-1 py-0.5 text-[13px] text-navy'>$1</code>");
}

function Markdown({ text }: { text: string }) {
  const blocks = text.trim().split(/\n\n+/);
  return (
    <div className="space-y-4">
      {blocks.map((b, i) => {
        const lines = b.split("\n");
        if (b.startsWith("## ")) {
          return <h2 key={i} className="pt-2 text-xl font-semibold text-navy">{b.slice(3)}</h2>;
        }
        if (b.startsWith("# ")) {
          return <h1 key={i} className="text-2xl font-bold text-navy">{b.slice(2)}</h1>;
        }
        if (lines.every((l) => l.trim().startsWith("- "))) {
          return (
            <ul key={i} className="ml-1 space-y-1.5">
              {lines.map((l, k) => (
                <li key={k} className="flex gap-2 text-[15px] leading-relaxed text-muted">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-lava" />
                  <span dangerouslySetInnerHTML={{ __html: inline(l.replace(/^-\s+/, "")) }} />
                </li>
              ))}
            </ul>
          );
        }
        return <p key={i} className="text-[15px] leading-relaxed text-muted" dangerouslySetInnerHTML={{ __html: inline(b) }} />;
      })}
    </div>
  );
}

export default function Faq() {
  const [md, setMd] = useState<string | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.faq().then(setMd).catch((e) => setErr(String(e)));
  }, []);

  return (
    <>
      <PageHeader title="Frequently asked questions" lead="Common questions about the hands-on workshop.">
        <div className="mt-4">
          <a href={REPO_FAQ} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-navy underline decoration-lava decoration-2 underline-offset-4 hover:text-lava">
            View FAQ.md in the repo <ExternalLink className="h-3.5 w-3.5" />
          </a>
        </div>
      </PageHeader>
      <div className="mx-auto max-w-3xl px-8 py-12 lg:px-14">
        {err && <p className="text-sm text-lava">Could not load FAQ: {err}</p>}
        {!md && !err && <div className="flex items-center gap-2 text-muted"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>}
        {md && <Markdown text={md} />}
      </div>
    </>
  );
}
