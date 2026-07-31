import { useState } from "react";
import { FileText, FileJson, Download } from "lucide-react";
import { api } from "@/lib/api";
import { useRun } from "@/lib/run";

// Export the workshop outcomes: a Markdown report (per-step complete/incomplete) and an
// outcomes.json the internal sales app ingests. The deliverer confirms the Salesforce id
// so the JSON links to the right account.
export default function ExportPanel() {
  const { runId } = useRun();
  const [sfid, setSfid] = useState("");
  const [name, setName] = useState("");

  function download(kind: "outcomes" | "report") {
    if (!sfid.trim()) return;
    const url = api.exportUrl(kind, runId, sfid.trim(), name.trim());
    // Force a download with a sensible filename.
    const a = document.createElement("a");
    a.href = url;
    a.download = kind === "outcomes" ? `${sfid.trim()}_workshop_outcomes.json` : `${sfid.trim()}_workshop_report.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  return (
    <div className="rounded-2xl border border-navy/10 bg-white p-6">
      <div className="mb-1 flex items-center gap-2">
        <Download className="h-4.5 w-4.5 text-lava" strokeWidth={2} />
        <h3 className="font-semibold text-navy">Export workshop outcomes</h3>
      </div>
      <p className="mb-4 text-sm leading-relaxed text-muted">
        Generate the leave-behind report and the outcomes file the internal sales app loads to
        track this account's workshop and next steps. Confirm the Salesforce account id first.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">Salesforce id</span>
          <input
            value={sfid}
            onChange={(e) => setSfid(e.target.value)}
            placeholder="0016100001Qcv4uAAB"
            className="mt-1.5 w-full rounded-xl border border-navy/15 bg-oat px-3.5 py-2.5 text-sm text-navy outline-none focus:border-navy"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">Account name (optional)</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Acme Corp"
            className="mt-1.5 w-full rounded-xl border border-navy/15 bg-oat px-3.5 py-2.5 text-sm text-navy outline-none focus:border-navy"
          />
        </label>
      </div>
      <div className="mt-4 flex flex-wrap gap-3">
        <button
          onClick={() => download("report")}
          disabled={!sfid.trim()}
          className="inline-flex items-center gap-2 rounded-full border border-navy/20 px-4 py-2 text-sm font-semibold text-navy hover:border-navy/50 disabled:opacity-40"
        >
          <FileText className="h-4 w-4" /> Download report (.md)
        </button>
        <button
          onClick={() => download("outcomes")}
          disabled={!sfid.trim()}
          className="inline-flex items-center gap-2 rounded-full bg-navy px-4 py-2 text-sm font-semibold text-white hover:bg-navy-700 disabled:opacity-40"
        >
          <FileJson className="h-4 w-4" /> Download outcomes (.json)
        </button>
      </div>
      <p className="mt-3 text-xs text-muted">
        Run: <code className="rounded bg-navy/5 px-1 py-0.5">{runId}</code> — load the .json in the internal
        sales app's account journey.
      </p>
    </div>
  );
}
