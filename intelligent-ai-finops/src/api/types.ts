// Data contracts - mirror BUILD-SPEC §4 exactly. The frontend NEVER computes
// cost (§7); every route returns a full RoutingReceipt from the backend.

export type Tier = 'frontier' | 'large-oss' | 'small-oss';

// Human labels for the three model categories.
export const TIER_LABEL: Record<Tier, string> = {
  frontier: 'Frontier',
  'large-oss': 'Large open-weight OSS',
  'small-oss': 'Small open source',
};
export const TIER_SHORT: Record<Tier, string> = {
  frontier: 'Frontier',
  'large-oss': 'Large OSS',
  'small-oss': 'Small OSS',
};
// Category order used for grouping (most → least capable).
export const TIER_ORDER: Tier[] = ['frontier', 'large-oss', 'small-oss'];

// Tier accent hexes tuned for the dark stage (charts/badges).
export const TIER_META: Record<Tier, { hex: string }> = {
  frontier: { hex: '#B487D0' },
  'large-oss': { hex: '#E3B876' },
  'small-oss': { hex: '#93D3AB' },
};

export type StageId =
  | 'service-principal'
  | 'rate-limits'
  | 'semantic-cache'
  | 'pii-guardrail'
  | 'complexity-score'
  | 'policy-table'
  | 'budget-check'
  | 'fallback-chain'
  | 'model-serving'
  | 'inference-tables'
  | 'uc-lineage';

export type StageCategory = 'guard' | 'route' | 'serve' | 'observe';

export interface ModelDef {
  id: string; // serving endpoint name, e.g. databricks-claude-opus-4-1
  short: string; // display short name
  tier: Tier;
  price_in_per_1m: number;
  price_out_per_1m: number;
}

export interface TraceEvent {
  stage: StageId;
  outcome: 'ok' | 'hit' | 'warn' | 'skip';
  message: string;
  latencyDeltaMs: number;
}

export interface RoutingReceipt {
  requestId: string;
  model: { id: string; short: string; tier: Tier };
  costUsd: number;
  latencyMs: number;
  judgeScore: number | null; // null when judging is off
  complexity: number; // 0–100
  policyMatched: string; // "complexity 34 → open"
  budgetState: { spentPct: number; daysLeft: number; escalated: boolean };
  counterfactual: {
    // what frontier would have done
    model: string;
    costUsd: number;
    judgeScore: number;
  };
  forced: boolean; // presenter overrode the router
  trace: TraceEvent[];
}

// ---- Compare (Tab 1) ----------------------------------------------------
export interface CompareLaneResult {
  modelId: string;
  short: string;
  tier: Tier;
  answer: string;
  costUsd: number;
  latencyMs: number;
  judgeScore: number | null;
  inputTokens: number;
  outputTokens: number;
  error?: string | null;
}

// The "Show context" payload from a lane's `done` event: the exact request sent
// to the model plus the routing decision that explains the tier fit.
export interface LaneContext {
  request: {
    endpoint: string;
    messages: { role: string; content: string }[];
    params: { max_tokens: number; temperature: number };
  };
  decision: {
    complexity: number;
    tier: Tier;
    requiredTier: Tier;
    clears: boolean;
    priceInPer1m: number;
    priceOutPer1m: number;
    counterfactual: { model: string; costUsd: number };
  };
}

// ---- Budget (Tab 3) -----------------------------------------------------
export interface BudgetSnapshot {
  spentUsd: number;
  projectedUsd: number;
  capUsd: number;
  frontierBarPct: number; // share of spend going to frontier
  mix: { small: number; large: number; frontier: number }; // percentages, sum 100
  log: { day: number; message: string; kind: 'ok' | 'warn' | 'hit' }[];
}

// ---- Config (merged models.yaml + policy.yaml) --------------------------
export interface PolicyConfig {
  thresholds: { small_max: number; large_max: number };
  budget: { monthly_cap_usd: number; downgrade_at_pct: number; open_only_at_pct: number };
  fallback: { on: (number | string)[]; timeout_ms: number };
  rate_limits: { calls_per_minute_per_user: number };
  cache: { similarity_threshold: number };
}

export interface AppConfig {
  models: ModelDef[];
  policy: PolicyConfig;
  demoMode: boolean;
  judgeEnabled: boolean;
  priceFootnote: string;
}

// ---- User-defined routing policy (Smart routing tab) --------------------
// A complexity band maps a 0-100 score range to a model tier. The customer
// builds their own bands (add / remove / rename / re-range / re-tier); the set
// of bands IS the routing policy that replaces the fixed config thresholds.
export interface Band {
  id: string;
  label: string;
  min: number; // inclusive 0-100
  max: number; // inclusive 0-100
  tier: Tier;
}

// A keyword rule forces any prompt containing one of its (comma-separated)
// keywords into a chosen band, regardless of the complexity score - e.g.
// "python, sql → Simple" or "NAV, valuation → Complex".
export interface KeywordRule {
  id: string;
  keywords: string; // comma-separated
  bandId: string; // which Band it forces
}
