import { useEffect, useState } from "react";
import { Loader2, ExternalLink } from "lucide-react";
import PageHeader from "@/components/PageHeader";
import { api } from "@/lib/api";
import Markdown from "@/components/Markdown";

const REPO_FAQ = "https://github.com/databricks-solutions/ai-governance/blob/main/workshop_app/FAQ.md";

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
