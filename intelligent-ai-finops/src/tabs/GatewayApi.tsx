import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useConfig } from '../api/useConfig';
import { useSession } from '../store/session';
import { gatewayChat, getCacheStats, getReadiness, optimizeAb, runEvalSet, type FinopsReceipt, type CacheStats, type Readiness, type OptimizeAbResult, type EvalResult } from '../api/client';
import type { Tier } from '../api/types';
import { formatMoney, formatPercent1, formatLatency, formatTokens } from '../lib/format';

// Tab 3 - the REAL inference proxy, in the app's dark panel style (matching the
// other tabs). The app routes each request to the cheapest sufficient model,
// guardrailed, rate-limited, compressed, cached, and served with a fallback chain.
// Fire a real request and read the routing receipt, prove output-shaping savings
// with an A/B, run your own eval set, and check deploy readiness.

// ---- Dark-theme tokens (shared look with Cost / Context-routing tabs) --------
const SECTION = 'font-display text-[13px] font-bold uppercase tracking-[.15em] text-[#7FB6F2]';
const EB = 'font-body text-[10px] font-semibold uppercase tracking-[.14em] text-white/45';
const PANEL = 'relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[22px] text-white shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4';
const INPUT_DARK = 'rounded-xl bg-white/[0.06] px-4 py-2.5 font-body text-[13.5px] text-white outline-none ring-1 ring-white/10 focus:ring-white/25 placeholder:text-white/35';

// A dark panel wrapper (the "box" the other tabs use). `glow` paints a soft
// coloured aura in a corner like the sibling tabs.
function Panel({ children, className = '', delay, glow }: { children: ReactNode; className?: string; delay?: string; glow?: string }) {
  return (
    <section className={`${PANEL} ${className}`} style={delay ? { animationDelay: delay } : undefined}>
      {glow && <div className="pointer-events-none absolute -right-28 -top-24 h-96 w-96 rounded-full opacity-[.09] blur-3xl" style={{ background: glow }} />}
      <div className="relative">{children}</div>
    </section>
  );
}

