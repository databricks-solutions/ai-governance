import type { AppConfig } from './types';

// Thin fetch wrapper. All real data comes from the backend.

export interface OptimizeResult {
  optimized: string;
  changed: boolean;
  model?: string;
  note?: string;
}

// Sharpen a prompt before the three Compare lanes run on it. Never throws for
// the caller's flow - on failure we return the original so the run continues.
export async function optimizePrompt(prompt: string, model?: string): Promise<OptimizeResult> {
  // Honors the "never throws" contract: on any failure return the original prompt
  // so the Compare run degrades gracefully instead of aborting.
  try {
    const res = await fetch('/api/optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, model }),
    });
    if (!res.ok) throw new Error(`POST /api/optimize failed: ${res.status}`);
    return res.json();
  } catch {
    return { optimized: prompt, changed: false, note: 'optimizer unavailable — using the original prompt' };
  }
}

// ---- Real inference proxy (/v1/chat/completions) -------------------------
// The `x_finops` receipt the proxy attaches to an OpenAI-compatible response.
export interface FinopsReceipt {
  requestedModel: string;
  mode: 'auto' | 'passthrough';
  routedTo: { id: string; short: string; tier: string };
  servedBy: { id: string; short: string; tier: string };
  complexity: number;
  requiredTier: string;
  requiredTierLabel: string;
  bandLabel: string | null;
  matchedRule: string | null;
  costUsd: number;
  baselineUsd: number;
  baselineModel: string;
  savingsUsd: number;
  savingsPct: number;
  inputTokens: number;
  outputTokens: number;
  latencyMs: number;
  candidates: string[];
  guardrail: { action: string; categories: string; count: number } | null;
  compression: { savedTokens: number; savedPct: number; tokensBefore: number; tokensAfter: number } | null;
  fallback: { enabled: boolean; armed: string[]; fired: boolean; from: string | null } | null;
  demo: boolean;
  cacheHit?: boolean;
  similarity?: number;
  cachedFrom?: string;
  budget?: { mtdUsd: number; capUsd: number; consumedPct: number; ceiling: string; note: string } | null;
  optimization?: { enabled: boolean; mode: string; targetWords: number; outputTokens: number; baselineOutputTokens: number; savedOutputTokens: number; savedUsdEst: number } | null;
}

export interface OptimizeAbResult {
  judge: string;
  unshaped: { outputTokens: number; costUsd: number; servedBy: string; quality: number | null; answer: string };
  shaped: { outputTokens: number; costUsd: number; servedBy: string; quality: number | null; answer: string; targetWords: number };
  savedOutputTokens: number;
  savedUsd: number;
  savedPct: number;
}

// Prove output-shaping nets positive: runs the same prompt shaped vs unshaped and
// returns the MEASURED output-token/cost delta + a quality score for each, scored by
// the chosen `judgeModel` (empty = backend default, the cheapest frontier).
export async function optimizeAb(prompt: string, model: string, targetWords: number, judgeModel?: string): Promise<OptimizeAbResult> {
  const res = await fetch('/api/gateway/optimize/ab', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, model, targetWords, ...(judgeModel ? { judgeModel } : {}) }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error?.message || `A/B failed: ${res.status}`);
  return data;
}

// ---- Smart Routing decision + ON-vs-OFF (Context-routing tab) ------------
// The auditable routing decision the app surfaces, mirroring Unity AI Gateway
// Smart Routing: task-type family, language family, complexity label, rationale.
export interface RoutingDecision {
  taskType: { id: string; label: string };
  language: { id: string; label: string };
  complexityScore: number;
  complexityLabel: { id: string; label: string };
  requiredTier: string;
  requiredTierLabel: string;
  chosenTier: string;
  rationale: string;
  classifier: string;
}

export interface SmartRoutingSide {
  model: string; tier: string; costUsd: number; latencyMs: number;
  quality: number | null; inputTokens: number; outputTokens: number; answer: string;
}

export interface SmartRoutingAb {
  decision: RoutingDecision;
  judge: string;
  on: SmartRoutingSide;
  off: SmartRoutingSide;
  savedUsd: number;
  savedPct: number;
  qualityDelta: number | null;
}

// Run the SAME prompt with Smart Routing ON (router picks cheapest-sufficient) vs
// OFF (a fixed frontier flagship). Both answers judged by the same model, so cost
// AND quality deltas are measured. Two live model calls + two judge calls, so it's
// deliberately slow - show a busy state.
export async function smartRoutingAb(
  prompt: string,
  opts: { models?: string[]; frontierModel?: string; routerModel?: string; judgeModel?: string } = {},
): Promise<SmartRoutingAb> {
  const res = await fetch('/api/smartrouting/ab', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, ...opts }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error?.message || `Smart Routing A/B failed: ${res.status}`);
  return data;
}

// ---- Bring-your-own evaluation set (validate routing holds quality) -------
export interface EvalRow {
  prompt: string; error?: string;
  routed?: { model: string; tier: string; costUsd: number; quality: number | null; complexity: number };
  frontier?: { model: string; costUsd: number; quality: number | null };
  savedUsd?: number; savedPct?: number;
}
export interface EvalAggregate {
  count: number; avgRoutedQuality: number | null; avgFrontierQuality: number | null;
  qualityRetentionPct: number | null; routedCostUsd: number; frontierCostUsd: number;
  savedUsd: number; savedPct: number; judge: string; frontierBaseline: string;
}
export interface EvalResult {
  aggregate?: EvalAggregate; rows?: EvalRow[]; errors?: EvalRow[];
  mlflow?: { logged: boolean; experiment?: string; runId?: string; reason?: string };
  error?: string;
}

