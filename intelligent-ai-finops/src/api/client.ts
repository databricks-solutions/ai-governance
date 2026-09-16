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

// ---- Admin gateway config (Context-routing tab), persisted to Lakebase -----
// The full admin-configured state so the USER persona (question-only) inherits
// exactly what the admin set. Opaque-ish blob; the Pipeline tab owns the shape.
export interface AppAdminConfig {
  autoClassifier?: boolean;
  models?: string[];                                   // 3 category picks (manual mode)
  criteria?: Record<string, string>;                   // tier key -> comma-separated keywords
  enabled?: string[];                                  // governance feature ids ticked on
  options?: { cache?: boolean; optimize?: boolean; optimizeWords?: number; smartAb?: boolean; outputAb?: boolean };
  guardrails?: { pii: boolean; mode: 'block' | 'mask'; keywords: string };
  rateLimit?: { perMin: number };
  budget?: { on: boolean; capUsd: number | null; consumedPct: number; downgradeAt: number; openOnlyAt: number; downgradeAction: string; openOnlyAction: string };
  access?: { group: string; tiers: Record<string, string[]> };
}

export async function getAppConfig(): Promise<AppAdminConfig> {
  try {
    const res = await fetch('/api/gateway/appconfig');
    if (!res.ok) return {};
    return res.json();
  } catch {
    return {};
  }
}

export async function saveAppConfig(cfg: AppAdminConfig): Promise<{ ok: boolean; saved: boolean }> {
  try {
    const res = await fetch('/api/gateway/appconfig', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cfg),
    });
    return res.json();
  } catch {
    return { ok: false, saved: false };
  }
}
