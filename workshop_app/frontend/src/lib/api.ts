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
  /** One-line "We can …" outcome statement shown under the title. */
  outcome?: string;
  /** Preview outcome — shown with a "Coming soon" badge, no Try-It yet. */
  coming_soon?: boolean;
  concept?: string;
  /** Key of a diagram to render under the concept — see VISUALS in StepCard. */
  visual?: string;
  /** Ids of steps that must be `done` before this one is meaningful (e.g. the governed
   *  endpoint must exist before its rate limits can be read). Surfaced as a warn-but-allow
   *  banner — never a hard block — so a room that set something up out-of-band is never trapped. */
  depends_on?: string[];
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
export interface DeployStep {
  do: string;
  cmd?: string;
  ensure?: string;
}
export interface DeployGuide {
  title: string;
  intro?: string;
  steps: DeployStep[];
  footer?: string;
}
export interface Workshop {
  intro: { title: string; body: string; deploy?: DeployGuide };
  pillars: Pillar[];
}

export interface TestResult {
  ok: boolean;
  // 'action_required' means the test ran but proved nothing yet (a guided UI step, or a
  // telemetry query with no data). Rendered amber, never as a pass.
  status?: "action_required";
  summary: string;
  detail?: Record<string, unknown>;
  /** The API surface this step exercised, e.g. "GET /api/2.1/unity-catalog/mcp-services". */
  api?: string;
  /** Link to the Databricks API reference index. */
  api_index?: string;
  /** Why a step is read-only or guided, when that needs saying. */
  api_note?: string;
}

export type ProgressMap = Record<
  string,
  {
    pillar_id: string;
    status: string;
    last_result: TestResult | null;
    notes: string | null;
    /** Hand-marked outcome, independent of the interactive test: "done" | "na" | null. */
    outcome?: string | null;
    /** Flagged for the POC follow-up doc. */
    poc?: boolean;
    updated_at: string | null;
  }
>;

/** Resolve a step's effective outcome from its saved record. A step is `done` if the Try-It
 *  test passed OR it was hand-marked done; `na` drops it from completion counts. */
export function stepOutcome(saved: ProgressMap[string] | null | undefined) {
  const status = saved?.status ?? "not_started";
  const outcome = saved?.outcome ?? null;
  const poc = !!saved?.poc;
  return { status, outcome, poc, done: outcome === "done" || status === "done", na: outcome === "na" };
}

/** A step's unmet dependencies: the `depends_on` ids that are not yet achieved. A dependency
 *  counts as met only when it is `done` (its Try-It passed or it was hand-marked done) — an
 *  `action_required` prerequisite (e.g. the endpoint still needs creating) is deliberately still
 *  unmet, since that is exactly the setup this step needs. Returns [{id, title}] for the banner. */
export function unmetDependencies(
  step: { depends_on?: string[] },
  progress: ProgressMap,
  titles: Record<string, string>,
): { id: string; title: string }[] {
  return (step.depends_on ?? [])
    .filter((id) => !stepOutcome(progress[id]).done)
    .map((id) => ({ id, title: titles[id] ?? id }));
}

/** Achieved / applicable / total counts for a group of steps (N/A excluded from applicable). */
export function groupCounts(steps: { id: string }[], progress: ProgressMap) {
  let done = 0;
  let applicable = 0;
  for (const s of steps) {
    const o = stepOutcome(progress[s.id]);
    if (o.na) continue;
    applicable++;
    if (o.done) done++;
  }
  return { done, applicable, total: steps.length };
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export interface Accelerators {
  overview: { title: string; body: string };
  accelerators: Pillar[]; // same shape as a pillar (id/title/tagline/steps)
}

export interface PrereqItem {
  id: string;
  item: string;
  why?: string;
  who?: string;
  /** Only needed for a specific scope (a named accelerator, external providers, …). */
  optional?: boolean;
  /** Hard blocker — the workshop cannot run until this is met. */
  blocker?: boolean;
}
export interface PrereqGroup {
  id: string;
  title: string;
  lead_time?: string;
  intro?: string;
  items: PrereqItem[];
}
export interface Prerequisites {
  lead_time_note?: string;
  groups: PrereqGroup[];
  /** Shareable Google Doc generated from the same prerequisites.yaml (kept in sync). */
  google_doc_url?: string | null;
  /** False when reportlab is missing from the deployment — hide the PDF button rather than 503. */
  pdf_available: boolean;
  pdf_unavailable_reason?: string | null;
}

export const api = {
  workshop: () => fetch("/api/workshop").then((r) => j<Workshop>(r)),
  accelerators: () => fetch("/api/accelerators").then((r) => j<Accelerators>(r)),
  faq: () => fetch("/api/faq").then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status))))),
  progress: () => fetch("/api/progress").then((r) => j<ProgressMap>(r)),
  runTest: (body: {
    test: string;
    step_id: string;
    pillar_id: string;
    kind?: string;
  }) =>
    fetch("/api/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => j<TestResult>(r)),
  setProgress: (body: { step_id: string; pillar_id: string; status: string; notes?: string }) =>
    fetch("/api/progress", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => j<{ ok: boolean }>(r)),

  // Clear ALL workshop progress so the room can start fresh. Cannot be undone — export first.
  resetProgress: () =>
    fetch("/api/progress/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    }).then((r) => j<{ ok: boolean; cleared: number }>(r)),

  // Set the hand-marked outcome flags (Done / N/A / Add-to-POC). The full desired state is sent
  // each time (Done and N/A are mutually exclusive; `poc` is independent).
  setOutcome: (body: {
    step_id: string;
    pillar_id: string;
    outcome: string | null;
    poc: boolean;
    updated_by?: string;
  }) =>
    fetch("/api/outcome", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => j<{ ok: boolean }>(r)),

  prerequisites: () => fetch("/api/prerequisites").then((r) => j<Prerequisites>(r)),

  // Export — the URLs the browser downloads (outcomes JSON + Markdown report).
  exportUrl: (kind: "outcomes" | "report") => `/api/export/${kind}`,

  // PDFs are generated server-side and set their own Content-Disposition filename, so these
  // URLs are navigated to rather than fetched.
  reportPdfUrl: () => "/api/export/report.pdf",
  prerequisitesPdfUrl: (customerName?: string) =>
    "/api/export/prerequisites.pdf" +
    (customerName ? `?${new URLSearchParams({ customer_name: customerName }).toString()}` : ""),
  // The one-page workshop brochure — a leave-ahead to book the session. No account needed.
  brochurePdfUrl: (customerName?: string) =>
    "/api/export/brochure.pdf" +
    (customerName ? `?${new URLSearchParams({ customer_name: customerName }).toString()}` : ""),
};
