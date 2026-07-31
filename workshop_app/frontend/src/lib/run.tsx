import { createContext, useContext, useState, type ReactNode } from "react";

// A "run" groups progress for one team/session so multiple teams can track
// independently on the same deployment. Persisted to localStorage.
interface RunCtx {
  runId: string;
  setRunId: (id: string) => void;
}

const Ctx = createContext<RunCtx | null>(null);
const KEY = "aigov.workshop.run";

export function RunProvider({ children }: { children: ReactNode }) {
  const [runId, setRunIdState] = useState<string>(() => localStorage.getItem(KEY) || "workshop-team");

  function setRunId(id: string) {
    const v = id.trim() || "workshop-team";
    setRunIdState(v);
    localStorage.setItem(KEY, v);
  }

  return <Ctx.Provider value={{ runId, setRunId }}>{children}</Ctx.Provider>;
}

export function useRun(): RunCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useRun must be used within RunProvider");
  return ctx;
}
