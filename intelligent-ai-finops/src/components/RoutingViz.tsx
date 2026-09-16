import { useEffect, useState } from 'react';
import type { ModelDef } from '../api/types';
import { formatHeadline } from '../lib/format';

// Shared routing-economics visuals for the Compare + Context-routing tabs: a
// bold, animated step-by-step routing pipeline (query → complexity → policy →
// model → response) that lights up live, plus the 12-month ROI projection.

// Compact currency ($1.2M / $940K) so large projections never overflow or get
// truncated inside the chart's fixed viewBox or the narrow stat tiles. Delegates
// to the shared headline formatter so the compaction rule lives in one place.
export const compact = (n: number) => formatHeadline(n);

const IN_TOK = 800, OUT_TOK = 400;
export const perQuery = (m: ModelDef) => (IN_TOK / 1e6) * m.price_in_per_1m + (OUT_TOK / 1e6) * m.price_out_per_1m;

export interface Roi {
  monthly: { frontier: number; routed: number };
  savedYr: number;
}

export function computeRoi(laneModels: (ModelDef | undefined)[], volume: number): Roi | null {
  const ms = laneModels.filter(Boolean) as ModelDef[];
  if (!ms.length) return null;
  const sorted = [...ms].sort((a, b) => perQuery(a) - perQuery(b));
  const shares = sorted.length >= 3 ? [0.6, 0.3, 0.1] : sorted.length === 2 ? [0.7, 0.3] : [1];
  const routedPer = shares.reduce((s, w, i) => s + w * perQuery(sorted[i]), 0);
  const frontierPer = perQuery(sorted[sorted.length - 1]);
  const monthly = { frontier: frontierPer * volume, routed: routedPer * volume };
  return { monthly, savedYr: (monthly.frontier - monthly.routed) * 12 };
}

// ---- Routing steps (the previous app's step-by-step live routing) --------
export interface RStep { key: string; label: string; detail: string; glyph: string; accent: string; landed?: boolean }

