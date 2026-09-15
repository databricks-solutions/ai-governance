import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useConfig } from '../api/useConfig';
import { useSession } from '../store/session';
import type { LaneContext, ModelDef, Tier } from '../api/types';
import { TIER_SHORT, TIER_META } from '../api/types';
import { formatMoney, formatHeadline, formatScore, formatLatency } from '../lib/format';
import { QuestionLibrary } from '../components/QuestionLibrary';
import { RoutingSteps, RoiChart, compact, type RStep } from '../components/RoutingViz';

// Tab 1 - Compare all models. Three fixed lanes; each streams its answer with
// live cost accrual; the cheapest lane within QUALITY_BAND judge points of the
// best wins. Numbers are server-authored - the client only selects the winner.

const usd = (n: number) => formatMoney(n);
const big = (n: number) => formatHeadline(n);
const tok = (n: number | null) => (n == null ? '-' : n.toLocaleString());

// The complexity class each tier is meant for - a heading on each lane.
const TIER_CX_LABEL: Record<Tier, string> = { 'small-oss': 'Simple', 'large-oss': 'Medium', frontier: 'Complex' };

const LBL = 'font-body text-[9.5px] font-semibold uppercase tracking-[.14em] text-white/45';
const SECTION = 'font-display text-[13px] font-bold uppercase tracking-[.15em] text-[#7FB6F2]';

interface Preset { label: string; prompt: string }
const PRESETS: Preset[] = [
  { label: 'What 112% NRR signals', prompt: 'In two sentences, explain what a net revenue retention of 112% signals to investors about the health of the business.' },
  { label: 'Star schema vs One Big Table', prompt: 'For a BI semantic layer over a 2TB events dataset, compare a Kimball star schema against a single wide "One Big Table" - query performance, storage and maintenance cost, and governance - and recommend which to use and when.' },
  { label: 'Explain a margin miss to the board', prompt: 'Operating margin came in at 18% against a 25% target. Walk through the most likely drivers, the questions the CFO should ask to find the cause, and how to frame it for the board in one slide.' },
  { label: 'RAG architecture on Databricks', prompt: 'Design an end-to-end RAG architecture on Databricks: document ingestion and chunking, embedding generation, a vector index, retrieval with reranking, and model serving. Specify the components, how they connect, and the failure modes and mitigations at each stage.' },
  { label: 'M&A valuation framework', prompt: "We're evaluating a $400M acquisition financed with cash, debt, and stock. Build the full valuation framework - DCF with a defensible WACC, comparable-company and precedent-transaction cross-checks, accretion/dilution, synergy assumptions, and downside scenarios - then give a go/no-go recommendation and the top three risks." },
];

// One execution of a prompt on one model.
interface RunData {
  answer: string;
  costUsd: number;
  latencyMs: number | null;
  judgeScore: number | null;
  judgeReason: string;
  inputTokens: number | null;
  outputTokens: number | null;
  context: LaneContext | null;
  streaming: boolean;
  done: boolean;
  error: boolean;
}

// Generous client-side lane cap. The backend allows a long multi-part answer up to
// ~240s per round (with SSE keep-alives keeping the proxy connection warm), so a 70s
// client cap used to kill legitimate long generations before they finished. 300s
// leaves ample headroom; a truly stuck lane still resolves and can be retried alone.
const LANE_TIMEOUT_MS = 300_000;
// A lane whose judge score is within this many points of the best counts as
// matching the top quality - the winner is then decided on cost.
const QUALITY_BAND = 1.0;

// Dark-surface 3D shadows. The design system's --lift-3d is a navy drop tuned for
// cards on the LIGHT page; on the dark Results box it's invisible, so cards/tiles get
// a real black drop shadow + a faint top bevel (inset highlight) so they read as raised.
const CARD_3D = 'shadow-[inset_0_1px_0_rgba(255,255,255,0.07),0_10px_24px_-8px_rgba(0,0,0,0.6),0_30px_60px_-24px_rgba(0,0,0,0.55)]';
const TILE_3D = 'shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_4px_12px_-4px_rgba(0,0,0,0.55)]';

interface LaneState { modelId: string; run: RunData }

type Phase = 'idle' | 'running';

const streamingRun = (): RunData => ({ answer: '', costUsd: 0, latencyMs: null, judgeScore: null, judgeReason: '', inputTokens: null, outputTokens: null, context: null, streaming: true, done: false, error: false });
const idleRun = (): RunData => ({ ...streamingRun(), streaming: false });

function defaultLanes(models: ModelDef[]): string[] {
  // Defaults: frontier → opus-5; large-OSS ("Medium") → glm-5.3; small-OSS →
  // cheapest by representative per-query cost. Pins fall back to cheapest-by-cost.
  const perQ = (m: ModelDef) => 800 * m.price_in_per_1m + 400 * m.price_out_per_1m;
  const cheapestOf = (t: Tier) => [...models.filter((m) => m.tier === t)].sort((a, b) => perQ(a) - perQ(b))[0]?.id;
  const pin = (id: string, t: Tier) => models.find((m) => m.id === id)?.id ?? cheapestOf(t);
  const chosen = [pin('databricks-claude-opus-5', 'frontier'), pin('databricks-glm-5-3', 'large-oss'), cheapestOf('small-oss')].filter(Boolean) as string[];
  for (const m of models) {
    if (chosen.length >= 3) break;
    if (!chosen.includes(m.id)) chosen.push(m.id);
  }
  return chosen.slice(0, 3);
}