// Run a set of prompts through the router vs a frontier baseline, judged, aggregated.
export async function runEvalSet(prompts: string[], opts: { models?: string[]; frontierModel?: string; judgeModel?: string } = {}): Promise<EvalResult> {
  const res = await fetch('/api/eval/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompts, ...opts }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error || `Eval failed: ${res.status}`);
  return data;
}

export interface ReadinessCheck { id: string; label: string; ok: boolean; optional?: boolean; detail: string; fix: string }
export interface Discovery { liveCount: number; registryCount: number; present: string[]; missing: string[]; extra: string[]; extraCount: number }
export interface Readiness {
  ready: boolean; checks: ReadinessCheck[]; discovery: Discovery;
  warehouseId: string | null; embedEndpoint: string; dataSource: string;
}

export async function getReadiness(): Promise<Readiness> {
  const res = await fetch('/api/setup/readiness');
  if (!res.ok) throw new Error(`GET /api/setup/readiness failed: ${res.status}`);
  return res.json();
}

export interface GatewayChatResult {
  answer: string;
  finops: FinopsReceipt;
}

export interface CacheStats {
  hits: number; misses: number; hitRate: number; savedUsd: number;
  entries: number; backend: string; embedEndpoint: string; threshold: number;
}

export async function getCacheStats(): Promise<CacheStats> {
  const res = await fetch('/api/gateway/cache/stats');
  if (!res.ok) throw new Error(`GET /api/gateway/cache/stats failed: ${res.status}`);
  return res.json();
}

export async function clearCache(): Promise<CacheStats> {
  const res = await fetch('/api/gateway/cache/clear', { method: 'POST' });
  if (!res.ok) throw new Error(`POST /api/gateway/cache/clear failed: ${res.status}`);
  return res.json();
}

// Call the app's own OpenAI-compatible proxy exactly as a customer's SDK would.
// `finops` is the proxy's non-standard per-request override (candidates, policy,
// semanticCache, etc.).
export async function gatewayChat(prompt: string, model: string, finops?: Record<string, unknown>): Promise<GatewayChatResult> {
  const res = await fetch('/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, messages: [{ role: 'user', content: prompt }], max_tokens: 1024, ...(finops ? { finops } : {}) }),
  });
  const data = await res.json();
  if (!res.ok) {
    const msg = data?.error?.message || `Gateway returned ${res.status}`;
    const err = new Error(msg) as Error & { finops?: FinopsReceipt };
    err.finops = data?.x_finops;
    throw err;
  }
  return { answer: data?.choices?.[0]?.message?.content ?? '', finops: data.x_finops as FinopsReceipt };
}

export interface RouterPolicy {
  models: string[];
  bands: unknown[] | null;
  policy: unknown | null;
  routerModel?: string;
  guardrails?: { enabled: boolean; pii: boolean; mode: string; keywords: string[] };
  rateLimit?: { enabled: boolean; perMin: number };
  fallback?: { enabled: boolean; order: string[] };
}

export async function getGatewayPolicy(): Promise<RouterPolicy> {
  const res = await fetch('/api/gateway/policy');
  if (!res.ok) throw new Error(`GET /api/gateway/policy failed: ${res.status}`);
  return res.json();
}

export async function saveGatewayPolicy(policy: Partial<RouterPolicy>): Promise<{ ok: boolean; saved: boolean }> {
  const res = await fetch('/api/gateway/policy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(policy),
  });
  if (!res.ok) throw new Error(`POST /api/gateway/policy failed: ${res.status}`);
  return res.json();
}

// ---- Coding-agent cost tracker (Cost tab, real system-table data) --------
export interface CodingHarness {
  harness: string; coding: boolean; requests: number; costUsd: number;
  inTok: number; outTok: number; avgLatencyMs: number; developers: number;
}
export interface CodingDeveloper { user: string; harness: string; requests: number; costUsd: number }
export interface CodingAgents {
  source: string; windowDays?: number; reason?: string;
  totals?: { requests: number; costUsd: number; codingRequests: number; codingCostUsd: number; codingDevelopers: number; codingSharePct: number };
  byHarness?: CodingHarness[];
  byDeveloper?: CodingDeveloper[];
}

// Per-harness + per-developer coding-agent spend, classified from the gateway's
// user_agent. Never throws for the caller - returns {source:'unavailable'} on failure.
export async function getCodingAgents(days = 30): Promise<CodingAgents> {
  try {
    const res = await fetch(`/api/coding-agents?days=${days}`);
    if (!res.ok) return { source: 'unavailable' };
    return res.json();
  } catch {
    return { source: 'unavailable' };
  }
}

// ---- Reliability & fallback observability (Cost tab, real routing_information) --
export interface Reliability {
  source: string; windowDays?: number; reason?: string;
  totals?: { requests: number; attempts: number; fallbackFires: number; fallbackRatePct: number; fallbackServedOk: number; initialErrorRatePct: number; okRatePct: number };
  byAction?: { action: string; count: number }[];
  statusClass?: Record<string, number>;
  attemptHist?: { attempts: number; requests: number }[];
  topFailing?: { destination: string; failures: number }[];
}

export async function getReliability(days = 30): Promise<Reliability> {
  try {
    const res = await fetch(`/api/reliability?days=${days}`);
    if (!res.ok) return { source: 'unavailable' };
    return res.json();
  } catch {
    return { source: 'unavailable' };
  }
}

export async function getConfig(): Promise<AppConfig> {
  const res = await fetch('/api/config');
  if (!res.ok) throw new Error(`GET /api/config failed: ${res.status}`);
  const raw = await res.json();
  return {
    models: raw.models ?? [],
    policy: raw.policy,
    demoMode: !!raw.demoMode,
    judgeEnabled: !!raw.judgeEnabled,
    priceFootnote: raw.priceFootnote ?? 'Prices from the DBU rate card - see config',
  };
}
