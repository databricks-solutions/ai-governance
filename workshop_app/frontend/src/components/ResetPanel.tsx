import { useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { api } from "@/lib/api";

/** Clear all workshop progress so the room can start fresh. Destructive — confirms first, and
 *  points the presenter at the Outcomes export to keep a record before wiping. Lives at the
 *  bottom of the Walkthrough, Prerequisites, and Outcomes so it's easy to find from anywhere. */
export default function ResetPanel({ onReset }: { onReset: () => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function reset() {
    if (!window.confirm(
      "Clear ALL workshop progress on this deployment? Every step returns to not-started. " +
      "This cannot be undone — export the outcomes first if you need the record.",
    )) return;
    setBusy(true);
    setMsg("");
    try {
      const res = await api.resetProgress();
      setMsg(`Cleared ${res.cleared} step(s). Starting fresh.`);
      onReset();
    } catch (e) {
      setMsg(`Reset failed: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-8 flex flex-wrap items-center gap-3 rounded-2xl border border-navy/10 bg-white p-5">
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-navy">Start over</div>
        <div className="mt-0.5 text-xs text-muted">
          Clears all progress on this deployment — for re-running the workshop or resetting a demo.
          Export from Outcomes first; this can't be undone.
        </div>
      </div>
      <button
        onClick={reset}
        disabled={busy}
        className="inline-flex shrink-0 items-center gap-2 rounded-full border border-navy/20 px-4 py-2 text-sm font-semibold text-navy hover:border-lava hover:text-lava disabled:opacity-40"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
        Reset workshop progress
      </button>
      {msg && <span className="w-full text-xs text-muted">{msg}</span>}
    </div>
  );
}