export function Compare() {
  const cfg = useConfig();
  const { logRun, setLastRouting } = useSession();
  const [prompt, setPrompt] = useState('');
  const [activePreset, setActivePreset] = useState(-1);
  const [lanes, setLanes] = useState<LaneState[]>([]);
  const [phase, setPhase] = useState<Phase>('idle');
  const [winnerIdx, setWinnerIdx] = useState<number | null>(null);
  const [users, setUsers] = useState(100);
  const [perUserQ, setPerUserQ] = useState(50);
  const volume = users * perUserQ;
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [judgeModel, setJudgeModel] = useState('');
  const [judgeInfo, setJudgeInfo] = useState(false);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [ctxOpen, setCtxOpen] = useState<Record<number, boolean>>({});
  const [tokOpen, setTokOpen] = useState<Record<number, boolean>>({});
  const sourcesRef = useRef<EventSource[]>([]);
  const timersRef = useRef<number[]>([]);
  const lastPromptRef = useRef('');  // the prompt of the most recent run, so Retry always re-fires all 3 lanes
  const clearTimers = () => { timersRef.current.forEach((t) => clearTimeout(t)); timersRef.current = []; };

  const running = phase !== 'idle';

  // Default the judge to kimi-k3 (a strong open-weight grader); fall back to the
  // cheapest small-OSS, then the first model, if it isn't in this workspace.
  useEffect(() => {
    if (cfg && !judgeModel) {
      const cheapestSmall = [...cfg.models.filter((m) => m.tier === 'small-oss')].sort((a, b) => a.price_out_per_1m - b.price_out_per_1m)[0];
      const pick = cfg.models.find((m) => m.id === 'databricks-kimi-k3') ?? cheapestSmall ?? cfg.models[0];
      if (pick) setJudgeModel(pick.id);
    }
  }, [cfg, judgeModel]);

  useEffect(() => {
    if (cfg && lanes.length === 0) {
      setLanes(defaultLanes(cfg.models).map((modelId) => ({ modelId, run: idleRun() })));
    }
  }, [cfg, lanes.length]);

  useEffect(() => () => { sourcesRef.current.forEach((s) => s.close()); clearTimers(); }, []);

  const models = cfg?.models ?? [];
  const modelById = useMemo(() => new Map(models.map((m) => [m.id, m])), [models]);

  const setLaneModel = (i: number, modelId: string) => {
    setWinnerIdx(null);
    setLanes((ls) => ls.map((l, j) => (j === i ? { modelId, run: idleRun() } : l)));
  };

  // Run: run all three lanes on the prompt exactly as typed.
  const run = () => {
    if (running || lanes.length < 3 || !prompt.trim()) return;
    runAll(prompt.trim());
  };

  const resetAll = () => {
    sourcesRef.current.forEach((s) => s.close());
    sourcesRef.current = [];
    clearTimers();
    setPrompt('');
    setActivePreset(-1);
    setWinnerIdx(null);
    setExpanded({});
    setCtxOpen({});
    setTokOpen({});
    setLanes((ls) => ls.map((l) => ({ modelId: l.modelId, run: idleRun() })));
    setPhase('idle');
  };

  // Fan out: open one SSE per lane on the prompt.
  const runAll = (basePrompt: string) => {
    sourcesRef.current.forEach((s) => s.close());
    sourcesRef.current = [];
    clearTimers();
    setWinnerIdx(null);
    setExpanded({});
    setCtxOpen({});
    setTokOpen({});
    setPhase('running');
    setLanes((ls) => ls.map((l) => ({ modelId: l.modelId, run: streamingRun() })));

    const finals: Record<number, RunData & { idx: number }> = {};
    const done = new Set<number>();
    const laneModelIds = lanes.map((l) => l.modelId);
    const total = lanes.length;

    const resolve = (i: number, patch: Partial<RunData>, es: EventSource) => {
      if (done.has(i)) return;
      done.add(i);
      es.close();
      setLanes((ls) => ls.map((l, j) => (j === i ? { ...l, run: { ...l.run, ...patch, streaming: false, done: true } } : l)));
      finals[i] = { idx: i, ...streamingRun(), ...patch, streaming: false, done: true };
      if (done.size === total) { clearTimers(); finish(finals, laneModelIds, basePrompt); }
    };

    lanes.forEach((lane, i) => {
      const es = new EventSource(`/api/compare/lane?prompt=${encodeURIComponent(basePrompt)}&modelId=${encodeURIComponent(lane.modelId)}&judgeModel=${encodeURIComponent(judgeModel)}`);
      sourcesRef.current.push(es);
      es.onmessage = (ev) => {
        const d = JSON.parse(ev.data);
        if (d.type === 'token') {
          setLanes((ls) => ls.map((l, j) => (j === i ? { ...l, run: { ...l.run, answer: d.text, costUsd: d.costUsd } } : l)));
        } else if (d.type === 'done') {
          resolve(i, { answer: d.answer, costUsd: d.costUsd, latencyMs: d.latencyMs, judgeScore: d.judgeScore, judgeReason: d.judgeReason ?? '', inputTokens: d.inputTokens, outputTokens: d.outputTokens, context: d.context ?? null, error: !!d.error }, es);
        }
      };
      es.onerror = () => {
        resolve(i, { answer: '(no response - the model timed out or is unavailable in this workspace)', costUsd: 0, latencyMs: null, judgeScore: 0, judgeReason: '', inputTokens: null, outputTokens: null, context: null, error: true }, es);
      };
      const timer = window.setTimeout(() => {
        resolve(i, { answer: '(timed out - this model took too long; try a faster frontier model like sonnet or opus-4-8)', costUsd: 0, latencyMs: null, judgeScore: 0, judgeReason: '', inputTokens: null, outputTokens: null, context: null, error: true }, es);
      }, LANE_TIMEOUT_MS);
      timersRef.current.push(timer);
    });
  };

  // Retry a SINGLE lane (not all three), so a stray guardrail-block/timeout on one
  // model can be re-fired without re-running the models that already answered. The
  // winner-recompute effect re-crowns automatically once the lane settles.
  const runLane = (i: number) => {
    if (running || !lanes[i]) return;
    const p = (lastPromptRef.current || prompt).trim();
    if (!p) return;
    const modelId = lanes[i].modelId;
    setLanes((ls) => ls.map((l, j) => (j === i ? { ...l, run: streamingRun() } : l)));
    const es = new EventSource(`/api/compare/lane?prompt=${encodeURIComponent(p)}&modelId=${encodeURIComponent(modelId)}&judgeModel=${encodeURIComponent(judgeModel)}`);
    sourcesRef.current.push(es);
    let settled = false;
    const settle = (patch: Partial<RunData>) => {
      if (settled) return;
      settled = true;
      es.close();
      setLanes((ls) => ls.map((l, j) => (j === i ? { ...l, run: { ...l.run, ...patch, streaming: false, done: true } } : l)));
    };
    es.onmessage = (ev) => {
      const d = JSON.parse(ev.data);
      if (d.type === 'token') {
        setLanes((ls) => ls.map((l, j) => (j === i ? { ...l, run: { ...l.run, answer: d.text, costUsd: d.costUsd } } : l)));
      } else if (d.type === 'done') {
        settle({ answer: d.answer, costUsd: d.costUsd, latencyMs: d.latencyMs, judgeScore: d.judgeScore, judgeReason: d.judgeReason ?? '', inputTokens: d.inputTokens, outputTokens: d.outputTokens, context: d.context ?? null, error: !!d.error });
      }
    };
    es.onerror = () => settle({ answer: '(no response - the model timed out or is unavailable in this workspace)', costUsd: 0, latencyMs: null, judgeScore: 0, judgeReason: '', inputTokens: null, outputTokens: null, context: null, error: true });
    const timer = window.setTimeout(() => settle({ answer: '(timed out - this model took too long)', costUsd: 0, latencyMs: null, judgeScore: 0, judgeReason: '', inputTokens: null, outputTokens: null, context: null, error: true }), LANE_TIMEOUT_MS);
    timersRef.current.push(timer);
  };

  // Retry only the lanes that failed (guardrail-block/timeout), leaving the good ones.
  const retryErrored = () => {
    lanes.forEach((l, i) => { if (l.run.done && l.run.error) runLane(i); });
  };

  // Best value = quality AND cost: among lanes within QUALITY_BAND of the best
  // answer, pick the cheapest.
  const pickWinner = (finals: Record<number, RunData & { idx: number }>, n: number): (RunData & { idx: number }) | null => {
    const cands = Array.from({ length: n }, (_, i) => finals[i]).filter((r) => r && !r.error && r.judgeScore != null);
    if (!cands.length) return null;
    const best = Math.max(...cands.map((r) => r.judgeScore ?? 0));
    const withinBar = cands.filter((r) => (r.judgeScore ?? 0) >= best - QUALITY_BAND);
    return [...withinBar].sort((a, b) => a.costUsd - b.costUsd || (b.judgeScore ?? 0) - (a.judgeScore ?? 0))[0];
  };

  const finish = (finals: Record<number, RunData & { idx: number }>, laneModelIds: string[], basePrompt: string) => {
    setPhase('idle');
    // Resilient: crown best value among the lanes that actually returned a judged
    // answer (pickWinner already ignores errored/blocked lanes). A single slow or
    // guardrail-blocked model no longer voids the whole comparison. The crown itself
    // is kept in sync by the winner-recompute effect below (covers single-lane retries
    // and model swaps too); finish() only logs the winning run to the session store.
    const win = pickWinner(finals, laneModelIds.length);
    if (!win) return;
    const cands = laneModelIds.map((_, i) => finals[i]).filter((r) => r && !r.error && r.judgeScore != null);
    const cf = win.context?.decision?.counterfactual?.costUsd ?? 0;
    const worst = Math.max(cf, ...cands.map((r) => r.costUsd));
    const wm = modelById.get(laneModelIds[win.idx]);
    if (wm) {
      logRun({
        source: 'compare', modelShort: wm.short, tier: wm.tier, costUsd: win.costUsd, baselineUsd: worst,
        inputTokens: win.inputTokens ?? 0, outputTokens: win.outputTokens ?? 0, latencyMs: win.latencyMs ?? undefined,
        optimized: false, promptSnippet: basePrompt,
      });
      setLastRouting({ model: wm.short, tier: wm.tier, costUsd: win.costUsd, source: 'compare' });
    }
  };

  // Single source of truth for the crown: recompute from whichever lanes hold a valid
  // judged answer whenever lanes settle (full run, single-lane retry, or model swap).
  // Errored/blocked lanes are simply ignored, so the winner is always shown among the
  // models that returned - no more "incomplete comparison" dead-end.
  const winnerFrom = (ls: { modelId: string; run: RunData }[]): number | null => {
    const finals: Record<number, RunData & { idx: number }> = {};
    ls.forEach((l, i) => { if (l.run.done) finals[i] = { idx: i, ...l.run }; });
    const win = pickWinner(finals, ls.length);
    return win ? win.idx : null;
  };
  useEffect(() => {
    if (phase === 'running') return; // wait for the full fan-out to settle (finish sets idle)
    setWinnerIdx(winnerFrom(lanes));
  }, [lanes, phase]); // eslint-disable-line react-hooks/exhaustive-deps

  // ROI: the best-value winner vs the frontier model over 12 months.
  const roi = useMemo(() => {
    if (winnerIdx == null) return null;
    const winRun = lanes[winnerIdx]?.run;
    if (!winRun?.done || winRun.error || winRun.costUsd <= 0) return null;
    const bestPer = winRun.costUsd;
    const doneRuns = lanes.map((l) => ({ r: l.run, m: modelById.get(l.modelId) })).filter((x) => x.r.done && !x.r.error && x.r.costUsd > 0);
    if (!doneRuns.length) return null;

    const successfulFrontier = doneRuns.find((x) => x.m?.tier === 'frontier');
    const selectedFrontier = lanes.map((l) => modelById.get(l.modelId)).find((mm) => mm?.tier === 'frontier');
    let frontierPer: number;
    let frontierShort: string | undefined;
    let frontierEstimated = false;
    if (successfulFrontier) {
      frontierPer = successfulFrontier.r.costUsd;
      frontierShort = successfulFrontier.m?.short;
    } else if (selectedFrontier && winRun.inputTokens != null && winRun.outputTokens != null) {
      frontierPer = (winRun.inputTokens / 1e6) * selectedFrontier.price_in_per_1m + (winRun.outputTokens / 1e6) * selectedFrontier.price_out_per_1m;
      frontierShort = selectedFrontier.short;
      frontierEstimated = true;
    } else {
      const top = doneRuns.reduce((a, b) => (b.r.costUsd > a.r.costUsd ? b : a));
      frontierPer = top.r.costUsd;
      frontierShort = top.m?.short;
    }
    const smalls = Array.from(modelById.values()).filter((m) => m.tier === 'small-oss').sort((a, b) => a.price_out_per_1m - b.price_out_per_1m);
    const smallModel = smalls[0];
    const inTok = winRun.inputTokens ?? 0;
    const routerPer = smallModel ? (inTok / 1e6) * smallModel.price_in_per_1m + (8 / 1e6) * smallModel.price_out_per_1m : 0;
    const allInPer = bestPer + routerPer;
    const cheaperX = allInPer > 0 ? frontierPer / allInPer : null;
    // `volume` is now DAILY (sliders are daily), so `monthly` holds the per-DAY cost
    // that the ROI panel + chart render on a daily basis; savedYr stays annual (×365).
    const monthly = { frontier: frontierPer * volume, routed: bestPer * volume };
    return {
      monthly, savedYr: (frontierPer - bestPer) * volume * 365, frontierShort, frontierEstimated,
      cheaperX: cheaperX != null ? Math.round(cheaperX * 10) / 10 : null,
    };
  }, [lanes, volume, winnerIdx, modelById]);

  const hasWinner = winnerIdx !== null;
  const winnerModel = winnerIdx !== null ? modelById.get(lanes[winnerIdx]?.modelId) : null;
  const frontierLaneShort = lanes.map((l) => modelById.get(l.modelId)).find((mm) => mm?.tier === 'frontier')?.short;
  const frontierRefShort = roi?.frontierShort ?? frontierLaneShort;
  const frontierEstimated = roi?.frontierEstimated ?? false;
  const frontierWon = !!roi && (roi.cheaperX == null || roi.cheaperX < 1.05);
  const doneLanes = lanes.map((l, i) => ({ r: l.run, i })).filter((x) => x.r.done && !x.r.error);
  const cheapestIdx = doneLanes.length ? doneLanes.reduce((a, b) => (b.r.costUsd < a.r.costUsd ? b : a)).i : null;
  const fastestIdx = doneLanes.length ? doneLanes.reduce((a, b) => ((b.r.latencyMs ?? 1e9) < (a.r.latencyMs ?? 1e9) ? b : a)).i : null;
  // Lanes that failed to return a response (guardrail-block / timeout). These are
  // simply excluded from best value; the comparison still crowns among the rest and
  // offers a per-lane retry, so one failed model never blocks the whole result.
  const erroredLanes = lanes.map((l, i) => ({ l, i })).filter((x) => x.l.run.done && x.l.run.error);
  const anyError = erroredLanes.length > 0 && !running;
  const erroredNames = erroredLanes.map((x) => modelById.get(x.l.modelId)?.short ?? `lane ${x.i + 1}`);
  const okCount = lanes.filter((l) => l.run.done && !l.run.error && l.run.judgeScore != null).length;

  const winRun = winnerIdx != null ? lanes[winnerIdx].run : null;
  const flowSteps: RStep[] = [
    { key: 'p', label: 'Prompt', detail: 'one question', glyph: '✎', accent: '#67B8F0' },
    { key: 'lanes', label: '3 models', detail: 'answer in parallel', glyph: '⋯', accent: '#67C7E8' },
    { key: 'judge', label: 'LLM judge', detail: 'scores each answer', glyph: '★', accent: '#F5B24B' },
    { key: 'win', label: winnerModel ? winnerModel.short : 'Winner', detail: winRun ? usd(winRun.costUsd) : 'best quality', glyph: '◆', accent: '#FF3621', landed: hasWinner },
    { key: 'resp', label: 'Response', detail: winRun?.latencyMs != null ? `${winRun.latencyMs}ms` : 'returned', glyph: '✓', accent: '#4FD79E' },
  ];

  const outcome = (() => {
    if (!hasWinner || !winnerModel || winnerIdx == null) return null;
    const wcost = lanes[winnerIdx].run.costUsd;
    const costs = lanes.map((l) => l.run).filter((r) => r.done && !r.error).map((r) => r.costUsd);
    const top = costs.length ? Math.max(...costs) : wcost;
    return { model: winnerModel.short, perQuery: usd(wcost), savedYear: big((top - wcost) * volume * 365) };
  })();

  return (
    <div className="flex flex-col gap-[22px] text-white">
      {/* Box 1 - intro + outcome */}
      <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink px-[26px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:px-4">
        <div className="pointer-events-none absolute -right-32 -top-24 h-96 w-96 rounded-full bg-lava opacity-[.10] blur-3xl" />
        <StoryHero outcome={outcome} />
      </section>

      {/* Box 2 - Your prompt */}
      <section className="relative animate-[fadeUp_.5s_ease_both] rounded-[26px] bg-ink p-[22px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.07s' }}>
        <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-[26px]">
          <div className="absolute -bottom-24 -left-24 h-72 w-72 rounded-full bg-lava opacity-[.08] blur-3xl" />
        </div>
        <div className={`${SECTION} relative mb-3`}>Your prompt</div>
        <div className="relative rounded-2xl bg-black/30 p-1 shadow-[0_0_0_4px_rgba(255,54,33,0.07),0_20px_44px_-16px_rgba(255,54,33,0.4)] ring-2 ring-lava/40 transition focus-within:ring-lava/70">
          <textarea
            className="block w-full resize-none border-none bg-transparent px-5 py-4 text-[15px] leading-[1.6] text-white outline-none placeholder:text-white/35"
            rows={2}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); run(); } }}
            placeholder="Ask anything, or paste a question here - the same prompt goes to all three lanes"
          />
        </div>

        <div className="relative mt-3.5 flex flex-wrap items-center gap-2">
          {PRESETS.map((p, i) => (
            <button key={i} aria-pressed={activePreset === i}
              onClick={() => { setActivePreset(i); setPrompt(p.prompt); }}
              className="inline-flex items-center rounded-pill bg-white/10 px-3.5 py-1.5 text-[12.5px] text-white/75 transition hover:-translate-y-px hover:bg-white/15 hover:text-white aria-pressed:bg-white aria-pressed:text-ink">
              {p.label}
            </button>
          ))}
          <button onClick={() => setLibraryOpen(true)} className="rounded-pill bg-white/15 px-3.5 py-1.5 text-[12.5px] font-bold text-white ring-1 ring-white/20 transition hover:bg-white/25">Browse examples →</button>
          <button onClick={resetAll} disabled={running} title="Clear the prompt and all results"
            className="ml-auto rounded-pill bg-white/[0.06] px-3.5 py-1.5 text-[12.5px] font-medium text-white/60 ring-1 ring-white/10 transition hover:bg-white/12 hover:text-white disabled:cursor-not-allowed disabled:opacity-40">↺ Reset</button>
        </div>

        {/* Action row - judge + Run */}
        <div className="relative mt-5 flex flex-wrap items-center justify-center gap-2.5">
          <div className="relative flex items-center gap-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-[.08em] text-white/55">Routing / Judge LLM</span>
            <select value={judgeModel} onChange={(e) => setJudgeModel(e.target.value)} aria-label="Routing / Judge LLM"
              className="num max-w-[150px] cursor-pointer rounded-pill bg-white/10 px-3 py-2.5 text-[12px] text-white ring-1 ring-white/10 outline-none">
              {models.map((m) => <option key={m.id} value={m.id} className="text-ink">{m.short}</option>)}
            </select>
            <button onClick={() => setJudgeInfo((v) => !v)} aria-label="How the routing / judge LLM works"
              className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-[12px] text-white/50 transition hover:bg-white/10 hover:text-white">ⓘ</button>
            {judgeInfo && <JudgeInfo onClose={() => setJudgeInfo(false)} />}
          </div>
          <button onClick={run} disabled={running || !prompt.trim()}
            className="rounded-pill bg-lava px-[26px] py-3 text-[13px] font-semibold text-white shadow-lift transition hover:bg-[#e22e1a] disabled:cursor-not-allowed disabled:opacity-45">
            {running ? 'Running…' : 'Run'}
          </button>
        </div>
      </section>

      {/* Box 3 - LLM results */}
      <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[22px] pt-5 shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.12s' }}>
        <div className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-lava opacity-[.09] blur-3xl" />
        <div className={`${SECTION} relative mb-1`}>Results</div>
        {anyError && (
          <div className="relative mb-2 flex flex-wrap items-center gap-3 rounded-xl bg-[#E3B876]/[0.12] px-4 py-3 ring-1 ring-[#E3B876]/40">
            <span className="text-[14px]">ⓘ</span>
            <span className="text-[12.5px] leading-[1.5] text-white/80">
              <b className="text-white">{okCount} of {lanes.length} models answered</b>{hasWinner ? ' - best value is shown among those.' : '.'} <b className="text-[#E3B876]">{erroredNames.join(', ')}</b> didn't return - the lane shows why. Retry just the failed {erroredLanes.length > 1 ? 'lanes' : 'lane'}, or pick a different model.
            </span>
            <button onClick={retryErrored} disabled={running} className="ml-auto rounded-pill bg-white/15 px-3.5 py-1.5 text-[12px] font-semibold text-white ring-1 ring-white/20 transition hover:bg-white/25 disabled:opacity-40">↺ Retry failed {erroredLanes.length > 1 ? 'lanes' : 'lane'}</button>
          </div>
        )}
        <div className="grid grid-cols-[repeat(3,minmax(280px,1fr))] items-start gap-[18px] overflow-x-auto px-4 py-6">
          {lanes.map((lane, i) => (
            <LaneCard
              key={i} lane={lane} i={i} model={modelById.get(lane.modelId)} models={models}
              won={winnerIdx === i} hasWinner={hasWinner} running={running}
              isCheapest={i === cheapestIdx} isFastest={i === fastestIdx}
              expanded={!!expanded[i]} ctxOpen={!!ctxOpen[i]} tokOpen={!!tokOpen[i]}
              onModel={(id) => setLaneModel(i, id)}
              onExpand={() => setExpanded((e) => ({ ...e, [i]: !e[i] }))}
              onCtx={() => setCtxOpen((c) => ({ ...c, [i]: !c[i] }))}
              onTok={() => setTokOpen((t) => ({ ...t, [i]: !t[i] }))}
              onRetry={() => runLane(i)}
            />
          ))}
        </div>
      </section>

      {/* Box 4 - routing economics */}
      <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[26px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.18s' }}>
        <div className="pointer-events-none absolute -bottom-24 -right-24 h-80 w-80 rounded-full bg-lava opacity-[.08] blur-3xl" />
        <div className="relative flex flex-col gap-[18px]">
          <div className={SECTION}>Routing economics</div>
          <div className="flex flex-col gap-[18px]">
            <VizPanel title="Visualizing intelligent routing flow"><RoutingSteps steps={flowSteps} running={running} /></VizPanel>
            <VizPanel title="Best value vs frontier - projected savings">
              <div className="flex flex-col gap-4">
                <div className="grid grid-cols-2 gap-4 max-[520px]:grid-cols-1">
                  <VizSlider label="Daily active users" value={users} min={100} max={200000} step={100} onChange={setUsers} accent="accent-[#B487D0]" />
                  <VizSlider label="Queries / user / day" value={perUserQ} min={1} max={500} step={1} onChange={setPerUserQ} accent="accent-lava" />
                </div>
                {frontierWon ? (
                  <>
                    <div className="grid grid-cols-4 gap-2 max-[520px]:grid-cols-2">
                      <VizStat label="Total queries / day" value={volume ? volume.toLocaleString() : '-'} />
                      <VizStat label={winnerModel ? `${winnerModel.short} / day` : 'Cost / day'} value={roi ? compact(roi.monthly.frontier) : '-'} />
                      <VizStat label="Saved / day" value="$0" />
                      <VizStat label="Saved / year" value="$0" />
                    </div>
                    <p className="rounded-lg bg-white/[0.04] px-3 py-2 text-[11.5px] leading-[1.5] text-white/55 ring-1 ring-white/10">
                      The frontier model was the best value model that cleared the quality bar on this prompt.
                    </p>
                  </>
                ) : (
                  <div className="grid grid-cols-5 gap-2 max-[720px]:grid-cols-3 max-[520px]:grid-cols-2">
                    <VizStat label="Total queries / day" value={volume ? volume.toLocaleString() : '-'} />
                    <VizStat label={frontierRefShort ? `${frontierRefShort}${frontierEstimated ? ' (est.)' : ''} / day` : 'Frontier / day'} value={roi ? compact(roi.monthly.frontier) : '-'} />
                    <VizStat label={winnerModel ? `${winnerModel.short} / day` : 'Best value / day'} value={roi ? compact(roi.monthly.routed) : '-'} />
                    <VizStat label="Saved / day" value={roi ? compact(roi.monthly.frontier - roi.monthly.routed) : '-'} color="#4FD79E" />
                    <VizStat label="Saved / year" value={roi ? compact(roi.savedYr) : '-'} color="#4FD79E" />
                  </div>
                )}
                <div className="relative">
                  <RoiChart roi={roi} periods={30} periodNoun="days" totalSuffix="mo" frontierLabel={frontierRefShort ? `${frontierEstimated ? 'FRONTIER (EST.)' : 'FRONTIER'} · ${frontierRefShort}` : 'FRONTIER MODEL'} routedLabel={winnerModel ? `BEST VALUE · ${winnerModel.short}` : 'BEST VALUE'} />
                  {!roi && (
                    <div className="absolute inset-0 grid place-items-center px-6 text-center">
                      <p className="max-w-[42ch] text-[12.5px] leading-[1.5] text-white/45">Run a comparison above: this plots the best-value winner against the frontier model over 30 days. Move the sliders to scale it to your traffic.</p>
                    </div>
                  )}
                </div>
                {roi && frontierEstimated && (
                  <p className="rounded-lg bg-white/[0.04] px-3 py-2 text-[11.5px] leading-[1.5] text-white/55 ring-1 ring-white/10">
                    <span className="font-semibold text-[#FF9E8C]">{frontierRefShort}</span> returned no data this run, so its line is <b>estimated</b> from its rate card × the winner's tokens - the saving shown is what routing avoids versus that frontier price.
                  </p>
                )}
                {/* Total saving per year - the punchline box at the end of the panel. */}
                {roi && !frontierWon && (
                  <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 rounded-2xl bg-[#4FD79E]/[0.08] px-5 py-4 ring-1 ring-[#4FD79E]/40">
                    <div>
                      <div className="font-body text-[10px] font-semibold uppercase tracking-[.14em] text-[#4FD79E]/80">Total saving / year</div>
                      <div className="mt-1 font-body text-[13px] leading-[1.4] text-white/60">
                        {winnerModel ? <span className="num text-white/80">{winnerModel.short}</span> : 'best value'} vs {frontierRefShort ? <span className="num text-white/80">{frontierRefShort}</span> : 'the frontier model'} at {volume ? volume.toLocaleString() : '-'} queries/day
                      </div>
                    </div>
                    <div className="num text-[34px] font-semibold leading-none tracking-[-.04em] text-[#4FD79E]">{compact(roi.savedYr)}</div>
                  </div>
                )}
              </div>
            </VizPanel>
          </div>
          <p className="num text-[10.5px] text-white/40">{cfg?.priceFootnote ?? 'Prices from the DBU rate card - see config'}</p>
        </div>
      </section>

      {libraryOpen && (
        <QuestionLibrary onPick={(query) => { setActivePreset(-1); setPrompt(query); }} onClose={() => setLibraryOpen(false)} />
      )}
    </div>
  );
}

