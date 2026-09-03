import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useConfig } from '../api/useConfig';
import { optimizePrompt } from '../api/client';
import { useSession } from '../store/session';
import type { LaneContext, ModelDef, Tier } from '../api/types';
import { TIER_SHORT, TIER_META } from '../api/types';
import { formatMoney, formatHeadline, formatScore, formatLatency } from '../lib/format';
import { QuestionLibrary } from '../components/QuestionLibrary';
import { RoutingSteps, RoiChart, compact, type RStep } from '../components/RoutingViz';

// Tab 1 - Compare all models (§6.1). Three fixed lanes; each streams its answer
// with live cost accrual; the cheapest lane within 1.0 judge point of the best
// wins. Numbers are server-authored (§7) - the client only selects the winner.
//
// Two run modes: "Run" sends the prompt as typed; "Optimize + Run" runs BOTH the
// prompt as typed AND the optimized rewrite through every lane so the tokenomics
// (tokens added/saved) and the output difference are shown side by side.

const usd = (n: number) => formatMoney(n); // per-query + rate figures (formatMoney keeps sub-cent precision)
const big = (n: number) => formatHeadline(n);
const tok = (n: number | null) => (n == null ? '-' : n.toLocaleString());

// The complexity class each tier is meant for - a "Simple / Medium / Complex"
// heading on each lane so it's clear what kind of prompt the model is the pick for.
const TIER_CX_LABEL: Record<Tier, string> = { 'small-oss': 'Simple', 'large-oss': 'Medium', frontier: 'Complex' };

// Small uppercase label on dark.
const LBL = 'font-body text-[9.5px] font-semibold uppercase tracking-[.14em] text-white/45';
// Bold, coloured section header (the box titles) - makes each box pop.
const SECTION = 'font-display text-[13px] font-bold uppercase tracking-[.15em] text-[#7FB6F2]';

// Preset prompts spanning trivial → data/AI-architecture → strategy, so the
// routing spread is visible when you run them. (Complexity dots live only on the
// Context routing tab; Compare just shows the prompt.)
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

// A lane that hasn't resolved in this long is force-finished as "timed out" so a
// slow model (e.g. opus-4-1 on a very long prompt, which can exceed the
// Databricks Apps request timeout) never hangs the whole comparison.
const LANE_TIMEOUT_MS = 70_000;

// A lane whose judge score is within this many points of the best answer counts
// as "matching" the top quality - so the winner is decided on cost among them.
// At 1.0 a cheaper/faster model that scores within a full judge point of the
// frontier is treated as the best value (a 1-point gap goes to the cheaper model).
const QUALITY_BAND = 1.0;

// A lane = one model, with the "as typed" run and (in optimize mode) the
// optimized-prompt run so we can show a true before/after.
interface LaneState {
  modelId: string;
  base: RunData;
  opt: RunData | null;
}

type Phase = 'idle' | 'optimizing' | 'running';
type RunMode = 'plain' | 'optimized';
type Variant = 'base' | 'opt';

const streamingRun = (): RunData => ({ answer: '', costUsd: 0, latencyMs: null, judgeScore: null, judgeReason: '', inputTokens: null, outputTokens: null, context: null, streaming: true, done: false, error: false });
const idleRun = (): RunData => ({ ...streamingRun(), streaming: false });

