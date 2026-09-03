import { describe, it, expect } from 'vitest';
import { buildSampleRuns, SAMPLE_SPECS } from './sampleSession';
import type { ModelDef } from '../api/types';

// A minimal registry covering every short used in the fixture, with the real
// rate-card DBU → $/1M conversion (× 0.07) so the cost recompute matches the app.
const D2U = 0.07;
const RAW: Array<[string, ModelDef['tier'], number, number]> = [
  ['gpt-oss-20b', 'small-oss', 1.0, 4.286],
  ['llama-3.1-8b', 'small-oss', 2.143, 6.429],
  ['gemma-3-12b', 'small-oss', 2.143, 7.143],
  ['gpt-oss-120b', 'large-oss', 2.143, 8.571],
  ['llama-4-maverick', 'large-oss', 7.143, 21.429],
  ['qwen-3.5-122b', 'large-oss', 3.143, 31.429],
  ['qwen3-next-80b', 'large-oss', 2.143, 17.143],
  ['llama-3.3-70b', 'large-oss', 7.143, 21.429],
  ['claude-sonnet-5', 'frontier', 28.571, 142.857],
  ['gpt-5', 'frontier', 17.857, 142.857],
];
const MODELS: ModelDef[] = RAW.map(([short, tier, din, dout]) => ({
  id: `databricks-${short}`, short, tier,
  price_in_per_1m: din * D2U, price_out_per_1m: dout * D2U,
}));

const cost = (m: ModelDef, i: number, o: number) => (i / 1e6) * m.price_in_per_1m + (o / 1e6) * m.price_out_per_1m;

describe('sample session fixture (P0-2)', () => {
  const runs = buildSampleRuns(MODELS);

  it('produces ~40 seeded rows, all tagged sample', () => {
    expect(runs.length).toBe(SAMPLE_SPECS.length);
    expect(runs.length).toBeGreaterThanOrEqual(38);
    expect(runs.every((r) => r.sample === true)).toBe(true);
  });

  it('every row carries a team tag (no unattributed bucket)', () => {
    expect(runs.every((r) => !!r.team)).toBe(true);
  });

  it('tier mix is within ±5pp of 55 / 30 / 15', () => {
    const n = runs.length;
    const share = (t: string) => (runs.filter((r) => r.tier === t).length / n) * 100;
    expect(Math.abs(share('small-oss') - 55)).toBeLessThanOrEqual(5);
    expect(Math.abs(share('large-oss') - 30)).toBeLessThanOrEqual(5);
    expect(Math.abs(share('frontier') - 15)).toBeLessThanOrEqual(5);
  });

  it('contains ≥ 3 frontier requests', () => {
    expect(runs.filter((r) => r.tier === 'frontier').length).toBeGreaterThanOrEqual(3);
  });

  it('cost is recomputed from tokens (no drift from the rate card)', () => {
    for (const r of runs) {
      const m = MODELS.find((x) => x.short === r.modelShort)!;
      expect(r.costUsd).toBeCloseTo(cost(m, r.inputTokens, r.outputTokens), 10);
    }
  });

  it('total spend equals the sum of per-request costs', () => {
    const total = runs.reduce((s, r) => s + r.costUsd, 0);
    const sum = runs.reduce((s, r) => s + r.costUsd, 0);
    expect(total).toBeCloseTo(sum, 10);
    expect(total).toBeGreaterThan(0);
  });

  it('baseline (frontier-only) ≥ actual cost for every row → savings never negative', () => {
    for (const r of runs) expect(r.baselineUsd).toBeGreaterThanOrEqual(r.costUsd - 1e-12);
  });
});