// ---- Lane card ----------------------------------------------------------
interface LaneCardProps {
  lane: LaneState;
  i: number;
  model: ModelDef | undefined;
  models: ModelDef[];
  won: boolean;
  hasWinner: boolean;
  running: boolean;
  isCheapest: boolean;
  isFastest: boolean;
  expanded: boolean;
  ctxOpen: boolean;
  tokOpen: boolean;
  onModel: (id: string) => void;
  onExpand: () => void;
  onCtx: () => void;
  onTok: () => void;
  onRetry: () => void;
}

function LaneCard({ lane, i, model: m, models, won, hasWinner, running, isCheapest, isFastest, expanded, ctxOpen, tokOpen, onModel, onExpand, onCtx, onTok, onRetry }: LaneCardProps) {
  const r = lane.run;
  const errored = r.done && r.error;
  const dimmed = hasWinner && !won && !errored;
  const isRunning = r.streaming || (running && !r.done && !r.error);

  return (
    <article
      style={{ animationDelay: `${i * 90}ms` }}
      className={`group relative flex animate-[fadeUp_.5s_ease_both] flex-col gap-4 overflow-hidden rounded-2xl p-5 transition-all duration-[300ms] ease-soft ${won ? '' : CARD_3D} ${
        won ? 'z-10 bg-lava/[0.06] shadow-lift-winner ring-2 ring-lava'
          : errored ? 'bg-white/[0.02] opacity-60 saturate-0 ring-1 ring-[#E3B876]/30'
            : dimmed ? 'bg-white/[0.03] opacity-50 ring-1 ring-white/10'
              : isRunning ? 'bg-white/[0.03] opacity-60 saturate-[.35] ring-1 ring-white/10'
                : 'bg-white/[0.04] ring-1 ring-white/12 hover:-translate-y-1 hover:bg-white/[0.06] hover:ring-white/25'
      }`}
    >
      {won && (
        <div className="-mx-5 -mt-5 flex items-center justify-center gap-1.5 bg-gradient-to-r from-lava to-[#FF6A54] py-1.5 text-[10px] font-semibold uppercase tracking-[.14em] text-white">
          <span className="text-[11px]">🏆</span> Best value
        </div>
      )}
      <div>
        {m && (
          <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-[.16em]" style={{ color: TIER_META[m.tier].hex }}>
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: TIER_META[m.tier].hex }} />
            {TIER_CX_LABEL[m.tier]}
          </div>
        )}
        <div className="relative">
          <select aria-label={`Model for lane ${i + 1}`} value={lane.modelId} onChange={(e) => onModel(e.target.value)}
            className={`w-full cursor-pointer appearance-none rounded-lg bg-black/25 px-3.5 py-3 pr-9 font-display text-[14px] font-semibold tracking-[-.01em] text-white ring-1 ring-white/10 transition hover:bg-black/35 ${TILE_3D}`}>
            {(m ? models.filter((mm) => mm.tier === m.tier) : models).map((mm) => (
              <option key={mm.id} value={mm.id} className="text-ink">{mm.short}</option>
            ))}
          </select>
          <span className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-[11px] text-white/45">▾</span>
        </div>
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          {m && <TierBadge tier={m.tier} />}
          {isCheapest && <TagPill color="#93D3AB" label="Cheapest" glyph="$" />}
          {isFastest && <TagPill color="#6BB0E8" label="Fastest" glyph="⚡" />}
        </div>
      </div>

      {isRunning && (
        <div className={`flex items-center gap-2 rounded-lg bg-white/[0.05] px-3 py-2 text-[11.5px] font-medium text-white/70 ring-1 ring-white/10 ${TILE_3D}`}>
          <Dots />Running the query on {m?.short ?? 'model'}…
        </div>
      )}

      {errored && (
        <div className={`flex items-center justify-between gap-2 rounded-lg bg-[#E3B876]/10 px-3 py-2 text-[11.5px] font-medium text-[#E3B876] ring-1 ring-[#E3B876]/25 ${TILE_3D}`}>
          <span>⚠ No response from this model</span>
          <button onClick={onRetry} className="rounded-pill bg-white/10 px-2.5 py-1 text-[11px] font-semibold text-white/85 transition hover:bg-white/20">↺ Retry</button>
        </div>
      )}

      <div className="grid grid-cols-3 gap-2">
        <div className={`min-w-0 rounded-xl p-2.5 ${TILE_3D} ${won ? 'bg-lava/20 ring-2 ring-lava/60' : 'bg-white/[0.04] ring-1 ring-white/10'}`}>
          <div className={LBL}>Cost / query</div>
          <div className={`num mt-1.5 truncate text-[14px] font-semibold leading-none tracking-[-.02em] ${won ? 'text-lava' : 'text-white'}`}>
            {r.error ? '-' : r.costUsd > 0 || r.done ? usd(r.costUsd) : '-'}
          </div>
        </div>
        <div className={`min-w-0 rounded-xl bg-white/[0.04] p-2.5 ring-1 ring-white/10 ${TILE_3D}`}>
          <div className={LBL}>Latency</div>
          <div className="num mt-1.5 truncate text-[14px] font-semibold leading-none text-white">{r.streaming ? '···' : r.latencyMs != null ? formatLatency(r.latencyMs) : '-'}</div>
        </div>
        <div className={`min-w-0 rounded-xl p-2.5 ${TILE_3D} ${won ? 'bg-[#2272B4]/25 ring-2 ring-[#2272B4]/60' : 'bg-white/[0.04] ring-1 ring-white/10'}`}>
          <div className={LBL}>Score</div>
          <div className={`num mt-1.5 truncate text-[14px] font-semibold leading-none tracking-[-.02em] ${won ? 'text-[#8FC1F0]' : 'text-white'}`}>{r.error ? '-' : r.judgeScore != null ? formatScore(r.judgeScore) : '-'}</div>
        </div>
      </div>

      {r.done && !r.error && r.judgeReason && (
        <div className={`rounded-lg px-3 py-2 text-[11.5px] leading-[1.5] ring-1 ${TILE_3D} ${won ? 'bg-lava/10 text-white/85 ring-lava/30' : 'bg-white/[0.03] text-white/60 ring-white/10'}`}>
          <span className={`font-semibold ${won ? 'text-lava' : 'text-white/70'}`}>{won ? '🏆 Why it won: ' : 'Judge: '}</span>
          {r.judgeReason}
          {won && <span className="mt-1 block text-[10.5px] text-white/45">Best value: the lowest-cost lane whose answer matched the top quality.</span>}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <div className="grid grid-cols-3 gap-2">
          <MiniToggle open={expanded} onClick={onExpand} disabled={!r.answer && !r.streaming} label="response" />
          <MiniToggle open={ctxOpen} onClick={onCtx} disabled={!r.context} label="context" title="The exact request sent to the model and how it routed" />
          <MiniToggle open={tokOpen} onClick={onTok} disabled={!r.done} label="tokens" title="Input / output / total tokens" />
        </div>

        {tokOpen && (
          <div className={`rounded-lg bg-black/25 p-3 ring-1 ring-white/10 ${TILE_3D}`}>
            <div className="grid grid-cols-3 gap-2">
              <TokenStat label="Input" value={r.inputTokens} />
              <TokenStat label="Output" value={r.outputTokens} />
              <TokenStat label="Total" value={r.inputTokens != null && r.outputTokens != null ? r.inputTokens + r.outputTokens : null} />
            </div>
          </div>
        )}

        {expanded && (
          <div className={`rounded-lg bg-black/25 ring-1 ring-white/10 ${TILE_3D}`}>
            <div className="max-h-[220px] overflow-y-auto px-3.5 py-3 text-[12px] leading-[1.65] text-white/85">
              {r.streaming && !r.answer ? (
                <div className="flex items-center gap-2 text-white/45"><Dots />Running {m?.short ?? 'model'}…</div>
              ) : r.answer ? (
                <span className={r.error ? 'text-white/50' : ''} style={{ whiteSpace: 'pre-wrap' }}>
                  {r.answer}
                  {r.streaming && <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-lava align-[-2px]" />}
                </span>
              ) : (
                <span className="text-white/40">Run the comparison to see this model's answer.</span>
              )}
            </div>
          </div>
        )}

        {ctxOpen && r.context && <ContextPanel ctx={r.context} />}
      </div>
    </article>
  );
}

function TokenStat({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded-xl bg-white/[0.04] p-2.5 ring-1 ring-white/10">
      <div className={LBL}>{label}</div>
      <div className="num mt-1.5 text-[16px] font-semibold leading-none text-white">{tok(value)}</div>
    </div>
  );
}

function ContextPanel({ ctx }: { ctx: LaneContext }) {
  const { request, decision } = ctx;
  const clears = decision.clears;
  return (
    <div className={`flex flex-col gap-3 rounded-lg bg-black/30 p-3.5 text-[11.5px] ring-1 ring-white/10 ${TILE_3D}`}>
      <div>
        <div className={`${LBL} mb-1.5`}>Request sent to the model</div>
        <div className="flex flex-col gap-1 rounded-md bg-black/40 p-2.5 ring-1 ring-white/10">
          <Row k="endpoint" v={request.endpoint} mono />
          <Row k="max_tokens" v={String(request.params.max_tokens)} mono />
          <Row k="temperature" v={String(request.params.temperature)} mono />
        </div>
        <div className="mt-2 rounded-md bg-black/40 p-2.5 ring-1 ring-white/10">
          {request.messages.map((msg, k) => (
            <div key={k} className="mb-1 last:mb-0">
              <span className="num rounded bg-white/10 px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide text-[#8FC1F0]">{msg.role}</span>
              <p className="mt-1 leading-[1.55] text-white/75" style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</p>
            </div>
          ))}
        </div>
      </div>
      <div>
        <div className={`${LBL} mb-1.5`}>Routing decision</div>
        <div className="flex flex-col gap-1 rounded-md bg-black/40 p-2.5 ring-1 ring-white/10">
          <Row k="complexity" v={`${decision.complexity} / 100`} />
          <Row k="model tier" v={TIER_SHORT[decision.tier]} />
          <Row k="tier needed" v={TIER_SHORT[decision.requiredTier]} />
          <Row k="verdict" v={clears ? 'clears the bar' : 'below the bar'} badge={clears ? '#93D3AB' : '#FF9E8C'} />
          <Row k="if routed to frontier" v={`${decision.counterfactual.model} · ${usd(decision.counterfactual.costUsd)}`} />
        </div>
      </div>
    </div>
  );
}

function Row({ k, v, mono = false, badge }: { k: string; v: string; mono?: boolean; badge?: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-white/45">{k}</span>
      {badge ? (
        <span className="rounded-pill px-2 py-0.5 text-[10.5px] font-bold" style={{ background: `${badge}26`, color: badge }}>{v}</span>
      ) : (
        <span className={`text-right text-white/85 ${mono ? 'num' : ''}`}>{v}</span>
      )}
    </div>
  );
}

function MiniToggle({ open, onClick, disabled, label, title }: { open: boolean; onClick: () => void; disabled?: boolean; label: string; title?: string }) {
  return (
    <button onClick={onClick} disabled={disabled} title={title}
      className={`flex items-center justify-center gap-1 rounded-lg py-2 text-[11.5px] font-medium ring-1 transition disabled:opacity-40 ${open ? 'bg-white/12 text-white ring-white/20' : 'bg-white/[0.06] text-white/75 ring-white/10 hover:bg-white/10 hover:text-white'}`}>
      {label}<span className="text-[8px]">{open ? '▲' : '▼'}</span>
    </button>
  );
}

function Dots() {
  return (
    <span className="flex gap-1">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-lava [animation-delay:-.2s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-lava [animation-delay:-.1s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-lava" />
    </span>
  );
}

function TierBadge({ tier }: { tier: Tier }) {
  const hex = TIER_META[tier].hex;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-[.07em]" style={{ background: `${hex}26`, color: hex }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: hex }} />{TIER_SHORT[tier]}
    </span>
  );
}

function TagPill({ color, label, glyph }: { color: string; label: string; glyph: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-[11px] font-extrabold uppercase tracking-[.08em]" style={{ background: `${color}2e`, color, boxShadow: `inset 0 0 0 1.5px ${color}80` }}>
      <span className="grid h-4 w-4 place-items-center rounded-full text-[9px] font-black" style={{ background: color, color: '#141414' }}>{glyph}</span>{label}
    </span>
  );
}

function VizPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/10">
      <div className="mb-3 font-body text-[11px] font-semibold uppercase tracking-[.16em] text-white/45">{title}</div>
      {children}
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

function VizStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-xl bg-black/25 px-3 py-2.5 ring-1 ring-white/10">
      <div className="font-body text-[9px] font-semibold uppercase tracking-[.1em] text-white/45">{label}</div>
      <div className="num mt-1 text-[15px] font-medium leading-none tracking-[-.03em]" style={color ? { color } : { color: '#fff' }}>{value}</div>
    </div>
  );
}

