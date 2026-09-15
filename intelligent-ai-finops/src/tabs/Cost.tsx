import { useEffect, useMemo, useState } from 'react';
import { useConfig } from '../api/useConfig';
import { useSession, type RunRecord } from '../store/session';
import { TIER_META, TIER_SHORT, type ModelDef, type Tier } from '../api/types';
import { RoiChart, compact, computeRoi, perQuery, type Roi } from '../components/RoutingViz';
import { formatMoney, formatPerQuery, formatPercent, formatPercent1, formatRate1, formatLatency } from '../lib/format';
import { getCodingAgents, getReliability, type CodingAgents as CodingAgentsData, type Reliability as ReliabilityData } from '../api/client';

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

// A representative user roster per group (team), for the users-and-groups spend
// view. Seeded sample runs carry a `team`; each run is deterministically
// attributed to one user in that team so the breakdown is stable across renders.
const TEAM_USERS: Record<string, string[]> = {
  Support: ['ava.chen', 'marco.diaz'],
  Finance: ['priya.nair', 'tom.wells'],
  Engineering: ['sam.okafor', 'lena.fischer'],
  Analytics: ['kaito.mori', 'dana.levin'],
};
const hashStr = (s: string) => [...s].reduce((a, c) => a + c.charCodeAt(0), 0);

const LBL = 'font-body text-[9.5px] font-semibold uppercase tracking-[.14em] text-white/45';
const SECTION = 'font-display text-[13px] font-bold uppercase tracking-[.15em] text-[#7FB6F2]';
const DAYS_PER_MONTH = 30;

// Fallback per-tier serving latency (ms) for runs that didn't record one (e.g.
// older sample rows) - keeps the observability latency stats populated.
const TIER_LAT: Record<Tier, number> = { 'small-oss': 560, 'large-oss': 1500, frontier: 3100 };
const latOf = (r: RunRecord) => r.latencyMs ?? TIER_LAT[r.tier];

// ---- V2: real cost/usage from Unity Catalog system tables --------------------
interface CostOverview {
  source: string; windowDays: number;
  totals: { spendUsd: number; requests: number };
  byModel: { model: string; tier: Tier; cost: number; count: number; avgLatencyMs: number; p50LatencyMs?: number; p95LatencyMs?: number }[];
  byTier: { tier: Tier; cost: number; count: number }[];
  byUser: { user: string; group: string; cost: number; count: number }[];
  byGroup: { group: string; cost: number; count: number }[];
  daily: { date: string; requests: number; users: number }[];
  recent: { ts: string; user: string; model: string; tier: Tier; costUsd: number; latencyMs: number }[];
  frontierShare: { frontier: number; smaller: number; smallerPct: number };
  frontierDownroute: { requests: number; frontierSpendUsd: number; ifLargeUsd: number; ifSmallUsd: number; savedLargePct: number; savedSmallPct: number };
  counterfactual: Counterfactual;
}

interface CfTier {
  tier: Tier; requests: number; actualCost: number; inTok: number; outTok: number;
  cheapestInTierCost: number; cheapestInTierModel: string | null;
  tierBelowCost: number | null; tierBelowModel: string | null;
}
interface Counterfactual {
  dbuToUsd: number; windowDays: number; actualTotalUsd: number;
  tiers: CfTier[]; defaults: Record<string, number>;
}

function useCostOverview(days: number): { ov: CostOverview | 'demo' | null; loading: boolean } {
  const [ov, setOv] = useState<CostOverview | 'demo' | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetch(`/api/cost/overview?days=${days}`)
      .then((r) => r.json())
      .then((d) => { if (alive) { setOv(d && d.source === 'system_tables' ? d : 'demo'); setLoading(false); } })
      .catch(() => { if (alive) { setOv('demo'); setLoading(false); } });
    return () => { alive = false; };
  }, [days]);
  return { ov, loading };
}

// Dispatcher: render the REAL system-tables view when the App SP can read them,
// else fall back to the synthesised demo session (so the app never hard-fails).
// While the (cold) system-tables scan is in flight, show the demo view with a
// "loading live usage" banner so the tab never looks like it's hanging.
export function Cost() {
  const [rangeDays, setRangeDays] = useState(30);
  const { ov, loading } = useCostOverview(rangeDays);
  if (ov && ov !== 'demo') return <RealCost data={ov} rangeDays={rangeDays} setRangeDays={setRangeDays} />;
  return <DemoCost loadingReal={loading} />;
}

