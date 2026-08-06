import { createContext, useContext, useState, type ReactNode } from "react";

// The whole workshop is tracked against one Account ID (a Salesforce account id in practice,
// but labelled neutrally because the app is customer-facing). Progress, tests, and the
// outcomes export are all keyed by it, so results flow straight into the internal sales app.
// Persisted to localStorage so a room can pause and resume.
interface AccountCtx {
  sfid: string;
  setSfid: (id: string) => void;
}

const Ctx = createContext<AccountCtx | null>(null);
const KEY = "aigov.workshop.sfid";

export function AccountProvider({ children }: { children: ReactNode }) {
  const [sfid, setSfidState] = useState<string>(() => localStorage.getItem(KEY) || "");

  function setSfid(id: string) {
    const v = id.trim();
    setSfidState(v);
    localStorage.setItem(KEY, v);
  }

  return <Ctx.Provider value={{ sfid, setSfid }}>{children}</Ctx.Provider>;
}

export function useAccount(): AccountCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAccount must be used within AccountProvider");
  return ctx;
}
