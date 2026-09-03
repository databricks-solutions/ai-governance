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
