import { useState, type ReactNode } from "react";
import { Check, Ban, FilePlus2 } from "lucide-react";
import { api, stepOutcome, type ProgressMap } from "@/lib/api";
import { cn } from "@/lib/cn";

// The per-step outcome control: Done / N/A / Add-to-POC. Shared by the step cards and the
// outcomes checklist on the Prerequisites page, so both edit the same backing state and stay
// in sync. The three are a SINGLE mutually-exclusive selection: a step is Done, or N/A, or
// flagged for the POC, or none. Selecting one clears the others; clicking the active one clears
// it. A step reads as done only when it was hand-marked here (a passing Try-It is shown by the
// result badge, but never auto-marks the outcome).
export default function OutcomeControls({
  stepId,
  pillarId,
  saved,
  onChange,
  className,
}: {
  stepId: string;
  pillarId: string;
  saved: ProgressMap[string] | null | undefined;
  onChange: () => void;
  className?: string;
}) {
  const { outcome, poc, done, na } = stepOutcome(saved);
  const [busy, setBusy] = useState(false);

  // One selection at a time: setting an outcome clears POC, and flagging POC clears the outcome.
  async function select(kind: "done" | "na" | "poc") {
    setBusy(true);
    try {
      const body =
        kind === "poc"
          ? { outcome: null as string | null, poc: !poc }
          : { outcome: outcome === kind ? null : kind, poc: false };
      await api.setOutcome({ step_id: stepId, pillar_id: pillarId, ...body });
      onChange();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <Chip
        active={done}
        onClick={() => select("done")}
        disabled={busy}
        tone="done"
        icon={<Check className="h-3.5 w-3.5" strokeWidth={3} />}
        label="Done"
        title="Mark this outcome done"
      />
      <Chip
        active={na}
        onClick={() => select("na")}
        disabled={busy}
        tone="na"
        icon={<Ban className="h-3.5 w-3.5" />}
        label="N/A"
        title="Not applicable for this customer (drops from the completion count)"
      />
      <Chip
        active={poc}
        onClick={() => select("poc")}
        disabled={busy}
        tone="poc"
        icon={<FilePlus2 className="h-3.5 w-3.5" />}
        label="Add to POC"
        title="Flag this step for the POC follow-up (clears Done/N/A)"
      />
    </div>
  );
}

function Chip({
  active,
  onClick,
  disabled,
  icon,
  label,
  tone,
  title,
}: {
  active: boolean;
  onClick: () => void;
  disabled?: boolean;
  icon: ReactNode;
  label: string;
  tone: "done" | "na" | "poc";
  title?: string;
}) {
  const tones: Record<string, string> = {
    done: active
      ? "border-[#1E7E34]/40 bg-[#E6F4EA] text-[#1E7E34]"
      : "border-navy/15 text-navy-300 hover:border-[#1E7E34]/40",
    na: active
      ? "border-navy/30 bg-navy/5 text-navy"
      : "border-navy/15 text-navy-300 hover:border-navy/40",
    poc: active
      ? "border-lava/40 bg-lava/10 text-lava"
      : "border-navy/15 text-navy-300 hover:border-lava/40",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-colors disabled:opacity-50",
        tones[tone],
      )}
    >
      {icon}
      {label}
    </button>
  );
}
