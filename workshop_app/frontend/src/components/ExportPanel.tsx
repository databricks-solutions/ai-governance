import { FileText, FileJson, Download } from "lucide-react";
import { api } from "@/lib/api";
import { useAccount } from "@/lib/account";

// Export the workshop outcomes: a Markdown report (per-step complete/incomplete) and an
// outcomes.json the internal sales app ingests. Everything is keyed to the Account ID set
// at the top of the workshop.
export default function ExportPanel() {
  const { sfid } = useAccount();

  function download(kind: "outcomes" | "report") {
    if (!sfid.trim()) return;
    const url = api.exportUrl(kind, sfid.trim());
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
        track this account's workshop and next steps. Everything is keyed to the Account ID
        set at the top of the workshop.
      </p>
      {!sfid.trim() ? (
        <p className="text-sm text-lava">Set an Account ID at the top of the Introduction to enable export.</p>
      ) : (
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => download("report")}
            className="inline-flex items-center gap-2 rounded-full border border-navy/20 px-4 py-2 text-sm font-semibold text-navy hover:border-navy/50"
          >
            <FileText className="h-4 w-4" /> Download report (.md)
          </button>
          <button
            onClick={() => download("outcomes")}
            className="inline-flex items-center gap-2 rounded-full bg-navy px-4 py-2 text-sm font-semibold text-white hover:bg-navy-700"
          >
            <FileJson className="h-4 w-4" /> Download outcomes (.json)
          </button>
        </div>
      )}
      <p className="mt-3 text-xs text-muted">
        Account: <code className="rounded bg-navy/5 px-1 py-0.5">{sfid || "not set"}</code> — load the .json in the
        internal sales app's account journey.
      </p>
    </div>
  );
}
