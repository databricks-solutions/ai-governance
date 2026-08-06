import { useState } from "react";
import { Play, ExternalLink, CheckCircle2, XCircle, AlertCircle, Loader2, Check, Circle } from "lucide-react";
import { api, type Step, type TestResult, type ProgressMap } from "@/lib/api";
import { useAccount } from "@/lib/account";
import { cn } from "@/lib/cn";

type Saved = ProgressMap[string] | null;

// Color-coded kind badges — same taxonomy as the l200 demo (concept/try-it/manual/verify).
const BADGES = {
  concept: { label: "CONCEPT", cls: "bg-[#E7F1FC] text-[#0B5FA5]" },
  action: { label: "TRY IT", cls: "bg-[#E6F4EA] text-[#1E7E34]" },
  manual: { label: "MANUAL (UI)", cls: "bg-[#FDF3E0] text-[#B7791F]" },
  verify: { label: "VERIFY", cls: "bg-navy/5 text-navy" },
} as const;

function Badge({ kind }: { kind: keyof typeof BADGES }) {
  const b = BADGES[kind];
  return <span className={cn("rounded px-2 py-0.5 text-[11px] font-semibold", b.cls)}>{b.label}</span>;
}

export default function StepCard({
  index,
  pillarId,
  step,
  saved,
  onProgressChange,
}: {
  index: number;
  pillarId: string;
  step: Step;
  saved: Saved;
  onProgressChange: () => void;
}) {
  const { sfid } = useAccount();
  const [running, setRunning] = useState<null | "action" | "verify">(null);
  const [result, setResult] = useState<TestResult | null>(saved?.last_result ?? null);
  const status = saved?.status ?? "not_started";

  async function run(kind: "action" | "verify", test: string) {
    setRunning(kind);
    try {
      const res = await api.runTest({ test, customer_sfid: sfid, step_id: step.id, pillar_id: pillarId, kind });
      setResult(res);
    } catch (e) {
      setResult({ ok: false, summary: String(e) });
    } finally {
      setRunning(null);
      onProgressChange();
    }
  }

  async function toggleDone() {
    const next = status === "done" ? "in_progress" : "done";
    await api.setProgress({ customer_sfid: sfid, step_id: step.id, pillar_id: pillarId, status: next });
    onProgressChange();
  }

  // A step that ran but proved nothing (a guided UI action, or telemetry with no data yet)
  // must not look complete — that is the difference between an honest workshop record and
  // a green wall of checks.
  const actionRequired = status === "action_required";

  return (
    <div className={cn("rounded-2xl border bg-white p-6", status === "done" ? "border-navy/25" : "border-navy/10")}>
      {/* Header */}
      <div className="mb-3 flex items-start gap-3">
        <button
          onClick={toggleDone}
          className={cn(
            "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border transition-colors",
            status === "done" ? "border-navy bg-navy text-white" : "border-navy/20 text-navy-300",
          )}
          title="Mark done"
        >
          {status === "done" ? <Check className="h-4 w-4" strokeWidth={3} /> : <Circle className="h-3.5 w-3.5" />}
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-navy-300">Step {index}</div>
            {actionRequired && (
              <span className="rounded bg-[#FDF3E0] px-2 py-0.5 text-[11px] font-semibold text-[#B7791F]">
                ACTION NEEDED
              </span>
            )}
          </div>
          <h3 className="text-lg font-semibold text-navy">{step.title}</h3>
        </div>
      </div>

      {/* Concept */}
      {step.concept && (
        <div className="mb-4 rounded-xl bg-oat p-4">
          <div className="mb-1.5">
            <Badge kind="concept" />
          </div>
          <p className="whitespace-pre-line text-sm leading-relaxed text-muted">{step.concept.trim()}</p>
        </div>
      )}

      {/* Actions row: manual deep-link, Try-It, Verify */}
      <div className="flex flex-wrap items-center gap-2">
        {step.manual?.url && (
          <a
            href={step.manual.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-full border border-[#B7791F]/30 bg-[#FDF3E0] px-4 py-2 text-sm font-semibold text-[#B7791F] hover:border-[#B7791F]/60"
          >
            <Badge kind="manual" /> {step.manual.label} <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
        {step.action?.test && (
          <button
            onClick={() => run("action", step.action!.test!)}
            disabled={running !== null}
            className="inline-flex items-center gap-2 rounded-full bg-navy px-4 py-2 text-sm font-semibold text-white hover:bg-navy-700 disabled:opacity-40"
          >
            {running === "action" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {step.action.label}
          </button>
        )}
        {step.verify?.test && (
          <button
            onClick={() => run("verify", step.verify!.test!)}
            disabled={running !== null}
            className="inline-flex items-center gap-2 rounded-full border border-navy/20 px-4 py-2 text-sm font-semibold text-navy hover:border-navy/50 disabled:opacity-40"
          >
            {running === "verify" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Badge kind="verify" />}
            {step.verify.label}
          </button>
        )}
      </div>

      {/* Result — three states, not two: passed, action needed, failed. */}
      {result && (
        <div
          className={cn(
            "mt-4 rounded-xl border p-4",
            result.status === "action_required"
              ? "border-[#B7791F]/30 bg-[#FDF3E0]/60"
              : result.ok
                ? "border-[#1E7E34]/20 bg-[#E6F4EA]/50"
                : "border-lava/30 bg-lava/[0.04]",
          )}
        >
          <div className="flex items-center gap-2 text-sm font-semibold">
            {result.status === "action_required" ? (
              <AlertCircle className="h-4.5 w-4.5 shrink-0 text-[#B7791F]" />
            ) : result.ok ? (
              <CheckCircle2 className="h-4.5 w-4.5 shrink-0 text-[#1E7E34]" />
            ) : (
              <XCircle className="h-4.5 w-4.5 shrink-0 text-lava" />
            )}
            <span className="text-navy">{result.summary}</span>
          </div>
          {result.detail && Object.keys(result.detail).length > 0 && (
            <pre className="mt-3 max-h-64 overflow-auto rounded-lg bg-navy/[0.03] p-3 text-xs leading-relaxed text-navy/80">
              {JSON.stringify(result.detail, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
