import { FileText, FileJson, Download, FileDown } from "lucide-react";
import { api } from "@/lib/api";

// Export the workshop outcomes: a PDF leave-behind (the primary artifact — it gets emailed and
// attached to a POC), a Markdown report, and a machine-readable outcomes.json.
export default function ExportPanel() {
  function download(kind: "outcomes" | "report" | "report-pdf") {
    // The PDF is generated server-side and already sends Content-Disposition with a filename,
    // so navigating to it is enough — no `download` attribute needed (and setting one would
    // override the server's name).
    if (kind === "report-pdf") {
      window.location.href = api.reportPdfUrl();
      return;
    }
    const a = document.createElement("a");
    a.href = api.exportUrl(kind);
    a.download = kind === "outcomes" ? "workshop_outcomes.json" : "workshop_report.md";
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
        Generate the POC-doc leave-behind and the machine-readable outcomes file — every step with
        its status, the incomplete items as next steps, and everything flagged for POC.
      </p>
      <div className="flex flex-wrap gap-3">
        <button
          onClick={() => download("report-pdf")}
          className="inline-flex items-center gap-2 rounded-full bg-navy px-4 py-2 text-sm font-semibold text-white hover:bg-navy-700"
        >
          <FileDown className="h-4 w-4" /> Download report (PDF)
        </button>
        <button
          onClick={() => download("report")}
          className="inline-flex items-center gap-2 rounded-full border border-navy/20 px-4 py-2 text-sm font-semibold text-navy hover:border-navy/50"
        >
          <FileText className="h-4 w-4" /> Report (.md)
        </button>
        <button
          onClick={() => download("outcomes")}
          className="inline-flex items-center gap-2 rounded-full border border-navy/20 px-4 py-2 text-sm font-semibold text-navy hover:border-navy/50"
        >
          <FileJson className="h-4 w-4" /> Outcomes (.json)
        </button>
      </div>
      <p className="mt-3 text-xs text-muted">
        The PDF is the customer leave-behind; the .json is the machine-readable outcomes record.
      </p>
    </div>
  );
}
