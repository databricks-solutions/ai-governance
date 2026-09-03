import { create } from 'zustand';
import type { ModelDef, Tier } from '../api/types';
import { buildSampleRuns } from '../data/sampleSession';

// Cross-tab session state. In-memory only - no browser storage APIs.

export type TabId = 'compare' | 'pipeline' | 'cost' | 'why' | 'arch' | 'styleguide';

// The last routing decision - from Compare's winner or the Gateway box - so the
// Architecture tab can render it live. Null before any run → generic diagram.
export interface LastRouting {
  model: string;
  tier: Tier;
  costUsd: number;
  complexity?: number | null;
  source: 'compare' | 'gateway';
}

// One recorded request - the raw material for the Cost tab's spend view,
// per-model breakdown, projections, and activity log. Every winning Compare run
// and every Gateway route appends one of these.
export interface RunRecord {
  id: string;
  ts: number;
  source: 'compare' | 'gateway';
  modelShort: string;
  tier: Tier;
  costUsd: number;
  baselineUsd: number; // priciest alternative that was on the table (for savings)
  inputTokens: number;
  outputTokens: number;
  latencyMs?: number; // serving latency (observability); derived from tier when absent
  optimized: boolean;
  promptSnippet: string;
  sample?: boolean; // seeded demo row (tagged in the activity log)
  team?: string; // team / use-case attribution
}

interface SessionState {
  activeTab: TabId;
  setTab: (t: TabId) => void;

  // Running session totals shown in the masthead: queries, spend, the baseline
  // (priciest option) and saved (base − spend).
  queries: number;
  spendUsd: number;
  baseUsd: number;

  // Full per-request log - drives the Cost tab.
  runs: RunRecord[];
  // Record a request; also advances the masthead totals (single source of truth).
  logRun: (r: Omit<RunRecord, 'id' | 'ts'>) => void;

  // Seeded demo session (P0-2): true once a sample is loaded / a fresh run has
  // happened, so we don't re-seed. `sampleActive` = the currently shown data is
  // (or started as) the seeded sample.
  seeded: boolean;
  sampleActive: boolean;
  seedSample: (models: ModelDef[]) => void; // load the fixture, computing costs from the rate card
  startFresh: () => void; // clear to an empty session

  lastRouting: LastRouting | null;
  setLastRouting: (r: LastRouting) => void;
}

function totals(runs: RunRecord[]) {
  return runs.reduce(
    (acc, r) => ({ queries: acc.queries + 1, spendUsd: acc.spendUsd + r.costUsd, baseUsd: acc.baseUsd + r.baselineUsd }),
    { queries: 0, spendUsd: 0, baseUsd: 0 },
  );
}

let _seq = 0;

export const useSession = create<SessionState>((set) => ({
  activeTab: 'compare',
  setTab: (t) => set({ activeTab: t }),

  queries: 0,
  spendUsd: 0,
  baseUsd: 0,

  runs: [],
  logRun: (r) =>
    set((s) => {
      // Cap the log AND derive the headline totals from the SAME capped array, so
      // the Cost tab's per-model / per-tier breakdown always reconciles with the
      // KPI tiles (they diverged once >200 requests accrued). A real run also
      // marks the session as no longer a pristine sample.
      const runs = [{ ...r, id: `run-${++_seq}`, ts: Date.now() }, ...s.runs].slice(0, 200);
      return { ...totals(runs), runs, sampleActive: false };
    }),

  seeded: false,
  sampleActive: false,
  seedSample: (models) =>
    set(() => {
      const runs = buildSampleRuns(models);
      return { ...totals(runs), runs, seeded: true, sampleActive: true };
    }),
  startFresh: () => set({ queries: 0, spendUsd: 0, baseUsd: 0, runs: [], seeded: true, sampleActive: false, lastRouting: null }),

  lastRouting: null,
  setLastRouting: (r) => set({ lastRouting: r }),
}));
