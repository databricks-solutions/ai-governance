import type { ModelDef, Tier } from '../api/types';
import type { RunRecord } from '../store/session';

// P0-2 - a seeded demo session so the app is never empty on arrival.
//
// We store only what a real request would produce (model, tokens, latency,
// judge score, team, whether the judge escalated to the frontier). Dollar costs
// are COMPUTED from the live rate card at seed time via the same arithmetic the
// real pipeline uses - never hardcoded - so the totals can't drift from the
// pricing shown elsewhere.

export interface SampleSpec {
  modelShort: string;
  tier: Tier;
  inputTokens: number;
  outputTokens: number;
  latencyMs: number;
  judgeScore: number;
  team: string;
  escalated: boolean; // cheaper lanes failed the bar → routed to the frontier
  promptSnippet: string;
}

// Teams the fixture attributes requests across (Support / Finance / Engineering
// / Analytics) - forward-compatible with per-team attribution (P1-3).
//
// ~40 requests, tier mix ≈ 55% small / 30% large / 15% frontier, with several
// genuine escalations to the frontier. Model shorts match config/models.yaml.
export const SAMPLE_SPECS: SampleSpec[] = [
  // ---- small OSS (22 ≈ 55%) ------------------------------------------------
  { modelShort: 'gpt-oss-20b', tier: 'small-oss', inputTokens: 420, outputTokens: 180, latencyMs: 540, judgeScore: 8.4, team: 'Support', escalated: false, promptSnippet: 'Summarize this ticket thread in two sentences.' },
  { modelShort: 'gpt-oss-20b', tier: 'small-oss', inputTokens: 380, outputTokens: 150, latencyMs: 480, judgeScore: 8.6, team: 'Support', escalated: false, promptSnippet: 'Classify this support email by intent.' },
  { modelShort: 'llama-3.1-8b', tier: 'small-oss', inputTokens: 510, outputTokens: 220, latencyMs: 610, judgeScore: 8.1, team: 'Support', escalated: false, promptSnippet: 'Draft a one-line acknowledgement reply.' },
  { modelShort: 'gemma-3-12b', tier: 'small-oss', inputTokens: 460, outputTokens: 200, latencyMs: 720, judgeScore: 8.3, team: 'Support', escalated: false, promptSnippet: 'Extract the product name from this message.' },
  { modelShort: 'gpt-oss-20b', tier: 'small-oss', inputTokens: 300, outputTokens: 120, latencyMs: 430, judgeScore: 8.7, team: 'Support', escalated: false, promptSnippet: 'Is this review positive or negative?' },
  { modelShort: 'gpt-oss-20b', tier: 'small-oss', inputTokens: 640, outputTokens: 260, latencyMs: 690, judgeScore: 8.2, team: 'Analytics', escalated: false, promptSnippet: 'Turn this metric definition into a sentence.' },
  { modelShort: 'llama-3.1-8b', tier: 'small-oss', inputTokens: 350, outputTokens: 140, latencyMs: 500, judgeScore: 8.5, team: 'Analytics', escalated: false, promptSnippet: 'Rephrase this dashboard title.' },
  { modelShort: 'gpt-oss-20b', tier: 'small-oss', inputTokens: 410, outputTokens: 170, latencyMs: 520, judgeScore: 8.4, team: 'Support', escalated: false, promptSnippet: 'Summarize the customer sentiment here.' },
  { modelShort: 'gemma-3-12b', tier: 'small-oss', inputTokens: 480, outputTokens: 210, latencyMs: 760, judgeScore: 8.0, team: 'Engineering', escalated: false, promptSnippet: 'Write a commit message for this diff.' },
  { modelShort: 'gpt-oss-20b', tier: 'small-oss', inputTokens: 330, outputTokens: 130, latencyMs: 450, judgeScore: 8.6, team: 'Analytics', escalated: false, promptSnippet: 'Give a TL;DR of this report section.' },
  { modelShort: 'llama-3.1-8b', tier: 'small-oss', inputTokens: 560, outputTokens: 240, latencyMs: 640, judgeScore: 8.2, team: 'Support', escalated: false, promptSnippet: 'Tag this conversation with a topic.' },
  { modelShort: 'gpt-oss-20b', tier: 'small-oss', inputTokens: 390, outputTokens: 160, latencyMs: 490, judgeScore: 8.5, team: 'Finance', escalated: false, promptSnippet: 'Summarize this expense note.' },
  { modelShort: 'gpt-oss-20b', tier: 'small-oss', inputTokens: 300, outputTokens: 110, latencyMs: 420, judgeScore: 8.8, team: 'Support', escalated: false, promptSnippet: 'Detect the language of this message.' },
  { modelShort: 'gemma-3-12b', tier: 'small-oss', inputTokens: 520, outputTokens: 230, latencyMs: 780, judgeScore: 8.1, team: 'Engineering', escalated: false, promptSnippet: 'Explain this log line in plain English.' },
  { modelShort: 'llama-3.1-8b', tier: 'small-oss', inputTokens: 440, outputTokens: 190, latencyMs: 580, judgeScore: 8.3, team: 'Analytics', escalated: false, promptSnippet: 'Name this cohort based on its traits.' },
  { modelShort: 'gpt-oss-20b', tier: 'small-oss', inputTokens: 360, outputTokens: 150, latencyMs: 470, judgeScore: 8.6, team: 'Support', escalated: false, promptSnippet: 'Shorten this canned response.' },
  { modelShort: 'gpt-oss-20b', tier: 'small-oss', inputTokens: 480, outputTokens: 200, latencyMs: 560, judgeScore: 8.4, team: 'Finance', escalated: false, promptSnippet: 'Categorize this transaction.' },
  { modelShort: 'gemma-3-12b', tier: 'small-oss', inputTokens: 410, outputTokens: 170, latencyMs: 700, judgeScore: 8.2, team: 'Support', escalated: false, promptSnippet: 'Summarize the resolution steps.' },
  { modelShort: 'llama-3.1-8b', tier: 'small-oss', inputTokens: 520, outputTokens: 210, latencyMs: 620, judgeScore: 8.3, team: 'Analytics', escalated: false, promptSnippet: 'Describe this trend in one line.' },
  { modelShort: 'gpt-oss-20b', tier: 'small-oss', inputTokens: 340, outputTokens: 140, latencyMs: 460, judgeScore: 8.7, team: 'Engineering', escalated: false, promptSnippet: 'Suggest a variable name for this value.' },
  { modelShort: 'gpt-oss-20b', tier: 'small-oss', inputTokens: 400, outputTokens: 165, latencyMs: 500, judgeScore: 8.5, team: 'Support', escalated: false, promptSnippet: 'Summarize this week’s FAQ hits.' },
  { modelShort: 'gemma-3-12b', tier: 'small-oss', inputTokens: 450, outputTokens: 185, latencyMs: 740, judgeScore: 8.1, team: 'Finance', escalated: false, promptSnippet: 'Normalize this vendor name.' },

  // ---- large OSS (12 ≈ 30%) ------------------------------------------------
  { modelShort: 'gpt-oss-120b', tier: 'large-oss', inputTokens: 820, outputTokens: 420, latencyMs: 1420, judgeScore: 8.9, team: 'Finance', escalated: false, promptSnippet: 'Reconcile these two expense reports and flag differences.' },
  { modelShort: 'llama-4-maverick', tier: 'large-oss', inputTokens: 760, outputTokens: 390, latencyMs: 1680, judgeScore: 8.7, team: 'Engineering', escalated: false, promptSnippet: 'Review this function for edge-case bugs.' },
  { modelShort: 'gpt-oss-120b', tier: 'large-oss', inputTokens: 900, outputTokens: 460, latencyMs: 1520, judgeScore: 8.8, team: 'Analytics', escalated: false, promptSnippet: 'Explain what drove the WoW revenue change.' },
  { modelShort: 'qwen-3.5-122b', tier: 'large-oss', inputTokens: 680, outputTokens: 350, latencyMs: 1600, judgeScore: 8.6, team: 'Finance', escalated: false, promptSnippet: 'Draft variance commentary for this P&L.' },
  { modelShort: 'gpt-oss-120b', tier: 'large-oss', inputTokens: 840, outputTokens: 410, latencyMs: 1480, judgeScore: 8.9, team: 'Engineering', escalated: false, promptSnippet: 'Summarize this incident and likely cause.' },
  { modelShort: 'llama-4-maverick', tier: 'large-oss', inputTokens: 720, outputTokens: 370, latencyMs: 1720, judgeScore: 8.5, team: 'Support', escalated: false, promptSnippet: 'Write a detailed troubleshooting guide.' },
  { modelShort: 'gpt-oss-120b', tier: 'large-oss', inputTokens: 880, outputTokens: 440, latencyMs: 1540, judgeScore: 8.8, team: 'Analytics', escalated: false, promptSnippet: 'Interpret this cohort retention curve.' },
  { modelShort: 'qwen3-next-80b', tier: 'large-oss', inputTokens: 700, outputTokens: 360, latencyMs: 1580, judgeScore: 8.6, team: 'Engineering', escalated: false, promptSnippet: 'Propose a schema for this dataset.' },
  { modelShort: 'gpt-oss-120b', tier: 'large-oss', inputTokens: 820, outputTokens: 400, latencyMs: 1500, judgeScore: 8.7, team: 'Finance', escalated: false, promptSnippet: 'Explain this budget deviation to a non-expert.' },
  { modelShort: 'llama-4-maverick', tier: 'large-oss', inputTokens: 780, outputTokens: 380, latencyMs: 1660, judgeScore: 8.6, team: 'Support', escalated: false, promptSnippet: 'Summarize the top 5 escalated tickets.' },
  { modelShort: 'gpt-oss-120b', tier: 'large-oss', inputTokens: 900, outputTokens: 450, latencyMs: 1560, judgeScore: 8.9, team: 'Analytics', escalated: false, promptSnippet: 'Describe the anomaly in this time series.' },
  { modelShort: 'llama-3.3-70b', tier: 'large-oss', inputTokens: 740, outputTokens: 370, latencyMs: 1620, judgeScore: 8.5, team: 'Engineering', escalated: false, promptSnippet: 'Refactor suggestions for this module.' },

  // ---- frontier (6 ≈ 15%) - includes escalations where cheaper lanes failed -
  { modelShort: 'claude-sonnet-5', tier: 'frontier', inputTokens: 1180, outputTokens: 760, latencyMs: 3200, judgeScore: 9.4, team: 'Finance', escalated: true, promptSnippet: 'Build a full DCF valuation with WACC and downside scenarios.' },
  { modelShort: 'claude-sonnet-5', tier: 'frontier', inputTokens: 1240, outputTokens: 820, latencyMs: 3600, judgeScore: 9.3, team: 'Engineering', escalated: true, promptSnippet: 'Design a zero-downtime 2TB Postgres shard migration.' },
  { modelShort: 'claude-sonnet-5', tier: 'frontier', inputTokens: 1120, outputTokens: 700, latencyMs: 3100, judgeScore: 9.2, team: 'Engineering', escalated: true, promptSnippet: 'Reconcile three conflicting incident timelines.' },
  { modelShort: 'gpt-5', tier: 'frontier', inputTokens: 1060, outputTokens: 640, latencyMs: 2900, judgeScore: 9.1, team: 'Finance', escalated: false, promptSnippet: 'Draft a 5-year capital-allocation strategy.' },
  { modelShort: 'claude-sonnet-5', tier: 'frontier', inputTokens: 1200, outputTokens: 780, latencyMs: 3400, judgeScore: 9.3, team: 'Analytics', escalated: true, promptSnippet: 'Explain the causal drivers behind the churn spike.' },
  { modelShort: 'gpt-5', tier: 'frontier', inputTokens: 980, outputTokens: 600, latencyMs: 2700, judgeScore: 9.0, team: 'Finance', escalated: false, promptSnippet: 'Model the accretion/dilution of this acquisition.' },
];