function RealCost({ data, rangeDays, setRangeDays }: { data: CostOverview; rangeDays: number; setRangeDays: (n: number) => void }) {
  const [users, setUsers] = useState(5000);
  const [perUserQ, setPerUserQ] = useState(50);
  const [projOpen, setProjOpen] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const vol = users * perUserQ;

  const spend = data.totals.spendUsd, reqs = data.totals.requests;
  const avg = reqs ? spend / reqs : 0;
  const dr = data.frontierDownroute, fs = data.frontierShare;
  const potentialSaved = Math.max(0, dr.frontierSpendUsd - dr.ifLargeUsd);
  const maxModelCost = Math.max(...data.byModel.map((m) => m.cost), 1e-9);
  const maxGroupCost = Math.max(...data.byGroup.map((g) => g.cost), 1e-9);
  const maxUserCost = Math.max(...data.byUser.map((u) => u.cost), 1e-9);
  const totalGroupCost = data.byGroup.reduce((s, g) => s + g.cost, 0) || 1e-9;

  // Spend-anomaly detection: flag the latest day if its request volume is a
  // statistical outlier vs the trailing mean (z-score >= 2 and >25% above).
  const anomaly = useMemo(() => {
    const vals = data.daily.map((d) => d.requests);
    if (vals.length < 5) return null;
    const hist = vals.slice(0, -1);
    const mean = hist.reduce((a, b) => a + b, 0) / hist.length;
    const sd = Math.sqrt(hist.reduce((a, b) => a + (b - mean) ** 2, 0) / hist.length) || 1;
    const last = vals[vals.length - 1];
    const z = (last - mean) / sd;
    if (z >= 2 && last > mean * 1.25) {
      return { last, mean: Math.round(mean), z: z.toFixed(1), pctOver: Math.round((last / mean - 1) * 100), date: data.daily[data.daily.length - 1].date };
    }
    return null;
  }, [data.daily]);

  // Projection: today's avg/query (mostly frontier) vs the same traffic once the
  // routine frontier work is routed down to large OSS.
  const routedPerQ = reqs ? Math.max(0, spend - (dr.frontierSpendUsd - dr.ifLargeUsd)) / reqs : 0;
  const roi = { monthly: { frontier: avg * vol, routed: routedPerQ * vol }, savedYr: (avg - routedPerQ) * vol * 12 };
  const proj = { day: (routedPerQ * vol) / DAYS_PER_MONTH, week: ((routedPerQ * vol) / DAYS_PER_MONTH) * 7, month: routedPerQ * vol, year: routedPerQ * vol * 12 };

  return (
    <div className="flex flex-col gap-[22px] text-white">
      {/* intro + live badge */}
      <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[26px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4">
        <div className="pointer-events-none absolute -right-32 -top-24 h-96 w-96 rounded-full bg-lava opacity-[.10] blur-3xl" />
        <div className="relative">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="font-body text-[11px] font-semibold uppercase tracking-[.22em] text-lava">Cost view</span>
            <span className="rounded-pill bg-[#4FD79E]/15 px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-[.06em] text-[#4FD79E] ring-1 ring-[#4FD79E]/30">● Live · system tables · {data.windowDays}d</span>
            {anomaly && <AnomalyTip anomaly={anomaly} />}
          </div>
          <h2 className="max-w-[26ch] font-display text-[clamp(24px,3.2vw,40px)] font-bold leading-[1.05] tracking-[-.03em]">Real spend from Unity Catalog - and where routing would cut it.</h2>
          <p className="mt-3 max-w-[70ch] font-body text-[15px] leading-[1.55] text-white/65">Pulled live from <span className="num text-white/85">system.ai_gateway.usage</span> via this app's service principal. Every number below is measured, not synthesised. Cost = real tokens × the published DBU rate card.</p>
        </div>
      </section>

      {/* KPIs */}
      <section className="relative animate-[fadeUp_.5s_ease_both] rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.06s' }}>
        <div className={`${SECTION} mb-4`}>Overall spend · last {data.windowDays} days</div>
        <div className="grid grid-cols-4 gap-3 max-[720px]:grid-cols-2">
          <Kpi label="Total spend" value={usd(spend)} accent="#FF6A54" />
          <Kpi label="Requests" value={reqs.toLocaleString()} />
          <Kpi label="Avg cost / query" value={perQ(avg)} />
          <Kpi label="Potential savings" value={usd(potentialSaved)} sub={`route frontier → OSS (−${dr.savedLargePct}%)`} accent="#4FD79E" />
        </div>
      </section>

      {/* Counterfactual: this real traffic replayed through the router */}
      <Counterfactual cf={data.counterfactual} />

      {/* Coding-agent cost tracker - real per-harness + per-developer spend */}
      <CodingAgents days={rangeDays} />

      {/* Reliability & fallback - real routing attempts from routing_information */}
      <Reliability days={rangeDays} />

      {/* Where the spend goes */}
      <section className="relative animate-[fadeUp_.5s_ease_both] rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.1s' }}>
        <div className={`${SECTION} mb-4`}>Where the spend goes</div>
        <div className="grid grid-cols-2 gap-4 max-[760px]:grid-cols-1">
          <div className="rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
            <div className="mb-3 font-body text-[11px] font-semibold uppercase tracking-[.16em] text-white/45">Spend by model</div>
            <div className="flex flex-col gap-2.5">
              {data.byModel.slice(0, 8).map((m) => (
                <div key={m.model}>
                  <div className="mb-1 flex items-center justify-between text-[12px]">
                    <span className="num flex items-center gap-1.5 font-medium text-white/85"><span className="h-2 w-2 rounded-full" style={{ background: TIER_META[m.tier].hex }} />{m.model}</span>
                    <span className="num text-white/70">{usd(m.cost)} · {num0(m.count)}×</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full" style={{ width: `${(m.cost / maxModelCost) * 100}%`, background: TIER_META[m.tier].hex }} /></div>
                  {(m.p50LatencyMs || m.avgLatencyMs) ? (
                    <div className="num mt-1 flex items-center gap-3 text-[10px] text-white/40">
                      <span>p50 {formatLatency(m.p50LatencyMs || m.avgLatencyMs)}</span>
                      {m.p95LatencyMs ? <span>p95 {formatLatency(m.p95LatencyMs)}</span> : null}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
            <div className="mb-3 font-body text-[11px] font-semibold uppercase tracking-[.16em] text-white/45">Requests by tier</div>
            <div className="flex h-3 overflow-hidden rounded-full bg-white/[0.06]">
              {data.byTier.map((t) => { const share = reqs ? (t.count / reqs) * 100 : 0; return share > 0 ? <div key={t.tier} style={{ width: `${share}%`, background: TIER_META[t.tier].hex }} title={`${TIER_SHORT[t.tier]}: ${t.count}`} /> : null; })}
            </div>
            <div className="mt-3 flex flex-col gap-2">
              {data.byTier.map((t) => (
                <div key={t.tier} className="flex items-center justify-between text-[12px]">
                  <span className="flex items-center gap-1.5 text-white/80"><span className="h-2 w-2 rounded-full" style={{ background: TIER_META[t.tier].hex }} />{TIER_SHORT[t.tier]}</span>
                  <span className="num text-white/65">{num0(t.count)} req · {usd(t.cost)} · {reqs ? Math.round((t.count / reqs) * 100) : 0}%</span>
                </div>
              ))}
            </div>
            <div className="mt-3 rounded-lg bg-moss/10 p-3 ring-1 ring-moss/25">
              <p className="text-[12px] leading-[1.5] text-white/75"><span className="num font-bold text-[#93D3AB]">{fs.smallerPct}%</span> of requests used a smaller open model; <span className="num font-semibold text-white/70">{100 - fs.smallerPct}%</span> went to the frontier.</p>
              <p className="mt-2 border-t border-white/10 pt-2 text-[11px] leading-[1.5] text-white/55">
                Retrospective: the frontier handled <span className="num text-white/75">{num0(dr.requests)}</span> requests costing <span className="num text-lava">{usd(dr.frontierSpendUsd)}</span>. Routine <span className="text-white/70">"how-to / summarize / code / reset"</span> asks rarely need it - the same work on <b className="text-[#93D3AB]">large OSS</b> would be ~<span className="num">{usd(dr.ifLargeUsd)}</span> (<span className="text-[#93D3AB]">−{dr.savedLargePct}%</span>), on <b className="text-[#93D3AB]">small OSS</b> ~<span className="num">{usd(dr.ifSmallUsd)}</span> (<span className="text-[#93D3AB]">−{dr.savedSmallPct}%</span>).
              </p>
            </div>
          </div>
        </div>
        {/* Chargeback / showback - who the spend is attributed to */}
        <div className="mt-4 rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
          <div className="mb-3 font-body text-[11px] font-semibold uppercase tracking-[.16em] text-white/45">Chargeback · spend by team &amp; user</div>
          <div className="grid grid-cols-2 gap-5 max-[760px]:grid-cols-1">
            <div>
              <div className={`${LBL} mb-2`}>Teams (showback)</div>
              <div className="flex flex-col gap-2.5">
                {data.byGroup.slice(0, 6).map((g) => (
                  <div key={g.group}>
                    <div className="mb-1 flex items-center justify-between text-[12px]"><span className="num font-medium text-white/85">{g.group}</span><span className="num text-white/70">{usd(g.cost)} · {Math.round((g.cost / totalGroupCost) * 100)}% · {num0(g.count)}×</span></div>
                    <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-[#7FB6F2]" style={{ width: `${(g.cost / maxGroupCost) * 100}%` }} /></div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className={`${LBL} mb-2`}>Top users</div>
              <div className="flex flex-col gap-2.5">
                {data.byUser.slice(0, 6).map((u) => (
                  <div key={u.user}>
                    <div className="mb-1 flex items-center justify-between text-[12px]"><span className="num font-medium text-white/85">{u.user}</span><span className="num text-white/70">{usd(u.cost)} · {num0(u.count)}×</span></div>
                    <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-[#B487D0]" style={{ width: `${(u.cost / maxUserCost) * 100}%` }} /></div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Daily trends (real) */}
      <section className="relative animate-[fadeUp_.5s_ease_both] rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.12s' }}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className={SECTION}>Daily trends</div>
          <div className="flex min-w-[220px] items-center gap-2.5">
            <span className="text-[11px] font-semibold uppercase tracking-[.08em] text-white/45">Time range</span>
            <input type="range" min={7} max={90} step={1} value={rangeDays} onChange={(e) => setRangeDays(+e.target.value)} className="w-[130px] accent-[#67C7E8]" aria-label="Time range in days" />
            <span className="num w-[52px] text-[12px] font-semibold text-white">{rangeDays} days</span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 max-[760px]:grid-cols-1">
          <MiniLine title="Daily requests" values={data.daily.map((d) => d.requests)} color="#FF6A54" days={rangeDays} fmt={num0} />
          <MiniLine title="Daily unique users" values={data.daily.map((d) => d.users)} color="#B487D0" days={rangeDays} fmt={num0} />
        </div>
      </section>

      {/* Cost projection (collapsible, min by default) */}
      <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.16s' }}>
        <div className="pointer-events-none absolute -bottom-24 -right-24 h-80 w-80 rounded-full bg-lava opacity-[.08] blur-3xl" />
        <div className="relative">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <div className={SECTION}>Cost projection</div>
            <button onClick={() => setProjOpen((v) => !v)} className="ml-auto rounded-pill bg-white/10 px-3 py-1 text-[11px] font-semibold text-white/75 ring-1 ring-white/10 transition hover:bg-white/15 hover:text-white">{projOpen ? 'Minimize ▲' : 'Expand ▼'}</button>
          </div>
          {!projOpen && <p className="text-[12.5px] leading-[1.5] text-white/50">Scale today's real per-query cost to your traffic and see the routed-down projection. <button onClick={() => setProjOpen(true)} className="font-semibold text-[#7FB6F2] hover:underline">Expand</button>.</p>}
          {projOpen && (<>
            <p className="mb-4 max-w-[70ch] text-[12.5px] leading-[1.5] text-white/55">At today's measured <span className="num text-white/80">{perQ(avg)}</span> / query, scaled across your traffic - versus the same traffic with routine frontier work routed down to OSS.</p>
            <div className="grid grid-cols-2 gap-4 max-[520px]:grid-cols-1">
              <VizSlider label="Monthly active users" value={users} min={100} max={200000} step={100} onChange={setUsers} accent="accent-[#B487D0]" />
              <VizSlider label="Queries / user / month" value={perUserQ} min={1} max={2000} step={1} onChange={setPerUserQ} accent="accent-lava" />
            </div>
            <div className="mt-4 grid grid-cols-4 gap-2.5 max-[520px]:grid-cols-2">
              <Proj label="Per day" value={compact(proj.day)} />
              <Proj label="Per week" value={compact(proj.week)} />
              <Proj label="Per month" value={compact(proj.month)} />
              <Proj label="Per year" value={compact(proj.year)} accent />
            </div>
            <div className="mt-4 rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
              <RoiChart roi={roi as Roi} frontierColor="#7C8BF5" routedColor="#4FD79E" />
              <div className="mt-3 grid grid-cols-3 gap-2">
                <VizStat label="Today (mostly frontier) / yr" value={compact(roi.monthly.frontier * 12)} color="#9AA8F7" />
                <VizStat label="Routed / yr" value={compact(roi.monthly.routed * 12)} />
                <VizStat label="Saved / yr" value={compact(roi.savedYr)} color="#4FD79E" />
              </div>
            </div>
          </>)}
        </div>
      </section>

      {/* Activity log (collapsible, min by default) - real recent requests */}
      <section className="relative animate-[fadeUp_.5s_ease_both] rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.2s' }}>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <div className={SECTION}>Recent activity</div>
          <button onClick={() => setLogOpen((v) => !v)} className="ml-auto rounded-pill bg-white/10 px-3 py-1 text-[11px] font-semibold text-white/75 ring-1 ring-white/10 transition hover:bg-white/15 hover:text-white">{logOpen ? 'Minimize ▲' : 'Expand ▼'}</button>
        </div>
        {!logOpen && <p className="text-[12.5px] leading-[1.5] text-white/50">The {data.recent.length} most recent gateway requests. <button onClick={() => setLogOpen(true)} className="font-semibold text-[#7FB6F2] hover:underline">Expand</button> to view.</p>}
        {logOpen && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-[12.5px]">
              <thead><tr className="text-left text-white/45"><Th>Time</Th><Th>User</Th><Th>Model</Th><Th>Tier</Th><Th right>Latency</Th><Th right>Cost</Th></tr></thead>
              <tbody>
                {data.recent.map((r, i) => (
                  <tr key={i} className="border-t border-white/[0.07]">
                    <Td><span className="num text-white/60">{new Date(r.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span></Td>
                    <Td><span className="num text-white/80">{r.user}</span></Td>
                    <Td><span className="num text-white/90">{r.model}</span></Td>
                    <Td><span className="inline-flex items-center gap-1.5 text-white/70"><span className="h-1.5 w-1.5 rounded-full" style={{ background: TIER_META[r.tier].hex }} />{TIER_SHORT[r.tier]}</span></Td>
                    <Td right><span className="num text-white/70">{formatLatency(r.latencyMs)}</span></Td>
                    <Td right><span className="num text-white/90">{usd(r.costUsd)}</span></Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="num mt-4 text-[10.5px] leading-[1.5] text-white/40">Live from <span className="text-white/55">system.ai_gateway.usage</span> via the app's service principal. Cost = real tokens × the published DBU rate card.</p>
      </section>
    </div>
  );
}

function DemoCost({ loadingReal = false }: { loadingReal?: boolean }) {
  const cfg = useConfig();
  const { runs, queries, spendUsd, baseUsd } = useSession();
  const [users, setUsers] = useState(5000);
  const [perUserQ, setPerUserQ] = useState(50);
  const monthlyVol = users * perUserQ;
  // Observability time window (days) for the daily trend charts.
  const [rangeDays, setRangeDays] = useState(30);
  // Cost projection + Activity log are collapsible and minimized by default.
  const [projOpen, setProjOpen] = useState(false);
  const [logOpen, setLogOpen] = useState(false);

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

  // Spend by group (team) and by user - the users-and-groups view. Live runs with
  // no team bucket as "Other" / "you (this session)".
  const byGroup = useMemo(() => {
    const map = new Map<string, { group: string; cost: number; count: number }>();
    for (const r of runs) {
      const g = r.team ?? 'Other';
      const e = map.get(g) ?? { group: g, cost: 0, count: 0 };
      e.cost += r.costUsd; e.count += 1; map.set(g, e);
    }
    return [...map.values()].sort((a, b) => b.cost - a.cost);
  }, [runs]);
  const byUser = useMemo(() => {
    const map = new Map<string, { user: string; group: string; cost: number; count: number }>();
    for (const r of runs) {
      const roster = r.team ? TEAM_USERS[r.team] : undefined;
      const user = roster ? roster[hashStr(r.id) % roster.length] : 'you (this session)';
      const group = r.team ?? 'Other';
      const e = map.get(user) ?? { user, group, cost: 0, count: 0 };
      e.cost += r.costUsd; e.count += 1; map.set(user, e);
    }
    return [...map.values()].sort((a, b) => b.cost - a.cost);
  }, [runs]);

  const maxModelCost = Math.max(...byModel.map((m) => m.cost), 1e-9);
  const maxGroupCost = Math.max(...byGroup.map((g) => g.cost), 1e-9);
  const maxUserCost = Math.max(...byUser.map((u) => u.cost), 1e-9);
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
    const codingAgent = mk(codingBase, 5.9);
    const mcpServers = Array.from({ length: n }, (_, i) => 6 + Math.round((i / Math.max(1, n - 1)) * 8) + (Math.sin(9 + i) > 0.7 ? 1 : 0));
    return { requests, uniqueUsers, codingAgent, mcpServers };
  }, [rangeDays, monthlyVol, users]);
  const codingAgentTotal = daily.codingAgent.reduce((s, v) => s + v, 0);
  const mcpServersNow = daily.mcpServers[daily.mcpServers.length - 1] ?? 0;

  return (
    <div className="flex flex-col gap-[22px] text-white">
      {/* While the (cold) system-tables scan is in flight, show a live-usage banner
          so the demo view reads as a placeholder, not the final answer. */}
      {loadingReal && (
        <div className="flex items-center gap-3 rounded-2xl bg-white/[0.05] px-5 py-3 ring-1 ring-white/10">
          <span className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-white/25 border-t-[#8FC1F0]" />
          <span className="text-[12.5px] font-medium text-white/70">Loading live usage from Unity Catalog system tables… (showing a sample session meanwhile; a cold serverless warehouse can take ~10-20s on the first load)</span>
        </div>
      )}
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
                {/* Retrospective: how traffic split FM vs OSS, and what routing avoided. */}
                <div className="mt-3 rounded-lg bg-moss/10 p-3 ring-1 ring-moss/25">
                  <p className="text-[12px] leading-[1.5] text-white/75">
                    <span className="num font-bold text-[#93D3AB]">{smallerSharePct}%</span> of requests were served by a smaller open model instead of Claude / a frontier model - only <span className="num font-semibold text-white/70">{frontierSharePct}%</span> needed the frontier.
                  </p>
                  <div className="mt-2.5 flex flex-col gap-1.5">
                    {byTier.map((t) => {
                      const share = queries > 0 ? (t.count / queries) * 100 : 0;
                      return (
                        <div key={t.tier} className="flex items-center gap-2">
                          <span className="w-[74px] shrink-0 text-[10.5px] text-white/55">{TIER_SHORT[t.tier]}</span>
                          <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                            <div className="h-full rounded-full" style={{ width: `${share}%`, background: TIER_META[t.tier].hex }} />
                          </div>
                          <span className="num w-[70px] shrink-0 text-right text-[10.5px] text-white/55">{t.count} · {Math.round(share)}%</span>
                        </div>
                      );
                    })}
                  </div>
                  <p className="mt-2 text-[11px] leading-[1.5] text-white/55">
                    Retrospective: the frontier handled <span className="num text-white/75">{frontierReqCount}</span> request{frontierReqCount === 1 ? '' : 's'}; routing kept the other <span className="num text-[#93D3AB]">{smallerSharePct}%</span> on OSS, avoiding <span className="num text-[#93D3AB]">{usd(savedSession)}</span> vs sending everything to the frontier.
                  </p>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Users & groups view - who the spend is attributed to */}
        {!empty && (
          <div className="mt-4 rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
            <div className="mb-3 font-body text-[11px] font-semibold uppercase tracking-[.16em] text-white/45">Spend by user &amp; group</div>
            <div className="grid grid-cols-2 gap-5 max-[760px]:grid-cols-1">
              <div>
                <div className={`${LBL} mb-2`}>Groups</div>
                <div className="flex flex-col gap-2.5">
                  {byGroup.map((g) => (
                    <div key={g.group}>
                      <div className="mb-1 flex items-center justify-between text-[12px]">
                        <span className="font-medium text-white/85">{g.group}</span>
                        <span className="num text-white/70">{usd(g.cost)} · {g.count}×</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
                        <div className="h-full rounded-full bg-[#7FB6F2]" style={{ width: `${(g.cost / maxGroupCost) * 100}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <div className={`${LBL} mb-2`}>Top users</div>
                <div className="flex flex-col gap-2.5">
                  {byUser.slice(0, 6).map((u) => (
                    <div key={u.user}>
                      <div className="mb-1 flex items-center justify-between text-[12px]">
                        <span className="num font-medium text-white/85">{u.user} <span className="text-white/40">· {u.group}</span></span>
                        <span className="num text-white/70">{usd(u.cost)} · {u.count}×</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
                        <div className="h-full rounded-full bg-[#B487D0]" style={{ width: `${(u.cost / maxUserCost) * 100}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <p className="num mt-3 text-[10px] leading-[1.5] text-white/35">Attributed from each request's group tag; per-user attribution in production comes from the gateway's authenticated identity (system.ai_gateway requester).</p>
          </div>
        )}
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
          <div className="grid grid-cols-2 gap-3 max-[760px]:grid-cols-1">
            <MiniLine title="Daily requests" values={daily.requests} color="#FF6A54" days={rangeDays} fmt={num0} />
            <MiniLine title="Daily unique users" values={daily.uniqueUsers} color="#B487D0" days={rangeDays} fmt={num0} />
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
            <button onClick={() => setProjOpen((v) => !v)} className="ml-auto rounded-pill bg-white/10 px-3 py-1 text-[11px] font-semibold text-white/75 ring-1 ring-white/10 transition hover:bg-white/15 hover:text-white">
              {projOpen ? 'Minimize ▲' : 'Expand ▼'}
            </button>
          </div>
          {!projOpen && (
            <p className="text-[12.5px] leading-[1.5] text-white/50">Projected spend and routing savings at your traffic. <button onClick={() => setProjOpen(true)} className="font-semibold text-[#7FB6F2] underline-offset-2 hover:underline">Expand</button> to edit the traffic inputs and view the chart.</p>
          )}
          {projOpen && (<>
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
          </>)}
        </div>
      </section>

      {/* Box 5 - activity log */}
      <section className="relative animate-[fadeUp_.5s_ease_both] rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.18s' }}>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <div className={SECTION}>Activity log</div>
          <button onClick={() => setLogOpen((v) => !v)} className="ml-auto rounded-pill bg-white/10 px-3 py-1 text-[11px] font-semibold text-white/75 ring-1 ring-white/10 transition hover:bg-white/15 hover:text-white">
            {logOpen ? 'Minimize ▲' : 'Expand ▼'}
          </button>
        </div>
        {!logOpen && (
          <p className="text-[12.5px] leading-[1.5] text-white/50">{queries.toLocaleString()} request{queries === 1 ? '' : 's'} logged this session. <button onClick={() => setLogOpen(true)} className="font-semibold text-[#7FB6F2] underline-offset-2 hover:underline">Expand</button> to view the per-request table.</p>
        )}
        {logOpen && (<>
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
        </>)}
      </section>
    </div>
  );
}

// ---- Counterfactual: replay the customer's REAL traffic through the router ----
// The FinOps proof, computed on their own bill. For each tier we reprice the
// tier's real tokens at the cheapest model IN that tier (a provable floor) and
// at the cheapest model in the tier BELOW (the routed-down projection); a
// downgrade slider blends the two. Every dollar here traces to real tokens x the
// published rate card, so it's the customer's own spend, not a synthetic session.
function Counterfactual({ cf }: { cf: Counterfactual }) {
  // Downgrade fraction per tier (share of that tier's traffic a lower tier clears).
  const [frac, setFrac] = useState<Record<string, number>>(() => ({
    frontier: Math.round((cf.defaults['frontier'] ?? 0.7) * 100),
    'large-oss': Math.round((cf.defaults['large-oss'] ?? 0.6) * 100),
    'small-oss': 0,
  }));

  const m = useMemo(() => {
    // routed cost per tier = f · (tier-below cheapest) + (1-f) · (cheapest-in-tier).
    // A provable "floor" keeps everything in its own tier (f=0) but on the cheapest
    // model of that tier - zero cross-tier quality assumption.
    let routed = 0, floor = 0;
    const rows = cf.tiers.map((t) => {
      const f = t.tierBelowCost == null ? 0 : (frac[t.tier] ?? 0) / 100;
      const routedTier = t.tierBelowCost == null ? t.cheapestInTierCost : f * t.tierBelowCost + (1 - f) * t.cheapestInTierCost;
      routed += routedTier;
      floor += t.cheapestInTierCost;
      return { ...t, routedTier };
    });
    const actual = cf.actualTotalUsd;
    const savedWin = Math.max(0, actual - routed);
    const savedPct = actual > 0 ? (savedWin / actual) * 100 : 0;
    const yrMult = cf.windowDays > 0 ? 365 / cf.windowDays : 12;
    return { rows, actual, routed, floor, savedWin, savedPct, savedYr: savedWin * yrMult, floorSavedWin: Math.max(0, actual - floor), yrMult };
  }, [cf, frac]);

  const maxBar = Math.max(m.actual, m.routed, 1e-9);

  return (
    <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.08s' }}>
      <div className="pointer-events-none absolute -right-28 -top-24 h-96 w-96 rounded-full bg-[#4FD79E] opacity-[.08] blur-3xl" />
      <div className="relative">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <div className={SECTION}>If this traffic had gone through the router</div>
          <span className="rounded-pill bg-[#4FD79E]/15 px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-[.06em] text-[#4FD79E] ring-1 ring-[#4FD79E]/30">● Your bill, replayed</span>
        </div>
        <p className="mb-4 max-w-[74ch] font-body text-[13px] leading-[1.55] text-white/60">
          We take the <span className="font-semibold text-white/85">real {m.actual > 0 ? usd(m.actual) : ''} you spent</span> over the last {cf.windowDays} days and reprice the exact same tokens as if the router had handled every request - cheapest model that clears each tier's bar, with a share routed one tier down. Move the sliders to set how aggressive the routing is.
        </p>

        {/* Headline: actual → routed → saved/yr */}
        <div className="grid grid-cols-4 gap-3 max-[720px]:grid-cols-2">
          <Kpi label={`Actual · ${cf.windowDays}d`} value={usd(m.actual)} accent="#FF6A54" />
          <Kpi label={`Routed · ${cf.windowDays}d`} value={usd(m.routed)} accent="#4FD79E" />
          <Kpi label={`Saved · ${cf.windowDays}d`} value={usd(m.savedWin)} sub={`${formatPercent1(m.savedPct)} of spend`} accent="#4FD79E" />
          <Kpi label="Saved / year" value={compact(m.savedYr)} sub={`at this ${cf.windowDays}d run-rate`} accent="#4FD79E" />
        </div>

        {/* Actual vs routed bars */}
        <div className="mt-4 rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
          <div className="flex flex-col gap-3">
            <BarRow label="Actual spend" value={m.actual} max={maxBar} color="#FF6A54" fmt={usd} />
            <BarRow label="Routed (projected)" value={m.routed} max={maxBar} color="#4FD79E" fmt={usd} />
          </div>
          <p className="mt-3 border-t border-white/10 pt-3 text-[11.5px] leading-[1.5] text-white/55">
            Provable floor: even with <span className="font-semibold text-white/75">no tier changes</span> - just picking the cheapest model within each tier you already use - this traffic would cost <span className="num text-[#93D3AB]">{usd(m.floor)}</span> (save <span className="num text-[#93D3AB]">{usd(m.floorSavedWin)}</span>). The sliders below add tier-down routing on top.
          </p>
        </div>

        {/* Downgrade sliders */}
        <div className="mt-4 grid grid-cols-2 gap-4 max-[520px]:grid-cols-1">
          <VizSlider label="Frontier → cheaper tier (%)" value={frac['frontier']} min={0} max={100} step={5} onChange={(v) => setFrac((s) => ({ ...s, frontier: v }))} accent="accent-[#B487D0]" />
          <VizSlider label="Large OSS → small OSS (%)" value={frac['large-oss']} min={0} max={100} step={5} onChange={(v) => setFrac((s) => ({ ...s, 'large-oss': v }))} accent="accent-[#67C7E8]" />
        </div>

        {/* Per-tier detail */}
        <div className="mt-4 overflow-x-auto rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
          <table className="w-full min-w-[560px] border-collapse text-[12px]">
            <thead>
              <tr className="text-left text-white/45">
                <Th>Tier</Th><Th right>Requests</Th><Th right>Actual</Th><Th right>Cheapest in tier</Th><Th right>Routed down to</Th><Th right>Routed</Th>
              </tr>
            </thead>
            <tbody>
              {m.rows.map((t) => (
                <tr key={t.tier} className="border-t border-white/[0.07]">
                  <Td><span className="inline-flex items-center gap-1.5 text-white/85"><span className="h-2 w-2 rounded-full" style={{ background: TIER_META[t.tier].hex }} />{TIER_SHORT[t.tier]}</span></Td>
                  <Td right><span className="num text-white/65">{num0(t.requests)}</span></Td>
                  <Td right><span className="num text-white/85">{usd(t.actualCost)}</span></Td>
                  <Td right><span className="num text-white/60">{usd(t.cheapestInTierCost)}<span className="ml-1 text-white/35">{t.cheapestInTierModel}</span></span></Td>
                  <Td right><span className="num text-white/60">{t.tierBelowCost == null ? <span className="text-white/30">-</span> : <>{usd(t.tierBelowCost)}<span className="ml-1 text-white/35">{t.tierBelowModel}</span></>}</span></Td>
                  <Td right><span className="num font-semibold text-[#93D3AB]">{usd(t.routedTier)}</span></Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="num mt-3 text-[10.5px] leading-[1.5] text-white/40">
          Computed on real tokens from <span className="text-white/55">system.ai_gateway.usage</span> × the published DBU rate card. The tier-down share is an assumption you control (the router classifies per prompt in production); the cheapest-in-tier floor needs no assumption.
        </p>
      </div>
    </section>
  );
}

// ---- Coding-agent cost tracker -------------------------------------------
// Per-harness (Claude Code / Codex / Cursor / SDKs) + per-developer spend,
// classified from the gateway's real user_agent and priced with the rate card.
// The #1 Unity AI Gateway adoption motion: governing coding-agent cost.
const HARNESS_HEX: Record<string, string> = {
  'Claude Code': '#D97757', Codex: '#67C7E8', Cursor: '#B487D0', Windsurf: '#4FD79E',
};
function CodingAgents({ days }: { days: number }) {
  const [data, setData] = useState<CodingAgentsData | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    getCodingAgents(days).then((d) => { if (alive) { setData(d); setLoading(false); } });
    return () => { alive = false; };
  }, [days]);

  // Nothing to show if the system tables can't be read (keeps the tab clean).
  if (!loading && (!data || data.source !== 'system_tables')) return null;

  const t = data?.totals;
  const harnesses = data?.byHarness ?? [];
  const devs = data?.byDeveloper ?? [];
  const maxH = Math.max(...harnesses.map((h) => h.costUsd), 1e-9);
  const maxD = Math.max(...devs.map((d) => d.costUsd), 1e-9);
  const hexOf = (h: { harness: string; coding: boolean }) => HARNESS_HEX[h.harness] ?? (h.coding ? '#E3B876' : '#5B6472');

  return (
    <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.09s' }}>
      <div className="pointer-events-none absolute -left-28 -top-24 h-96 w-96 rounded-full bg-[#67C7E8] opacity-[.07] blur-3xl" />
      <div className="relative">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <div className={SECTION}>Coding-agent spend</div>
          <span className="rounded-pill bg-[#4FD79E]/15 px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-[.06em] text-[#4FD79E] ring-1 ring-[#4FD79E]/30">● Live · by user_agent · {days}d</span>
        </div>
        <p className="mb-4 max-w-[74ch] font-body text-[13px] leading-[1.55] text-white/60">
          Every request through the gateway carries a <span className="num text-white/80">user_agent</span>, so spend is attributable to the coding harness that made it - Claude Code, Codex, Cursor - and to each developer. The top governance question for AI coding tools: <span className="text-white/80">who is spending what, on which harness</span>.
        </p>

        {loading ? (
          <div className="flex items-center gap-3 rounded-2xl bg-white/[0.04] p-6 ring-1 ring-white/10">
            <span className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-white/25 border-t-[#67C7E8]" />
            <span className="text-[12.5px] text-white/70">Classifying coding-agent traffic from system.ai_gateway.usage…</span>
          </div>
        ) : (
          <>
            {t && (
              <div className="grid grid-cols-4 gap-3 max-[720px]:grid-cols-2">
                <Kpi label="Coding-agent spend" value={usd(t.codingCostUsd)} sub={`${formatPercent1(t.codingSharePct)} of all gateway spend`} accent="#D97757" />
                <Kpi label="Coding-agent requests" value={num0(t.codingRequests)} />
                <Kpi label="Developers" value={t.codingDevelopers.toLocaleString()} sub="using coding agents" />
                <Kpi label="All gateway spend" value={usd(t.costUsd)} sub={`${num0(t.requests)} requests`} />
              </div>
            )}
            <div className="mt-4 grid grid-cols-2 gap-4 max-[760px]:grid-cols-1">
              {/* Spend by harness */}
              <div className="rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
                <div className="mb-3 font-body text-[11px] font-semibold uppercase tracking-[.16em] text-white/45">Spend by harness</div>
                <div className="flex flex-col gap-2.5">
                  {harnesses.map((h) => (
                    <div key={h.harness}>
                      <div className="mb-1 flex items-center justify-between text-[12px]">
                        <span className="flex items-center gap-1.5 font-medium text-white/85">
                          <span className="h-2 w-2 rounded-full" style={{ background: hexOf(h) }} />
                          {h.harness}
                          {h.coding && <span className="rounded-pill bg-[#D97757]/20 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[.05em] text-[#E7967A]">coding</span>}
                        </span>
                        <span className="num text-white/70">{usd(h.costUsd)} · {num0(h.requests)}×</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full" style={{ width: `${(h.costUsd / maxH) * 100}%`, background: hexOf(h) }} /></div>
                    </div>
                  ))}
                </div>
              </div>
              {/* Top developers (coding-agent) */}
              <div className="rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
                <div className="mb-3 font-body text-[11px] font-semibold uppercase tracking-[.16em] text-white/45">Top developers · coding agents</div>
                {devs.length === 0 ? (
                  <EmptyMini text="No labeled coding-agent traffic in this window." />
                ) : (
                  <div className="flex flex-col gap-2.5">
                    {devs.map((d) => (
                      <div key={d.user}>
                        <div className="mb-1 flex items-center justify-between text-[12px]">
                          <span className="num font-medium text-white/85">{d.user} <span className="text-white/40">· {d.harness}</span></span>
                          <span className="num text-white/70">{usd(d.costUsd)} · {num0(d.requests)}×</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full" style={{ width: `${(d.costUsd / maxD) * 100}%`, background: HARNESS_HEX[d.harness] ?? '#E3B876' }} /></div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <p className="num mt-3 text-[10.5px] leading-[1.5] text-white/40">
              Harness classified from <span className="text-white/55">system.ai_gateway.usage.user_agent</span> (e.g. <span className="text-white/55">claude-cli</span> → Claude Code, <span className="text-white/55">ucode … codex/</span> → Codex). Cost = real tokens × the published DBU rate card. Per-developer rows cover labeled coding-agent traffic.
            </p>
          </>
        )}
      </div>
    </section>
  );
}

// ---- Reliability & fallback observability --------------------------------
// Real per-request routing attempts from system.ai_gateway.usage
// routing_information.attempts: fallback fire rate, initial error rate, status
// breakdown, and which destinations fail most. The gateway's native fallback
// telemetry - complements the app-level fallback feature on Context routing.
const STATUS_META: { key: string; label: string; hex: string }[] = [
  { key: 'ok', label: 'Success', hex: '#4FD79E' },
  { key: 'rate_limited', label: 'Rate-limited (429)', hex: '#E3B876' },
  { key: 'client_error', label: 'Client error (4xx)', hex: '#D97757' },
  { key: 'server_error', label: 'Server error (5xx)', hex: '#FF6A54' },
];
function Reliability({ days }: { days: number }) {
  const [data, setData] = useState<ReliabilityData | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    getReliability(days).then((d) => { if (alive) { setData(d); setLoading(false); } });
    return () => { alive = false; };
  }, [days]);

  if (!loading && (!data || data.source !== 'system_tables')) return null;

  const t = data?.totals;
  const sc = data?.statusClass ?? {};
  const scTotal = Object.values(sc).reduce((a, b) => a + b, 0) || 1;
  const failing = data?.topFailing ?? [];
  const maxFail = Math.max(...failing.map((f) => f.failures), 1e-9);

  return (
    <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.11s' }}>
      <div className="pointer-events-none absolute -right-28 -top-24 h-96 w-96 rounded-full bg-[#E3B876] opacity-[.07] blur-3xl" />
      <div className="relative">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <div className={SECTION}>Reliability &amp; fallback</div>
          <span className="rounded-pill bg-[#4FD79E]/15 px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-[.06em] text-[#4FD79E] ring-1 ring-[#4FD79E]/30">● Live · routing_information · {days}d</span>
        </div>
        <p className="mb-4 max-w-[74ch] font-body text-[13px] leading-[1.55] text-white/60">
          The gateway records every routing <span className="text-white/80">attempt</span> per request - initial call and any fallbacks - with status and destination. This is the native fallback telemetry: how often a request needed a second model, the initial error rate, and which endpoints fail most.
        </p>

        {loading ? (
          <div className="flex items-center gap-3 rounded-2xl bg-white/[0.04] p-6 ring-1 ring-white/10">
            <span className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-white/25 border-t-[#E3B876]" />
            <span className="text-[12.5px] text-white/70">Reading routing attempts from system.ai_gateway.usage…</span>
          </div>
        ) : (
          <>
            {t && (
              <div className="grid grid-cols-4 gap-3 max-[720px]:grid-cols-2">
                <Kpi label="Fallback fires" value={num0(t.fallbackFires)} sub={`${formatPercent1(t.fallbackRatePct)} of requests`} accent="#E3B876" />
                <Kpi label="Served on fallback" value={num0(t.fallbackServedOk)} sub="recovered by a backup model" accent="#4FD79E" />
                <Kpi label="Initial error rate" value={formatPercent1(t.initialErrorRatePct)} sub="first-attempt non-2xx" />
                <Kpi label="Overall success" value={formatPercent1(t.okRatePct)} sub={`${num0(t.attempts)} attempts`} accent="#4FD79E" />
              </div>
            )}
            <div className="mt-4 grid grid-cols-2 gap-4 max-[760px]:grid-cols-1">
              {/* Attempt status breakdown */}
              <div className="rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
                <div className="mb-3 font-body text-[11px] font-semibold uppercase tracking-[.16em] text-white/45">Attempt outcomes</div>
                <div className="flex h-3 overflow-hidden rounded-full bg-white/[0.06]">
                  {STATUS_META.map((s) => { const share = ((sc[s.key] ?? 0) / scTotal) * 100; return share > 0 ? <div key={s.key} style={{ width: `${share}%`, background: s.hex }} title={`${s.label}: ${sc[s.key]}`} /> : null; })}
                </div>
                <div className="mt-3 flex flex-col gap-2">
                  {STATUS_META.map((s) => (
                    <div key={s.key} className="flex items-center justify-between text-[12px]">
                      <span className="flex items-center gap-1.5 text-white/80"><span className="h-2 w-2 rounded-full" style={{ background: s.hex }} />{s.label}</span>
                      <span className="num text-white/65">{num0(sc[s.key] ?? 0)} · {Math.round(((sc[s.key] ?? 0) / scTotal) * 100)}%</span>
                    </div>
                  ))}
                </div>
              </div>
              {/* Top failing destinations */}
              <div className="rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
                <div className="mb-3 font-body text-[11px] font-semibold uppercase tracking-[.16em] text-white/45">Top failing endpoints · initial attempt</div>
                {failing.length === 0 ? (
                  <EmptyMini text="No failed initial attempts in this window." />
                ) : (
                  <div className="flex flex-col gap-2.5">
                    {failing.map((f) => (
                      <div key={f.destination}>
                        <div className="mb-1 flex items-center justify-between text-[12px]">
                          <span className="num font-medium text-white/85">{f.destination}</span>
                          <span className="num text-white/70">{num0(f.failures)} fail{f.failures === 1 ? '' : 's'}</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-[#D97757]" style={{ width: `${(f.failures / maxFail) * 100}%` }} /></div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <p className="num mt-3 text-[10.5px] leading-[1.5] text-white/40">
              From <span className="text-white/55">system.ai_gateway.usage.routing_information.attempts</span> - the gateway's real per-request routing chain (INITIAL_ATTEMPT → FALLBACK). Fallback fires = requests that took more than one attempt.
            </p>
          </>
        )}
      </div>
    </section>
  );
}

// A single labelled horizontal comparison bar (actual vs routed spend).
function BarRow({ label, value, max, color, fmt }: { label: string; value: number; max: number; color: string; fmt: (n: number) => string }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[12px]">
        <span className="font-medium text-white/80">{label}</span>
        <span className="num font-semibold" style={{ color }}>{fmt(value)}</span>
      </div>
      <div className="h-3 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full transition-all duration-300" style={{ width: `${(value / max) * 100}%`, background: color }} /></div>
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

// Spend-anomaly indicator: a compact "!" sitting next to the live badge instead of a
// full banner row. Hover (or keyboard focus) reveals the detail in a light popover with
// dark text, so it stays out of the way until the reader wants it.
function AnomalyTip({ anomaly }: { anomaly: { last: number; mean: number; z: string; pctOver: number; date: string } }) {
  return (
    <span className="group relative inline-flex items-center">
      <span
        tabIndex={0}
        role="img"
        aria-label={`Spend anomaly detected on ${anomaly.date}`}
        className="grid h-[18px] w-[18px] cursor-help place-items-center rounded-full bg-[#E3B876] text-[11px] font-extrabold leading-none text-[#3a2a06] ring-1 ring-[#E3B876]/50"
      >!</span>
      <span className="pointer-events-none absolute left-0 top-full z-40 mt-2 hidden w-[320px] rounded-xl bg-white px-3.5 py-3 text-[12px] leading-[1.5] text-ink shadow-lift-3d-hi ring-1 ring-black/10 group-hover:block group-focus-within:block">
        <span className="font-bold text-[#9A6B12]">Spend anomaly detected.</span> {anomaly.date} saw <span className="num font-semibold">{num0(anomaly.last)}</span> requests, <span className="num font-semibold">{anomaly.pctOver}%</span> above the <span className="num">{num0(anomaly.mean)}</span> trailing daily average (z={anomaly.z}). In production this fires a Slack / email alert via the gateway's usage stream.
      </span>
    </span>
  );
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

// Editable projection input: a number field (type an exact value) paired with a
// slider. Both write the same value, so users can drag or type.
function VizSlider({ label, value, min, max, step, onChange, accent }: { label: string; value: number; min: number; max: number; step: number; onChange: (n: number) => void; accent: string }) {
  const clamp = (n: number) => Math.max(min, Math.min(max, n));
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <span className={LBL}>{label}</span>
        <input
          type="number" min={min} max={max} step={step} value={value}
          onChange={(e) => onChange(clamp(Number(e.target.value) || min))}
          aria-label={label}
          className="num w-[92px] rounded bg-white/10 px-2 py-0.5 text-right text-[12px] text-white ring-1 ring-white/10 outline-none focus:ring-white/25"
        />
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