interface Outcome { model: string; perQuery: string; savedYear: string }
interface Page { eyebrow: string; big: string; sub: string }

const INTRO_ADV: Page[] = [
  { eyebrow: 'Compare all models', big: 'Your prompt, three models, one bar to clear.', sub: 'Pick a model for each lane - frontier or open weights - then run them side by side. The cheapest answer that stays within a judge point of the best one wins.' },
  { eyebrow: 'Why it works', big: 'Most queries never needed a frontier model.', sub: '≈ 90% clear the quality bar on a smaller, cheaper one - route them there and pocket the difference.' },
  { eyebrow: 'Why it works', big: 'Route by complexity - not by habit.', sub: 'The prompt decides the model, one request at a time - automatically.' },
  { eyebrow: 'Why it works', big: 'Same governance. A fraction of the cost.', sub: 'Unity Gateway + Model Serving - already on Databricks.' },
];

function StoryHero({ outcome }: { outcome: Outcome | null }) {
  const [page, setPage] = useState(0);
  const [paused, setPaused] = useState(false);
  const dragX = useRef<number | null>(null);
  const pages = INTRO_ADV;
  const n = pages.length;
  const cur = Math.min(page, n - 1);
  const go = (d: number) => setPage((i) => Math.max(0, Math.min(n - 1, i + d)));

  useEffect(() => {
    if (paused || n <= 1) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const id = setInterval(() => setPage((p) => (p + 1) % n), 3200);
    return () => clearInterval(id);
  }, [paused, n]);

  const onPointerDown = (e: React.PointerEvent) => { dragX.current = e.clientX; };
  const onPointerUp = (e: React.PointerEvent) => {
    if (dragX.current == null) return;
    const dx = e.clientX - dragX.current;
    dragX.current = null;
    if (Math.abs(dx) > 45) go(dx < 0 ? 1 : -1);
  };

  return (
    <div className="relative overflow-hidden py-11 max-[720px]:py-7" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <button onClick={() => go(-1)} disabled={cur === 0} aria-label="Previous"
        className="absolute left-3 top-1/2 z-10 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-full bg-white/10 text-[18px] text-white/80 transition hover:bg-white/20 disabled:pointer-events-none disabled:opacity-25 max-[560px]:hidden">‹</button>
      <button onClick={() => go(1)} disabled={cur === n - 1} aria-label="Next"
        className="absolute right-3 top-1/2 z-10 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-full bg-white/10 text-[18px] text-white/80 transition hover:bg-white/20 disabled:pointer-events-none disabled:opacity-25 max-[560px]:hidden">›</button>

      <div className="overflow-hidden px-12 max-[560px]:px-6" onPointerDown={onPointerDown} onPointerUp={onPointerUp} onPointerLeave={() => (dragX.current = null)}>
        <div className="flex touch-pan-y transition-transform duration-[520ms] ease-soft" style={{ transform: `translateX(-${cur * 100}%)` }}>
          {pages.map((pg, i) => (
            <div key={i} className="flex min-h-[188px] w-full shrink-0 select-none flex-col items-center justify-center text-center" aria-hidden={i !== cur}>
              <div className="mb-4 font-body text-[11px] font-semibold uppercase tracking-[.22em] text-lava">{pg.eyebrow}</div>
              <h2 className="mx-auto max-w-[22ch] font-display text-[clamp(26px,3.6vw,46px)] font-bold leading-[1.04] tracking-[-.035em]">{pg.big}</h2>
              <p className="mx-auto mt-4 max-w-[52ch] font-body text-[16px] leading-[1.5] text-white/65">{pg.sub}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-8 flex items-center justify-center gap-2">
        {pages.map((_, i) => (
          <button key={i} onClick={() => setPage(i)} aria-label={`Go to page ${i + 1}`}
            className={`h-1.5 rounded-full transition-all duration-300 ${i === cur ? 'w-6 bg-lava' : 'w-1.5 bg-white/25 hover:bg-white/50'}`} />
        ))}
      </div>

      {outcome && (
        <div className="mt-5 flex flex-wrap items-center justify-center gap-x-3 gap-y-1.5 text-center">
          <span className="rounded-pill bg-lava/20 px-2.5 py-1 text-[11px] font-bold uppercase tracking-[.08em] text-lava">🏆 {outcome.model} wins</span>
          <span className="num text-[13px] font-semibold text-white">{outcome.perQuery} / query</span>
          <span className="num text-[13px] font-semibold text-[#93D3AB]">{outcome.savedYear} / yr avoided</span>
        </div>
      )}
    </div>
  );
}

function JudgeInfo({ onClose }: { onClose: () => void }) {
  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="absolute bottom-full left-1/2 z-50 mb-2 w-[320px] -translate-x-1/2 rounded-xl bg-card p-4 text-left text-[12px] leading-[1.55] text-ink-2 shadow-lift-hi">
        <div className="mb-2 flex items-center justify-between">
          <span className="font-display text-[12.5px] font-semibold text-ink">Routing / Judge LLM</span>
          <button onClick={onClose} aria-label="Close" className="text-[15px] leading-none text-ink-3 hover:text-ink">×</button>
        </div>
        <ul className="flex list-disc flex-col gap-1.5 pl-4">
          <li>One model both <b>routes</b> (classifies complexity to pick the cheapest sufficient tier) and <b>judges</b> (grades each answer 1-10).</li>
          <li>Defaults to <b>kimi-k3</b> - a strong open-weight grader. Pick a smaller model to keep the grading overhead cheaper, or a frontier one for stricter grading.</li>
          <li>The score drives the winner: the cheapest answer <b>within a judge point of the best</b> is chosen as <b>best value</b> - so price, not just quality, decides.</li>
        </ul>
        <p className="mt-2 text-[11px] text-ink-3">Runs as a real, deterministic (temperature 0) call in live mode; each grade is logged to MLflow.</p>
      </div>
    </>
  );
}