// The cheapest frontier model is the "what if every request went to a frontier
// model" reference used to price the savings baseline.
function cheapestFrontier(models: ModelDef[]): ModelDef | undefined {
  return [...models.filter((m) => m.tier === 'frontier')].sort((a, b) => a.price_out_per_1m - b.price_out_per_1m)[0];
}

function cost(m: ModelDef | undefined, inTok: number, outTok: number): number {
  if (!m) return 0;
  return (inTok / 1e6) * m.price_in_per_1m + (outTok / 1e6) * m.price_out_per_1m;
}

// Build the seeded runs, computing each cost from the live rate card. Timestamps
// are spread over the last ~2 hours, newest first (matching a real session).
export function buildSampleRuns(models: ModelDef[]): RunRecord[] {
  const byShort = new Map(models.map((m) => [m.short, m]));
  const frontier = cheapestFrontier(models);
  const now = Date.now();
  const n = SAMPLE_SPECS.length;
  return SAMPLE_SPECS.map((s, i) => {
    const m = byShort.get(s.modelShort);
    return {
      id: `sample-${i + 1}`,
      ts: now - (n - i) * 90_000, // ~90s apart, oldest first → newest last
      source: 'compare' as const,
      modelShort: s.modelShort,
      tier: s.tier,
      costUsd: cost(m, s.inputTokens, s.outputTokens),
      baselineUsd: cost(frontier, s.inputTokens, s.outputTokens), // frontier-only counterfactual
      inputTokens: s.inputTokens,
      outputTokens: s.outputTokens,
      latencyMs: s.latencyMs,
      optimized: false,
      promptSnippet: s.promptSnippet,
      sample: true,
      team: s.team,
    };
  });
}