export function RoutingSteps({ steps, running = false }: { steps: RStep[]; running?: boolean }) {
  const [active, setActive] = useState(-1);
  useEffect(() => {
    if (!running || !steps.length) { setActive(-1); return; }
    let i = 0; setActive(0);
    const id = setInterval(() => { i = (i + 1) % steps.length; setActive(i); }, 480);
    return () => clearInterval(id);
  }, [running, steps.length]);

  return (
    <div className="flex flex-wrap items-stretch justify-center gap-y-4">
      {steps.map((s, i) => {
        const lit = running ? i <= active : true;
        const isActive = running && i === active;
        const glow = !!s.landed && !running;
        return (
          <div key={s.key} className="flex items-center">
            <div
              style={{ animationDelay: `${i * 70}ms`, background: `${s.accent}14`, boxShadow: glow ? `0 0 0 1.6px ${s.accent}, 0 10px 28px ${s.accent}55` : `inset 0 0 0 1px ${s.accent}33` }}
              className={`relative flex w-[136px] animate-[fadeUp_.45s_ease_both] flex-col items-center rounded-2xl px-3 py-4 text-center transition-all duration-300 max-[520px]:w-[108px] ${lit ? 'opacity-100' : 'opacity-35'} ${isActive ? 'scale-[1.06]' : ''}`}
            >
              {isActive && <span className="absolute inset-0 animate-pulse rounded-2xl" style={{ boxShadow: `0 0 0 1.6px ${s.accent}` }} />}
              <div className="grid h-10 w-10 place-items-center rounded-full text-[16px] font-bold" style={{ background: `${s.accent}2b`, color: s.accent }}>{s.glyph}</div>
              <div className="mt-2 text-[12px] font-bold leading-tight text-white">{s.label}</div>
              <div className="num mt-1 text-[10.5px] font-semibold leading-tight" style={{ color: s.accent }}>{s.detail}</div>
            </div>
            {i < steps.length - 1 && (
              <div className="relative mx-1.5 hidden h-[3px] w-[30px] items-center self-center sm:flex">
                <div className="h-full w-full rounded-full" style={{ background: `${s.accent}33` }} />
                <span className="absolute left-0 h-[6px] w-[6px] rounded-full" style={{ background: steps[i + 1]?.accent ?? s.accent, animation: 'flowX 1.1s linear infinite' }} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---- ROI chart: cumulative cost over 12 months on a LOG y-axis ----------
// A linear axis sized to the frontier line squashes the best-value line onto $0
// (routed cost is ~30-100× smaller). A log axis makes BOTH lines visible; the
// (near-constant) vertical gap between them IS the "N× cheaper" multiple.
export function RoiChart({ roi, frontierLabel = 'FRONTIER ONLY', routedLabel = 'INTELLIGENT ROUTING', frontierColor = 'var(--lava)', routedColor = '#6BB0E8', periods = 12, periodNoun = 'months', totalSuffix = 'yr' }: { roi: Roi | null; frontierLabel?: string; routedLabel?: string; frontierColor?: string; routedColor?: string; periods?: number; periodNoun?: string; totalSuffix?: string }) {
  const W = 380, H = 140, PADL = 48, PADR = 16, PADT = 12, PADB = 30;
  // Unique gradient ids per colour pair so two charts with different palettes on
  // the same page (Compare = red/blue, Cost = blue/green) don't share a fill.
  const uid = `${frontierColor}-${routedColor}`.replace(/[^a-zA-Z0-9]/g, '');
  const frGradId = `frGrad-${uid}`, rtGradId = `rtGrad-${uid}`;
  if (!roi) return <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" />;
  // roi.monthly holds the PER-PERIOD cost (a month for the Cost tab, a day for the
  // Compare tab). Cumulative cost at the END of period i. Period 0 (=$0) is undefined
  // on a log axis, so we plot 1..periods.
  const N = Math.max(2, periods);
  const frAt = (i: number) => roi.monthly.frontier * i;
  const rtAt = (i: number) => roi.monthly.routed * i;
  const frN = frAt(N), rtN = rtAt(N);
  const pts = Array.from({ length: N }, (_, i) => i + 1); // 1..N
  // Log domain: nice powers of ten bounding routed-period-1 (smallest) and
  // frontier-period-N (largest).
  const lo = Math.max(rtAt(1), 1e-9);
  const hi = Math.max(frN, lo * 10);
  const lBot = Math.floor(Math.log10(lo));
  const lTop = Math.ceil(Math.log10(hi));
  const yLo = Math.pow(10, lBot);
  const x = (i: number) => PADL + ((i - 1) / (N - 1)) * (W - PADL - PADR);
  const y = (v: number) => H - PADB - ((Math.log10(Math.max(v, yLo)) - lBot) / (lTop - lBot)) * (H - PADT - PADB);
  const line = (f: (i: number) => number) => pts.map((i, k) => `${k === 0 ? 'M' : 'L'}${x(i)},${y(f(i))}`).join(' ');
  const areaTo = (f: (i: number) => number) => `${line(f)} L${x(N)},${y(yLo)} L${x(1)},${y(yLo)} Z`;
  const ticks: number[] = [];
  for (let p = lBot; p <= lTop; p++) ticks.push(Math.pow(10, p));
  // The savings multiple = frontier / best-value (constant across time); the gap
  // between the two lines visualises exactly this.
  const cheaperX = rtN > 0 ? frN / rtN : null;
  const cheaperLabel = cheaperX == null ? null : cheaperX >= 10 ? Math.round(cheaperX) : Math.round(cheaperX * 10) / 10;
  // Evenly spaced x-axis ticks (5) across 1..N.
  const xTicks = Array.from(new Set(Array.from({ length: 5 }, (_, k) => Math.round(1 + (k * (N - 1)) / 4))));
  const total = `/${totalSuffix}`;
  // When the frontier model IS the best value (nothing cheaper cleared the bar),
  // the two lines coincide - draw a SINGLE line instead of two overlapping ones.
  const single = Math.abs(frN - rtN) < Math.max(frN, 1) * 0.005;
  return (
    <div>
      {/* Legend above the plot: one row when the frontier is the best value, two otherwise. */}
      <div className="mb-2 flex justify-end">
        {single ? (
          <div className="flex items-center gap-2">
            <span className="h-[3px] w-4 shrink-0 rounded-full" style={{ background: frontierColor }} />
            <span className="text-[10px] font-bold uppercase tracking-[.06em]" style={{ color: frontierColor }}>{frontierLabel} = best value</span>
            <span className="num shrink-0 text-[13px] font-bold" style={{ color: frontierColor }}>{compact(frN)}{total}</span>
          </div>
        ) : (
          <div className="flex flex-col items-end gap-1">
            <div className="flex items-center gap-2">
              <span className="h-[3px] w-4 shrink-0 rounded-full" style={{ background: frontierColor }} />
              <span className="text-[10px] font-bold uppercase tracking-[.06em]" style={{ color: frontierColor }}>{frontierLabel}</span>
              <span className="num shrink-0 text-[13px] font-bold" style={{ color: frontierColor }}>{compact(frN)}{total}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-[3px] w-4 shrink-0 rounded-full" style={{ background: routedColor }} />
              <span className="text-[10px] font-bold uppercase tracking-[.06em]" style={{ color: routedColor }}>{routedLabel}</span>
              <span className="num shrink-0 text-[13px] font-bold" style={{ color: routedColor }}>{compact(rtN)}{total}</span>
            </div>
          </div>
        )}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={`ROI projection over ${N} ${periodNoun}, log scale`}>
        <defs>
          <linearGradient id={frGradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={frontierColor} stopOpacity="0.26" />
            <stop offset="100%" stopColor={frontierColor} stopOpacity="0.03" />
          </linearGradient>
          <linearGradient id={rtGradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={routedColor} stopOpacity="0.24" />
            <stop offset="100%" stopColor={routedColor} stopOpacity="0.03" />
          </linearGradient>
        </defs>
        {/* log gridlines + power-of-ten labels */}
        {ticks.map((v, i) => (
          <g key={i}>
            <line x1={PADL} y1={y(v)} x2={W - PADR} y2={y(v)} stroke="rgba(255,255,255,0.08)" />
            <text x={PADL - 6} y={y(v) + 3} textAnchor="end" fontSize={7} fill="rgba(255,255,255,0.4)" className="num">{compact(v)}</text>
          </g>
        ))}
        {/* fills + lines. When single (frontier == best value) draw ONE lava line. */}
        <path d={areaTo(frAt)} fill={`url(#${frGradId})`} />
        {!single && <path d={areaTo(rtAt)} fill={`url(#${rtGradId})`} />}
        <path key={`f${Math.round(frN)}`} d={line(frAt)} fill="none" stroke={frontierColor} strokeWidth={2.2} className="[stroke-dasharray:600] [stroke-dashoffset:600] motion-safe:animate-[draw_1s_ease_forwards]" />
        {!single && <path key={`r${Math.round(rtN)}`} d={line(rtAt)} fill="none" stroke={routedColor} strokeWidth={2.2} className="[stroke-dasharray:600] [stroke-dashoffset:600] motion-safe:animate-[draw_1s_ease_.15s_forwards]" />}
        <circle cx={x(N)} cy={y(frN)} r={3} fill={frontierColor} />
        {!single && <circle cx={x(N)} cy={y(rtN)} r={3} fill={routedColor} />}
        {/* "N× cheaper" placed INSIDE the plot, centred in the gap between the two
            lines. Centred (not right-aligned) so the chip can never clip the plot edge
            the way the old pill did, with a small background chip and a compact 9.5px
            font (smaller than the previous large label) so it stays legible over the fill. */}
        {!single && cheaperLabel != null && cheaperLabel >= 1.2 && (() => {
          const li = (N + 1) / 2;              // centre period
          const lx = x(li);                    // = plot centre x, always well inside
          const lyF = y(frAt(li)), lyR = y(rtAt(li));
          const ly = (lyF + lyR) / 2;          // midway between frontier + routed lines
          const txt = `${cheaperLabel}× cheaper`;
          const bw = txt.length * 5.4 + 12;    // chip width sized to the text (no truncation)
          return (
            <g>
              <line x1={lx} y1={lyF + 2} x2={lx} y2={lyR - 2} stroke="rgba(255,255,255,0.3)" strokeWidth={1} strokeDasharray="2 2" />
              <rect x={lx - bw / 2} y={ly - 8} width={bw} height={16} rx={5} fill="rgba(9,12,16,0.78)" stroke="#93D3AB" strokeOpacity={0.55} strokeWidth={0.8} />
              <text x={lx} y={ly + 3.3} textAnchor="middle" fontSize={9.5} fontWeight={800} fill="#93D3AB" className="num">{txt}</text>
            </g>
          );
        })()}
        {xTicks.map((i) => <text key={i} x={x(i)} y={H - PADB + 13} textAnchor="middle" fontSize={8} fill="rgba(255,255,255,0.4)" className="num">{i}</text>)}
        {/* x-axis title */}
        <text x={(PADL + (W - PADR)) / 2} y={H - 5} textAnchor="middle" fontSize={8} fontWeight={700} fill="rgba(255,255,255,0.5)" style={{ letterSpacing: '.08em' }}>{periodNoun.toUpperCase()}</text>
      </svg>
      <div className="mt-1 text-center text-[10px] text-white/40">{single ? `cumulative cost over ${N} ${periodNoun} · the frontier model was the best value here — nothing cheaper cleared the bar` : `cumulative cost over ${N} ${periodNoun} · log scale — the gap between the lines is the savings multiple`}</div>
    </div>
  );
}
