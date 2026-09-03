// Number formatting policy (P0-3). ONE formatter per role; components import
// these and never call `toFixed` inline, so precision is consistent everywhere
// and a currency value is never rendered as "$0.0000".
//
// All `toFixed` in the app lives HERE, in the lib layer - not in components.

const stripZeros = (s: string): string => (s.includes('.') ? s.replace(/0+$/, '').replace(/\.$/, '') : s);

// Format a sub-$1 amount keeping ~2 significant figures so a tiny per-query cost
// (e.g. $0.000017) never collapses to "$0" or "$0.0000". Trailing zeros trimmed.
const smallAmount = (a: number): string => {
  if (a >= 0.01) return stripZeros(a.toFixed(4)); // 0.0087, 0.042
  const digits = Math.min(8, Math.ceil(-Math.log10(a)) + 1);
  return stripZeros(a.toFixed(digits)); // 0.00035, 0.000017
};

// Hero and section-level totals: $154K, $2.1M, $26.1K, $2,175, $0.
// Two-significant compaction above $10K; whole dollars in the thousands; a
// sub-dollar amount keeps enough precision to never collapse to "$0".
export function formatHeadline(n: number): string {
  if (!isFinite(n)) return '$0';
  const sign = n < 0 ? '-' : '';
  const a = Math.abs(n);
  if (a === 0) return '$0';
  if (a < 1) return `${sign}$${smallAmount(a)}`; // $0.0044 / $0.000017 - never "$0"
  if (a < 10_000) return `${sign}$${Math.round(a).toLocaleString('en-US')}`; // $840, $2,175, $8,420
  if (a < 1_000_000) return `${sign}$${stripZeros((a / 1000).toFixed(a / 1000 < 100 ? 1 : 0))}K`; // $26.1K, $154K
  if (a < 1_000_000_000) return `${sign}$${stripZeros((a / 1e6).toFixed(2))}M`; // $1.84M, $2.1M
  return `${sign}$${stripZeros((a / 1e9).toFixed(2))}B`;
}

// Table cells and tiles: $2,175, $71.51, $6.45. Sub-dollar keeps precision.
export function formatMoney(n: number): string {
  if (!isFinite(n)) return '$0';
  const sign = n < 0 ? '-' : '';
  const a = Math.abs(n);
  if (a === 0) return '$0';
  if (a < 0.01) return `${sign}$${smallAmount(a)}`; // $0.0044 / $0.000017 - keep sig figs, never "$0"
  if (a < 1000) return `${sign}$${a.toFixed(2)}`; // $0.50, $71.51, $6.45
  return `${sign}$${Math.round(a).toLocaleString('en-US')}`; // $2,175
}

// Per-query cost - the only place sub-cent decimals are the point. Callers add
// the "/ query" suffix. Keeps ~2 significant figures so a $0.000017/query model
// never renders as "$0"; $0.0087 still renders exactly.
export function formatPerQuery(n: number): string {
  if (!isFinite(n) || n === 0) return '$0';
  const sign = n < 0 ? '-' : '';
  return `${sign}$${smallAmount(Math.abs(n))}`;
}

// Rate card entries: $2.00 / 1M.
export function formatRate(n: number): string {
  return `$${n.toFixed(2)} / 1M`;
}

export function formatPercent(n: number): string {
  if (!isFinite(n)) return '0%';
  return `${Math.round(n)}%`;
}

// Percent with one decimal: 0.0%, 0.2%, 12.5% (error rates, small shares).
export function formatPercent1(n: number): string {
  if (!isFinite(n)) return '0%';
  return `${stripZeros(n.toFixed(1))}%`;
}

// A count/rate rendered whole when large, one decimal when small (e.g. req/min).
export function formatRate1(n: number): string {
  if (!isFinite(n)) return '0';
  return n < 10 ? stripZeros(n.toFixed(1)) : Math.round(n).toLocaleString('en-US');
}

// Latency: 820ms, 1.4s.
export function formatLatency(ms: number): string {
  if (!isFinite(ms)) return '-';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${stripZeros((ms / 1000).toFixed(1))}s`;
}

// Token counts (not dollars): 1,240, 18.2K, 1.2M.
export function formatTokens(n: number): string {
  const a = Math.abs(n);
  if (a < 10_000) return Math.round(n).toLocaleString('en-US');
  if (a < 1_000_000) return `${stripZeros((a / 1000).toFixed(1))}K`;
  return `${stripZeros((a / 1e6).toFixed(1))}M`;
}

// Judge / quality score, one decimal (e.g. 8.7).
export function formatScore(n: number): string {
  return n.toFixed(1);
}

// A bare 0-1 similarity or ratio, two decimals (config inspector).
export function formatDecimal2(n: number): string {
  return n.toFixed(2);
}