// Dark chip / pill. Variants map the old light PillVariant onto dark tints.
type ChipVariant = 'neutral' | 'accent' | 'tier-small' | 'tier-large' | 'tier-frontier';
const CHIP: Record<ChipVariant, string> = {
  neutral: 'bg-white/10 text-white/70 ring-white/10',
  accent: 'bg-lava/15 text-[#FF9E7E] ring-lava/30',
  'tier-small': 'bg-moss/15 text-[#93D3AB] ring-moss/30',
  'tier-large': 'bg-[#E3B876]/15 text-[#E3B876] ring-[#E3B876]/30',
  'tier-frontier': 'bg-plum/20 text-[#CBA6E2] ring-plum/30',
};
function Chip({ variant = 'neutral', dot = false, className = '', children }: { variant?: ChipVariant; dot?: boolean; className?: string; children: ReactNode }) {
  const dotColor = variant === 'tier-frontier' ? '#CBA6E2' : variant === 'tier-large' ? '#E3B876' : variant === 'tier-small' ? '#93D3AB' : variant === 'accent' ? '#FF9E7E' : 'rgba(255,255,255,.5)';
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 font-body text-[10px] font-semibold uppercase tracking-[.06em] ring-1 ${CHIP[variant]} ${className}`}>
      {dot && <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: dotColor }} />}
      {children}
    </span>
  );
}
function chipVariant(tier: Tier): ChipVariant {
  return tier === 'frontier' ? 'tier-frontier' : tier === 'large-oss' ? 'tier-large' : 'tier-small';
}

// Manual routing (Live Gateway): a complexity slider + a dual-handle range selector
// that defines the tier boundaries, with a live preview of which tier/model the
// current score lands in. finops-auto still runs; this just hand-drives the router.
type ModelLite = { id: string; short: string; tier: string; price_out_per_1m?: number };
const TIER_META: Record<Tier, { label: string; hex: string }> = {
  'small-oss': { label: 'small OSS', hex: '#93D3AB' },
  'large-oss': { label: 'large OSS', hex: '#E3B876' },
  frontier: { label: 'frontier', hex: '#B487D0' },
};
const tierFor = (cx: number, b1: number, b2: number): Tier => (cx < b1 ? 'small-oss' : cx < b2 ? 'large-oss' : 'frontier');

function ManualRouting({ cx, setCx, b1, b2, setB1, setB2, models }: {
  cx: number; setCx: (n: number) => void; b1: number; b2: number;
  setB1: (n: number) => void; setB2: (n: number) => void; models: ModelLite[];
}) {
  const tier = tierFor(cx, b1, b2);
  const meta = TIER_META[tier];
  const predicted = models.filter((m) => m.tier === tier)
    .sort((a, z) => (a.price_out_per_1m ?? 1e9) - (z.price_out_per_1m ?? 1e9))[0];
  return (
    <div className="mt-3 flex flex-col gap-4">
      <div>
        <div className="flex items-center justify-between">
          <span className={EB}>Prompt complexity</span>
          <span className="num text-[13px] font-semibold" style={{ color: meta.hex }}>{cx} · {meta.label}</span>
        </div>
        <input type="range" min={0} max={100} value={cx} onChange={(e) => setCx(+e.target.value)}
          aria-label="Prompt complexity 0 to 100" className="mt-2 w-full accent-lava" />
      </div>
      <div>
        <span className={EB}>Tier ranges · drag the two handles</span>
        <BandRange b1={b1} b2={b2} setB1={setB1} setB2={setB2} cx={cx} />
        <div className="mt-1.5 flex justify-between font-body text-[10.5px] text-white/45">
          <span style={{ color: TIER_META['small-oss'].hex }}>small OSS 0–{b1 - 1}</span>
          <span style={{ color: TIER_META['large-oss'].hex }}>large OSS {b1}–{b2 - 1}</span>
          <span style={{ color: TIER_META.frontier.hex }}>frontier {b2}–100</span>
        </div>
      </div>
      <div className="rounded-lg bg-white/[0.04] px-3 py-2 font-body text-[12px] leading-[1.5] text-white/70 ring-1 ring-white/10">
        At complexity <b className="text-white">{cx}</b> this routes to the <span className="font-semibold" style={{ color: meta.hex }}>{meta.label}</span> tier
        {predicted ? <> → <b className="text-white">{predicted.short}</b></> : null}. Hit send to run it for real.
      </div>
    </div>
  );
}

// Dual-thumb range selector on a 0-100 track with the three tier zones colored and
// a marker for the current complexity. Pointer-driven (no dependency on native
// slider-thumb styling), so both handles stay draggable and the zones stay in sync.
function BandRange({ b1, b2, setB1, setB2, cx }: {
  b1: number; b2: number; setB1: (n: number) => void; setB2: (n: number) => void; cx: number;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const dragging = useRef<null | 'b1' | 'b2'>(null);
  useEffect(() => {
    const toPct = (clientX: number) => {
      const el = trackRef.current;
      if (!el) return 0;
      const r = el.getBoundingClientRect();
      return Math.round(Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100)));
    };
    const move = (e: PointerEvent) => {
      if (!dragging.current) return;
      const v = toPct(e.clientX);
      if (dragging.current === 'b1') setB1(Math.min(Math.max(1, v), b2 - 1));
      else setB2(Math.max(Math.min(99, v), b1 + 1));
    };
    const up = () => { dragging.current = null; };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); };
  }, [b1, b2, setB1, setB2]);
  return (
    <div ref={trackRef} className="relative mt-2 h-6 select-none">
      <div className="absolute top-1/2 left-0 h-2.5 w-full -translate-y-1/2 overflow-hidden rounded-full">
        <div className="absolute inset-y-0 left-0" style={{ width: `${b1}%`, background: TIER_META['small-oss'].hex }} />
        <div className="absolute inset-y-0" style={{ left: `${b1}%`, width: `${b2 - b1}%`, background: TIER_META['large-oss'].hex }} />
        <div className="absolute inset-y-0 right-0" style={{ left: `${b2}%`, background: TIER_META.frontier.hex }} />
      </div>
      <div className="absolute top-1/2 h-5 w-[2px] -translate-x-1/2 -translate-y-1/2 rounded bg-white shadow" style={{ left: `${cx}%` }} title={`complexity ${cx}`} />
      <button type="button" aria-label="small to large boundary"
        onPointerDown={(e) => { e.preventDefault(); dragging.current = 'b1'; }}
        className="absolute top-1/2 h-5 w-5 -translate-x-1/2 -translate-y-1/2 cursor-grab touch-none rounded-full border-2 bg-white shadow-lift active:cursor-grabbing"
        style={{ left: `${b1}%`, borderColor: TIER_META['large-oss'].hex }} />
      <button type="button" aria-label="large to frontier boundary"
        onPointerDown={(e) => { e.preventDefault(); dragging.current = 'b2'; }}
        className="absolute top-1/2 h-5 w-5 -translate-x-1/2 -translate-y-1/2 cursor-grab touch-none rounded-full border-2 bg-white shadow-lift active:cursor-grabbing"
        style={{ left: `${b2}%`, borderColor: TIER_META.frontier.hex }} />
    </div>
  );
}

// Primary (lava) + secondary (ghost) buttons, dark theme.
function PrimaryBtn({ className = '', children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={`rounded-pill bg-lava px-[22px] py-2.5 text-[13px] font-semibold text-white shadow-lift transition hover:bg-[#e22e1a] disabled:cursor-not-allowed disabled:opacity-45 ${className}`} {...rest}>{children}</button>;
}
function GhostBtn({ className = '', children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={`rounded-pill bg-white/10 px-[18px] py-2.5 text-[13px] font-medium text-white/80 ring-1 ring-white/15 transition hover:bg-white/15 hover:text-white disabled:cursor-not-allowed disabled:opacity-45 ${className}`} {...rest}>{children}</button>;
}

// Dark figure (label above a mono value).
type FigTone = 'ink' | 'ink-2' | 'lava' | 'moss';
function Figure({ label, value, tone = 'ink', className = '' }: { label: string; value: ReactNode; tone?: FigTone; className?: string }) {
  const color = tone === 'lava' ? '#FF6A54' : tone === 'moss' ? '#4FD79E' : tone === 'ink-2' ? 'rgba(255,255,255,.7)' : '#fff';
  return (
    <div className={className}>
      <div className={EB}>{label}</div>
      <div className="num mt-1.5 text-[18px] font-semibold leading-none tracking-[-.03em]" style={{ color }}>{value}</div>
    </div>
  );
}

export function GatewayApi() {
  const cfg = useConfig();
  const logRun = useSession((s) => s.logRun);
  const setLastRouting = useSession((s) => s.setLastRouting);

  const [model, setModel] = useState('finops-auto');
  const [prompt, setPrompt] = useState('Draft a one-paragraph summary of our Q3 revenue trend for the board.');
  const [cacheOn, setCacheOn] = useState(true);
  const [capUsd, setCapUsd] = useState('');  // optional live budget cap (blank = off)
  const [optOn, setOptOn] = useState(false); // output-shaping optimization
  const [optWords, setOptWords] = useState(150);
  // Routing mode for finops-auto: 'auto' = classifier scores it; 'manual' = user
  // sets the complexity + tier ranges (cx skips the classifier, bands drive tiers).
  const [routeMode, setRouteMode] = useState<'auto' | 'manual'>('auto');
  const [cxManual, setCxManual] = useState(50);
  const [b1, setB1] = useState(40); // small <-> large boundary
  const [b2, setB2] = useState(75); // large <-> frontier boundary
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<FinopsReceipt | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [ab, setAb] = useState<OptimizeAbResult | null>(null);
  const [abBusy, setAbBusy] = useState(false);
  const [judgeModel, setJudgeModel] = useState('');  // A/B evaluation judge (empty until cfg loads)

  const refreshStats = useCallback(() => { getCacheStats().then(setCacheStats).catch(() => {}); }, []);
  useEffect(() => { refreshStats(); }, [refreshStats]);
  useEffect(() => { getReadiness().then(setReadiness).catch(() => {}); }, []);
  // Default the A/B judge to a strong, reliable evaluator (claude-opus-4-8), else the
  // first frontier model, else the first model.
  useEffect(() => {
    if (cfg && !judgeModel) {
      const pick = cfg.models.find((m) => m.id === 'databricks-claude-opus-4-8')
        ?? cfg.models.find((m) => m.tier === 'frontier') ?? cfg.models[0];
      if (pick) setJudgeModel(pick.id);
    }
  }, [cfg, judgeModel]);

  const modelOptions = useMemo(
    () => [{ id: 'finops-auto', short: 'finops-auto (router picks)' }, ...(cfg?.models ?? []).map((m) => ({ id: m.id, short: m.short }))],
    [cfg],
  );

  async function run() {
    if (!prompt.trim() || busy) return;
    setBusy(true);
    setErr(null);
    setAnswer(null);
    setReceipt(null);
    try {
      const cap = parseFloat(capUsd);
      const finopsOpts: Record<string, unknown> = { semanticCache: { enabled: cacheOn, threshold: 0.92 } };
      if (cap > 0) finopsOpts.budget = { enabled: true, capUsd: cap, downgradeAtPct: 55, openOnlyAtPct: 80, downgradeAction: 'large-oss', openOnlyAction: 'block' };
      if (optOn) finopsOpts.optimize = { enabled: true, targetWords: optWords };
      // Manual routing (finops-auto only): send the hand-set complexity + tier ranges.
      if (model === 'finops-auto' && routeMode === 'manual') {
        finopsOpts.complexity = cxManual;
        finopsOpts.bands = [
          { label: 'Simple', min: 0, max: b1 - 1, tier: 'small-oss' },
          { label: 'Standard', min: b1, max: b2 - 1, tier: 'large-oss' },
          { label: 'Complex', min: b2, max: 100, tier: 'frontier' },
        ];
      }
      const { answer: ans, finops } = await gatewayChat(prompt, model, finopsOpts);
      setAnswer(ans);
      setReceipt(finops);
      refreshStats();
      // Feed the routed call into the session so the Cost & savings tab reflects it.
      logRun({
        source: 'gateway',
        modelShort: finops.servedBy.short,
        tier: finops.servedBy.tier as Tier,
        costUsd: finops.costUsd,
        baselineUsd: finops.baselineUsd,
        inputTokens: finops.inputTokens,
        outputTokens: finops.outputTokens,
        latencyMs: finops.latencyMs,
        optimized: (finops.compression?.savedTokens ?? 0) > 0,
        promptSnippet: prompt.slice(0, 80),
      });
      setLastRouting({
        model: finops.servedBy.short,
        tier: finops.servedBy.tier as Tier,
        costUsd: finops.costUsd,
        complexity: finops.complexity,
        source: 'gateway',
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Gateway request failed');
    } finally {
      setBusy(false);
    }
  }

  async function runAb() {
    if (!prompt.trim() || abBusy) return;
    setAbBusy(true);
    setErr(null);
    setAb(null);
    try {
      setAb(await optimizeAb(prompt, model, optWords, judgeModel || undefined));
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'A/B failed');
    } finally {
      setAbBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-[18px]">
      {/* Hero (dark box, matches the other tabs) */}
      <Panel glow="var(--lava)">
        <div className="font-body text-[11px] font-semibold uppercase tracking-[.22em] text-lava">Live gateway</div>
        <h2 className="mt-2 max-w-[24ch] font-display text-[clamp(22px,3vw,34px)] font-bold leading-[1.06] tracking-[-.03em]">
          The app <span className="text-lava">is</span> the gateway.
        </h2>
        <p className="mt-3 max-w-[70ch] font-body text-[14.5px] leading-[1.55] text-white/65">
          Not a simulation. Send a live request as <span className="font-semibold text-white">finops-auto</span> and the router picks the
          <span className="font-semibold text-white"> cheapest model that clears the bar</span>, then guardrails, rate-limits, compresses, caches, and serves it with a fallback, with no change to the calling app.
        </p>
      </Panel>

      {/* Try it live */}
      <Panel delay=".05s">
        <div className="mb-3 flex items-center justify-between">
          <div className={SECTION}>Try it live</div>
          {cfg?.demoMode && <Chip>demo mode</Chip>}
        </div>

        <label className="block">
          <span className={EB}>Model</span>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className={`mt-1.5 w-full ${INPUT_DARK}`}
          >
            {modelOptions.map((m) => (
              <option key={m.id} value={m.id} className="bg-ink text-white">{m.short}</option>
            ))}
          </select>
        </label>
        <p className="mt-1.5 font-body text-[12px] leading-[1.5] text-white/50">
          <span className="font-semibold text-white/75">finops-auto</span> lets the router choose the cheapest model that clears this prompt's bar. Pick a specific model to govern it and pass the call through unchanged.
        </p>

        {model === 'finops-auto' && (
          <div className="mt-3 rounded-xl bg-white/[0.03] p-3 ring-1 ring-white/10">
            <div className="flex items-center justify-between">
              <span className={EB}>Complexity routing</span>
              <div className="flex rounded-pill bg-white/[0.06] p-0.5 ring-1 ring-white/10">
                {(['auto', 'manual'] as const).map((m) => (
                  <button key={m} type="button" onClick={() => setRouteMode(m)}
                    className={`rounded-pill px-3 py-1 text-[11.5px] font-semibold transition ${routeMode === m ? 'bg-lava text-white' : 'text-white/55 hover:text-white'}`}>
                    {m === 'auto' ? 'Auto (classifier)' : 'Manual'}
                  </button>
                ))}
              </div>
            </div>
            {routeMode === 'auto' ? (
              <p className="mt-2 font-body text-[12px] leading-[1.5] text-white/50">A small classifier scores this prompt 0-100 and routes to the cheapest model that clears the bar. Switch to <span className="font-semibold text-white/75">Manual</span> to set the score and the tier ranges yourself.</p>
            ) : (
              <ManualRouting cx={cxManual} setCx={setCxManual} b1={b1} b2={b2} setB1={setB1} setB2={setB2} models={cfg?.models ?? []} />
            )}
          </div>
        )}

        <label className="mt-3 block">
          <span className={EB}>Prompt</span>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            className={`mt-1.5 w-full resize-y ${INPUT_DARK} leading-[1.5]`}
            placeholder="Ask anything - the router scores it and picks a model."
          />
        </label>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex cursor-pointer items-center gap-2 text-[12.5px] text-white/75">
              <input type="checkbox" checked={cacheOn} onChange={(e) => setCacheOn(e.target.checked)} className="h-3.5 w-3.5 accent-lava" />
              Semantic cache
            </label>
            <label className="flex items-center gap-2 text-[12.5px] text-white/75">
              Budget cap $/30d
              <input type="number" min={0} value={capUsd} onChange={(e) => setCapUsd(e.target.value)} placeholder="off"
                className="num w-[92px] rounded bg-white/[0.06] px-2 py-1 text-right text-[12px] text-white outline-none ring-1 ring-white/10 placeholder:text-white/35" />
            </label>
            <label className="flex cursor-pointer items-center gap-2 text-[12.5px] text-white/75">
              <input type="checkbox" checked={optOn} onChange={(e) => setOptOn(e.target.checked)} className="h-3.5 w-3.5 accent-lava" />
              Optimize output
            </label>
            {optOn && (
              <label className="flex items-center gap-2 text-[12.5px] text-white/75">
                ≤ words
                <input type="number" min={20} max={800} value={optWords} onChange={(e) => setOptWords(Math.max(20, Number(e.target.value) || 150))}
                  className="num w-[70px] rounded bg-white/[0.06] px-2 py-1 text-right text-[12px] text-white outline-none ring-1 ring-white/10" />
              </label>
            )}
          </div>
          <PrimaryBtn onClick={run} disabled={busy || !prompt.trim()}>
            {busy ? 'Routing…' : 'Send through the gateway'}
          </PrimaryBtn>
        </div>

        {/* Prove output-shaping nets positive: same prompt shaped vs unshaped, measured. */}
        <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-white/10 pt-3">
          <GhostBtn className="px-3.5 py-2 text-[12px]" onClick={runAb} disabled={abBusy || !prompt.trim()}>
            {abBusy ? 'Measuring…' : 'A/B: prove output savings'}
          </GhostBtn>
          <label className="flex items-center gap-2 text-[12px] text-white/70">
            Judge
            <select value={judgeModel} onChange={(e) => setJudgeModel(e.target.value)} aria-label="Evaluation judge model"
              className="rounded-pill bg-white/[0.06] px-3 py-1.5 font-body text-[12px] text-white outline-none ring-1 ring-white/10">
              {(cfg?.models ?? []).map((m) => (
                <option key={m.id} value={m.id} className="bg-ink text-white">{m.short}</option>
              ))}
            </select>
          </label>
          <span className="font-body text-[11.5px] text-white/45">Same prompt shaped vs unshaped on the same model; the judge scores both so you see quality held.</span>
        </div>
        {ab && <AbResult ab={ab} />}

        {err && (
          <div className="mt-3 rounded-xl bg-lava/15 px-4 py-3 font-body text-[13px] text-[#FF9E8C] ring-1 ring-lava/30">{err}</div>
        )}

        {/* Semantic cache: a single running counter of the $ it has saved by
            serving near-duplicate prompts from cache instead of re-calling a model. */}
        {cacheStats && (
          <div className="mt-4 flex items-center justify-between rounded-xl bg-moss/12 px-4 py-3 ring-1 ring-moss/25">
            <span className={EB}>Saved by semantic cache</span>
            <span className="num text-[20px] font-semibold leading-none tracking-[-.03em] text-[#93D3AB]">{formatMoney(cacheStats.savedUsd)}</span>
          </div>
        )}
        {/* Routing receipt - the direct result of the request sent above, so it lives in
            the SAME box as "Try it live" rather than a disconnected panel below. */}
        {receipt && (
          <div className="mt-5 border-t border-white/10 pt-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className={SECTION}>Routing receipt</div>
            <div className="flex flex-wrap items-center gap-2">
              {receipt.cacheHit && (
                <Chip variant="tier-small">⚡ cache hit · {receipt.similarity != null ? `${Math.round(receipt.similarity * 100)}% match` : 'match'}</Chip>
              )}
              <Chip variant={receipt.mode === 'auto' ? 'accent' : 'neutral'}>
                {receipt.mode === 'auto' ? 'router picked' : 'governed passthrough'}
              </Chip>
              {receipt.guardrail && (
                <Chip variant="tier-large">guardrail: {receipt.guardrail.action} {receipt.guardrail.categories}</Chip>
              )}
              {receipt.fallback?.fired && (
                <Chip variant="tier-large">fallback fired: {receipt.fallback.from} → {receipt.servedBy.short}</Chip>
              )}
              {!receipt.fallback?.fired && receipt.fallback?.armed?.length ? (
                <Chip variant="neutral">fallback armed: {receipt.fallback.armed.join(' → ')}</Chip>
              ) : null}
              {receipt.compression && receipt.compression.savedTokens > 0 && (
                <Chip variant="tier-small">compressed −{receipt.compression.savedPct}%</Chip>
              )}
              {receipt.budget && (
                <Chip variant="tier-large">budget {receipt.budget.consumedPct}% of ${receipt.budget.capUsd.toLocaleString()}{receipt.budget.ceiling !== 'frontier' ? ` · cap ${receipt.budget.ceiling}` : ''}</Chip>
              )}
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-y-5 sm:grid-cols-3 lg:grid-cols-6">
            <div>
              <div className={EB}>Served by</div>
              <div className="num mt-1.5 text-[16px] font-medium tracking-[-.03em] text-white">{receipt.servedBy.short}</div>
              <Chip className="mt-1.5" variant={chipVariant(receipt.servedBy.tier as Tier)} dot>
                {receipt.servedBy.tier}
              </Chip>
            </div>
            <Figure label="Cost / call" value={formatMoney(receipt.costUsd)} tone="lava" />
            <Figure label={`vs ${receipt.baselineModel}`} value={formatMoney(receipt.baselineUsd)} tone="ink-2" />
            <Figure label="Saved" value={`${formatPercent1(receipt.savingsPct)}`} tone="moss" />
            <div>
              <div className={EB}>Complexity</div>
              <div className="num mt-1.5 text-[18px] font-semibold tracking-[-.03em] text-white">{receipt.complexity}</div>
              <div className="mt-1 font-body text-[11px] text-white/45">needs {receipt.requiredTierLabel}</div>
            </div>
            <Figure label="Latency" value={formatLatency(receipt.latencyMs)} tone="ink-2" />
          </div>

          <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 font-body text-[12px] text-white/45">
            <span>Candidates: <span className="text-white/70">{receipt.candidates.join(', ')}</span></span>
            <span>Tokens: <span className="text-white/70">{formatTokens(receipt.inputTokens)} in · {formatTokens(receipt.outputTokens)} out</span></span>
            {receipt.matchedRule && <span>Matched rule: <span className="text-white/70">"{receipt.matchedRule}"</span></span>}
          </div>
          {receipt.optimization && (
            <div className="mt-3 rounded-xl bg-moss/12 px-4 py-2.5 font-body text-[12px] text-[#93D3AB] ring-1 ring-moss/25">
              Output-shaped to ≤{receipt.optimization.targetWords} words: {formatTokens(receipt.optimization.outputTokens)} out vs ~{formatTokens(receipt.optimization.baselineOutputTokens)} typical for this complexity
              {receipt.optimization.savedOutputTokens > 0 && <> · est. −{formatTokens(receipt.optimization.savedOutputTokens)} output tokens ({formatMoney(receipt.optimization.savedUsdEst)})</>}
              . Use A/B for a measured number.
            </div>
          )}

          {answer && (
            <div className="mt-4 rounded-xl bg-white/[0.04] p-4 ring-1 ring-white/10">
              <div className={EB}>Response</div>
              <div className="mt-2 whitespace-pre-wrap font-body text-[13.5px] leading-[1.6] text-white/90">{answer}</div>
            </div>
          )}
          </div>
        )}
      </Panel>

      {/* Bring-your-own evaluation set */}
      <EvalSetCard judgeModel={judgeModel} />

      {readiness && <ReadinessPanel r={readiness} />}
    </div>
  );
}

// Bring-your-own eval set: paste representative prompts and MEASURE how Smart Routing
// compares to a frontier baseline on quality and cost for YOUR workload. Each prompt is
// run both ways and judged; the aggregate answers "how does routing compare for my domain".
const EVAL_DEFAULT = [
  'Reply to a customer asking where their delayed order is.',
  'Summarize our Q3 revenue trend in one paragraph for the board.',
  'Design a multi-region disaster-recovery plan and justify the tradeoffs.',
].join('\n');
function EvalSetCard({ judgeModel }: { judgeModel: string }) {
  const [text, setText] = useState(EVAL_DEFAULT);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<EvalResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const prompts = text.split('\n').map((s) => s.trim()).filter(Boolean);
  const run = async () => {
    if (!prompts.length || busy) return;
    setBusy(true); setErr(null); setRes(null);
    try {
      setRes(await runEvalSet(prompts.slice(0, 6), { judgeModel: judgeModel || undefined }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Eval failed');
    } finally {
      setBusy(false);
    }
  };
  const a = res?.aggregate;
  return (
    <Panel delay=".08s" glow="#67C7E8">
      <div className="flex items-center justify-between">
        <div className={SECTION}>Evaluation set · your prompts</div>
        <Chip>routed vs frontier · judged</Chip>
      </div>
      <p className="mt-2 max-w-[74ch] font-body text-[13px] leading-[1.55] text-white/80"><span className="font-semibold text-[#7FB6F2]">Why it matters:</span> measure the quality and cost difference between routing and a frontier flagship on your own prompts, before you commit either way. An evidence-based decision, not a leap of faith.</p>
      <p className="mt-2 max-w-[74ch] font-body text-[12.5px] leading-[1.5] text-white/60">
        Paste prompts from your own workload (up to 6). Each runs through the router and through a frontier flagship, both scored by the same judge, so you can <span className="font-semibold text-white">see how routed quality compares on your domain</span> and what it costs.
      </p>
      <textarea
        value={text} onChange={(e) => setText(e.target.value)} rows={4}
        className={`mt-3 w-full resize-y ${INPUT_DARK} text-[13px] leading-[1.6]`}
        placeholder="One prompt per line…"
      />
      <div className="mt-3 flex items-center justify-between gap-3">
        <span className="font-body text-[11.5px] text-white/45">{Math.min(6, prompts.length)} prompt{prompts.length === 1 ? '' : 's'} · judged by {judgeModel ? judgeModel.replace('databricks-', '') : 'frontier'} · ~15-30s (runs in parallel)</span>
        <PrimaryBtn onClick={run} disabled={busy || !prompts.length}>{busy ? 'Evaluating…' : 'Run evaluation'}</PrimaryBtn>
      </div>
      {err && <div className="mt-3 rounded-xl bg-lava/15 px-4 py-2.5 font-body text-[12.5px] text-[#FF9E8C] ring-1 ring-lava/30">{err}</div>}
      {a && (
        <div className="mt-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Figure label="Routed avg quality" value={a.avgRoutedQuality != null ? `${a.avgRoutedQuality.toFixed(1)}/10` : '-'} tone="ink" />
            <Figure label={`Frontier avg (${a.frontierBaseline})`} value={a.avgFrontierQuality != null ? `${a.avgFrontierQuality.toFixed(1)}/10` : '-'} tone="ink-2" />
            <Figure label="Quality vs frontier" value={a.qualityRetentionPct != null ? `${a.qualityRetentionPct}%` : '-'} tone="moss" />
            <Figure label="Cost vs frontier" value={`−${formatPercent1(a.savedPct)}`} tone="lava" />
          </div>
          <div className="mt-3 overflow-x-auto rounded-xl bg-white/[0.04] p-2 ring-1 ring-white/10">
            <table className="w-full min-w-[560px] border-collapse font-body text-[12px]">
              <thead><tr className="text-left text-white/45">
                <th className="px-2 py-1.5 font-semibold">Prompt</th><th className="px-2 py-1.5 font-semibold">Routed to</th>
                <th className="px-2 py-1.5 text-right font-semibold">Routed q</th><th className="px-2 py-1.5 text-right font-semibold">Frontier q</th><th className="px-2 py-1.5 text-right font-semibold">Saved</th>
              </tr></thead>
              <tbody>
                {(res?.rows ?? []).map((r, i) => (
                  <tr key={i} className="border-t border-white/[0.07]">
                    <td className="px-2 py-1.5 text-white/85">{r.error ? <span className="text-[#FF9E8C]">⚠ {r.prompt.slice(0, 40)}… ({r.error.slice(0, 40)})</span> : <span title={r.prompt}>{r.prompt.length > 46 ? r.prompt.slice(0, 46) + '…' : r.prompt}</span>}</td>
                    <td className="px-2 py-1.5">{r.routed ? <Chip variant={chipVariant(r.routed.tier as Tier)} dot>{r.routed.model}</Chip> : '-'}</td>
                    <td className="px-2 py-1.5 text-right num text-white/85">{r.routed?.quality != null ? r.routed.quality.toFixed(1) : '-'}</td>
                    <td className="px-2 py-1.5 text-right num text-white/60">{r.frontier?.quality != null ? r.frontier.quality.toFixed(1) : '-'}</td>
                    <td className="px-2 py-1.5 text-right num text-[#93D3AB]">{r.savedPct != null ? `${r.savedPct}%` : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 font-body text-[11px] leading-[1.5] text-white/40">
            Each prompt run through finops-auto vs {a.frontierBaseline}, both scored by {a.judge}. {res?.mlflow?.logged
              ? <>Logged to MLflow experiment <span className="num">{res.mlflow.experiment}</span> (run {res.mlflow.runId?.slice(0, 8)}).</>
              : <>MLflow logging {res?.mlflow?.reason ? 'unavailable here' : 'off'} - the eval itself is fully measured regardless.</>}
          </p>
        </div>
      )}
    </Panel>
  );
}

// Measured A/B: output-shaping vs none, same model. Proves the net saving (and that
// quality held) with real numbers instead of an estimate.
function AbResult({ ab }: { ab: OptimizeAbResult }) {
  const qHeld = ab.unshaped.quality != null && ab.shaped.quality != null;
  const won = ab.savedPct > 2;
  return (
    <div className="mt-3 rounded-xl bg-white/[0.04] p-4 ring-1 ring-white/10">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className={EB}>A/B result · measured · judge {ab.judge}</span>
        {won
          ? <Chip variant="tier-small">−{formatPercent1(ab.savedPct)} output cost{ab.savedOutputTokens > 0 ? ` · −${formatTokens(ab.savedOutputTokens)} tok` : ''}</Chip>
          : <Chip variant="neutral">already concise · little to shape</Chip>}
      </div>
      {!won && (
        <p className="mt-2 font-body text-[11.5px] leading-[1.5] text-white/45">This answer was already short, so shaping saved little here. Output-shaping pays off on the verbose tail; try a broad open-ended prompt, or measure across many requests.</p>
      )}
      <div className="mt-3 grid grid-cols-2 gap-3">
        <div className="rounded-lg bg-black/25 p-3 ring-1 ring-white/10">
          <div className={EB}>Unshaped</div>
          <div className="num mt-1 text-[15px] font-medium text-white">{formatMoney(ab.unshaped.costUsd)}</div>
          <div className="mt-0.5 font-body text-[11px] text-white/45">{formatTokens(ab.unshaped.outputTokens)} out{ab.unshaped.quality != null ? ` · quality ${ab.unshaped.quality.toFixed(1)}` : ''}</div>
        </div>
        <div className="rounded-lg bg-black/25 p-3 ring-1 ring-moss/40">
          <div className="font-body text-[10px] font-semibold uppercase tracking-[.14em] text-[#93D3AB]">Shaped ≤{ab.shaped.targetWords}w</div>
          <div className="num mt-1 text-[15px] font-medium text-white">{formatMoney(ab.shaped.costUsd)}</div>
          <div className="mt-0.5 font-body text-[11px] text-white/45">{formatTokens(ab.shaped.outputTokens)} out{ab.shaped.quality != null ? ` · quality ${ab.shaped.quality.toFixed(1)}` : ''}</div>
        </div>
      </div>
      {qHeld && (
        <div className="mt-2 font-body text-[11.5px] text-white/70">
          Quality {ab.shaped.quality! >= ab.unshaped.quality! - 0.5 ? <span className="font-semibold text-[#93D3AB]">held</span> : <span className="font-semibold text-[#FF9E8C]">dropped</span>} ({ab.unshaped.quality!.toFixed(1)} → {ab.shaped.quality!.toFixed(1)}) · both served by {ab.shaped.servedBy}
        </div>
      )}
    </div>
  );
}

// Deployment readiness + endpoint discovery - the "can a customer stand this up in
// their own workspace" checklist, self-diagnosed live. Minimized by default so the
// working boxes above stay the focus; expand to see the full checklist.
function ReadinessPanel({ r }: { r: Readiness }) {
  const [open, setOpen] = useState(false);
  const d = r.discovery;
  const passed = r.checks.filter((c) => c.ok).length;
  return (
    <Panel delay=".1s">
      <div className="flex flex-wrap items-center gap-2">
        <div className={SECTION}>Deployment readiness</div>
        <Chip variant={r.ready ? 'tier-small' : 'tier-large'}>{r.ready ? '✓ ready to deploy' : 'needs attention'}</Chip>
        <button onClick={() => setOpen((v) => !v)} className="ml-auto rounded-pill bg-white/10 px-3 py-1 text-[11px] font-semibold text-white/75 ring-1 ring-white/10 transition hover:bg-white/15 hover:text-white">{open ? 'Minimize ▲' : 'Expand ▼'}</button>
      </div>
      {!open && (
        <p className="mt-2 text-[12.5px] leading-[1.5] text-white/50">
          <span className="num text-white/75">{passed}/{r.checks.length}</span> checks passing · <span className="num text-white/75">{d.liveCount}</span> endpoints live · <span className="num text-white/75">{d.present.length}</span>/{d.registryCount} registry models routable here. <button onClick={() => setOpen(true)} className="font-semibold text-[#7FB6F2] hover:underline">Expand</button> for the full checklist.
        </p>
      )}
      {open && (<>
        <div className="mt-3 flex flex-col gap-2">
          {r.checks.map((c) => (
            <div key={c.id} className="flex items-start gap-3 rounded-xl bg-white/[0.04] px-4 py-2.5 ring-1 ring-white/10">
              <span className={`mt-0.5 text-[13px] ${c.ok ? 'text-[#93D3AB]' : c.optional ? 'text-white/40' : 'text-[#FF9E8C]'}`}>{c.ok ? '✓' : c.optional ? '○' : '✗'}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <span className="font-body text-[13px] font-medium text-white">{c.label}{c.optional && <span className="ml-1.5 text-[10px] uppercase tracking-[.06em] text-white/40">optional</span>}</span>
                  <span className="num text-[11.5px] text-white/45">{c.detail}</span>
                </div>
                {!c.ok && !c.optional && <div className="mt-1 font-body text-[11.5px] leading-[1.5] text-white/70">Fix: {c.fix}</div>}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-xl bg-white/[0.04] p-4 ring-1 ring-white/10">
          <div className={EB}>Endpoint discovery</div>
          <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 font-body text-[12px] text-white/70">
            <span><span className="num font-semibold text-white">{d.present.length}</span>/{d.registryCount} registry models routable here</span>
            <span><span className="num font-semibold text-white">{d.liveCount}</span> endpoints live</span>
            {d.extraCount > 0 && <span><span className="num font-semibold text-white">{d.extraCount}</span> unpriced (add a DBU rate to route to them)</span>}
          </div>
          {d.missing.length > 0 && (
            <div className="mt-2 font-body text-[11px] leading-[1.5] text-white/45">Registry models not deployed here: <span className="num">{d.missing.slice(0, 8).join(', ')}{d.missing.length > 8 ? ` +${d.missing.length - 8}` : ''}</span></div>
          )}
        </div>
        <p className="mt-3 font-body text-[11px] leading-[1.5] text-white/40">
          Checks run live against this workspace via the app service principal. Unpriced endpoints are flagged, never given a fabricated price.
        </p>
      </>)}
    </Panel>
  );
}
