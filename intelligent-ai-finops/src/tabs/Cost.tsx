import { useMemo, useState } from 'react';
import { useConfig } from '../api/useConfig';
import { useSession, type RunRecord } from '../store/session';
import { TIER_META, TIER_SHORT, type ModelDef, type Tier } from '../api/types';
import { RoiChart, compact, computeRoi, perQuery, type Roi } from '../components/RoutingViz';
import { formatMoney, formatPerQuery, formatPercent, formatPercent1, formatRate1, formatLatency } from '../lib/format';

// Tab 3 - Cost. The FinOps view: what this session has actually run, what it
// cost, how spend splits across models and tiers, and what it projects to over
// a day / month / year at your traffic. This is the Unity Gateway usage
// dashboard (requests · latency · cost by endpoint) plus the two things it doesn't
// give you out of the box: forward projection and the savings from routing.

const usd = (n: number) => formatMoney(n); // table cells / tiles
const perQ = (n: number) => formatPerQuery(n); // per-query figures
const pct = (n: number) => formatPercent(n);
// Compact count formatter (8.3k / 1.2M) for the daily-trend charts and tiles.
const num0 = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(n >= 1e4 ? 0 : 1)}k` : Math.round(n).toString());

const LBL = 'font-body text-[9.5px] font-semibold uppercase tracking-[.14em] text-white/45';
const SECTION = 'font-display text-[13px] font-bold uppercase tracking-[.15em] text-[#7FB6F2]';
const DAYS_PER_MONTH = 30;

// Fallback per-tier serving latency (ms) for runs that didn't record one (e.g.
// older sample rows) - keeps the observability latency stats populated.
const TIER_LAT: Record<Tier, number> = { 'small-oss': 560, 'large-oss': 1500, frontier: 3100 };
const latOf = (r: RunRecord) => r.latencyMs ?? TIER_LAT[r.tier];

export function Cost() {
  const cfg = useConfig();
  const { runs, queries, spendUsd, baseUsd } = useSession();
  const [users, setUsers] = useState(5000);
  const [perUserQ, setPerUserQ] = useState(50);
  const monthlyVol = users * perUserQ;
  // Observability time window (days) for the daily trend charts.
  const [rangeDays, setRangeDays] = useState(30);

  const measuredAvg = queries > 0 ? spendUsd / queries : null;
  const savedSession = baseUsd - spendUsd;
  const savedPct = baseUsd > 0 ? (savedSession / baseUsd) * 100 : 0;

  // Fallback per-query estimate from the model registry (a 60/30/10 routed blend
  // vs a frontier-only baseline), used to project before any run happens.
  const est = useMemo(() => {
    if (!cfg) return null;
    const cheapestOf = (t: Tier) => cfg.models.filter((m) => m.tier === t).sort((a, b) => perQuery(a) - perQuery(b))[0];
    const s = cheapestOf('small-oss'), l = cheapestOf('large-oss'), f = cheapestOf('frontier');
    if (!f) return null;
    const routed = 0.6 * perQuery(s ?? f) + 0.3 * perQuery(l ?? f) + 0.1 * perQuery(f);
    return { routed, frontier: perQuery(f) };
  }, [cfg]);

  // The distinct models this session has actually run, as full registry defs -
  // the routing projection blends these (cheapest→priciest, 60/30/10) vs routing
  // everything to the priciest, exactly like the Compare tab's ROI.
  const runModelDefs = useMemo(() => {
    if (!cfg) return [] as ModelDef[];
    const shorts = [...new Set(runs.map((r) => r.modelShort))];
    return shorts.map((s) => cfg.models.find((m) => m.short === s)).filter(Boolean) as ModelDef[];
  }, [runs, cfg]);

  // Prefer a projection built from the models actually run (needs ≥2 distinct so
  // there's a real routed-vs-frontier spread); otherwise fall back to a
  // registry-blend estimate so the chart is never mysteriously blank.
  const roi: Roi | null = useMemo(() => {
    const measuredRoi = runModelDefs.length >= 2 ? computeRoi(runModelDefs, monthlyVol) : null;
    if (measuredRoi && measuredRoi.savedYr > 0) return measuredRoi;
    if (est) return { monthly: { frontier: est.frontier * monthlyVol, routed: est.routed * monthlyVol }, savedYr: (est.frontier - est.routed) * monthlyVol * 12 };
    return null;
  }, [runModelDefs, monthlyVol, est]);
  const measured = runModelDefs.length >= 2 && !!computeRoi(runModelDefs, monthlyVol);

  // The per-query cost the projection is drawn from (the routed blend) and the
  // day/week/month/year tiles, kept consistent with the chart.
  const routedPerQuery = roi ? roi.monthly.routed / monthlyVol : null;
  const proj = useMemo(() => {
    if (routedPerQuery == null) return null;
    const month = routedPerQuery * monthlyVol;
    return { day: month / DAYS_PER_MONTH, week: (month / DAYS_PER_MONTH) * 7, month, year: month * 12 };
  }, [routedPerQuery, monthlyVol]);

  // Spend grouped by model, sorted by spend.
  const byModel = useMemo(() => {
    const map = new Map<string, { model: string; tier: Tier; cost: number; count: number }>();
    for (const r of runs) {
      const e = map.get(r.modelShort) ?? { model: r.modelShort, tier: r.tier, cost: 0, count: 0 };
      e.cost += r.costUsd;
      e.count += 1;
      map.set(r.modelShort, e);
    }
    return [...map.values()].sort((a, b) => b.cost - a.cost);
  }, [runs]);

  // Spend + request split across the three tiers.
  const byTier = useMemo(() => {
    const tiers: Tier[] = ['small-oss', 'large-oss', 'frontier'];
    return tiers.map((t) => {
      const rs = runs.filter((r) => r.tier === t);
      return { tier: t, cost: rs.reduce((s, r) => s + r.costUsd, 0), count: rs.length };
    });
  }, [runs]);

  const maxModelCost = Math.max(...byModel.map((m) => m.cost), 1e-9);
  const empty = runs.length === 0;

  // Share of traffic that avoided the frontier (Claude) tier - the headline
  // "how much went to a smaller model instead of Claude" number.
  const frontierReqCount = byTier.find((t) => t.tier === 'frontier')?.count ?? 0;
  const frontierSharePct = queries > 0 ? Math.round((frontierReqCount / queries) * 100) : 0;
  const smallerSharePct = queries > 0 ? 100 - frontierSharePct : 0;

  // Observability signals the Unity Gateway captures. Traces, latency and
  // endpoint usage are real (from the session's runs); guardrail/rate-limit
  // counts are illustrative for the demo (production: system.ai_gateway).
  const obs = useMemo(() => {
    if (!runs.length) return null;
    const lats = runs.map(latOf).sort((a, b) => a - b);
    const q = (p: number) => lats[Math.min(lats.length - 1, Math.floor(p * (lats.length - 1)))];
    const times = runs.map((r) => r.ts);
    const spanMin = Math.max(1 / 60, (Math.max(...times) - Math.min(...times)) / 60000);
    return {
      traces: runs.length,
      p50: q(0.5),
      p95: q(0.95),
      reqPerMin: runs.length / spanMin,
      guardrailBlocks: Math.round(runs.length * 0.03),
      rateLimitHits: 0,
      errorRatePct: 0,
      latSeries: [...runs].reverse().map(latOf), // chronological (runs are newest-first)
    };
  }, [runs]);

  // Fabricated daily observability trends over the selected window. Deterministic
  // (seeded sine + weekday seasonality + gentle growth) so the charts are stable
  // across renders and react to the traffic sliders. In production these come
  // from system.serving.endpoint_usage / system.ai_gateway aggregated by day.
  const daily = useMemo(() => {
    const n = rangeDays;
    const reqBase = Math.max(60, monthlyVol / 30);
    const userBase = Math.max(20, users * 0.35);
    const tokBase = reqBase * 1500;
    const codingBase = reqBase * 0.18;
    const mk = (base: number, seed: number, weekend = true) =>
      Array.from({ length: n }, (_, i) => {
        const dow = i % 7;
        const wk = weekend && (dow === 5 || dow === 6) ? 0.62 : 1;
        const trend = 1 + (i / Math.max(1, n - 1)) * 0.35; // gentle growth toward today
        const noise = 0.86 + ((Math.sin(seed + i * 1.7) + 1) / 2) * 0.28;
        return Math.max(1, Math.round(base * wk * trend * noise));
      });
    const requests = mk(reqBase, 1.3);
    const uniqueUsers = mk(userBase, 4.1);
    const tokens = mk(tokBase, 2.7);
    const codingAgent = mk(codingBase, 5.9);
    const mcpServers = Array.from({ length: n }, (_, i) => 6 + Math.round((i / Math.max(1, n - 1)) * 8) + (Math.sin(9 + i) > 0.7 ? 1 : 0));
    return { requests, uniqueUsers, tokens, codingAgent, mcpServers };
  }, [rangeDays, monthlyVol, users]);
  const codingAgentTotal = daily.codingAgent.reduce((s, v) => s + v, 0);
  const mcpServersNow = daily.mcpServers[daily.mcpServers.length - 1] ?? 0;

  return (
    <div className="flex flex-col gap-[22px] text-white">
      {/* Box 1 - intro */}
      <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[26px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4">
        <div className="pointer-events-none absolute -right-32 -top-24 h-96 w-96 rounded-full bg-lava opacity-[.10] blur-3xl" />
        <div className="relative">
          <div className="mb-3 font-body text-[11px] font-semibold uppercase tracking-[.22em] text-lava">Cost view</div>
          <h2 className="max-w-[24ch] font-display text-[clamp(24px,3.2vw,40px)] font-bold leading-[1.05] tracking-[-.03em]">
            Every request, priced - and projected forward.
          </h2>
          <p className="mt-3 max-w-[68ch] font-body text-[15.5px] leading-[1.55] text-white/65">
            The <span className="font-semibold text-white">best-value model</span> chosen for each request on <span className="font-semibold text-white">Compare</span> and
            <span className="font-semibold text-white"> Context routing</span> lands here with its cost and savings - the
            <span className="font-semibold text-white"> Unity Gateway usage dashboard</span>, plus the two things it doesn't ship with: a
            <span className="font-semibold text-white"> forward projection</span> and the <span className="font-semibold text-white">savings from routing</span>. Move the sliders to scale it to your traffic.
          </p>
        </div>
      </section>

      {/* Box 2 - headline KPIs */}
      <section className="relative animate-[fadeUp_.5s_ease_both] rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.06s' }}>
        <div className={`${SECTION} mb-4`}>Overall spend</div>
        <div className="grid grid-cols-4 gap-3 max-[720px]:grid-cols-2">
          <Kpi label="Total spend" value={usd(spendUsd)} accent="#FF6A54" />
          <Kpi label="Requests" value={queries.toLocaleString()} />
          <Kpi label="Avg cost / query" value={measuredAvg != null ? perQ(measuredAvg) : '-'} />
          <Kpi label="Saved by routing" value={usd(savedSession)} sub={baseUsd > 0 ? `${pct(savedPct)} vs baseline` : ''} accent="#93D3AB" />
        </div>
        {empty && (
          <p className="mt-4 rounded-xl bg-white/[0.04] px-4 py-3 text-[12.5px] text-white/55 ring-1 ring-white/10">
            No requests yet this session. Run a comparison on the <span className="font-semibold text-white">Compare</span> tab or route a question on <span className="font-semibold text-white">Context routing</span>, and this view fills in live. The projection below uses a model-registry estimate until then.
          </p>
        )}
      </section>

      {/* Box 3 - spend breakdown */}
      <section className="relative animate-[fadeUp_.5s_ease_both] rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.1s' }}>
        <div className={`${SECTION} mb-4`}>Where the spend goes</div>
        <div className="grid grid-cols-2 gap-4 max-[760px]:grid-cols-1">
          {/* Spend by model */}
          <div className="rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
            <div className="mb-3 font-body text-[11px] font-semibold uppercase tracking-[.16em] text-white/45">Spend by model</div>
            {empty ? (
              <EmptyMini text="Model-level spend appears here after your first request." />
            ) : (
              <div className="flex flex-col gap-2.5">
                {byModel.map((m) => (
                  <div key={m.model}>
                    <div className="mb-1 flex items-center justify-between text-[12px]">
                      <span className="flex items-center gap-1.5 font-medium text-white/85">
                        <span className="h-2 w-2 rounded-full" style={{ background: TIER_META[m.tier].hex }} />
                        {m.model}
                      </span>
                      <span className="num text-white/70">{usd(m.cost)} · {m.count}×</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
                      <div className="h-full rounded-full transition-all" style={{ width: `${(m.cost / maxModelCost) * 100}%`, background: TIER_META[m.tier].hex }} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Spend + request split across tiers */}
          <div className="rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
            <div className="mb-3 font-body text-[11px] font-semibold uppercase tracking-[.16em] text-white/45">Requests by tier</div>
            {empty ? (
              <EmptyMini text="The routing spread across small / large / frontier appears here." />
            ) : (
              <>
                <div className="flex h-3 overflow-hidden rounded-full bg-white/[0.06]">
                  {byTier.map((t) => {
                    const share = queries > 0 ? (t.count / queries) * 100 : 0;
                    return share > 0 ? <div key={t.tier} style={{ width: `${share}%`, background: TIER_META[t.tier].hex }} title={`${TIER_SHORT[t.tier]}: ${t.count}`} /> : null;
                  })}
                </div>
                <div className="mt-3 flex flex-col gap-2">
                  {byTier.map((t) => (
                    <div key={t.tier} className="flex items-center justify-between text-[12px]">
                      <span className="flex items-center gap-1.5 text-white/80">
                        <span className="h-2 w-2 rounded-full" style={{ background: TIER_META[t.tier].hex }} />
                        {TIER_SHORT[t.tier]}
                      </span>
                      <span className="num text-white/65">{t.count} req · {usd(t.cost)} · {queries > 0 ? Math.round((t.count / queries) * 100) : 0}%</span>
                    </div>
                  ))}
                </div>
                {/* How much traffic a smaller model absorbed instead of Claude. */}
                <div className="mt-3 rounded-lg bg-moss/10 px-3 py-2 text-[12px] leading-[1.5] text-white/75 ring-1 ring-moss/25">
                  <span className="num font-bold text-[#93D3AB]">{smallerSharePct}%</span> of requests were served by a smaller open model instead of Claude / a frontier model - only <span className="num font-semibold text-white/70">{frontierSharePct}%</span> needed the frontier.
                </div>
              </>
            )}
          </div>
        </div>
      </section>

      {/* Box 3b - observability */}
      <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.12s' }}>
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <div className={SECTION}>Observability</div>
          <span className="rounded-pill bg-white/10 px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-[.06em] text-white/55">Unity Gateway</span>
        </div>
        <p className="mb-4 max-w-[72ch] text-[12.5px] leading-[1.5] text-white/55">
          Every request through the gateway is observable - traces, usage, latency and guardrail activity - with nothing to wire up. In production these read from <span className="num text-white/75">system.serving.endpoint_usage</span> and <span className="num text-white/75">system.ai_gateway</span>.
        </p>
        {empty || !obs ? (
          <EmptyMini text="Observability signals - traces, latency percentiles, guardrail activity - appear here after your first request." />
        ) : (
          <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] gap-4 max-[820px]:grid-cols-1">
            {/* Signals panel */}
            <div className="grid grid-cols-3 gap-2.5 max-[520px]:grid-cols-2">
              <Signal label="Traces logged" value={obs.traces.toLocaleString()} sub="MLflow" />
              <Signal label="Inference tables" value="On" sub="system.serving" accent="#93D3AB" />
              <Signal label="Requests / min" value={formatRate1(obs.reqPerMin)} />
              <Signal label="Latency p50" value={formatLatency(obs.p50)} />
              <Signal label="Latency p95" value={formatLatency(obs.p95)} accent="#E3B876" />
              <Signal label="Error rate" value={formatPercent1(obs.errorRatePct)} accent="#93D3AB" />
              <Signal label="Guardrail blocks" value={obs.guardrailBlocks.toLocaleString()} sub="AI guardrails" />
              <Signal label="Rate-limit hits" value={obs.rateLimitHits.toLocaleString()} />
              <Signal label="Endpoints" value={byModel.length.toString()} sub="served" />
              <Signal label="Coding-agent calls" value={num0(codingAgentTotal)} sub={`${rangeDays}d`} accent="#C08BF2" />
              <Signal label="External MCP servers" value={mcpServersNow.toString()} sub="connected" accent="#67C7E8" />
            </div>
            {/* Latency sparkline */}
            <div className="rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
              <div className="mb-1 flex items-center justify-between">
                <span className={LBL}>Latency over session</span>
                <span className="num text-[11px] text-white/45">p95 {formatLatency(obs.p95)}</span>
              </div>
              <Sparkline values={obs.latSeries} color="#67C7E8" />
              <div className="mt-1 flex justify-between text-[10px] text-white/35"><span>oldest</span><span>latest</span></div>
            </div>
          </div>
        )}
        {/* Daily trends over a configurable time window (fabricated for the demo) */}
        <div className="mt-5 border-t border-white/[0.08] pt-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <span className={LBL}>Daily trends</span>
            <div className="flex min-w-[220px] items-center gap-2.5">
              <span className="text-[11px] font-semibold uppercase tracking-[.08em] text-white/45">Time range</span>
              <input type="range" min={7} max={90} step={1} value={rangeDays} onChange={(e) => setRangeDays(+e.target.value)} className="w-[130px] accent-[#67C7E8]" aria-label="Time range in days" />
              <span className="num w-[52px] text-[12px] font-semibold text-white">{rangeDays} days</span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3 max-[760px]:grid-cols-1">
            <MiniLine title="Daily requests" values={daily.requests} color="#FF6A54" days={rangeDays} fmt={num0} />
            <MiniLine title="Daily unique users" values={daily.uniqueUsers} color="#B487D0" days={rangeDays} fmt={num0} />
            <MiniLine title="Daily tokens used" values={daily.tokens} color="#67C7E8" days={rangeDays} fmt={num0} />
          </div>
        </div>
        <p className="num mt-4 text-[10.5px] leading-[1.5] text-white/40">
          Traces, latency and endpoint usage are captured live by the gateway. Guardrail, rate-limit, coding-agent and MCP-server counts and the daily trends are illustrative for this demo; in production they come from <span className="text-white/55">system.ai_gateway</span> and <span className="text-white/55">system.serving.endpoint_usage</span>.
        </p>
      </section>

      {/* Box 4 - projection */}
      <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.14s' }}>
        <div className="pointer-events-none absolute -bottom-24 -right-24 h-80 w-80 rounded-full bg-lava opacity-[.08] blur-3xl" />
        <div className="relative">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <div className={SECTION}>Cost projection</div>
            <span className={`rounded-pill px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-[.06em] ${measured ? 'bg-moss/20 text-[#93D3AB]' : 'bg-white/10 text-white/55'}`}>
              {measured ? 'from this session' : 'registry estimate'}
            </span>
          </div>
          <p className="mb-4 max-w-[70ch] text-[12.5px] leading-[1.5] text-white/55">
            Projected at <span className="num text-white/80">{routedPerQuery != null ? perQ(routedPerQuery) : '-'}</span> / query{measured ? ' (routed blend of the models you ran)' : ' (registry-estimated routed blend)'} across your traffic. The chart plots cumulative spend over 12 months versus routing every query to a frontier model.
          </p>

          <div className="grid grid-cols-2 gap-4 max-[520px]:grid-cols-1">
            <VizSlider label="Monthly active users" value={users} min={100} max={200000} step={100} onChange={setUsers} accent="accent-[#B487D0]" />
            <VizSlider label="Queries / user / month" value={perUserQ} min={1} max={2000} step={1} onChange={setPerUserQ} accent="accent-lava" />
          </div>

          <div className="mt-4 grid grid-cols-4 gap-2.5 max-[520px]:grid-cols-2">
            <Proj label="Per day" value={proj ? compact(proj.day) : '-'} />
            <Proj label="Per week" value={proj ? compact(proj.week) : '-'} />
            <Proj label="Per month" value={proj ? compact(proj.month) : '-'} />
            <Proj label="Per year" value={proj ? compact(proj.year) : '-'} accent />
          </div>

          <div className="mt-4 rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
            <div className="relative">
              {/* Cost view palette: frontier-only in blue, routed in green - no red. */}
              <RoiChart roi={roi} frontierColor="#7C8BF5" routedColor="#4FD79E" />
              {!roi && (
                <div className="absolute inset-0 grid place-items-center px-6 text-center">
                  <p className="max-w-[42ch] text-[12.5px] leading-[1.5] text-white/45">A routed-vs-frontier projection appears once there's a measurable gap between routing and frontier-only cost.</p>
                </div>
              )}
            </div>
            {roi && (
              <div className="mt-3 grid grid-cols-3 gap-2">
                <VizStat label="Frontier-only / yr" value={compact(roi.monthly.frontier * 12)} color="#9AA8F7" />
                <VizStat label="Routed / yr" value={compact(roi.monthly.routed * 12)} />
                <VizStat label="Saved / yr" value={compact(roi.savedYr)} color="#4FD79E" />
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Box 5 - activity log */}
      <section className="relative animate-[fadeUp_.5s_ease_both] rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.18s' }}>
        <div className={`${SECTION} mb-4`}>Activity log</div>
        {empty ? (
          <EmptyMini text="Each request you run is logged here - time, model, tier, latency, and cost - the raw material for the numbers above." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-[12.5px]">
              <thead>
                <tr className="text-left text-white/45">
                  <Th>Time</Th><Th>Source</Th><Th>Model</Th><Th>Tier</Th><Th right>Latency</Th><Th right>Cost</Th><Th right>Saved</Th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => <LogRow key={r.id} r={r} />)}
              </tbody>
            </table>
          </div>
        )}
        <p className="num mt-4 text-[10.5px] leading-[1.5] text-white/40">
          In production this is backed by the Unity Gateway usage tables (<span className="text-white/55">system.serving.endpoint_usage</span>) and <span className="text-white/55">system.billing.usage</span> - the same request, latency and cost data, queryable from Unity Catalog. The projection and routing-savings layers are what this view adds.
        </p>
      </section>
    </div>
  );
}

function LogRow({ r }: { r: RunRecord }) {
  const saved = r.baselineUsd - r.costUsd;
  return (
    <tr className="border-t border-white/[0.07]">
      <Td><span className="num text-white/60">{new Date(r.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span></Td>
      <Td>
        <span className="rounded-pill bg-white/10 px-2 py-0.5 text-[10.5px] font-semibold text-white/70">{r.source === 'compare' ? 'Compare' : 'Gateway'}</span>
        {r.sample && <span className="ml-1 rounded-pill bg-white/10 px-2 py-0.5 text-[10.5px] font-medium text-white/50">sample</span>}
        {r.optimized && <span className="ml-1 rounded-pill bg-plum/20 px-2 py-0.5 text-[10.5px] font-semibold text-[#CBA6E2]">✨ opt</span>}
      </Td>
      <Td><span className="font-medium text-white/90">{r.modelShort}</span></Td>
      <Td>
        <span className="inline-flex items-center gap-1.5 text-white/70">
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: TIER_META[r.tier].hex }} />
          {TIER_SHORT[r.tier]}
        </span>
      </Td>
      <Td right><span className="num text-white/70">{formatLatency(latOf(r))}</span></Td>
      <Td right><span className="num text-white/90">{usd(r.costUsd)}</span></Td>
      <Td right><span className={`num ${saved > 0 ? 'text-[#93D3AB]' : 'text-white/40'}`}>{saved > 0 ? usd(saved) : '-'}</span></Td>
    </tr>
  );
}

function Th({ children, right = false }: { children: React.ReactNode; right?: boolean }) {
  return <th className={`pb-2 font-body text-[10px] font-semibold uppercase tracking-[.1em] ${right ? 'text-right' : ''}`}>{children}</th>;
}
function Td({ children, right = false }: { children: React.ReactNode; right?: boolean }) {
  return <td className={`py-2.5 align-middle ${right ? 'text-right' : ''}`}>{children}</td>;
}

function Kpi({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="rounded-2xl bg-white/[0.04] px-4 py-3.5 ring-1 ring-white/10">
      <div className={LBL}>{label}</div>
      <div className="num mt-2 text-[22px] font-semibold leading-none tracking-[-.03em]" style={{ color: accent ?? '#fff' }}>{value}</div>
      {sub && <div className="num mt-1.5 text-[10.5px] text-white/45">{sub}</div>}
    </div>
  );
}

// The projection tiles show the INTELLIGENT-ROUTING (routed) spend, so the
// accented "Per year" tile is green to match the routed line in the chart - not
// red, which would read as the expensive frontier-only cost.
function Proj({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`rounded-2xl px-4 py-3.5 ring-1 ${accent ? 'bg-[#4FD79E]/[0.08] ring-[#4FD79E]/40' : 'bg-white/[0.04] ring-white/10'}`}>
      <div className={LBL}>{label}</div>
      <div className={`num mt-2 text-[20px] font-semibold leading-none tracking-[-.03em] ${accent ? 'text-[#4FD79E]' : 'text-white'}`}>{value}</div>
    </div>
  );
}

function VizSlider({ label, value, min, max, step, onChange, accent }: { label: string; value: number; min: number; max: number; step: number; onChange: (n: number) => void; accent: string }) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <span className={LBL}>{label}</span>
        <span className="num text-[12px] text-white">{value.toLocaleString()}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} className={`mt-1.5 w-full ${accent}`} />
    </div>
  );
}

function VizStat({ label, value, lava = false, color }: { label: string; value: string; lava?: boolean; color?: string }) {
  return (
    <div className="rounded-xl bg-black/25 px-3 py-2.5 ring-1 ring-white/10">
      <div className="font-body text-[9px] font-semibold uppercase tracking-[.1em] text-white/45">{label}</div>
      <div className={`num mt-1 text-[15px] font-medium leading-none tracking-[-.03em] ${!color && lava ? 'text-lava' : !color ? 'text-white' : ''}`} style={color ? { color } : undefined}>{value}</div>
    </div>
  );
}

function EmptyMini({ text }: { text: string }) {
  return <p className="rounded-xl bg-black/20 px-3.5 py-4 text-[12px] leading-[1.5] text-white/45 ring-1 ring-white/10">{text}</p>;
}

// One observability stat tile.
function Signal({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="rounded-xl bg-white/[0.04] px-3.5 py-3 ring-1 ring-white/10">
      <div className={LBL}>{label}</div>
      <div className="num mt-1.5 text-[18px] font-semibold leading-none tracking-[-.03em]" style={{ color: accent ?? '#fff' }}>{value}</div>
      {sub && <div className="num mt-1 text-[9.5px] uppercase tracking-[.08em] text-white/35">{sub}</div>}
    </div>
  );
}

// A labelled daily-trend line chart (title + latest value + filled polyline).
// Used for the daily requests / unique users / tokens trends.
function MiniLine({ title, values, color, days, fmt }: { title: string; values: number[]; color: string; days: number; fmt: (n: number) => string }) {
  const w = 240, h = 60, pad = 4;
  const max = Math.max(...values), min = Math.min(...values);
  const rng = max - min || 1;
  const x = (i: number) => (i / Math.max(1, values.length - 1)) * w;
  const y = (v: number) => h - pad - ((v - min) / rng) * (h - pad * 2);
  const line = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const area = `0,${h} ${line} ${w},${h}`;
  const latest = values[values.length - 1] ?? 0;
  return (
    <div className="rounded-2xl bg-white/[0.04] p-3.5 ring-1 ring-white/10">
      <div className="flex items-center justify-between">
        <span className={LBL}>{title}</span>
        <span className="num text-[14px] font-semibold" style={{ color }}>{fmt(latest)}</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="mt-2 h-14 w-full" role="img" aria-label={title}>
        <polygon points={area} fill={color} fillOpacity={0.12} />
        <polyline points={line} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      </svg>
      <div className="mt-1 flex justify-between text-[9.5px] text-white/35"><span>{days}d ago</span><span>today</span></div>
    </div>
  );
}

// Minimal inline latency sparkline (no chart lib) - a filled polyline over the
// session's requests in chronological order.
function Sparkline({ values, color = '#67C7E8' }: { values: number[]; color?: string }) {
  if (values.length < 2) return <div className="grid h-12 place-items-center text-[11px] text-white/40">One request so far - the trend fills in as you run more.</div>;
  const w = 240, h = 44, pad = 3;
  const max = Math.max(...values), min = Math.min(...values);
  const rng = max - min || 1;
  const x = (i: number) => (i / (values.length - 1)) * w;
  const y = (v: number) => h - pad - ((v - min) / rng) * (h - pad * 2);
  const line = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const area = `0,${h} ${line} ${w},${h}`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-12 w-full" role="img" aria-label="Latency over the session">
      <polygon points={area} fill={color} fillOpacity={0.12} />
      <polyline points={line} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