function defaultLanes(models: ModelDef[]): string[] {
  // Defaults: frontier → opus-5; large-OSS ("Medium") → glm-5.3 (the pick shown in
  // that dropdown); small-OSS → the cheapest model in the tier. "Cheapest" is by
  // representative per-query cost (800 in / 400 out) so a low output rate can't
  // hide a higher input rate. Pins fall back to cheapest-by-cost if absent.
  const perQ = (m: ModelDef) => 800 * m.price_in_per_1m + 400 * m.price_out_per_1m;
  const cheapestOf = (t: Tier) => [...models.filter((m) => m.tier === t)].sort((a, b) => perQ(a) - perQ(b))[0]?.id;
  const pin = (id: string, t: Tier) => models.find((m) => m.id === id)?.id ?? cheapestOf(t);
  const chosen = [pin('databricks-claude-opus-5', 'frontier'), pin('databricks-glm-5-3', 'large-oss'), cheapestOf('small-oss')].filter(Boolean) as string[];
  // Backfill to exactly three from the registry if a tier is missing.
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
  const [runMode, setRunMode] = useState<RunMode>('plain');
  const [winnerIdx, setWinnerIdx] = useState<number | null>(null);
  const [baseWinnerIdx, setBaseWinnerIdx] = useState<number | null>(null);
  const [users, setUsers] = useState(100);
  const [perUserQ, setPerUserQ] = useState(50);
  const volume = users * perUserQ; // total monthly query volume - both sliders drive it
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [judgeModel, setJudgeModel] = useState('');
  const [judgeInfo, setJudgeInfo] = useState(false);
  const [optionsInfo, setOptionsInfo] = useState(false);
  const [optimizedPrompt, setOptimizedPrompt] = useState<string | null>(null);
  const [optimizeNote, setOptimizeNote] = useState<string | null>(null);
  const [baselinePrompt, setBaselinePrompt] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({}); // per-lane response expand
  const [ctxOpen, setCtxOpen] = useState<Record<number, boolean>>({}); // per-lane context expand
  const [tokOpen, setTokOpen] = useState<Record<number, boolean>>({}); // per-lane tokenomics expand
  const [respView, setRespView] = useState<Record<number, Variant>>({}); // which run's answer to show
  const [optOpen, setOptOpen] = useState(false); // expand the full optimized prompt text
  const sourcesRef = useRef<EventSource[]>([]);
  const timersRef = useRef<number[]>([]);
  const clearTimers = () => { timersRef.current.forEach((t) => clearTimeout(t)); timersRef.current = []; };

  const running = phase !== 'idle';
  const isOpt = runMode === 'optimized';

  // The run shown as the headline for a lane: the optimized run in optimize mode,
  // else the "as typed" run.
  const primaryOf = (l: LaneState): RunData => (isOpt && l.opt ? l.opt : l.base);

  // Default the judge to opus-4-8 (a strong, impartial grader); fall back to any
  // frontier model, then the first model, if it isn't in this workspace.
  useEffect(() => {
    if (cfg && !judgeModel) {
      const f = cfg.models.find((m) => m.id === 'databricks-claude-opus-4-8')
        ?? cfg.models.find((m) => m.tier === 'frontier') ?? cfg.models[0];
      if (f) setJudgeModel(f.id);
    }
  }, [cfg, judgeModel]);

  // Seed the three lanes once config lands.
  useEffect(() => {
    if (cfg && lanes.length === 0) {
      setLanes(defaultLanes(cfg.models).map((modelId) => ({ modelId, base: idleRun(), opt: null })));
    }
  }, [cfg, lanes.length]);

  useEffect(() => () => { sourcesRef.current.forEach((s) => s.close()); clearTimers(); }, []);

  const models = cfg?.models ?? [];
  const modelById = useMemo(() => new Map(models.map((m) => [m.id, m])), [models]);

  const setLaneModel = (i: number, modelId: string) => {
    setWinnerIdx(null);
    setBaseWinnerIdx(null);
    setLanes((ls) => ls.map((l, j) => (j === i ? { modelId, base: idleRun(), opt: null } : l)));
  };

  // Editing the prompt invalidates any prior optimized rewrite.
  const editPrompt = (v: string) => {
    setPrompt(v);
    if (optimizedPrompt || baselinePrompt) {
      setOptimizedPrompt(null);
      setBaselinePrompt(null);
      setOptimizeNote(null);
    }
  };

  // Option A - Run: run all three lanes on the prompt exactly as typed.
  const run = () => {
    if (running || lanes.length < 3 || !prompt.trim()) return;
    setOptimizedPrompt(null);
    setBaselinePrompt(null);
    setOptimizeNote(null);
    runAll(prompt.trim(), null);
  };

  // Option B - Optimize + Run: rewrite the prompt first, reveal it, then run the
  // three lanes on BOTH the original and the optimized prompt for a before/after.
  const optimizeAndRun = async () => {
    if (running || lanes.length < 3 || !prompt.trim()) return;
    const base = prompt.trim();
    setWinnerIdx(null);
    setBaseWinnerIdx(null);
    setBaselinePrompt(base); // remember the original to price the delta
    setPhase('optimizing');
    let effective = base;
    try {
      const r = await optimizePrompt(base, judgeModel);
      if (r.optimized) {
        setOptimizedPrompt(r.optimized);
        setOptimizeNote(r.model ? `Rewritten by ${r.model}` : r.note ?? null);
        effective = r.optimized;
      }
    } catch {
      // Optimizer unavailable - fall back to running the original prompt only.
    }
    // If the rewrite matched the original (or failed), just run plainly.
    runAll(base, effective !== base ? effective : null);
  };

  // Reset - clear the prompt, presets, optimizer state and all three lanes.
  const resetAll = () => {
    sourcesRef.current.forEach((s) => s.close());
    sourcesRef.current = [];
    clearTimers();
    setPrompt('');
    setActivePreset(-1);
    setOptimizedPrompt(null);
    setBaselinePrompt(null);
    setOptimizeNote(null);
    setOptOpen(false);
    setWinnerIdx(null);
    setBaseWinnerIdx(null);
    setExpanded({});
    setCtxOpen({});
    setTokOpen({});
    setRespView({});
    setRunMode('plain');
    setLanes((ls) => ls.map((l) => ({ modelId: l.modelId, base: idleRun(), opt: null })));
    setPhase('idle');
  };

  // Fan out: open one SSE per (lane × variant). When optPrompt is given every
  // lane runs twice - the "as typed" prompt and the optimized rewrite.
  const runAll = (basePrompt: string, optPrompt: string | null) => {
    sourcesRef.current.forEach((s) => s.close());
    sourcesRef.current = [];
    clearTimers();
    const mode: RunMode = optPrompt ? 'optimized' : 'plain';
    setRunMode(mode);
    setWinnerIdx(null);
    setBaseWinnerIdx(null);
    setExpanded({});
    setCtxOpen({});
    setTokOpen({});
    setRespView(optPrompt ? Object.fromEntries(lanes.map((_, i) => [i, 'opt' as Variant])) : {});
    setPhase('running');
    setLanes((ls) => ls.map((l) => ({ modelId: l.modelId, base: streamingRun(), opt: optPrompt ? streamingRun() : null })));

    const variants: { v: Variant; p: string }[] = optPrompt
      ? [{ v: 'base', p: basePrompt }, { v: 'opt', p: optPrompt }]
      : [{ v: 'base', p: basePrompt }];
    const totalConns = lanes.length * variants.length;
    const finals: Record<string, RunData & { idx: number }> = {};
    const done = new Set<string>();
    const laneModelIds = lanes.map((l) => l.modelId);

    const resolve = (i: number, v: Variant, patch: Partial<RunData>, es: EventSource) => {
      const key = `${i}:${v}`;
      if (done.has(key)) return;
      done.add(key);
      es.close();
      setLanes((ls) =>
        ls.map((l, j) => {
          if (j !== i) return l;
          const cur = v === 'opt' ? l.opt ?? streamingRun() : l.base;
          const merged = { ...cur, ...patch, streaming: false, done: true };
          return v === 'opt' ? { ...l, opt: merged } : { ...l, base: merged };
        }),
      );
      finals[key] = { idx: i, ...streamingRun(), ...patch, streaming: false, done: true };
      if (done.size === totalConns) { clearTimers(); finish(finals, mode, laneModelIds, basePrompt); }
    };

    variants.forEach(({ v, p }) => {
      lanes.forEach((lane, i) => {
        const es = new EventSource(`/api/compare/lane?prompt=${encodeURIComponent(p)}&modelId=${encodeURIComponent(lane.modelId)}&judgeModel=${encodeURIComponent(judgeModel)}`);
        sourcesRef.current.push(es);
        es.onmessage = (ev) => {
          const d = JSON.parse(ev.data);
          if (d.type === 'token') {
            setLanes((ls) =>
              ls.map((l, j) => {
                if (j !== i) return l;
                if (v === 'opt') return { ...l, opt: { ...(l.opt ?? streamingRun()), answer: d.text, costUsd: d.costUsd } };
                return { ...l, base: { ...l.base, answer: d.text, costUsd: d.costUsd } };
              }),
            );
          } else if (d.type === 'done') {
            resolve(i, v, { answer: d.answer, costUsd: d.costUsd, latencyMs: d.latencyMs, judgeScore: d.judgeScore, judgeReason: d.judgeReason ?? '', inputTokens: d.inputTokens, outputTokens: d.outputTokens, context: d.context ?? null, error: !!d.error }, es);
          }
        };
        es.onerror = () => {
          resolve(i, v, { answer: '(no response - the model timed out or is unavailable in this workspace)', costUsd: 0, latencyMs: null, judgeScore: 0, judgeReason: '', inputTokens: null, outputTokens: null, context: null, error: true }, es);
        };
        // Watchdog: a lane that never resolves (slow model past the Apps request
        // timeout) is force-finished as timed-out so the comparison completes.
        const timer = window.setTimeout(() => {
          resolve(i, v, { answer: '(timed out - this model took too long for a side-by-side comparison; try a faster frontier model like sonnet or opus-4-8)', costUsd: 0, latencyMs: null, judgeScore: 0, judgeReason: '', inputTokens: null, outputTokens: null, context: null, error: true }, es);
        }, LANE_TIMEOUT_MS);
        timersRef.current.push(timer);
      });
    });
  };

  // Best value = quality AND cost: among the lanes whose answer is within
  // QUALITY_BAND judge points of the best answer (i.e. that "clear the bar"),
  // pick the cheapest. On an easy prompt a cheap model ties on quality and wins
  // on price; on a hard one only the frontier clears the bar, so it wins.
  const pickWinner = (finals: Record<string, RunData & { idx: number }>, v: Variant, n: number): (RunData & { idx: number }) | null => {
    const cands = Array.from({ length: n }, (_, i) => finals[`${i}:${v}`]).filter((r) => r && !r.error && r.judgeScore != null);
    if (!cands.length) return null;
    const best = Math.max(...cands.map((r) => r.judgeScore ?? 0));
    const withinBar = cands.filter((r) => (r.judgeScore ?? 0) >= best - QUALITY_BAND);
    return [...withinBar].sort((a, b) => a.costUsd - b.costUsd || (b.judgeScore ?? 0) - (a.judgeScore ?? 0))[0];
  };

  const finish = (finals: Record<string, RunData & { idx: number }>, mode: RunMode, laneModelIds: string[], basePrompt: string) => {
    setPhase('idle');
    const primary: Variant = mode === 'optimized' ? 'opt' : 'base';
    const win = pickWinner(finals, primary, laneModelIds.length);
    if (!win) {
      setWinnerIdx(null);
      return;
    }
    const primCands = laneModelIds.map((_, i) => finals[`${i}:${primary}`]).filter((r) => r && !r.error && r.judgeScore != null);
    // Baseline = priciest lane that returned, OR the winner's frontier
    // counterfactual when the frontier lane failed - so savings never collapse to
    // $0 just because the expensive lane timed out.
    const cf = win.context?.decision?.counterfactual?.costUsd ?? 0;
    const worst = Math.max(cf, ...primCands.map((r) => r.costUsd));
    setWinnerIdx(win.idx);
    if (mode === 'optimized') {
      const bw = pickWinner(finals, 'base', laneModelIds.length);
      setBaseWinnerIdx(bw ? bw.idx : null);
    }
    // Record the winning request for the Cost tab + masthead totals.
    const wm = modelById.get(laneModelIds[win.idx]);
    if (wm) {
      logRun({
        source: 'compare',
        modelShort: wm.short,
        tier: wm.tier,
        costUsd: win.costUsd,
        baselineUsd: worst,
        inputTokens: win.inputTokens ?? 0,
        outputTokens: win.outputTokens ?? 0,
        latencyMs: win.latencyMs ?? undefined,
        optimized: mode === 'optimized',
        promptSnippet: basePrompt,
      });
      setLastRouting({ model: wm.short, tier: wm.tier, costUsd: win.costUsd, source: 'compare' });
    }
  };

  // ROI compares the ACTUAL best-value winner against the frontier model, so the
  // chart shows the real saving from routing this prompt to the cheaper lane that
  // still cleared the quality bar (vs sending it to the frontier). Blank until a
  // winner is known; reacts live to both sliders.
  const roi = useMemo(() => {
    if (winnerIdx == null) return null;
    const winRun = primaryOf(lanes[winnerIdx]);
    if (!winRun.done || winRun.error || winRun.costUsd <= 0) return null;
    const bestPer = winRun.costUsd;
    const doneRuns = lanes
      .map((l, i) => ({ r: primaryOf(l), m: modelById.get(l.modelId), i }))
      .filter((x) => x.r.done && !x.r.error && x.r.costUsd > 0);
    if (!doneRuns.length) return null;

    // The frontier reference line, chosen so it NEVER implies a model returned
    // data when it didn't:
    //  1) a frontier-tier lane that actually returned → real, labelled with it;
    //  2) else if your selected frontier model returned NOTHING → estimate its
    //     cost from ITS OWN rate card × the winner's tokens, and mark it "est.";
    //  3) else (no frontier lane at all) → the priciest lane that returned.
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
    // The add-on cost of the SMALL LLM that does the routing (classify) and, in
    // optimize mode, the prompt optimization - priced on the cheapest small model.
    // Shown so the story is honest: even after paying the router/optimizer, the
    // all-in routed cost stays far below always calling the frontier.
    const smalls = Array.from(modelById.values()).filter((m) => m.tier === 'small-oss').sort((a, b) => a.price_out_per_1m - b.price_out_per_1m);
    const smallModel = smalls[0];
    const inTok = winRun.inputTokens ?? 0;
    const routerPer = smallModel ? (inTok / 1e6) * smallModel.price_in_per_1m + (8 / 1e6) * smallModel.price_out_per_1m : 0;
    const optimizerPer = isOpt && smallModel ? (inTok / 1e6) * smallModel.price_in_per_1m + (inTok / 1e6) * smallModel.price_out_per_1m : 0;
    const overheadPer = routerPer + optimizerPer;
    const allInPer = bestPer + overheadPer;
    const cheaperX = allInPer > 0 ? frontierPer / allInPer : null;

    const monthly = { frontier: frontierPer * volume, routed: bestPer * volume };
    return {
      monthly, savedYr: (frontierPer - bestPer) * volume * 12, frontierShort, frontierEstimated,
      overheadYr: overheadPer * volume * 12, allInYr: allInPer * volume * 12,
      cheaperX: cheaperX != null ? Math.round(cheaperX * 10) / 10 : null,
      routerShort: smallModel?.short, hasOptimizer: isOpt && optimizerPer > 0,
    };
  }, [lanes, volume, isOpt, winnerIdx, modelById]); // eslint-disable-line react-hooks/exhaustive-deps

  const hasWinner = winnerIdx !== null;
  const winnerModel = winnerIdx !== null ? modelById.get(lanes[winnerIdx]?.modelId) : null;
  // The frontier-tier lane's model - the reference line in the ROI chart. After a
  // run, use the frontier the ROI actually priced against (which is marked
  // estimated if that model returned no data), so the label never misrepresents a
  // non-responding model as measured.
  const frontierLaneShort = lanes.map((l) => modelById.get(l.modelId)).find((mm) => mm?.tier === 'frontier')?.short;
  const frontierRefShort = roi?.frontierShort ?? frontierLaneShort;
  const frontierEstimated = roi?.frontierEstimated ?? false;
  // Frontier is the best value here (no cheaper model cleared the bar): routed ≈
  // frontier, so the two "/ yr" tiles would duplicate and there's no saving.
  const frontierWon = !!roi && (roi.cheaperX == null || roi.cheaperX < 1.05);
  // Cheapest / fastest tags (on the primary run) - independent of the judge's winner.
  const doneLanes = lanes.map((l, i) => ({ r: primaryOf(l), i })).filter((x) => x.r.done && !x.r.error);
  const cheapestIdx = doneLanes.length ? doneLanes.reduce((a, b) => (b.r.costUsd < a.r.costUsd ? b : a)).i : null;
  const fastestIdx = doneLanes.length ? doneLanes.reduce((a, b) => ((b.r.latencyMs ?? 1e9) < (a.r.latencyMs ?? 1e9) ? b : a)).i : null;

  // Step-by-step routing pipeline (the previous app's live routing steps).
  const winRun = winnerIdx != null ? primaryOf(lanes[winnerIdx]) : null;
  const flowSteps: RStep[] = [
    { key: 'p', label: 'Prompt', detail: isOpt ? 'optimized' : 'one question', glyph: '✎', accent: '#67B8F0' },
    { key: 'lanes', label: '3 models', detail: 'answer in parallel', glyph: '⋯', accent: '#67C7E8' },
    { key: 'judge', label: 'LLM judge', detail: 'scores each answer', glyph: '★', accent: '#F5B24B' },
    { key: 'win', label: winnerModel ? winnerModel.short : 'Winner', detail: winRun ? usd(winRun.costUsd) : 'best quality', glyph: '◆', accent: '#FF3621', landed: hasWinner },
    { key: 'resp', label: 'Response', detail: winRun?.latencyMs != null ? `${winRun.latencyMs}ms` : 'returned', glyph: '✓', accent: '#4FD79E' },
  ];

  // Optimization impact: the whole point of the tab. Compares the optimized run
  // to the "as typed" run - both on the same winning model (per-query token/cost
  // delta) AND across lanes (a sharper prompt letting a cheaper model win).
  const impact = useMemo(() => {
    if (!isOpt || winnerIdx == null) return null;
    const optW = lanes[winnerIdx]?.opt;
    if (!optW || !optW.done) return null;
    const baseW = baseWinnerIdx != null ? lanes[baseWinnerIdx]?.base : null;
    const optModel = modelById.get(lanes[winnerIdx].modelId)?.short ?? '';
    const baseModel = baseWinnerIdx != null ? modelById.get(lanes[baseWinnerIdx].modelId)?.short ?? '' : '';
    // Same-model token delta: optimized winner vs its own "as typed" run.
    const selfBase = lanes[winnerIdx]?.base;
    const dIn = selfBase?.done && selfBase.inputTokens != null && optW.inputTokens != null ? optW.inputTokens - selfBase.inputTokens : null;
    const dOut = selfBase?.done && selfBase.outputTokens != null && optW.outputTokens != null ? optW.outputTokens - selfBase.outputTokens : null;
    // Cross-lane cost delta: the priciest model shifted to the optimized winner.
    const baseCost = baseW?.done ? baseW.costUsd : null;
    const optCost = optW.costUsd;
    const perQuerySaved = baseCost != null ? baseCost - optCost : null;
    const pctSaved = baseCost && baseCost > 0 && perQuerySaved != null ? (perQuerySaved / baseCost) * 100 : null;
    const modelChanged = baseWinnerIdx != null && baseWinnerIdx !== winnerIdx;
    return { optModel, baseModel, dIn, dOut, baseCost, optCost, perQuerySaved, pctSaved, modelChanged, savedYear: perQuerySaved != null ? perQuerySaved * volume * 12 : null };
  }, [isOpt, winnerIdx, baseWinnerIdx, lanes, modelById, volume]);

  // Counterfactual hint after a plain Run: what optimizing the prompt could save
  // (grounded in the lanes actually run). Optimized mode shows the ImpactPanel
  // instead, so this only appears for plain Run.
  const runModeHint = useMemo(() => {
    if (isOpt || winnerIdx == null) return null;
    const winRun = primaryOf(lanes[winnerIdx]);
    if (!winRun.done || winRun.error) return null;
    const done = lanes.map((l) => ({ r: primaryOf(l), m: modelById.get(l.modelId) })).filter((x) => x.r.done && !x.r.error && x.r.costUsd > 0);
    if (!done.length) return null;
    const cheapest = done.reduce((a, b) => (b.r.costUsd < a.r.costUsd ? b : a));
    const winnerIsCheapest = cheapest.r.costUsd >= winRun.costUsd - 1e-12;
    const potentialYr = Math.max(0, (winRun.costUsd - cheapest.r.costUsd) * volume * 12);
    return { winner: winnerModel?.short ?? '', cheaper: cheapest.m?.short ?? '', winnerIsCheapest, potentialYr };
  }, [isOpt, winnerIdx, lanes, volume, modelById, winnerModel]); // eslint-disable-line react-hooks/exhaustive-deps

  // Outcome for the StoryHero (Box 1): the winning lane vs the priciest lane it beat.
  const outcome = (() => {
    if (!hasWinner || !winnerModel || winnerIdx == null) return null;
    const wcost = primaryOf(lanes[winnerIdx]).costUsd;
    const costs = lanes.map(primaryOf).filter((r) => r.done && !r.error).map((r) => r.costUsd);
    const top = costs.length ? Math.max(...costs) : wcost;
    return { model: winnerModel.short, perQuery: usd(wcost), savedYear: big((top - wcost) * volume * 12) };
  })();

  return (
    <div className="flex flex-col gap-[22px] text-white">
      {/* Box 1 - Compare models + why */}
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

        {/* Wide, highlighted prompt box - copy/paste freely; ⌘/Ctrl+Enter to run */}
        <div className="relative rounded-2xl bg-black/30 p-1 shadow-[0_0_0_4px_rgba(255,54,33,0.07),0_20px_44px_-16px_rgba(255,54,33,0.4)] ring-2 ring-lava/40 transition focus-within:ring-lava/70">
          <textarea
            className="block w-full resize-none border-none bg-transparent px-5 py-4 text-[15px] leading-[1.6] text-white outline-none placeholder:text-white/35"
            rows={2}
            value={prompt}
            onChange={(e) => editPrompt(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); run(); } }}
            placeholder="Ask anything, or paste a question here - the same prompt goes to all three lanes"
          />
        </div>

        {/* Preset prompts + reset. */}
        <div className="relative mt-3.5 flex flex-wrap items-center gap-2">
          {PRESETS.map((p, i) => (
            <button
              key={i}
              aria-pressed={activePreset === i}
              onClick={() => {
                setActivePreset(i);
                editPrompt(p.prompt);
              }}
              className="inline-flex items-center rounded-pill bg-white/10 px-3.5 py-1.5 text-[12.5px] text-white/75 transition hover:-translate-y-px hover:bg-white/15 hover:text-white aria-pressed:bg-white aria-pressed:text-ink"
            >
              {p.label}
            </button>
          ))}
          <button
            onClick={() => setLibraryOpen(true)}
            className="rounded-pill bg-white/15 px-3.5 py-1.5 text-[12.5px] font-bold text-white ring-1 ring-white/20 transition hover:bg-white/25"
          >
            Browse examples →
          </button>
          <button
            onClick={resetAll}
            disabled={running}
            title="Clear the prompt and all results"
            className="ml-auto rounded-pill bg-white/[0.06] px-3.5 py-1.5 text-[12.5px] font-medium text-white/60 ring-1 ring-white/10 transition hover:bg-white/12 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            ↺ Reset
          </button>
        </div>

        {/* Action row - centered on its own line: judge + the two run options */}
        <div className="relative mt-5 flex flex-wrap items-center justify-center gap-2.5">
          {/* Pick a Judge */}
          <div className="relative flex items-center gap-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-[.08em] text-white/55">Pick a Judge</span>
            <select
              value={judgeModel}
              onChange={(e) => setJudgeModel(e.target.value)}
              aria-label="Pick a Judge"
              className="num max-w-[150px] cursor-pointer rounded-pill bg-white/10 px-3 py-2.5 text-[12px] text-white ring-1 ring-white/10 outline-none"
            >
              {models.map((m) => <option key={m.id} value={m.id} className="text-ink">{m.short}</option>)}
            </select>
            <button
              onClick={() => { setJudgeInfo((v) => !v); setOptionsInfo(false); }}
              aria-label="How to pick a judge"
              className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-[12px] text-white/50 transition hover:bg-white/10 hover:text-white"
            >
              ⓘ
            </button>
            {judgeInfo && <JudgeInfo onClose={() => setJudgeInfo(false)} />}
          </div>

          <span className="mx-1 hidden h-6 w-px bg-white/15 sm:block" />

          {/* Option A - Run (as typed) */}
          <button
            onClick={run}
            disabled={running || !prompt.trim()}
            className="rounded-pill bg-white/10 px-[24px] py-3 text-[13px] font-semibold text-white/90 ring-1 ring-white/15 shadow-lift transition hover:bg-white/15 hover:text-white disabled:cursor-not-allowed disabled:opacity-45"
          >
            {phase === 'running' && !isOpt ? 'Running…' : 'Run'}
          </button>
          {/* Option B - Optimize + Run */}
          <button
            onClick={optimizeAndRun}
            disabled={running || !prompt.trim()}
            className="flex items-center gap-1.5 rounded-pill bg-lava px-[24px] py-3 text-[13px] font-semibold text-white shadow-lift transition hover:bg-[#e22e1a] disabled:cursor-not-allowed disabled:opacity-45"
          >
            <span className="text-[12px]">✨</span>
            {phase === 'optimizing' ? 'Optimizing…' : phase === 'running' && isOpt ? 'Running both…' : 'Optimize + Run'}
          </button>
          {/* Single info popover explaining both options - opens upward */}
          <div className="relative flex items-center">
            <button
              onClick={() => { setOptionsInfo((v) => !v); setJudgeInfo(false); }}
              aria-label="What do Run and Optimize + Run do?"
              className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-[12px] text-white/50 transition hover:bg-white/10 hover:text-white"
            >
              ⓘ
            </button>
            {optionsInfo && <OptionsInfo onClose={() => setOptionsInfo(false)} />}
          </div>
        </div>

        {/* Optimized-prompt reveal - KPIs only; the full prompt is behind an expand */}
        {optimizedPrompt && (
          <div className="relative mt-4 overflow-hidden rounded-xl bg-white/[0.05] p-[16px] ring-1 ring-white/10">
            <div className="absolute inset-y-0 left-0 w-1.5 bg-gradient-to-b from-plum to-[#B487D0]" />
            <div className="flex flex-wrap items-center gap-2 pl-2">
              <span className="text-[16px]">✨</span>
              <span className="font-display text-[15px] font-bold text-[#CBA6E2]">Optimized prompt</span>
              {optimizeNote && <span className="text-[12.5px] font-medium text-white/60">· {optimizeNote}</span>}
              {phase === 'running' && isOpt && <span className="text-[12.5px] font-medium text-white/60">· running both prompts</span>}
              <span className="ml-auto flex items-center gap-2">
                <span className="text-[11.5px] text-white/45">Editable · re-run to compare your version</span>
                <button
                  onClick={() => setOptOpen((v) => !v)}
                  className="rounded-pill bg-white/10 px-3 py-1.5 text-[12px] font-semibold text-white/75 ring-1 ring-white/10 transition hover:bg-white/15 hover:text-white"
                >
                  {optOpen ? 'Hide prompt ▲' : 'Edit prompt ▼'}
                </button>
                <button
                  onClick={() => { const b = (baselinePrompt ?? prompt).trim(); const o = optimizedPrompt?.trim(); if (b && o && !running) runAll(b, o); }}
                  disabled={running || !optimizedPrompt?.trim()}
                  className="rounded-pill bg-lava px-3 py-1.5 text-[12px] font-semibold text-white shadow-lift transition hover:bg-[#e22e1a] disabled:cursor-not-allowed disabled:opacity-45"
                >
                  ↻ Re-run
                </button>
              </span>
            </div>
            {optOpen && (
              <div className="mt-2.5 grid grid-cols-2 gap-3 pl-2 max-[560px]:grid-cols-1">
                <div className="rounded-lg bg-black/25 p-3 ring-1 ring-white/10">
                  <div className={LBL}>As typed</div>
                  <p className="mt-1.5 text-[13px] leading-[1.6] text-white/70">{baselinePrompt}</p>
                </div>
                <div className="rounded-lg bg-plum/10 p-3 ring-1 ring-plum/25">
                  <div className={`${LBL} text-[#CBA6E2]`}>Optimized · editable</div>
                  <textarea
                    value={optimizedPrompt ?? ''}
                    onChange={(e) => setOptimizedPrompt(e.target.value)}
                    rows={5}
                    className="mt-1.5 w-full resize-y rounded bg-black/20 px-2.5 py-2 text-[13px] leading-[1.6] text-white/90 ring-1 ring-plum/25 outline-none transition focus:ring-plum/60"
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Box 3 - LLM results */}
      <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[22px] pt-5 shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.12s' }}>
        <div className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-lava opacity-[.09] blur-3xl" />
        <div className={`${SECTION} relative mb-1`}>Results</div>

        {/* Optimization impact - the headline before/after when Optimize + Run was used */}
        {impact && <ImpactPanel impact={impact} />}

        {/* Counterfactual hint - after a plain Run, show what optimizing could save */}
        {runModeHint && <RunHint hint={runModeHint} />}

        {/* Lanes (dark cards), staggered entrance motion. Fixed 3 columns;
            scroll horizontally on narrow, never stack. Padding leaves room for the
            winner's ring/glow. */}
        <div className="grid grid-cols-[repeat(3,minmax(280px,1fr))] items-start gap-[18px] overflow-x-auto px-4 py-6">
          {lanes.map((lane, i) => (
            <LaneCard
              key={i}
              lane={lane}
              i={i}
              model={modelById.get(lane.modelId)}
              models={models}
              isOpt={isOpt}
              won={winnerIdx === i}
              hasWinner={hasWinner}
              running={running}
              isCheapest={i === cheapestIdx}
              isFastest={i === fastestIdx}
              respView={respView[i] ?? (isOpt ? 'opt' : 'base')}
              expanded={!!expanded[i]}
              ctxOpen={!!ctxOpen[i]}
              tokOpen={!!tokOpen[i]}
              onModel={(id) => setLaneModel(i, id)}
              onRespView={(v) => setRespView((s) => ({ ...s, [i]: v }))}
              onExpand={() => setExpanded((e) => ({ ...e, [i]: !e[i] }))}
              onCtx={() => setCtxOpen((c) => ({ ...c, [i]: !c[i] }))}
              onTok={() => setTokOpen((t) => ({ ...t, [i]: !t[i] }))}
            />
          ))}
        </div>
      </section>

      {/* Box 4 - routing economics: how traffic routes across tiers + the ROI of doing so */}
      <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[26px] shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.18s' }}>
        <div className="pointer-events-none absolute -bottom-24 -right-24 h-80 w-80 rounded-full bg-lava opacity-[.08] blur-3xl" />
        <div className="relative flex flex-col gap-[18px]">
          <div className={SECTION}>Routing economics</div>
          <div className="flex flex-col gap-[18px]">
            <VizPanel title="Visualizing intelligent routing flow"><RoutingSteps steps={flowSteps} running={running} /></VizPanel>
            <VizPanel title="Best value vs frontier - projected savings">
              <div className="flex flex-col gap-4">
                <div className="grid grid-cols-2 gap-4 max-[520px]:grid-cols-1">
                  <VizSlider label="Monthly active users" value={users} min={100} max={200000} step={100} onChange={setUsers} accent="accent-[#B487D0]" />
                  <VizSlider label="Queries / user / month" value={perUserQ} min={1} max={2000} step={1} onChange={setPerUserQ} accent="accent-lava" />
                </div>
                {/* Cumulative cost figures ABOVE the chart, so they stay readable
                    while you drag the sliders (the chart re-animates below). When
                    the frontier IS the best value, the two "/ yr" tiles would be
                    identical - collapse to a single cost tile + a $0-saved note. */}
                {frontierWon ? (
                  <>
                    <div className="grid grid-cols-3 gap-2 max-[520px]:grid-cols-1">
                      <VizStat label="Total queries / mo" value={volume ? volume.toLocaleString() : '-'} />
                      <VizStat label={winnerModel ? `${winnerModel.short} / yr` : 'Cost / yr'} value={roi ? compact(roi.monthly.frontier * 12) : '-'} />
                      <VizStat label="Saved / yr" value="$0" />
                    </div>
                    <p className="rounded-lg bg-white/[0.04] px-3 py-2 text-[11.5px] leading-[1.5] text-white/55 ring-1 ring-white/10">
                      The frontier model was the best value model that cleared the quality bar on this prompt.
                    </p>
                  </>
                ) : (
                  <div className="grid grid-cols-4 gap-2 max-[520px]:grid-cols-2">
                    <VizStat label="Total queries / mo" value={volume ? volume.toLocaleString() : '-'} />
                    <VizStat label={frontierRefShort ? `${frontierRefShort}${frontierEstimated ? ' (est.)' : ''} / yr` : 'Frontier / yr'} value={roi ? compact(roi.monthly.frontier * 12) : '-'} />
                    <VizStat label={winnerModel ? `${winnerModel.short} / yr` : 'Best value / yr'} value={roi ? compact(roi.monthly.routed * 12) : '-'} />
                    <VizStat label="Saved / yr" value={roi ? compact(roi.savedYr) : '-'} color="#4FD79E" />
                  </div>
                )}
                <div className="relative">
                  <RoiChart roi={roi} frontierLabel={frontierRefShort ? `${frontierEstimated ? 'FRONTIER (EST.)' : 'FRONTIER'} · ${frontierRefShort}` : 'FRONTIER MODEL'} routedLabel={winnerModel ? `BEST VALUE · ${winnerModel.short}` : 'BEST VALUE'} />
                  {!roi && (
                    <div className="absolute inset-0 grid place-items-center px-6 text-center">
                      <p className="max-w-[42ch] text-[12.5px] leading-[1.5] text-white/45">
                        Run a comparison above: this plots the best-value winner against the frontier model over 12 months, so you see the true saving. Move the sliders to scale it to your traffic.
                      </p>
                    </div>
                  )}
                </div>
                {roi && frontierEstimated && (
                  <p className="rounded-lg bg-white/[0.04] px-3 py-2 text-[11.5px] leading-[1.5] text-white/55 ring-1 ring-white/10">
                    <span className="font-semibold text-[#FF9E8C]">{frontierRefShort}</span> returned no data this run, so its line is <b>estimated</b> from its rate card × the winner's tokens - the saving shown is what routing avoids versus that frontier price.
                  </p>
                )}
              </div>
            </VizPanel>
          </div>
          <p className="num text-[10.5px] text-white/40">{cfg?.priceFootnote ?? 'Prices from the DBU rate card - see config'}</p>
        </div>
      </section>

      {libraryOpen && (
        <QuestionLibrary
          onPick={(query) => {
            setActivePreset(-1);
            editPrompt(query);
          }}
          onClose={() => setLibraryOpen(false)}
        />
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
  isOpt: boolean;
  won: boolean;
  hasWinner: boolean;
  running: boolean;
  isCheapest: boolean;
  isFastest: boolean;
  respView: Variant;
  expanded: boolean;
  ctxOpen: boolean;
  tokOpen: boolean;
  onModel: (id: string) => void;
  onRespView: (v: Variant) => void;
  onExpand: () => void;
  onCtx: () => void;
  onTok: () => void;
}

function LaneCard({ lane, i, model: m, models, isOpt, won, hasWinner, running, isCheapest, isFastest, respView, expanded, ctxOpen, tokOpen, onModel, onRespView, onExpand, onCtx, onTok }: LaneCardProps) {
  const prim = isOpt && lane.opt ? lane.opt : lane.base;
  const dimmed = hasWinner && !won;
  const isRunning = prim.streaming || (running && !prim.done && !prim.error);
  const shown = respView === 'opt' && lane.opt ? lane.opt : lane.base;
  // Same-model token delta (optimized vs as-typed) for this lane.
  const bothDone = isOpt && lane.opt?.done && lane.base.done && !lane.opt.error && !lane.base.error;
  const dTotal = bothDone && lane.opt!.inputTokens != null && lane.base.inputTokens != null && lane.opt!.outputTokens != null && lane.base.outputTokens != null
    ? (lane.opt!.inputTokens + lane.opt!.outputTokens) - (lane.base.inputTokens + lane.base.outputTokens)
    : null;

  return (
    <article
      style={{ animationDelay: `${i * 90}ms` }}
      className={`group relative flex animate-[fadeUp_.5s_ease_both] flex-col gap-4 overflow-hidden rounded-2xl p-5 transition-all duration-[300ms] ease-soft ${
        won
          ? 'z-10 bg-lava/[0.06] shadow-lift-winner ring-2 ring-lava'
          : dimmed
            ? 'bg-white/[0.03] opacity-50 ring-1 ring-white/10'
            : isRunning
              ? 'bg-white/[0.03] opacity-60 saturate-[.35] ring-1 ring-white/10'
              : 'bg-white/[0.04] ring-1 ring-white/12 hover:-translate-y-1 hover:bg-white/[0.06] hover:ring-white/25'
      }`}
    >
      {won && (
        <div className="-mx-5 -mt-5 flex items-center justify-center gap-1.5 bg-gradient-to-r from-lava to-[#FF6A54] py-1.5 text-[10px] font-semibold uppercase tracking-[.14em] text-white">
          <span className="text-[11px]">🏆</span> Best value
        </div>
      )}
      {/* Header - complexity class this lane is the pick for + model select */}
      <div>
        {m && (
          <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-[.16em]" style={{ color: TIER_META[m.tier].hex }}>
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: TIER_META[m.tier].hex }} />
            {TIER_CX_LABEL[m.tier]}
          </div>
        )}
        <div className="relative">
          <select
            aria-label={`Model for lane ${i + 1}`}
            value={lane.modelId}
            onChange={(e) => onModel(e.target.value)}
            className="w-full cursor-pointer appearance-none rounded-lg bg-black/25 px-3.5 py-3 pr-9 font-display text-[14px] font-semibold tracking-[-.01em] text-white ring-1 ring-white/10 transition hover:bg-black/35"
          >
            {/* Each lane is locked to its own category - the frontier lane lists only
                frontier models, large OSS only large, small OSS only small. */}
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
        <div className="flex items-center gap-2 rounded-lg bg-white/[0.05] px-3 py-2 text-[11.5px] font-medium text-white/70 ring-1 ring-white/10">
          <Dots />
          {isOpt ? `Running both prompts on ${m?.short ?? 'model'}…` : `Running the query on ${m?.short ?? 'model'}…`}
        </div>
      )}

      {/* KPIs - only the winner is highlighted (Cost lava, Score blue). Values are
          tabular + non-wrapping and the tiles can shrink, so nothing overflows. */}
      <div className="grid grid-cols-3 gap-2">
        <div className={`min-w-0 rounded-xl p-2.5 ${won ? 'bg-lava/20 ring-2 ring-lava/60' : 'bg-white/[0.04] ring-1 ring-white/10'}`}>
          <div className={LBL}>Cost / query</div>
          <div className={`num mt-1.5 truncate text-[14px] font-semibold leading-none tracking-[-.02em] ${won ? 'text-lava' : 'text-white'}`}>
            {prim.error ? '-' : prim.costUsd > 0 || prim.done ? usd(prim.costUsd) : '-'}
          </div>
        </div>
        <div className="min-w-0 rounded-xl bg-white/[0.04] p-2.5 ring-1 ring-white/10">
          <div className={LBL}>Latency</div>
          <div className="num mt-1.5 truncate text-[14px] font-semibold leading-none text-white">{prim.streaming ? '···' : prim.latencyMs != null ? formatLatency(prim.latencyMs) : '-'}</div>
        </div>
        <div className={`min-w-0 rounded-xl p-2.5 ${won ? 'bg-[#2272B4]/25 ring-2 ring-[#2272B4]/60' : 'bg-white/[0.04] ring-1 ring-white/10'}`}>
          <div className={LBL}>Score</div>
          <div className={`num mt-1.5 truncate text-[14px] font-semibold leading-none tracking-[-.02em] ${won ? 'text-[#8FC1F0]' : 'text-white'}`}>{prim.error ? '-' : prim.judgeScore != null ? formatScore(prim.judgeScore) : '-'}</div>
        </div>
      </div>

      {/* Why the judge scored it this way - emphasised on the winner */}
      {prim.done && !prim.error && prim.judgeReason && (
        <div className={`rounded-lg px-3 py-2 text-[11.5px] leading-[1.5] ring-1 ${won ? 'bg-lava/10 text-white/85 ring-lava/30' : 'bg-white/[0.03] text-white/60 ring-white/10'}`}>
          <span className={`font-semibold ${won ? 'text-lava' : 'text-white/70'}`}>{won ? '🏆 Why it won: ' : 'Judge: '}</span>
          {prim.judgeReason}
          {won && <span className="mt-1 block text-[10.5px] text-white/45">Best value: the lowest-cost lane whose answer matched the top quality.</span>}
        </div>
      )}

      {/* Response / context / tokenomics - all collapsed so nothing steals focus */}
      <div className="flex flex-col gap-2">
        <div className="grid grid-cols-3 gap-2">
          <MiniToggle open={expanded} onClick={onExpand} disabled={!shown.answer && !shown.streaming} label="response" />
          <MiniToggle open={ctxOpen} onClick={onCtx} disabled={!prim.context} label="context" title="The exact request sent to the model and how it routed" />
          <MiniToggle open={tokOpen} onClick={onTok} disabled={!prim.done} label="tokens" title="Input / output / total tokens" />
        </div>

        {/* Tokenomics - collapsed by default so it doesn't compete with the result */}
        {tokOpen && (
          <div className="rounded-lg bg-black/25 p-3 ring-1 ring-white/10">
            {isOpt && dTotal != null && (
              <div className="mb-2 flex items-center justify-end">
                <span className={`num text-[10.5px] font-bold ${dTotal > 0 ? 'text-[#FF9E8C]' : dTotal < 0 ? 'text-[#93D3AB]' : 'text-white/50'}`}>
                  {dTotal > 0 ? '▲ +' : dTotal < 0 ? '▼ −' : '= '}{dTotal !== 0 ? `${Math.abs(dTotal).toLocaleString()} tok total` : 'no change'}
                </span>
              </div>
            )}
            <div className="grid grid-cols-3 gap-2">
              <TokenStat label="Input" opt={lane.opt} base={lane.base} field="inputTokens" isOpt={isOpt} respView={respView} />
              <TokenStat label="Output" opt={lane.opt} base={lane.base} field="outputTokens" isOpt={isOpt} respView={respView} />
              <TokenStat label="Total" opt={lane.opt} base={lane.base} field="total" isOpt={isOpt} respView={respView} />
            </div>
          </div>
        )}

        {/* Response panel - in optimize mode, a toggle picks which run's answer */}
        {expanded && (
          <div className="rounded-lg bg-black/25 ring-1 ring-white/10">
            {isOpt && lane.opt && (
              <div className="flex gap-1 border-b border-white/10 p-1.5">
                <MiniTab active={respView === 'opt'} onClick={() => onRespView('opt')} label="Optimized" />
                <MiniTab active={respView === 'base'} onClick={() => onRespView('base')} label="As typed" />
              </div>
            )}
            <div className="max-h-[220px] overflow-y-auto px-3.5 py-3 text-[12px] leading-[1.65] text-white/85">
              {shown.streaming && !shown.answer ? (
                <div className="flex items-center gap-2 text-white/45"><Dots />Running {m?.short ?? 'model'}…</div>
              ) : shown.answer ? (
                <span className={shown.error ? 'text-white/50' : ''} style={{ whiteSpace: 'pre-wrap' }}>
                  {shown.answer}
                  {shown.streaming && <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-lava align-[-2px]" />}
                </span>
              ) : (
                <span className="text-white/40">Run the comparison to see this model's answer.</span>
              )}
            </div>
          </div>
        )}

        {ctxOpen && prim.context && <ContextPanel ctx={prim.context} optimized={isOpt} />}
      </div>
    </article>
  );
}

// Per-token stat cell. In optimize mode shows as-typed → optimized (the shown
// variant emphasised); otherwise the single run's count.
function TokenStat({ label, opt, base, field, isOpt, respView }: { label: string; opt: RunData | null; base: RunData; field: 'inputTokens' | 'outputTokens' | 'total'; isOpt: boolean; respView: Variant }) {
  const val = (r: RunData | null) => {
    if (!r) return null;
    if (field === 'total') return r.inputTokens != null && r.outputTokens != null ? r.inputTokens + r.outputTokens : null;
    return r[field];
  };
  const bv = val(base);
  const ov = val(opt);
  if (isOpt && opt) {
    return (
      <div className="rounded-xl bg-white/[0.04] p-2.5 ring-1 ring-white/10">
        <div className={LBL}>{label}</div>
        <div className="num mt-1.5 flex items-baseline gap-1 text-[13px] font-semibold leading-none text-white">
          <span className={respView === 'base' ? '' : 'text-white/40'}>{tok(bv)}</span>
          <span className="text-[10px] text-white/40">→</span>
          <span className={respView === 'opt' ? 'text-[#CBA6E2]' : 'text-white/40'}>{tok(ov)}</span>
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-xl bg-white/[0.04] p-2.5 ring-1 ring-white/10">
      <div className={LBL}>{label}</div>
      <div className="num mt-1.5 text-[16px] font-semibold leading-none text-white">{tok(bv)}</div>
    </div>
  );
}

// The "Show context" panel: exact request payload + routing decision.
function ContextPanel({ ctx, optimized }: { ctx: LaneContext; optimized: boolean }) {
  const { request, decision } = ctx;
  const clears = decision.clears;
  return (
    <div className="flex flex-col gap-3 rounded-lg bg-black/30 p-3.5 text-[11.5px] ring-1 ring-white/10">
      {/* Request payload */}
      <div>
        <div className={`${LBL} mb-1.5`}>Request sent to the model{optimized ? ' (optimized prompt)' : ''}</div>
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
      {/* Routing decision */}
      <div>
        <div className={`${LBL} mb-1.5`}>Routing decision</div>
        <div className="flex flex-col gap-1 rounded-md bg-black/40 p-2.5 ring-1 ring-white/10">
          <Row k="complexity" v={`${decision.complexity} / 100`} />
          <Row k="model tier" v={TIER_SHORT[decision.tier]} />
          <Row k="tier needed" v={TIER_SHORT[decision.requiredTier]} />
          <Row
            k="verdict"
            v={clears ? 'clears the bar' : 'below the bar'}
            badge={clears ? '#93D3AB' : '#FF9E8C'}
          />
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

// Optimization impact headline - the before/after story of Optimize + Run.
interface Impact {
  optModel: string;
  baseModel: string;
  dIn: number | null;
  dOut: number | null;
  baseCost: number | null;
  optCost: number;
  perQuerySaved: number | null;
  pctSaved: number | null;
  modelChanged: boolean;
  savedYear: number | null;
}

function ImpactPanel({ impact }: { impact: Impact }) {
  const saved = impact.perQuerySaved != null && impact.perQuerySaved > 0;
  const cheaper = impact.perQuerySaved != null && impact.perQuerySaved < 0;
  return (
    <div className="relative mb-2 overflow-hidden rounded-2xl bg-gradient-to-br from-plum/[0.14] to-white/[0.02] p-4 ring-1 ring-plum/25">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-[16px]">✨</span>
        <span className="font-display text-[14px] font-bold text-[#CBA6E2]">Optimization impact</span>
        <span className="text-[12px] text-white/55">· optimized prompt vs the prompt as typed</span>
      </div>
      <div className="grid grid-cols-3 gap-2.5 max-[720px]:grid-cols-1">
        <ImpactStat label="Winner (as typed)" value={impact.baseModel || '-'} sub={impact.baseCost != null ? `${usd(impact.baseCost)}/query` : ''} />
        <ImpactStat label="Winner (optimized)" value={impact.optModel} sub={`${usd(impact.optCost)}/query`} accent="#CBA6E2" />
        <ImpactStat
          label={saved ? 'Saved / query' : cheaper ? 'Added / query' : 'Cost / query'}
          value={impact.perQuerySaved != null ? usd(Math.abs(impact.perQuerySaved)) : usd(impact.optCost)}
          sub={impact.pctSaved != null ? `${impact.pctSaved >= 0 ? '−' : '+'}${Math.round(Math.abs(impact.pctSaved))}% vs as-typed` : ''}
          accent={saved ? '#93D3AB' : cheaper ? '#FF9E8C' : undefined}
        />
      </div>
      <p className="mt-3 text-[13.5px] font-semibold leading-[1.55] text-white">
        {impact.modelChanged && saved ? (
          <>The sharper prompt let <b className="text-[#CBA6E2]">{impact.optModel}</b> clear the quality bar instead of <b className="text-white">{impact.baseModel}</b> - saving about <b className="text-[#93D3AB]">{big((impact.savedYear ?? 0))}</b>/yr at this traffic.</>
        ) : saved ? (
          <>Optimizing kept the same winner but produced a tighter, cheaper answer - saving <b className="text-[#93D3AB]">{big((impact.savedYear ?? 0))}</b>/yr at this traffic.</>
        ) : (
          <>Optimizing sharpened the prompt here. It pays off when a sharper prompt lets a cheaper model clear the bar - try a harder prompt to see the routing win.</>
        )}
      </p>
    </div>
  );
}

function ImpactStat({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="rounded-xl bg-black/25 px-3 py-2.5 ring-1 ring-white/10">
      <div className={LBL}>{label}</div>
      <div className="num mt-1 text-[15px] font-semibold leading-none tracking-[-.02em]" style={{ color: accent ?? '#fff' }}>{value}</div>
      {sub && <div className="num mt-1 text-[10.5px] text-white/45">{sub}</div>}
    </div>
  );
}

// A compact expand/collapse toggle (response / context / tokens) - keeps all
// three secondary panels quiet so the KPIs stay the focus.
function MiniToggle({ open, onClick, disabled, label, title }: { open: boolean; onClick: () => void; disabled?: boolean; label: string; title?: string }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`flex items-center justify-center gap-1 rounded-lg py-2 text-[11.5px] font-medium ring-1 transition disabled:opacity-40 ${open ? 'bg-white/12 text-white ring-white/20' : 'bg-white/[0.06] text-white/75 ring-white/10 hover:bg-white/10 hover:text-white'}`}
    >
      {label}
      <span className="text-[8px]">{open ? '▲' : '▼'}</span>
    </button>
  );
}

// Counterfactual hover after a plain Run: hover reveals what optimizing could save.
interface RunHintData { winner: string; cheaper: string; winnerIsCheapest: boolean; potentialYr: number }
function RunHint({ hint }: { hint: RunHintData }) {
  return (
    <div className="group relative mb-2 inline-flex w-full items-center gap-2 rounded-xl bg-white/[0.05] px-4 py-2.5 ring-1 ring-white/10">
      <span className="text-[14px]">💡</span>
      <span className="text-[13.5px] font-semibold text-white">
        Ran <b className="text-white">as typed</b> - best value was <b className="text-white">{hint.winner}</b>.
        {hint.winnerIsCheapest ? ' Try ' : ' Could you save more? '}
        <b className="text-[#CBA6E2]">Optimize + Run</b> to compare.
      </span>
      <span className="ml-auto grid h-5 w-5 shrink-0 cursor-help place-items-center rounded-full text-[11px] text-white/50 ring-1 ring-white/15">ⓘ</span>
      <div className="invisible absolute right-0 top-full z-50 mt-2 w-[320px] rounded-xl bg-card p-3.5 text-left text-[12px] leading-[1.55] text-ink-2 opacity-0 shadow-lift-hi transition group-hover:visible group-hover:opacity-100">
        <div className="mb-1.5 font-display text-[12.5px] font-semibold text-ink">What Optimize + Run could do</div>
        {hint.winnerIsCheapest ? (
          <p>Your best-value pick <b className="text-ink">{hint.winner}</b> is already the cheapest lane, so optimizing mostly sharpens the answer (and can trim output tokens). Run <b className="text-ink">Optimize + Run</b> to measure the exact token and cost delta.</p>
        ) : (
          <p>A sharper prompt often lets the cheaper lane <b className="text-ink">{hint.cheaper}</b> clear the quality bar. If it does here, you'd save about <b className="text-[#1F9d6b]">{formatHeadline(hint.potentialYr)}/yr</b> at this traffic vs today's pick. Run <b className="text-ink">Optimize + Run</b> to see the real result.</p>
        )}
        <p className="mt-1.5 text-[11px] text-ink-3">Optimize + Run executes both prompts, so the savings shown are measured, not estimated.</p>
      </div>
    </div>
  );
}

function MiniTab({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button onClick={onClick} className={`flex-1 rounded-md px-2 py-1 text-[11px] font-semibold transition ${active ? 'bg-white/15 text-white' : 'text-white/50 hover:text-white/80'}`}>{label}</button>
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

// Bold, colour-forward tier badge - pops on the dark card.
function TierBadge({ tier }: { tier: Tier }) {
  const hex = TIER_META[tier].hex;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-[.07em]" style={{ background: `${hex}26`, color: hex }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: hex }} />
      {TIER_SHORT[tier]}
    </span>
  );
}

// Cheapest / fastest tag - bold, high-contrast chip with a coloured ring.
function TagPill({ color, label, glyph }: { color: string; label: string; glyph: string }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-[11px] font-extrabold uppercase tracking-[.08em]"
      style={{ background: `${color}2e`, color, boxShadow: `inset 0 0 0 1.5px ${color}80` }}
    >
      <span className="grid h-4 w-4 place-items-center rounded-full text-[9px] font-black" style={{ background: color, color: '#141414' }}>{glyph}</span>
      {label}
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

function VizStat({ label, value, lava = false, color, badge }: { label: string; value: string; lava?: boolean; color?: string; badge?: string }) {
  return (
    <div className="rounded-xl bg-black/25 px-3 py-2.5 ring-1 ring-white/10">
      <div className="font-body text-[9px] font-semibold uppercase tracking-[.1em] text-white/45">{label}</div>
      <div className={`num mt-1 text-[15px] font-medium leading-none tracking-[-.03em] ${!color && lava ? 'text-lava' : !color ? 'text-white' : ''}`} style={color ? { color } : undefined}>{value}</div>
      {badge && <div className="mt-1 inline-block rounded-pill bg-moss/20 px-1.5 py-0.5 text-[9.5px] font-extrabold uppercase tracking-[.04em] text-moss">{badge}</div>}
    </div>
  );
}

interface Outcome {
  model: string;
  perQuery: string;
  savedYear: string;
}

interface Page {
  eyebrow: string;
  big: string;
  sub: string;
}

// Intro + advantages, plus this run's outcome after a run. A horizontal carousel
// (arrows / dots / swipe) with an entrance reveal - the black-motion-box feel.
const INTRO_ADV: Page[] = [
  {
    eyebrow: 'Compare all models',
    big: 'Your prompt, three models, one bar to clear.',
    sub: 'Pick a model for each lane - frontier or open weights - then run them side by side. The cheapest answer that stays within a judge point of the best one wins.',
  },
  {
    eyebrow: 'Why it works',
    big: 'Most queries never needed a frontier model.',
    sub: '≈ 90% clear the quality bar on a smaller, cheaper one - route them there and pocket the difference.',
  },
  {
    eyebrow: 'Why it works',
    big: 'Route by complexity - not by habit.',
    sub: 'The prompt decides the model, one request at a time - automatically.',
  },
  {
    eyebrow: 'Why it works',
    big: 'Same governance. A fraction of the cost.',
    sub: 'Unity Gateway + Model Serving - already on Databricks.',
  },
];

function StoryHero({ outcome }: { outcome: Outcome | null }) {
  const [page, setPage] = useState(0);
  const [paused, setPaused] = useState(false);
  const dragX = useRef<number | null>(null);

  // The moving carousel only ever shows the intro / advantage pages. The run's
  // outcome is NOT injected here - it's rendered as a static line below (see the
  // outcome banner), so the result stays put with the same value text.
  const pages: Page[] = INTRO_ADV;
  const n = pages.length;
  const cur = Math.min(page, n - 1);
  const go = (d: number) => setPage((i) => Math.max(0, Math.min(n - 1, i + d)));

  // Auto-advance through the pages so it walks itself (pauses on hover).
  useEffect(() => {
    if (paused || n <= 1) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const id = setInterval(() => setPage((p) => (p + 1) % n), 3200);
    return () => clearInterval(id);
  }, [paused, n]);

  const onPointerDown = (e: React.PointerEvent) => {
    dragX.current = e.clientX;
  };
  const onPointerUp = (e: React.PointerEvent) => {
    if (dragX.current == null) return;
    const dx = e.clientX - dragX.current;
    dragX.current = null;
    if (Math.abs(dx) > 45) go(dx < 0 ? 1 : -1);
  };

  return (
    <div className="relative overflow-hidden py-11 max-[720px]:py-7" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <button
        onClick={() => go(-1)}
        disabled={cur === 0}
        aria-label="Previous"
        className="absolute left-3 top-1/2 z-10 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-full bg-white/10 text-[18px] text-white/80 transition hover:bg-white/20 disabled:pointer-events-none disabled:opacity-25 max-[560px]:hidden"
      >
        ‹
      </button>
      <button
        onClick={() => go(1)}
        disabled={cur === n - 1}
        aria-label="Next"
        className="absolute right-3 top-1/2 z-10 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-full bg-white/10 text-[18px] text-white/80 transition hover:bg-white/20 disabled:pointer-events-none disabled:opacity-25 max-[560px]:hidden"
      >
        ›
      </button>

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
          <button
            key={i}
            onClick={() => setPage(i)}
            aria-label={`Go to page ${i + 1}`}
            className={`h-1.5 rounded-full transition-all duration-300 ${i === cur ? 'w-6 bg-lava' : 'w-1.5 bg-white/25 hover:bg-white/50'}`}
          />
        ))}
      </div>

      {/* Run outcome - a STATIC line (not part of the rotating carousel), so the
          result stays put with the same value text. */}
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

// Guidance popover: what each run option does.
function OptionsInfo({ onClose }: { onClose: () => void }) {
  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="absolute bottom-full left-1/2 z-50 mb-2 w-[360px] -translate-x-1/2 rounded-xl bg-card p-4 text-left text-[12px] leading-[1.55] text-ink-2 shadow-lift-hi">
        <div className="mb-2 flex items-center justify-between">
          <span className="font-display text-[12.5px] font-semibold text-ink">Two ways to run</span>
          <button onClick={onClose} aria-label="Close" className="text-[15px] leading-none text-ink-3 hover:text-ink">×</button>
        </div>
        <ul className="flex flex-col gap-2">
          <li>
            <span className="font-semibold text-ink">Run</span> - sends your prompt to all three lanes <b>exactly as typed</b>, and shows each lane's tokenomics (input / output / total tokens) and cost. The LLM judge picks the winner.
          </li>
          <li>
            <span className="font-semibold text-ink">✨ Optimize + Run</span> - rewrites your prompt into a sharper version, then runs <b>both</b> the original and the optimized prompt through every lane. You see the <b>before/after</b>: tokens added or saved, the cost delta, and both answers - so the benefit of optimizing (a cheaper model clearing the bar) is provable, not asserted.
          </li>
        </ul>
        <p className="mt-2 text-[11px] text-ink-3">Live mode uses a real model to rewrite; demo mode uses a deterministic rewrite.</p>
      </div>
    </>
  );
}

// Guidance popover: how to choose which LLM judges the answers.
function JudgeInfo({ onClose }: { onClose: () => void }) {
  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="absolute bottom-full left-1/2 z-50 mb-2 w-[320px] -translate-x-1/2 rounded-xl bg-card p-4 text-left text-[12px] leading-[1.55] text-ink-2 shadow-lift-hi">
        <div className="mb-2 flex items-center justify-between">
          <span className="font-display text-[12.5px] font-semibold text-ink">Choosing an LLM judge</span>
          <button onClick={onClose} aria-label="Close" className="text-[15px] leading-none text-ink-3 hover:text-ink">×</button>
        </div>
        <ul className="flex list-disc flex-col gap-1.5 pl-4">
          <li>Pick a <b>strong, capable</b> model - grading well is harder than answering, so frontier models make the most reliable judges.</li>
          <li>Prefer a judge that <b>isn't one of the models being compared</b>, to avoid a model favouring its own answer (self‑preference bias).</li>
          <li>Keep the <b>same judge across all three lanes</b> so the scores are comparable.</li>
          <li>The judge scores <b>quality</b> (correctness, completeness, clarity) on 1–10. <b>Cost is then part of the verdict</b>: the cheapest answer that stays within a judge point of the best is chosen as <b>best value</b> - so price, not just the quality score, decides the winner.</li>
        </ul>
        <p className="mt-2 text-[11px] text-ink-3">Runs as a real LLM‑as‑judge call in live mode; the run is logged to MLflow.</p>
      </div>
    </>
  );
}
