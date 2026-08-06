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
  // 'action_required' means the test ran but proved nothing yet (a guided UI step, or a
  // telemetry query with no data). Rendered amber, never as a pass.
  status?: "action_required";
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

export interface Accelerators {
  overview: { title: string; body: string };
  accelerators: Pillar[]; // same shape as a pillar (id/title/tagline/steps)
}

export const api = {
  workshop: () => fetch("/api/workshop").then((r) => j<Workshop>(r)),
  accelerators: () => fetch("/api/accelerators").then((r) => j<Accelerators>(r)),
  faq: () => fetch("/api/faq").then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status))))),
  progress: (sfid: string) => fetch(`/api/progress/${encodeURIComponent(sfid)}`).then((r) => j<ProgressMap>(r)),
  runTest: (body: {
    test: string;
    customer_sfid: string;
    step_id: string;
    pillar_id: string;
    kind?: string;
  }) =>
    fetch("/api/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => j<TestResult>(r)),
  setProgress: (body: { customer_sfid: string; step_id: string; pillar_id: string; status: string; notes?: string }) =>
    fetch("/api/progress", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => j<{ ok: boolean }>(r)),

  // Export — build the URLs the browser downloads (outcomes JSON + Markdown report).
  exportUrl: (kind: "outcomes" | "report", sfid: string) => {
    const q = new URLSearchParams({ customer_sfid: sfid });
    return `/api/export/${kind}?${q.toString()}`;
  },
};
