import { useState, type ReactNode } from "react";
import { Check, Ban, FilePlus2 } from "lucide-react";
import { api, stepOutcome, type ProgressMap } from "@/lib/api";
import { cn } from "@/lib/cn";

// The per-step outcome control: Done / N/A / Add-to-POC. Shared by the step cards and the
// outcomes checklist on the Prerequisites page, so both edit the same backing state and stay
// in sync. Done and N/A are mutually exclusive; "Add to POC" is an independent flag.
//
// A step reads as done when the interactive Try-It test passed OR it was hand-marked done — so
// a room that runs activities without clicking Try-It can still record real outcomes here.
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
  const { outcome, poc, done, na, status } = stepOutcome(saved);
  const [busy, setBusy] = useState(false);
  // Done shows lit because the Try-It test passed, not because someone ticked it here.
  const autoDone = status === "done" && outcome !== "done";

  async function send(nextOutcome: string | null, nextPoc: boolean) {
    setBusy(true);
    try {
      await api.setOutcome({ step_id: stepId, pillar_id: pillarId, outcome: nextOutcome, poc: nextPoc });
      onChange();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <Chip
        active={done}
        onClick={() => send(outcome === "done" ? null : "done", poc)}
        disabled={busy}
        tone="done"
        icon={<Check className="h-3.5 w-3.5" strokeWidth={3} />}
        label={autoDone ? "Done · auto" : "Done"}
        title={autoDone ? "Achieved by running Try-It" : "Mark this outcome done"}
      />
      <Chip
        active={na}
        onClick={() => send(outcome === "na" ? null : "na", poc)}
        disabled={busy}
        tone="na"
        icon={<Ban className="h-3.5 w-3.5" />}
        label="N/A"
        title="Not applicable for this customer (drops from the completion count)"
      />
      <Chip
        active={poc}
        onClick={() => send(outcome, !poc)}
        disabled={busy}
        tone="poc"
        icon={<FilePlus2 className="h-3.5 w-3.5" />}
        label="Add to POC"
        title="Flag this step for the POC follow-up"
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
