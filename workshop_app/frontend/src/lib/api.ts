// API client for the workshop backend.
export interface StepAction {
  label: string;
  test?: string;
}
export interface StepManual {
  label: string;
  deep_link?: string;
  url?: string;
}
export interface Step {
  id: string;
  title: string;
  concept?: string;
  action?: StepAction;
  verify?: StepAction;
  manual?: StepManual;
}
export interface Pillar {
  id: string;
  title: string;
  tagline: string;
  steps: Step[];
}
export interface Workshop {
  intro: { title: string; body: string };
  pillars: Pillar[];
}

export interface TestResult {
  ok: boolean;
  summary: string;
  detail?: Record<string, unknown>;
}

export type ProgressMap = Record<
  string,
  { pillar_id: string; status: string; last_result: TestResult | null; notes: string | null; updated_at: string | null }
>;

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export const api = {
  workshop: () => fetch("/api/workshop").then((r) => j<Workshop>(r)),
  progress: (runId: string) => fetch(`/api/progress/${encodeURIComponent(runId)}`).then((r) => j<ProgressMap>(r)),
  runTest: (body: {
    test: string;
    run_id: string;
    step_id: string;
    pillar_id: string;
    kind?: string;
  }) =>
    fetch("/api/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => j<TestResult>(r)),
  setProgress: (body: { run_id: string; step_id: string; pillar_id: string; status: string; notes?: string }) =>
    fetch("/api/progress", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => j<{ ok: boolean }>(r)),

  // Export — build the URLs the browser downloads (outcomes JSON + Markdown report).
  exportUrl: (kind: "outcomes" | "report", runId: string, sfid: string, name: string) => {
    const q = new URLSearchParams({ run_id: runId, customer_sfid: sfid });
    if (name) q.set("customer_name", name);
    return `/api/export/${kind}?${q.toString()}`;
  },
};
