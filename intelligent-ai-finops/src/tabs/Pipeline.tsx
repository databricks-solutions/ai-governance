import { useCallback, useEffect, useMemo, useState } from 'react';
import { DndContext, PointerSensor, useSensor, useSensors, useDraggable, useDroppable, type DragEndEvent } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { StageConfigPanel, ConfigCard } from '../components/StageConfigPanel';
import { QuestionLibrary } from '../components/QuestionLibrary';
import { RoutingSteps } from '../components/RoutingViz';
import { useSession } from '../store/session';
import { useConfig } from '../api/useConfig';
import { gatewayChat, getCacheStats, getAppConfig, saveAppConfig,
  type FinopsReceipt, type CacheStats, type AppAdminConfig } from '../api/client';
import type { Tier, Band, ModelDef } from '../api/types';
import { TIER_LABEL, TIER_SHORT, TIER_ORDER, TIER_META } from '../api/types';
import { formatMoney, formatScore, formatTokens } from '../lib/format';

// Tab 2 - the Unity Gateway box. Drag a predefined question (or type your
// own) into the gateway; pick the 2-3 candidate models and tick the governance
// features; route it and see which model answered and what it cost ($$$).

const usd = (n: number) => formatMoney(n);

// Prompt-complexity buckets (from the gateway's 0-100 score), shared visual
// language with the Compare tab.
type Complexity = 'small' | 'medium' | 'complex';
const CX_META: Record<Complexity, { label: string; hex: string; blurb: string }> = {
  small: { label: 'Small', hex: '#93D3AB', blurb: 'Trivial lookups and short tasks - routes to a Small model.' },
  medium: { label: 'Medium', hex: '#E3B876', blurb: 'Multi-step reasoning and analysis - routes to a Medium model.' },
  complex: { label: 'Complex', hex: '#B487D0', blurb: 'Open-ended architecture and strategy - routes to a Complex, most-capable model.' },
};
const complexityOf = (cx: number): Complexity => (cx < 35 ? 'small' : cx < 75 ? 'medium' : 'complex');

type Persona = 'user' | 'admin';

// Representative per-query cost - used to pick the cheapest model in each category.
const _perQ = (m: ModelDef) => 800 * m.price_in_per_1m + 400 * m.price_out_per_1m;
// Cheapest model per size category, ordered Small -> Medium -> Complex. This is the
// spread the router actually chooses from (it picks the cheapest that clears the bar),
// and it drives the fallback chain + the live per-endpoint AI Gateway config panel.
function cheapestPerCategory(models: ModelDef[]): ModelDef[] {
  return (['small-oss', 'large-oss', 'frontier'] as Tier[])
    .map((t) => [...models.filter((m) => m.tier === t)].sort((a, b) => _perQ(a) - _perQ(b))[0])
    .filter((m): m is ModelDef => !!m);
}

interface Question { id: string; t: string; cx: number }
interface Feature { id: string; label: string; feature: string }
interface GwCfg { ok: boolean; usageTracking?: boolean; rateLimits?: number; guardrails?: boolean; inferenceTable?: boolean; fallback?: boolean; error?: string }
interface Chosen { id: string; short: string; tier: Tier }
interface BudgetEffect {
  applied: boolean; consumedPct: number; capUsd: number | null;
  frontierBarPct: number | null; downgraded: boolean; note: string; blocked?: boolean;
}
interface FallbackEffect { enabled: boolean; armed: string[]; fired: boolean; from: string | null }
interface Result {
  chosen: Chosen; routedTo?: Chosen; fallback?: FallbackEffect | null;
  costUsd: number; latencyMs: number; judgeScore: number | null; complexity: number;
  bandLabel?: string | null; matchedRule?: string | null;
  inputTokens?: number; outputTokens?: number;
  requiredTier: Tier; baseRequiredTier?: Tier; reason: string; baseline: { short: string; costUsd: number };
  savingsUsd: number; savingsPct: number; appliedFeatures: string[]; budget?: BudgetEffect | null;
  routingOverheadUsd?: number; routerModel?: string; allInCostUsd?: number; cheaperThanBaselineX?: number | null;
  compression?: {
    prompt: { tokensBefore: number; tokensAfter: number; savedTokens: number; savedPct: number };
    tools: { toolsBefore: number; toolsAfter: number; tokensBefore: number; tokensAfter: number; savedPct: number; selected: string[]; dropped?: string[]; catalog?: { name: string; kept: boolean; desc: string }[]; source?: string };
  };
  blocked?: boolean;
  answer?: string; judgeReason?: string;
  trace: { kind: string; text: string }[];
}

// A budget threshold's action: cap the ceiling at a tier, or block new requests.
type BudgetAction = Tier | 'block';

// A free-text routing rule: comma-separated keywords → a tier.
interface CriteriaRule { id: string; keywords: string; tier: Tier }

// ABAC access control: a requester group and the model tiers it may use. Mirrors a
// Unity Catalog EXECUTE/ABAC policy (e.g. "frontier models → data scientists only").
type AccessGroup = 'Data scientist' | 'Analyst' | 'Contractor';
const ACCESS_GROUPS: AccessGroup[] = ['Data scientist', 'Analyst', 'Contractor'];
const ACCESS_DEFAULT: Record<AccessGroup, Tier[]> = {
  'Data scientist': ['frontier', 'large-oss', 'small-oss'],
  Analyst: ['large-oss', 'small-oss'],
  Contractor: ['small-oss'],
};

const TIER_DOT: Record<Tier, string> = { frontier: 'bg-plum', 'large-oss': 'bg-amber', 'small-oss': 'bg-moss' };
// Uppercase label on the dark stage (the light .eyebrow util is too dark here).
const EB = 'font-body text-[11.5px] font-bold uppercase tracking-[.12em] text-white/60';
// Bold, coloured section header (box titles), matching the Compare tab.
const SECTION = 'font-display text-[13px] font-bold uppercase tracking-[.15em] text-[#7FB6F2]';

// A 3D pressable toggle for a live AI Gateway setting on one endpoint. On = raised
// green; off = raised grey; both physically depress on click. Interactive only when
// an onClick is supplied (Admin view); otherwise it's a read-only 3D status pill.
function GwToggle({ on, label, onClick, busy = false, disabled = false, title }: { on: boolean; label: string; onClick?: () => void; busy?: boolean; disabled?: boolean; title?: string }) {
  const interactive = !!onClick && !disabled && !busy;
  return (
    <button
      type="button"
      onClick={interactive ? onClick : undefined}
      disabled={!interactive}
      title={title}
      aria-pressed={on}
      className={[
        'num inline-flex select-none items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-semibold transition-all duration-100',
        on ? 'bg-moss/25 text-[#B7E8C8] ring-1 ring-moss/50' : 'bg-white/[0.07] text-white/45 ring-1 ring-white/15',
        interactive
          ? (on
              ? 'shadow-[0_2.5px_0_rgba(20,90,55,0.95),0_5px_10px_rgba(0,0,0,0.35)] hover:brightness-110 active:translate-y-[2px] active:shadow-none'
              : 'shadow-[0_2.5px_0_rgba(0,0,0,0.55),0_5px_10px_rgba(0,0,0,0.3)] hover:bg-white/[0.12] hover:text-white/70 active:translate-y-[2px] active:shadow-none')
          : 'cursor-default opacity-90',
        busy ? 'opacity-50' : '',
      ].join(' ')}
    >
      <span aria-hidden>{busy ? '…' : on ? '✓' : '—'}</span> {label}
    </button>
  );
}

export function Pipeline() {
  const cfg = useConfig();
  const { logRun, setLastRouting } = useSession();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [features, setFeatures] = useState<Feature[]>([]);
  const [custom, setCustom] = useState('');
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  const [inspect, setInspect] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [persona, setPersona] = useState<Persona>('admin'); // admin sees governance + budget + policy editor; user sees a simple ask
  const [cxInfo, setCxInfo] = useState(false); // complexity-legend popover

  // ---- Real finops-auto proxy state (POST /v1/chat/completions) -----------
  // Auto-classifier is the master switch: ON = finops-auto routes across ALL deployed
  // models and picks the cheapest that clears the bar (model picks grayed, no per-endpoint
  // config panel); OFF = the admin picks the 3 category models + writes keyword criteria.
  const [autoClassifier, setAutoClassifier] = useState(true);
  const [selected, setSelected] = useState<string[]>([]); // 3 category picks (manual mode)
  // Free-text keyword criteria per category (manual mode): a prompt matching a keyword
  // routes to that category; anything unmatched falls back to the classifier's score.
  const [criteria, setCriteria] = useState<Record<Tier, string>>({
    'small-oss': 'code, sql, python, how do i, reset, format, classify, extract',
    'large-oss': 'summarize, draft, translate, compare, analyze, explain',
    frontier: 'strategy, architecture, valuation, acquisition, migrate, design, root cause',
  });
  const [cacheOn, setCacheOn] = useState(true); // semantic cache on the routed call
  const [optOn, setOptOn] = useState(false); // output-shaping (optimize output)
  const [optWords, setOptWords] = useState(150);
  const [receipt, setReceipt] = useState<FinopsReceipt | null>(null); // raw receipt → chip row + cache/optimize panels
  const [blockedErr, setBlockedErr] = useState<{ message: string; finops?: FinopsReceipt } | null>(null); // proxy throws on guardrail/budget/rate block
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);
  const [cfgReady, setCfgReady] = useState(false); // persisted admin config loaded (gates auto-save)
  const refreshCacheStats = useCallback(() => { getCacheStats().then(setCacheStats).catch(() => {}); }, []);
  useEffect(() => { refreshCacheStats(); }, [refreshCacheStats]);

  // The customer's OWN routing policy: user-defined complexity bands. Seeded once
  // from the default config thresholds, then fully editable.
  const [bands, setBands] = useState<Band[]>([]);
  // Routing-policy mode: 'bands' = complexity score → band; 'criteria' = free-text
  // rules the customer writes ("code -> small", "finance -> complex").
  const [policyMode, setPolicyMode] = useState<'bands' | 'criteria'>('bands');
  // Free-text routing rules (keywords → tier), edited as rows like the complexity
  // bands and auto-populated with defaults. A prompt matching a keyword routes to
  // that tier; anything unmatched falls back to the bands.
  const [policyRules, setPolicyRules] = useState<CriteriaRule[]>([
    { id: 'cr-1', keywords: 'code, sql, python, how do i, reset', tier: 'small-oss' },
    { id: 'cr-2', keywords: 'summarize, draft, translate, compare', tier: 'large-oss' },
    { id: 'cr-3', keywords: 'strategy, architecture, valuation, acquisition, migrate', tier: 'frontier' },
  ]);
  // Routing LLM: the small model that classifies each question's complexity and
  // routes it (admin-only, picked in the composer). Defaults to the cheapest
  // small-OSS model so the routing overhead stays cheap.
  const [routerModel, setRouterModel] = useState('');

  // Setting a fresh question (pill / example library / clear) also clears the result.
  const setPrompt = (q: string) => { setCustom(q); setResult(null); setReceipt(null); setBlockedErr(null); };
  const useLibraryQuestion = (q: string) => setPrompt(q);

  // Whether the budget applies is driven by the "Budgets" governance TICK (the
  // enabled set) - the single source of truth, so unticking it truly turns budget
  // routing off. (No separate flag - the tick is the switch.)
  const [consumedPct, setConsumedPct] = useState(61);
  const [capUsd, setCapUsd] = useState<number | null>(null);
  useEffect(() => { if (cfg && capUsd == null) setCapUsd(cfg.policy.budget.monthly_cap_usd); }, [cfg, capUsd]);
  // Budget thresholds + the ACTION at each - cap at a tier, or block. Seeded once
  // from config, then user-editable.
  const [downgradeAt, setDowngradeAt] = useState(55);
  const [openOnlyAt, setOpenOnlyAt] = useState(80);
  const [downgradeAction, setDowngradeAction] = useState<BudgetAction>('large-oss');
  const [openOnlyAction, setOpenOnlyAction] = useState<BudgetAction>('small-oss');
  const [polSeeded, setPolSeeded] = useState(false);
  useEffect(() => {
    if (cfg && !polSeeded) { setDowngradeAt(cfg.policy.budget.downgrade_at_pct); setOpenOnlyAt(cfg.policy.budget.open_only_at_pct); setPolSeeded(true); }
  }, [cfg, polSeeded]);

  // V2: the LIVE per-endpoint AI Gateway config, read from each routable endpoint via
  // the SDK. WRITES run as the SIGNED-IN USER (Databricks Apps on-behalf-of-user), so
  // a human admin can alter these platform-managed system endpoints even though the
  // app's own SP cannot. Errors (e.g. you lack Manage) are surfaced inline.
  const [gwConfig, setGwConfig] = useState<Record<string, GwCfg>>({});
  const [rlInput, setRlInput] = useState<Record<string, string>>({});
  const [gwErr, setGwErr] = useState<Record<string, string>>({});
  const [gwBusy, setGwBusy] = useState<string | null>(null);
  // Load the live per-endpoint config for the admin's 3 category picks (manual mode).
  // In auto-classifier mode there's no hand-picked set, so the panel is hidden.
  useEffect(() => {
    if (autoClassifier || selected.length === 0) return;
    fetch(`/api/governance/config?models=${encodeURIComponent(selected.join(','))}`)
      .then((r) => r.json()).then(setGwConfig).catch(() => {});
  }, [selected, autoClassifier]);
  const applyGateway = async (model: string, patch: object) => {
    setGwBusy(model);
    setGwErr((e) => { const n = { ...e }; delete n[model]; return n; });
    const r = await fetch('/api/governance/update', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model, patch }),
    }).then((x) => x.json()).catch(() => null);
    setGwBusy(null);
    if (r?.ok) setGwConfig((g) => ({ ...g, [model]: r.config }));
    else {
      const raw = r?.error || 'write failed';
      // OBO: the forwarded token only carries the model-serving scope after the admin
      // approves the app once in-browser - point them at that instead of a raw scope error.
      const msg = /scope|consent/i.test(raw)
        ? 'Approve the app’s model-serving permission once (reload the app in your browser and accept), then this write applies as you.'
        : /Manage/i.test(raw)
          ? 'You need CAN MANAGE on this endpoint (writes run as you, the signed-in admin).'
          : raw;
      setGwErr((e) => ({ ...e, [model]: msg }));
    }
  };

  // App-layer governance (Idea 2): the gateway app enforces these itself on every
  // request. Guardrails scan the prompt (PII + keyword) and block or mask; rate limits
  // cap requests/user/minute. Both are real and work for any endpoint.
  const [guardCfg, setGuardCfg] = useState<{ pii: boolean; mode: 'block' | 'mask'; keywords: string }>({ pii: true, mode: 'block', keywords: 'confidential, internal-only' });
  const [rateCfg, setRateCfg] = useState<{ perMin: number }>({ perMin: 20 });
  // ABAC access control: the requester group being simulated + each group's allowed tiers.
  const [accessGroup, setAccessGroup] = useState<AccessGroup>('Contractor');
  const [accessTiers, setAccessTiers] = useState<Record<AccessGroup, Tier[]>>(ACCESS_DEFAULT);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  useEffect(() => {
    fetch('/api/pipeline/meta')
      .then((r) => r.json())
      .then((d) => {
        const feats: Feature[] = d.features ?? [];
        setQuestions(d.questions ?? []);
        setFeatures(feats);
        setEnabled(new Set(feats.map((f) => f.id))); // all on by default
      })
      .catch(() => {});
  }, []);

  // Seed the routing policy from the default config thresholds the first time
  // config loads. After that it's the user's to edit - the app never overwrites it.
  useEffect(() => {
    if (!cfg || bands.length) return;
    const { small_max, large_max } = cfg.policy.thresholds;
    setBands([
      { id: 'band-simple', label: 'Simple', min: 0, max: small_max - 1, tier: 'small-oss' },
      { id: 'band-standard', label: 'Standard', min: small_max, max: large_max - 1, tier: 'large-oss' },
      { id: 'band-complex', label: 'Complex', min: large_max, max: 100, tier: 'frontier' },
    ]);
  }, [cfg, bands.length]);

  const models = cfg?.models ?? [];
  const byId = useMemo(() => new Map(models.map((m) => [m.id, m])), [models]);
  // No hand-picked model set: the router considers EVERY deployed model and picks the
  // cheapest one that clears the bar. `repModels` = the cheapest in each category (what
  // it actually chooses from), used for the fallback chain + per-endpoint config panel.
  const poolIds = useMemo(() => models.map((m) => m.id), [models]);
  const repModels = useMemo(() => cheapestPerCategory(models), [models]);
  const repIds = useMemo(() => repModels.map((m) => m.id), [repModels]);
  // Curated questions carry a hand-tuned complexity (drives the actual route when
  // that exact question is the prompt). The backend classifier scores anything else.
  const knownCx = useMemo(() => new Map(questions.map((q) => [q.t, q.cx])), [questions]);

  // Default the Routing LLM to gpt-oss-20b (else the cheapest small-OSS): the same
  // cheap model that should route the traffic, so the routing overhead stays low.
  useEffect(() => {
    if (!cfg || routerModel) return;
    const cheapestSmall = [...cfg.models.filter((m) => m.tier === 'small-oss')].sort((a, b) => a.price_out_per_1m - b.price_out_per_1m)[0];
    const pick = cfg.models.find((m) => m.id === 'databricks-gpt-oss-20b') ?? cheapestSmall ?? cfg.models[0];
    if (pick) setRouterModel(pick.id);
  }, [cfg, routerModel]);

  // Fallback chain mirrors the models actually routed across: the admin's 3 picks in
  // manual mode, or the cheapest-per-category set in auto mode. Ordered Small -> Medium
  // -> Complex (ascending capability). No hand-ordering.
  const fbChain = useMemo(() => {
    const order: Tier[] = ['small-oss', 'large-oss', 'frontier'];
    const source = autoClassifier ? repIds : selected;
    return [...source].sort((a, b) => order.indexOf(byId.get(a)?.tier as Tier) - order.indexOf(byId.get(b)?.tier as Tier));
  }, [autoClassifier, repIds, selected, byId]);

  // Seed the 3 category picks (manual mode) once config loads: opus-5 / glm-5.3 / cheapest
  // Small - a visible spread. The persisted admin config (below) overrides this if present.
  useEffect(() => {
    if (!cfg || selected.length) return;
    const pin = (id: string, t: Tier) => cfg.models.find((m) => m.id === id)?.id
      ?? [...cfg.models.filter((m) => m.tier === t)].sort((a, b) => _perQ(a) - _perQ(b))[0]?.id;
    const picks = [pin('databricks-claude-opus-5', 'frontier'), pin('databricks-glm-5-3', 'large-oss'), pin('', 'small-oss')].filter(Boolean) as string[];
    if (picks.length) setSelected(picks);
  }, [cfg, selected.length]);

  const setTierModel = (t: Tier, id: string) =>
    setSelected((prev) => {
      const others = prev.filter((x) => byId.get(x)?.tier !== t);
      return id ? [...others, id] : others;
    });

  // ---- Persist the admin config so the USER persona inherits it (point 6) ----
  // Load once on mount (both personas), then the admin auto-saves on change.
  useEffect(() => {
    getAppConfig().then((c: AppAdminConfig) => {
      if (c && Object.keys(c).length) {
        if (typeof c.autoClassifier === 'boolean') setAutoClassifier(c.autoClassifier);
        if (Array.isArray(c.models) && c.models.length) setSelected(c.models);
        if (c.criteria) setCriteria((prev) => ({ ...prev, ...c.criteria } as Record<Tier, string>));
        if (Array.isArray(c.enabled)) setEnabled(new Set(c.enabled));
        if (c.options) {
          if (typeof c.options.cache === 'boolean') setCacheOn(c.options.cache);
          if (typeof c.options.optimize === 'boolean') setOptOn(c.options.optimize);
          if (typeof c.options.optimizeWords === 'number') setOptWords(c.options.optimizeWords);
        }
        if (c.guardrails) setGuardCfg(c.guardrails);
        if (c.rateLimit) setRateCfg(c.rateLimit);
        if (c.access) { setAccessGroup(c.access.group as AccessGroup); if (c.access.tiers) setAccessTiers(c.access.tiers as Record<AccessGroup, Tier[]>); }
      }
    }).finally(() => setCfgReady(true));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Admin auto-save (debounced) so edits flow to the user persona + survive restarts.
  const adminConfig: AppAdminConfig = useMemo(() => ({
    autoClassifier, models: selected, criteria, enabled: [...enabled],
    options: { cache: cacheOn, optimize: optOn, optimizeWords: optWords },
    guardrails: guardCfg, rateLimit: rateCfg,
    access: { group: accessGroup, tiers: accessTiers },
  }), [autoClassifier, selected, criteria, enabled, cacheOn, optOn, optWords, guardCfg, rateCfg, accessGroup, accessTiers]);
  useEffect(() => {
    if (!cfgReady || persona !== 'admin') return;
    const id = setTimeout(() => { saveAppConfig(adminConfig).catch(() => {}); }, 600);
    return () => clearTimeout(id);
  }, [adminConfig, cfgReady, persona]);

  // Show just 3 impactful example questions - one at each end of the complexity
  // range and one in the middle - so the routing spread (small → large → frontier)
  // is obvious without a wall of chips.
  const shownQuestions = useMemo(() => {
    const sorted = [...questions].sort((a, b) => a.cx - b.cx);
    if (sorted.length <= 3) return sorted;
    const picks = [0, 0.5, 1].map((f) => sorted[Math.round(f * (sorted.length - 1))]);
    return Array.from(new Set(picks));
  }, [questions]);

  const toggleFeature = (id: string) =>
    setEnabled((e) => { const n = new Set(e); n.has(id) ? n.delete(id) : n.add(id); return n; });
  // Auto-classifier handles governance automatically: close any open Configure panel.
  useEffect(() => { if (autoClassifier) setInspect(null); }, [autoClassifier]);

  const onDragEnd = (e: DragEndEvent) => {
    if (e.over?.id !== 'gateway-question' || !String(e.active.id).startsWith('q:')) return;
    const q = questions.find((x) => `q:${x.id}` === String(e.active.id));
    if (q) setPrompt(q.t);
  };

  const route = async () => {
    const text = custom.trim();
    if (!text || poolIds.length < 1 || busy) return;
    setBusy(true);
    setResult(null);
    setReceipt(null);
    setBlockedErr(null);
    try {
      // Governance TICKS are the switches: a feature only affects the route when enabled.
      // In Auto-classifier mode every governance feature is on automatically (the chips
      // render all-green + locked); in Manual mode the admin's ticks decide. This tab
      // calls the REAL finops-auto proxy (POST /v1/chat/completions).
      const featOn = (id: string) => autoClassifier || enabled.has(id);
      const budgetActive = enabled.has('budget');
      // Candidate pool: Auto-classifier ON = every deployed model (finops-auto picks the
      // cheapest that clears the bar); OFF = the admin's 3 category picks. ABAC is a Manual
      // simulation control, so it only narrows the pool when auto-classifier is off.
      const basePool = autoClassifier ? poolIds : selected;
      const allowedTiers = !autoClassifier && enabled.has('access-control') ? accessTiers[accessGroup] : null;
      const candidateIds = allowedTiers
        ? basePool.filter((id) => allowedTiers.includes(byId.get(id)?.tier as Tier))
        : basePool;
      if (candidateIds.length === 0) {
        setBlockedErr({ message: allowedTiers
          ? `Access control: ${accessGroup} may not use any of the configured model categories, so the request is blocked before routing.`
          : 'No candidate models are configured, so there is nothing to route to.' });
        setBusy(false);
        return;
      }
      // Complexity: a curated question's hand-tuned score wins; else the classifier scores
      // it live. In Manual mode (auto-classifier OFF) the keyword criteria decide the
      // category (a match overrides the score); anything unmatched falls back to the score.
      const complexity = knownCx.get(text) ?? undefined;

      const finopsOpts: Record<string, unknown> = {
        models: candidateIds,
        routerModel,
        semanticCache: { enabled: cacheOn, threshold: 0.92 },
        optimize: { enabled: optOn, targetWords: optWords },
      };
      if (complexity != null) finopsOpts.complexity = complexity;
      if (!autoClassifier) {
        // Free-text criteria: one keyword rule per category (blank rules are dropped).
        const rules = (['small-oss', 'large-oss', 'frontier'] as Tier[])
          .map((t) => ({ keywords: criteria[t], tier: t }))
          .filter((r) => r.keywords.trim().length > 0);
        if (rules.length) finopsOpts.policy = { mode: 'criteria', rules };
      }
      if (budgetActive) finopsOpts.budget = { enabled: true, capUsd: capUsd ?? undefined, downgradeAtPct: downgradeAt, openOnlyAtPct: openOnlyAt, downgradeAction, openOnlyAction, consumedPct };
      // Fallback: retry down the chosen routing models (Small -> Medium -> Complex).
      if (featOn('fallbacks')) finopsOpts.fallback = { enabled: true, order: fbChain.filter((id) => candidateIds.includes(id)) };
      if (featOn('guardrails')) finopsOpts.guardrails = { enabled: true, pii: guardCfg.pii, mode: guardCfg.mode, keywords: guardCfg.keywords.split(',').map((k) => k.trim()).filter(Boolean) };
      if (featOn('rate-limits')) finopsOpts.rateLimit = { enabled: true, perMin: rateCfg.perMin };

      const { answer, finops: f } = await gatewayChat(text, 'finops-auto', finopsOpts);
      setReceipt(f);
      refreshCacheStats();

      const result: Result = {
        chosen: f.servedBy as Chosen,
        routedTo: f.routedTo as Chosen,
        fallback: f.fallback ? { enabled: f.fallback.enabled, armed: f.fallback.armed, fired: f.fallback.fired, from: f.fallback.from } : null,
        costUsd: f.costUsd,
        latencyMs: f.latencyMs,
        judgeScore: null, // a single routed call is not judged - quality lives in the A/B panels
        complexity: f.complexity,
        bandLabel: f.bandLabel,
        matchedRule: f.matchedRule,
        inputTokens: f.inputTokens,
        outputTokens: f.outputTokens,
        requiredTier: f.requiredTier as Tier,
        reason: routeReason(f),
        baseline: { short: f.baselineModel, costUsd: f.baselineUsd },
        savingsUsd: f.savingsUsd,
        savingsPct: f.savingsPct,
        appliedFeatures: [...enabled],
        budget: f.budget ? { applied: true, consumedPct: f.budget.consumedPct, capUsd: f.budget.capUsd, frontierBarPct: null, downgraded: f.budget.ceiling !== 'frontier', note: f.budget.note } : null,
        answer,
        trace: routeTrace(f),
      };
      setResult(result);
      logRun({
        source: 'gateway',
        modelShort: f.servedBy.short,
        tier: f.servedBy.tier as Tier,
        costUsd: f.costUsd,
        baselineUsd: f.baselineUsd,
        inputTokens: f.inputTokens,
        outputTokens: f.outputTokens,
        latencyMs: f.latencyMs,
        optimized: (f.optimization?.savedOutputTokens ?? 0) > 0 || (f.compression?.savedTokens ?? 0) > 0,
        promptSnippet: text,
      });
      // Feed the Architecture tab: this routed model becomes the "live" request.
      setLastRouting({ model: f.servedBy.short, tier: f.servedBy.tier as Tier, costUsd: f.costUsd, complexity: f.complexity, source: 'gateway' });
    } catch (e) {
      const err = e as Error & { finops?: FinopsReceipt };
      setBlockedErr({ message: err.message || 'Gateway request failed', finops: err.finops });
    } finally {
      setBusy(false);
    }
  };

  const activeQuestionText = custom;
  const inspectFeature = inspect ? features.find((f) => f.id === inspect) : null;

  return (
    <DndContext sensors={sensors} onDragEnd={onDragEnd}>
      <div className="flex flex-col gap-[22px]">
        {/* Box 1 - intro + example questions */}
        <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[26px] text-white shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4">
          <div className="pointer-events-none absolute -right-32 -top-24 h-96 w-96 rounded-full bg-lava opacity-[.10] blur-3xl" />
          <div className="relative flex flex-col gap-[18px]">
            <div>
              <div className="mb-2 flex flex-wrap items-center gap-3">
                <span className="font-body text-[11px] font-semibold uppercase tracking-[.22em] text-lava">Context routing</span>
                {/* Persona toggle - User sees a simple ask; Admin sees governance + budget */}
                <PersonaToggle persona={persona} onChange={setPersona} />
              </div>
              <h2 className="font-display text-[clamp(20px,2.4vw,28px)] font-bold tracking-[-.02em] text-white">Route to Unity Gateway</h2>
              <p className="mt-2 max-w-[80ch] text-[13px] text-white/65">
                {persona === 'admin'
                  ? "Type or drop in a question. Leave the auto-classifier on and finops-auto routes across every deployed model; turn it off to pick the model for each category and write your own keyword criteria. Tick the governance features - rate limits, guardrails, access control, inference tables, fallbacks - each with a Configure panel, and add semantic cache or output shaping as options. The gateway routes to the cheapest model that clears the bar."
                  : 'Ask a question and hit Get response. It routes through the gateway with the settings your admin configured, returning the cheapest answer that still clears the quality bar.'}
              </p>
            </div>

            <div>
              <div className="mb-3 flex items-center gap-2">
                <span className={SECTION}>Example questions</span>
                <span className="relative">
                  <button onClick={() => setCxInfo((v) => !v)} aria-label="What do the complexity categories mean?" className="grid h-5 w-5 place-items-center rounded-full text-[11px] text-white/50 transition hover:bg-white/10 hover:text-white">ⓘ</button>
                  {cxInfo && <ComplexityInfo onClose={() => setCxInfo(false)} />}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-2.5">
                {shownQuestions.map((q) => <QuestionPill key={q.id} q={q} onClick={() => setPrompt(q.t)} />)}
                <button
                  onClick={() => setLibraryOpen(true)}
                  className="inline-flex items-center gap-2 rounded-pill bg-white/15 px-3.5 py-2.5 text-[12.5px] font-bold text-white ring-1 ring-white/20 transition hover:-translate-y-[2px] hover:bg-white/25"
                >
                  Browse examples →
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* Box 2 - the Unity Gateway */}
        <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[26px] text-white shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.06s' }}>
          <div className="pointer-events-none absolute -bottom-24 -left-24 h-80 w-80 rounded-full bg-lava opacity-[.08] blur-3xl" />
          <div className="relative flex flex-col gap-5">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-lava" />
              <span className="font-display text-[16px] font-bold uppercase tracking-[.14em] text-[#8FC1F0]">Unity Gateway</span>
              <span className="num ml-auto text-[12px] font-semibold text-white/55">governed · one endpoint</span>
            </div>
              {/* Question slot - the composer (just the prompt; the classifier model is a
                  sensible default, and complexity Auto/Manual lives in the governance features). */}
              <QuestionSlot
                custom={custom}
                onCustom={(v) => { setCustom(v); setResult(null); setReceipt(null); setBlockedErr(null); }}
                onClear={() => setPrompt('')}
              />

              {/* Admin: the auto-classifier master switch + (manual) model picks, criteria,
                  and per-endpoint config. The user persona sees none of this - just the
                  question + Get response, applying whatever the admin persisted. */}
              {persona === 'admin' && (
              <>
              {/* Auto-classifier master toggle */}
              <div className="rounded-xl bg-white/[0.03] p-3 ring-1 ring-white/10">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <span className={EB}>Auto-classifier <span className="font-normal normal-case text-white/40">· finops-auto</span></span>
                    <p className="mt-1 truncate whitespace-nowrap text-[11.5px] leading-[1.5] text-white/50">
                      {autoClassifier
                        ? 'ON: the router picks the cheapest of all deployed models that clears the bar.'
                        : 'OFF: you pick the model for each category and define the keyword criteria that route to it.'}
                    </p>
                  </div>
                  <button type="button" role="switch" aria-checked={autoClassifier} aria-label="Auto-classifier"
                    onClick={() => setAutoClassifier((v) => !v)}
                    className={`relative h-7 w-12 shrink-0 rounded-full transition ${autoClassifier ? 'bg-moss' : 'bg-white/20'}`}>
                    <span className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow transition-all duration-200 ${autoClassifier ? 'left-6' : 'left-1'}`} />
                  </button>
                </div>
              </div>

              {/* Models to route across - one per category. Grayed out when auto-classifier is on. */}
              <div className={autoClassifier ? 'pointer-events-none opacity-45' : ''}>
                <div className="mb-2.5 flex items-center gap-2">
                  <span className={EB}>Models to route across</span>
                  <span className="num text-[11.5px] text-white/50">{autoClassifier ? 'auto — finops-auto picks the cheapest per category' : 'one per category'}</span>
                </div>
                <div className="grid grid-cols-3 gap-3 max-[640px]:grid-cols-1">
                  {TIER_ORDER.map((t) => {
                    const tierModelsList = models.filter((m) => m.tier === t);
                    if (!tierModelsList.length) return null;
                    const current = selected.find((id) => byId.get(id)?.tier === t) ?? '';
                    return (
                      <div key={t} className="flex flex-col gap-2 rounded-xl bg-black/20 p-3 ring-1 ring-white/10">
                        <span className="flex items-center gap-1.5 text-[12.5px] font-bold text-white/80">
                          <span className={`h-2.5 w-[3px] rounded-[2px] ${TIER_DOT[t]}`} />{TIER_LABEL[t]}
                        </span>
                        <div className="relative">
                          <select value={current} onChange={(e) => setTierModel(t, e.target.value)} disabled={autoClassifier} aria-label={`${TIER_LABEL[t]} model`}
                            className={`num w-full appearance-none rounded-lg bg-black/30 px-3.5 py-2.5 pr-9 text-[13px] font-semibold text-white ring-1 ring-white/10 outline-none transition ${autoClassifier ? 'cursor-not-allowed' : 'cursor-pointer hover:bg-black/40'}`}>
                            <option value="" className="text-ink">none</option>
                            {tierModelsList.map((m) => <option key={m.id} value={m.id} className="text-ink">{m.short}</option>)}
                          </select>
                          <span className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-[11px] text-white/45">▾</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Manual only: free-text keyword criteria per category (V1 "define criteria yourself") */}
              {!autoClassifier && (
                <div className="rounded-xl bg-white/[0.03] p-3 ring-1 ring-white/10">
                  <div className={`${EB} mb-2`}>Routing criteria · keywords → category</div>
                  <div className="flex flex-col gap-2">
                    {TIER_ORDER.map((t) => (
                      <div key={t} className="flex items-center gap-2">
                        <span className="flex w-[86px] shrink-0 items-center gap-1.5 text-[12px] font-semibold" style={{ color: TIER_META[t].hex }}>
                          <span className="h-2 w-2 rounded-full" style={{ background: TIER_META[t].hex }} />{TIER_LABEL[t]}
                        </span>
                        <input value={criteria[t]} onChange={(e) => setCriteria((c) => ({ ...c, [t]: e.target.value }))} aria-label={`${TIER_LABEL[t]} keywords`} placeholder="keywords, comma-separated"
                          className="min-w-0 flex-1 rounded bg-white/10 px-2.5 py-1.5 text-[12px] text-white ring-1 ring-white/10 outline-none placeholder:text-white/30" />
                      </div>
                    ))}
                  </div>
                  <p className="mt-2 text-[11px] leading-[1.5] text-white/45">A prompt containing one of a category's keywords routes to that category; anything unmatched falls back to the classifier's score. In production the small router LLM interprets these directly.</p>
                </div>
              )}

              {/* Manual only: live per-endpoint AI Gateway config for the 3 picks, via the SDK */}
              {!autoClassifier && Object.keys(gwConfig).length > 0 && (
                <div className="rounded-xl bg-white/[0.03] p-3 ring-1 ring-white/10">
                  <div className={`${EB} mb-2`}>Live AI Gateway config <span className="font-normal normal-case text-white/40">· read from each endpoint via the SDK</span></div>
                  <div className="flex flex-col gap-1.5">
                    {selected.map((id) => {
                      const c = gwConfig[id];
                      if (!c) return null;
                      const short = byId.get(id)?.short ?? id;
                      const admin = persona === 'admin';
                      const busyId = gwBusy === id;
                      return (
                        <div key={id} className="flex flex-col gap-0.5">
                          <div className="flex flex-wrap items-center gap-1.5 text-[11.5px]">
                            <span className="num w-[120px] shrink-0 font-semibold text-white/80">{short}</span>
                            {c.ok ? (
                              <>
                                {/* Each option is a 3D pressable button. In Admin view a click writes the
                                    change to the real endpoint AS THE SIGNED-IN USER (OBO) - a human admin can
                                    alter these platform-managed endpoints even though the app SP can't. */}
                                <GwToggle on={!!c.usageTracking} label="usage" busy={busyId} disabled={!admin}
                                  onClick={admin ? () => applyGateway(id, { usage_tracking_config: { enabled: !c.usageTracking } }) : undefined}
                                  title={admin ? 'Toggle usage tracking (feeds system.ai_gateway.usage) - runs as you' : 'Usage-tracking status - switch to Admin to change'} />
                                <GwToggle on={(c.rateLimits ?? 0) > 0} label={`rate limits${c.rateLimits ? ` (${c.rateLimits})` : ''}`} busy={busyId} disabled={!admin}
                                  onClick={admin ? () => applyGateway(id, (c.rateLimits ?? 0) > 0 ? { rate_limits: [] } : { rate_limits: [{ calls: 60, renewal_period: 'minute', key: 'endpoint' }] }) : undefined}
                                  title={admin ? 'Toggle a 60/min endpoint rate limit on/off (runs as you); use the field to set a custom rpm' : 'Rate-limit status - switch to Admin to change'} />
                                <GwToggle on={!!c.guardrails} label="guardrails" busy={busyId} disabled={!admin}
                                  onClick={admin ? () => applyGateway(id, c.guardrails ? { guardrails: null } : { guardrails: { input: { pii: { behavior: 'BLOCK' }, safety: true }, output: { pii: { behavior: 'BLOCK' }, safety: true } } }) : undefined}
                                  title={admin ? 'Toggle PII + safety guardrails on this endpoint (runs as you)' : 'Guardrail status - switch to Admin to change'} />
                                <GwToggle on={!!c.inferenceTable} label="inference table" busy={busyId} disabled={!admin || !c.inferenceTable}
                                  onClick={admin && c.inferenceTable ? () => applyGateway(id, { inference_table_config: { enabled: false } }) : undefined}
                                  title={admin ? (c.inferenceTable ? 'Turn inference-table logging off (runs as you)' : 'Enabling needs a Unity Catalog catalog.schema target - configure it in the workspace') : 'Inference-table status - switch to Admin to change'} />
                                {/* Fallback can't attach to a system pay-per-token endpoint (platform-verified) */}
                                <span className="num inline-flex items-center rounded-lg bg-white/[0.05] px-2 py-1 text-[10px] text-white/35 ring-1 ring-white/10" title="Fallback is not supported on system pay-per-token endpoints - it needs a custom endpoint you own.">⊘ fallback (custom endpoint)</span>
                                {admin && (
                                  <span className="ml-auto flex items-center gap-1">
                                    <input value={rlInput[id] ?? ''} onChange={(e) => setRlInput((s) => ({ ...s, [id]: e.target.value }))} placeholder="rpm" aria-label="custom rate limit per minute" className="num w-[46px] rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-white ring-1 ring-white/10 outline-none" />
                                    <button disabled={busyId} onClick={() => { const n = parseInt(rlInput[id] || '', 10); applyGateway(id, { rate_limits: n > 0 ? [{ calls: n, renewal_period: 'minute', key: 'endpoint' }] : [] }); }} title="Set a custom per-minute rate limit on this endpoint (runs as you)" className="rounded bg-lava/80 px-1.5 py-0.5 text-[10px] font-semibold text-white transition hover:bg-lava disabled:opacity-40">{busyId ? '…' : 'set rpm'}</button>
                                  </span>
                                )}
                              </>
                            ) : (
                              <span className="text-white/40">config unavailable</span>
                            )}
                          </div>
                          {gwErr[id] && <span className="num pl-[128px] text-[10px] leading-[1.4] text-[#FF9E8C]">✕ {gwErr[id]}</span>}
                        </div>
                      );
                    })}
                  </div>
                  <p className="mt-2 text-[10.5px] leading-[1.5] text-white/40">Real per-endpoint policy, live via the SDK. These are <b className="text-white/55">system pay-per-token</b> endpoints (platform-managed): the app's service principal can't write to them, so <b className="text-white/55">writes run as you (the signed-in admin)</b> via on-behalf-of-user auth and are audited to you. <span className="text-[#93D3AB]">Usage tracking</span> feeds <span className="num">system.ai_gateway.usage</span>. <b className="text-white/55">Fallback</b> isn't supported on this endpoint type - it's enforced app-side (Fallbacks panel) or on a custom endpoint.</p>
                </div>
              )}

              {/* Governance features */}
              <div>
                <div className={`${EB} mb-2`}>Governance features · {autoClassifier ? <span className="text-[#93D3AB]">all applied automatically by finops-auto</span> : <>tick to apply, <span className="text-[#8FC1F0]">Configure</span> to inspect &amp; edit</>}</div>
                <div className="flex flex-wrap gap-2">
                  {features.map((f) => (
                    <FeatureChip key={f.id} f={f} on={enabled.has(f.id)} locked={autoClassifier} onToggle={() => toggleFeature(f.id)} onInspect={() => setInspect((cur) => (cur === f.id ? null : f.id))} inspecting={inspect === f.id} />
                  ))}
                </div>
              </div>

              {/* Options: per-request levers applied on Route */}
              <div>
                <div className={`${EB} mb-2`}>Options · applied on Route</div>
                <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
                  <label className="flex cursor-pointer items-center gap-2 text-[12.5px] text-white/75">
                    <input type="checkbox" checked={cacheOn} onChange={(e) => setCacheOn(e.target.checked)} className="h-3.5 w-3.5 accent-lava" />
                    Semantic cache
                  </label>
                  <label className="flex cursor-pointer items-center gap-2 text-[12.5px] text-white/75">
                    <input type="checkbox" checked={optOn} onChange={(e) => setOptOn(e.target.checked)} className="h-3.5 w-3.5 accent-lava" />
                    Optimize output
                  </label>
                  {optOn && (
                    <label className="flex items-center gap-2 text-[12.5px] text-white/75">≤ words
                      <input type="number" min={20} max={800} value={optWords} onChange={(e) => setOptWords(Math.max(20, Number(e.target.value) || 150))}
                        className="num w-[70px] rounded bg-white/[0.06] px-2 py-1 text-right text-[12px] text-white outline-none ring-1 ring-white/10" />
                    </label>
                  )}
                  {cacheStats && (
                    <span className="ml-auto inline-flex items-center gap-2 rounded-pill bg-moss/12 px-3 py-1 ring-1 ring-moss/25" title={cfg?.demoMode ? 'Demo mode: the semantic cache is disabled, so this stays at $0.' : 'Cumulative $ saved by serving near-duplicate prompts from the durable semantic cache.'}>
                      <span className="font-body text-[10px] font-semibold uppercase tracking-[.1em] text-[#93D3AB]">saved by cache</span>
                      <span className="num text-[13px] font-semibold text-[#93D3AB]">{formatMoney(cacheStats.savedUsd)}</span>
                    </span>
                  )}
                </div>
              </div>
              </>
              )}

              {/* Action row (both personas). The user persona just asks and gets a response
                  routed with everything the admin persisted. */}
              <div className="flex flex-wrap gap-2.5">
                <button
                  onClick={route}
                  disabled={busy || !activeQuestionText.trim()}
                  className="rounded-pill bg-lava px-[22px] py-2.5 text-[13px] font-semibold text-white shadow-lift transition hover:bg-[#e22e1a] disabled:cursor-not-allowed disabled:opacity-45"
                >
                  {busy ? (persona === 'user' ? 'Working…' : 'Routing…') : (persona === 'user' ? 'Get response' : 'Route through the gateway')}
                </button>
                {persona === 'admin' && (
                  <button
                    onClick={() => { setPrompt(''); setInspect(null); }}
                    disabled={busy}
                    className="rounded-pill bg-white/10 px-[22px] py-2.5 text-[13px] font-medium text-white/80 ring-1 ring-white/10 transition hover:bg-white/15 hover:text-white disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    Reset
                  </button>
                )}
              </div>

            {/* Feature Configure panel - inside the gateway box (Admin only). Budgets
                and Routing policy carry real routing state, so they render inline; the
                rest are illustrative config panels from StageConfigPanel. */}
            {persona === 'admin' && inspectFeature && (
              inspectFeature.feature === 'budgets' ? (
                <ConfigCard title={inspectFeature.label}>
                  <BudgetForm budgetOn={enabled.has('budget')} setBudgetOn={() => toggleFeature('budget')} capUsd={capUsd} setCapUsd={setCapUsd} consumedPct={consumedPct} setConsumedPct={setConsumedPct}
                    downgradeAt={downgradeAt} setDowngradeAt={setDowngradeAt} openOnlyAt={openOnlyAt} setOpenOnlyAt={setOpenOnlyAt}
                    downgradeAction={downgradeAction} setDowngradeAction={setDowngradeAction} openOnlyAction={openOnlyAction} setOpenOnlyAction={setOpenOnlyAction} />
                </ConfigCard>
              ) : inspectFeature.feature === 'routing-policy' ? (
                <ConfigCard title={inspectFeature.label}>
                  <RoutingPolicyForm bands={bands} setBands={setBands} policyMode={policyMode} setPolicyMode={setPolicyMode} policyRules={policyRules} setPolicyRules={setPolicyRules} />
                </ConfigCard>
              ) : inspectFeature.feature === 'fallbacks' ? (
                <ConfigCard title={inspectFeature.label}>
                  <FallbackForm
                    fbOn={enabled.has('fallbacks')} setFbOn={() => toggleFeature('fallbacks')}
                    chain={fbChain} byId={byId}
                  />
                </ConfigCard>
              ) : inspectFeature.feature === 'guardrails' ? (
                <ConfigCard title={inspectFeature.label}>
                  <GuardrailsForm on={enabled.has('guardrails')} setOn={() => toggleFeature('guardrails')} cfg={guardCfg} setCfg={setGuardCfg} />
                </ConfigCard>
              ) : inspectFeature.feature === 'rate-limits' ? (
                <ConfigCard title={inspectFeature.label}>
                  <RateLimitForm on={enabled.has('rate-limits')} setOn={() => toggleFeature('rate-limits')} cfg={rateCfg} setCfg={setRateCfg} />
                </ConfigCard>
              ) : inspectFeature.feature === 'access-control' ? (
                <ConfigCard title={inspectFeature.label}>
                  <AccessControlForm on={enabled.has('access-control')} setOn={() => toggleFeature('access-control')} group={accessGroup} setGroup={setAccessGroup} tiers={accessTiers} setTiers={setAccessTiers} />
                </ConfigCard>
              ) : (
                <StageConfigPanel feature={inspectFeature.feature} stageName={inspectFeature.label} />
              )
            )}
          </div>
        </section>

        {/* Blocked before routing - guardrail, budget cap, rate limit, or access control.
            The real proxy THROWS on a block, so this renders from the caught error. */}
        {blockedErr && (
          <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[26px] text-white shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.12s' }}>
            <div className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-lava opacity-[.14] blur-3xl" />
            <div className="relative flex flex-col gap-4">
              <div className={SECTION}>Result</div>
              <div className="flex items-start gap-3 rounded-2xl bg-lava/10 p-5 ring-1 ring-lava/40">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-lava/25 text-[18px]">🛑</span>
                <div>
                  <div className="font-display text-[15px] font-bold text-lava">Blocked before routing</div>
                  <p className="mt-1.5 text-[12.5px] leading-[1.6] text-white/75">{blockedErr.message}</p>
                  <p className="mt-2 text-[11.5px] leading-[1.6] text-white/50">No model was called. The gateway app enforced this itself (guardrail, budget cap, rate limit, or access control) before any inference ran.</p>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Box 3 - result */}
        {result && !('error' in result) && !result.blocked && (
          <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[26px] text-white shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.12s' }}>
            <div className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-lava opacity-[.09] blur-3xl" />
            <div className="relative flex flex-col gap-[18px]">
              <div className={SECTION}>Result</div>
              {receipt && <ReceiptChips f={receipt} demoMode={!!cfg?.demoMode} />}
              {/* Live routing steps - query → complexity → policy → model → response */}
              <div className="rounded-2xl bg-white/[0.04] p-4 pt-5 ring-1 ring-white/10">
                <div className={`${EB} mb-4`}>Live routing flow</div>
                <RoutingSteps
                  running={busy}
                  steps={[
                    { key: 'q', label: 'Query', detail: 'received', glyph: '✎', accent: '#67B8F0' },
                    { key: 'cx', label: 'Complexity', detail: `score ${result.complexity}${result.bandLabel ? ` · ${result.bandLabel}` : ''}`, glyph: '▦', accent: '#67C7E8' },
                    { key: 'pol', label: 'Complexity routing', detail: `→ ${TIER_SHORT[result.chosen.tier]}`, glyph: '⑃', accent: '#F5B24B' },
                    ...(result.budget?.applied ? [{ key: 'bud', label: 'Budget', detail: `${Math.round(result.budget.consumedPct)}%${result.budget.downgraded ? ' · eased' : ''}`, glyph: '◱', accent: '#C08BF2' }] : []),
                    { key: 'model', label: result.chosen.short, detail: usd(result.costUsd), glyph: '◆', accent: '#FF3621', landed: true },
                    { key: 'resp', label: 'Response', detail: `${result.latencyMs}ms`, glyph: '✓', accent: '#4FD79E' },
                  ]}
                />
              </div>

              {/* App-level fallback: the chain the gateway is armed to retry through,
                  and a banner when a fallback actually served this request. */}
              {result.fallback?.enabled && result.fallback.armed.length > 1 && (
                <div className={`flex flex-wrap items-center gap-x-2 gap-y-1.5 rounded-2xl p-4 ring-1 ${result.fallback.fired ? 'bg-lava/10 ring-lava/40' : 'bg-white/[0.04] ring-white/10'}`}>
                  <span className="text-[15px]">{result.fallback.fired ? '↩' : '🛡'}</span>
                  <span className={`${EB} ${result.fallback.fired ? 'text-lava' : ''}`}>Fallback {result.fallback.fired ? 'fired' : 'armed'}</span>
                  {result.fallback.fired && result.fallback.from && (
                    <span className="text-[12.5px] font-semibold text-white/85"><span className="num">{result.fallback.from}</span> failed → served by <span className="num text-[#93D3AB]">{result.chosen.short}</span></span>
                  )}
                  <span className="ml-auto flex items-center gap-1.5">
                    {result.fallback.armed.map((s, i) => (
                      <span key={i} className="flex items-center gap-1.5">
                        {i > 0 && <span className="text-[10px] text-white/35">→</span>}
                        <span className={`num rounded-pill px-2 py-0.5 text-[11px] font-semibold ${s === result.chosen.short ? 'bg-moss/20 text-[#93D3AB]' : i === 0 ? 'bg-white/10 text-white/80' : 'bg-white/[0.06] text-white/50'}`}>{i === 0 ? 'primary · ' : ''}{s}</span>
                      </span>
                    ))}
                  </span>
                  <p className="w-full text-[10.5px] leading-[1.5] text-white/40">Enforced by the gateway app itself (application-level failover) - retries the next model on error/timeout. Saved to Lakebase.</p>
                </div>
              )}

              <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] gap-[18px] max-[900px]:grid-cols-1">
              {/* Routed-to + cost */}
              <div className="rounded-2xl bg-black/30 p-6 ring-1 ring-white/10">
                <div className={EB}>Routed to</div>
                <div className="mt-2 flex items-center gap-2.5">
                  <span className={`h-2.5 w-[3px] rounded-[2px] ${TIER_DOT[result.chosen.tier]}`} />
                  <span className="num text-[18px] font-medium text-white">{result.chosen.short}</span>
                  <span className="num rounded-pill bg-white/10 px-2 py-1 text-[10px] uppercase tracking-[.08em] text-white/70">{TIER_LABEL[result.chosen.tier]}</span>
                </div>
                <div className="mt-5 flex items-end gap-6">
                  <div>
                    <div className={EB}>Cost</div>
                    <div className="num mt-1.5 text-[30px] font-medium leading-none tracking-[-.045em] text-lava">{usd(result.costUsd)}</div>
                  </div>
                  {/* Only show the comparison when a cheaper model was actually
                      avoided. When the chosen model IS the priciest one selected
                      (e.g. the frontier won), "vs itself" and "Saved 0%" are redundant. */}
                  {result.savingsUsd > 0 && result.baseline.short !== result.chosen.short ? (
                    <>
                      <div>
                        <div className={EB}>vs {result.baseline.short}</div>
                        <div className="num mt-1.5 text-[16px] text-white/80">{usd(result.baseline.costUsd)}</div>
                      </div>
                      <div>
                        <div className={EB}>Saved</div>
                        <div className="num mt-1.5 text-[16px] text-lava">{result.savingsPct}%</div>
                      </div>
                    </>
                  ) : (
                    <div>
                      <div className={EB}>Best value</div>
                      <div className="num mt-1.5 text-[16px] text-white/80">of your selected models</div>
                    </div>
                  )}
                </div>
                {/* Router add-on: even after paying the small-LLM router, the all-in
                    cost stays far under always calling the frontier baseline. */}
                {result.routingOverheadUsd != null && result.allInCostUsd != null && (
                  <div className="mt-4 rounded-xl bg-white/[0.04] p-3 ring-1 ring-white/10">
                    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[11.5px]">
                      <span className="text-white/55">+ router{result.routerModel ? ` (${result.routerModel})` : ''} · small LLM that classified the prompt</span>
                      <span className="num font-semibold text-white/80">+{usd(result.routingOverheadUsd)}</span>
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t border-white/10 pt-1.5 text-[12px]">
                      <span className="font-semibold text-white/80">All-in / query (model + router)</span>
                      <span className="num font-bold text-moss">{usd(result.allInCostUsd)}
                        {result.cheaperThanBaselineX && result.cheaperThanBaselineX >= 1.2 ? <span className="ml-2 rounded-pill bg-moss/20 px-2 py-0.5 text-[10.5px] font-extrabold text-moss">{result.cheaperThanBaselineX}× cheaper than {result.baseline.short}</span> : null}
                      </span>
                    </div>
                  </div>
                )}
                <div className="num mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] text-white/50">
                  <span>{result.latencyMs} ms</span>
                  {result.judgeScore != null && <span>judge {formatScore(result.judgeScore)}/10</span>}
                  <span>complexity {result.complexity}{result.bandLabel ? ` · ${result.bandLabel} band` : ''}</span>
                  {result.budget?.applied && (
                    <span className={`rounded-pill px-2 py-1 text-[10px] uppercase tracking-[.08em] ${result.budget.downgraded ? 'bg-lava/20 text-lava' : 'bg-white/10 text-white/70'}`}>
                      budget {Math.round(result.budget.consumedPct)}%{result.budget.downgraded ? ' · eased' : ''}
                    </span>
                  )}
                </div>
              </div>

              {/* How it routed */}
              <div className="rounded-2xl bg-white/[0.04] p-5 ring-1 ring-white/10">
                <h6 className="mb-2 font-display text-[12px] font-semibold text-white">How it routed</h6>
                <p className="mb-3 text-[12.5px] leading-[1.6] text-white/70">{result.reason}</p>
                <div className="num flex flex-col gap-1.5 text-[11.5px] leading-[1.7]">
                  {result.trace.map((e, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span className={e.kind === 'feature' ? 'text-moss' : e.kind === 'route' ? 'text-lava' : 'text-white/45'}>
                        {e.kind === 'feature' ? '✓' : '→'}
                      </span>
                      <span className="text-white/70">{e.text}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* True router: prompt-token + tool-schema compression actually applied to the request. */}
            {result.compression && (
              <div className="rounded-2xl bg-white/[0.04] p-5 ring-1 ring-white/10">
                <div className="mb-2.5 flex flex-wrap items-center gap-2">
                  <h6 className="font-display text-[12px] font-semibold text-white">Compression</h6>
                  <span className="num text-[11px] text-white/45">applied to the request before routing</span>
                  <span className="num ml-auto rounded-pill bg-moss/20 px-2.5 py-1 text-[11px] font-bold text-[#93D3AB] ring-1 ring-moss/30">real · sent to the model</span>
                </div>
                <div className="grid grid-cols-2 gap-3 max-[560px]:grid-cols-1">
                  <div className="rounded-lg bg-black/25 p-3 ring-1 ring-white/10">
                    <div className={EB}>Prompt tokens</div>
                    <div className="num mt-1.5 flex items-baseline gap-2 text-[15px] font-semibold text-white">
                      {result.compression.prompt.tokensBefore}<span className="text-[11px] text-white/40">→</span><span className="text-[#93D3AB]">{result.compression.prompt.tokensAfter}</span>
                      <span className="ml-auto text-[12px] font-bold text-[#93D3AB]">−{result.compression.prompt.savedPct}%</span>
                    </div>
                  </div>
                  <div className="rounded-lg bg-black/25 p-3 ring-1 ring-white/10">
                    <div className={EB}>Tool schema · {result.compression.tools.toolsBefore}→{result.compression.tools.toolsAfter} tools</div>
                    <div className="num mt-1.5 flex items-baseline gap-2 text-[15px] font-semibold text-white">
                      {result.compression.tools.tokensBefore}<span className="text-[11px] text-white/40">→</span><span className="text-[#93D3AB]">{result.compression.tools.tokensAfter}</span>
                      <span className="ml-auto text-[12px] font-bold text-[#93D3AB]">−{result.compression.tools.savedPct}%</span>
                    </div>
                  </div>
                </div>
                {/* Tool catalog: which tools were SENT vs PRUNED for this request. */}
                {result.compression.tools.catalog && result.compression.tools.catalog.length > 0 && (
                  <div className="mt-3">
                    <div className={`${EB} mb-1.5 flex flex-wrap items-center gap-2`}>
                      <span>Tool selection · {result.compression.tools.toolsAfter} of {result.compression.tools.toolsBefore} sent</span>
                      {result.compression.tools.source && (
                        <span className={`num rounded-pill px-2 py-0.5 text-[10px] normal-case ${result.compression.tools.source.startsWith('uc:') ? 'bg-moss/20 text-[#93D3AB] ring-1 ring-moss/30' : 'bg-white/10 text-white/50'}`}>
                          {result.compression.tools.source.startsWith('uc:') ? `real · ${result.compression.tools.source.slice(3)}` : 'sample set'}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {result.compression.tools.catalog.map((t) => (
                        <span key={t.name} title={t.desc}
                          className={`num inline-flex items-center gap-1 rounded-pill px-2 py-1 text-[11px] ${t.kept ? 'bg-moss/20 text-[#93D3AB] ring-1 ring-moss/30' : 'text-white/35 line-through'}`}>
                          {t.kept ? '✓' : '✗'} {t.name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                <p className="mt-2 text-[11px] leading-[1.5] text-white/45">The compressed prompt is what's actually sent; pruned tools (struck through) aren't. Served via governed Model Serving (captured in system.ai_gateway.usage).</p>
              </div>
            )}

            {/* The model's actual answer + quality score, once routed. */}
            {result.answer && (
              <div className="rounded-2xl bg-white/[0.04] p-5 ring-1 ring-white/10">
                <div className="mb-2.5 flex flex-wrap items-center gap-2">
                  <h6 className="font-display text-[12px] font-semibold text-white">Response</h6>
                  <span className="num text-[11px] text-white/45">from {result.chosen.short}</span>
                  {result.judgeScore != null && <span className="num ml-auto rounded-pill bg-[#2272B4]/25 px-2.5 py-1 text-[11px] font-bold text-[#8FC1F0] ring-1 ring-[#2272B4]/40">Quality {formatScore(result.judgeScore)}/10</span>}
                </div>
                <div className="max-h-[300px] overflow-y-auto rounded-lg bg-black/25 px-3.5 py-3 text-[13px] leading-[1.65] text-white/85 ring-1 ring-white/10" style={{ whiteSpace: 'pre-wrap' }}>{result.answer}</div>
                {result.judgeReason && <p className="mt-2 text-[11.5px] leading-[1.5] text-white/55"><span className="font-semibold text-white/70">Judge:</span> {result.judgeReason}</p>}
              </div>
            )}
            </div>
          </section>
        )}

        {libraryOpen && (
          <QuestionLibrary
            onPick={(q) => useLibraryQuestion(q)}
            onClose={() => setLibraryOpen(false)}
          />
        )}
      </div>
    </DndContext>
  );
}

// ---- pieces -------------------------------------------------------------

function QuestionPill({ q, onClick }: { q: Question; onClick: () => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: `q:${q.id}` });
  const c = complexityOf(q.cx);
  return (
    <button ref={setNodeRef} style={{ transform: CSS.Translate.toString(transform) }} {...listeners} {...attributes} onClick={onClick}
      title={`${CX_META[c].label} (complexity ${q.cx}) - ${CX_META[c].blurb}`}
      className={`inline-flex cursor-grab items-center gap-2 rounded-pill bg-white/10 px-3.5 py-2.5 text-[12.5px] text-white/85 ring-1 ring-white/10 transition hover:-translate-y-[2px] hover:bg-white/15 hover:text-white ${isDragging ? 'opacity-35' : ''}`}>
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: CX_META[c].hex }} />
      <span>{q.t}</span>
    </button>
  );
}

// The composer: an editable textarea (drop a question in, type, paste, edit
// freely). For Admins it carries a model picker at its foot - the Routing LLM
// The composer: an editable textarea (drop a question in, type, paste, edit freely).
function QuestionSlot({ custom, onCustom, onClear }: { custom: string; onCustom: (v: string) => void; onClear: () => void }) {
  const { setNodeRef, isOver } = useDroppable({ id: 'gateway-question' });
  const has = custom.trim().length > 0;
  return (
    <div ref={setNodeRef} className={`rounded-lg border-[1.5px] border-dashed p-3.5 transition ${isOver ? 'border-lava bg-lava/10' : 'border-white/20'}`}>
      <div className="mb-2 flex items-center justify-between">
        <span className={EB}>Question</span>
        {has && <button onClick={onClear} className="text-[15px] leading-none text-white/45 hover:text-lava" aria-label="Clear">×</button>}
      </div>
      <textarea
        value={custom}
        onChange={(e) => onCustom(e.target.value)}
        onPointerDown={(e) => e.stopPropagation()}
        onPointerDownCapture={(e) => e.stopPropagation()}
        rows={2}
        placeholder="Drop a question here, type your own, or paste text…"
        className="block w-full resize-none bg-transparent text-[14.5px] leading-[1.5] text-white outline-none placeholder:text-white/35"
      />
    </div>
  );
}

// Persona radio - User (simple ask) vs Admin (governance + budget).
function PersonaToggle({ persona, onChange }: { persona: Persona; onChange: (p: Persona) => void }) {
  return (
    <div role="radiogroup" aria-label="Persona" className="inline-flex items-center gap-1 rounded-pill bg-white/10 p-1 ring-1 ring-white/10">
      {(['admin', 'user'] as Persona[]).map((p) => (
        <button
          key={p}
          role="radio"
          aria-checked={persona === p}
          onClick={() => onChange(p)}
          className={`rounded-pill px-3 py-1 text-[11.5px] font-semibold capitalize transition ${persona === p ? 'bg-white text-ink' : 'text-white/70 hover:text-white'}`}
        >
          {p}
        </button>
      ))}
    </div>
  );
}

// Complexity legend - what small / medium / complex mean (dark-stage popover).
function ComplexityInfo({ onClose }: { onClose: () => void }) {
  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="absolute left-0 top-full z-50 mt-2 w-[320px] rounded-xl bg-card p-4 text-left text-[12px] leading-[1.5] text-ink-2 shadow-lift-hi">
        <div className="mb-2 flex items-center justify-between">
          <span className="font-display text-[12.5px] font-semibold text-ink">Prompt complexity</span>
          <button onClick={onClose} aria-label="Close" className="text-[15px] leading-none text-ink-3 hover:text-ink">×</button>
        </div>
        <ul className="flex flex-col gap-2">
          {(['small', 'medium', 'complex'] as Complexity[]).map((c) => (
            <li key={c} className="flex gap-2">
              <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: CX_META[c].hex }} />
              <span><b className="text-ink">{CX_META[c].label}.</b> {CX_META[c].blurb}</span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11px] text-ink-3">The gateway scores each question 0-100 and routes to the cheapest tier that clears the bar.</p>
      </div>
    </>
  );
}

// A 0-100 track showing each band as a colored segment - the routing policy at a glance.
function BandBar({ bands }: { bands: Band[] }) {
  return (
    <div className="relative h-3 w-full overflow-hidden rounded-full bg-white/[0.06]">
      {bands.map((b) => {
        const left = Math.max(0, Math.min(100, b.min));
        const width = Math.max(0, Math.min(100, b.max) - left + 1);
        return <div key={b.id} className="absolute top-0 h-full" style={{ left: `${left}%`, width: `${width}%`, background: TIER_META[b.tier].hex, opacity: 0.85 }} title={`${b.label}: ${b.min}-${b.max}`} />;
      })}
    </div>
  );
}

function TierSelect({ value, onChange }: { value: Tier; onChange: (t: Tier) => void }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value as Tier)} aria-label="Tier"
      className="num cursor-pointer rounded bg-black/30 px-2 py-1 text-[12px] font-semibold text-white ring-1 ring-white/10 outline-none">
      {[...TIER_ORDER].reverse().map((t) => <option key={t} value={t} className="text-ink">{TIER_SHORT[t]}</option>)}
    </select>
  );
}

// Admin routing policy - TWO ways to define it: complexity-score bands, or
// free-text criteria you write yourself. Rendered inside the "Routing policy"
// Configure panel; drives real routing. Budget fallback lives in the Budgets panel.
function RoutingPolicyForm({ bands, setBands, policyMode, setPolicyMode, policyRules, setPolicyRules }: {
  bands: Band[];
  setBands: React.Dispatch<React.SetStateAction<Band[]>>;
  policyMode: 'bands' | 'criteria';
  setPolicyMode: (m: 'bands' | 'criteria') => void;
  policyRules: CriteriaRule[];
  setPolicyRules: React.Dispatch<React.SetStateAction<CriteriaRule[]>>;
}) {
  const clamp = (n: number) => Math.max(0, Math.min(100, Math.round(n) || 0));
  const addBand = () => setBands((bs) => [...bs, { id: `band-${Date.now()}`, label: `Band ${bs.length + 1}`, min: 0, max: 100, tier: 'large-oss' }]);
  const updBand = (id: string, patch: Partial<Band>) => setBands((bs) => bs.map((b) => (b.id === id ? { ...b, ...patch } : b)));
  const delBand = (id: string) => setBands((bs) => bs.filter((b) => b.id !== id));
  const addRule = () => setPolicyRules((rs) => [...rs, { id: `cr-${Date.now()}`, keywords: '', tier: 'large-oss' }]);
  const updRule = (id: string, patch: Partial<CriteriaRule>) => setPolicyRules((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const delRule = (id: string) => setPolicyRules((rs) => rs.filter((r) => r.id !== id));
  const btn = 'rounded-pill bg-white/10 px-2.5 py-1 text-[11px] font-semibold text-white/80 ring-1 ring-white/15 transition hover:bg-white/20 disabled:opacity-30';
  return (
    <div>
      {/* Mode toggle - score-based bands vs free-text criteria */}
      <div className="mb-3 inline-flex rounded-pill bg-white/10 p-0.5 ring-1 ring-white/10">
        {([['bands', 'Complexity score'], ['criteria', 'Define criteria yourself']] as const).map(([m, label]) => (
          <button key={m} onClick={() => setPolicyMode(m)} aria-pressed={policyMode === m}
            className={`rounded-pill px-3 py-1.5 text-[11.5px] font-semibold transition ${policyMode === m ? 'bg-white text-ink' : 'text-white/65 hover:text-white'}`}>
            {label}
          </button>
        ))}
      </div>

      {policyMode === 'bands' ? (
        <>
          <BandBar bands={bands} />
          <div className="mt-3 flex items-center justify-between">
            <span className={EB}>Complexity bands · score 0-100 → tier</span>
            <button onClick={addBand} className={btn}>+ Add band</button>
          </div>
          <div className="mt-2 flex flex-col gap-2">
            {bands.map((b) => (
              <div key={b.id} className="flex flex-wrap items-center gap-2 rounded-lg bg-black/20 p-2 ring-1 ring-white/10">
                <span className="h-4 w-[3px] shrink-0 rounded" style={{ background: TIER_META[b.tier].hex }} />
                <input value={b.label} onChange={(e) => updBand(b.id, { label: e.target.value })} aria-label="Band name"
                  className="w-[110px] rounded bg-white/10 px-2 py-1 text-[12px] font-semibold text-white ring-1 ring-white/10 outline-none" />
                <span className="num text-[11px] text-white/45">score</span>
                <input type="number" min={0} max={100} value={b.min} onChange={(e) => updBand(b.id, { min: clamp(+e.target.value) })} aria-label="Band minimum"
                  className="num w-[54px] rounded bg-white/10 px-2 py-1 text-right text-[12px] text-white ring-1 ring-white/10 outline-none" />
                <span className="text-[11px] text-white/45">–</span>
                <input type="number" min={0} max={100} value={b.max} onChange={(e) => updBand(b.id, { max: clamp(+e.target.value) })} aria-label="Band maximum"
                  className="num w-[54px] rounded bg-white/10 px-2 py-1 text-right text-[12px] text-white ring-1 ring-white/10 outline-none" />
                <span className="text-[11px] text-white/45">→</span>
                <TierSelect value={b.tier} onChange={(t) => updBand(b.id, { tier: t })} />
                <button onClick={() => delBand(b.id)} disabled={bands.length <= 1} className="ml-auto text-[16px] leading-none text-white/40 transition hover:text-lava disabled:opacity-25" aria-label="Remove band">×</button>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] leading-[1.5] text-white/45">
            Each question is scored 0-100 by the small router LLM and falls into the matching band. Every decision is logged to Unity Catalog.
          </p>
        </>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <span className={EB}>Criteria · keywords → tier</span>
            <button onClick={addRule} className={btn}>+ Add rule</button>
          </div>
          <div className="mt-2 flex flex-col gap-2">
            {policyRules.map((r) => (
              <div key={r.id} className="flex flex-wrap items-center gap-2 rounded-lg bg-black/20 p-2 ring-1 ring-white/10">
                <span className="h-4 w-[3px] shrink-0 rounded" style={{ background: TIER_META[r.tier].hex }} />
                <input value={r.keywords} onChange={(e) => updRule(r.id, { keywords: e.target.value })} aria-label="Rule keywords" placeholder="keywords, comma-separated"
                  className="min-w-[170px] flex-1 rounded bg-white/10 px-2 py-1 text-[12px] text-white ring-1 ring-white/10 outline-none placeholder:text-white/30" />
                <span className="text-[11px] text-white/45">→</span>
                <TierSelect value={r.tier} onChange={(t) => updRule(r.id, { tier: t })} />
                <button onClick={() => delRule(r.id)} disabled={policyRules.length <= 1} className="text-[16px] leading-none text-white/40 transition hover:text-lava disabled:opacity-25" aria-label="Remove rule">×</button>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] leading-[1.6] text-white/50">
            <span className="font-semibold text-white/70">How it works:</span> if a prompt contains one of a rule's keywords it routes to that tier; anything unmatched falls back to the complexity bands. In production the small router LLM interprets these criteria directly.
          </p>
        </>
      )}
    </div>
  );
}

// A budget action picker: cap the ceiling at a tier, or block new requests.
function ActionSelect({ value, onChange }: { value: BudgetAction; onChange: (a: BudgetAction) => void }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value as BudgetAction)} aria-label="Budget action"
      className="num cursor-pointer rounded bg-black/30 px-2 py-1 text-[12px] font-semibold text-white ring-1 ring-white/10 outline-none">
      {[...TIER_ORDER].reverse().map((t) => <option key={t} value={t} className="text-ink">cap at {TIER_SHORT[t]}</option>)}
      <option value="block" className="text-ink">block requests</option>
    </select>
  );
}

const actionLabel = (a: BudgetAction) => (a === 'block' ? 'blocks new requests' : `caps at ${TIER_SHORT[a as Tier]}`);

// Admin budget - the "Apply a budget" controls. Each threshold carries its own
// ACTION (cap at a chosen tier, or block new requests) as spend rises.
function BudgetForm({ budgetOn, setBudgetOn, capUsd, setCapUsd, consumedPct, setConsumedPct,
  downgradeAt, setDowngradeAt, openOnlyAt, setOpenOnlyAt, downgradeAction, setDowngradeAction, openOnlyAction, setOpenOnlyAction }: {
  budgetOn: boolean; setBudgetOn: (b: boolean) => void;
  capUsd: number | null; setCapUsd: (n: number) => void;
  consumedPct: number; setConsumedPct: (n: number) => void;
  downgradeAt: number; setDowngradeAt: (n: number) => void;
  openOnlyAt: number; setOpenOnlyAt: (n: number) => void;
  downgradeAction: BudgetAction; setDowngradeAction: (a: BudgetAction) => void;
  openOnlyAction: BudgetAction; setOpenOnlyAction: (a: BudgetAction) => void;
}) {
  const clampPct = (n: number) => Math.max(0, Math.min(100, Math.round(n) || 0));
  // What happens right now at the current consumed %, and which threshold fires.
  const activeAt = consumedPct >= openOnlyAt ? 'oo' : consumedPct >= downgradeAt ? 'dg' : null;
  const effect = activeAt === 'oo' ? openOnlyAction : activeAt === 'dg' ? downgradeAction : null;
  const minTrigger = Math.min(downgradeAt, openOnlyAt); // lowest % that engages any cap
  return (
    <div className="flex flex-col gap-3">
      <label className="flex cursor-pointer items-center gap-2">
        <input type="checkbox" checked={budgetOn} onChange={(e) => setBudgetOn(e.target.checked)} className="accent-lava" />
        <span className={EB}>Apply a budget</span>
        <span className="text-[12px] font-medium text-white/55">budget pressure tightens routing as spend rises</span>
      </label>
      {budgetOn ? (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <span className="w-[92px] shrink-0 text-[11px] text-white/45">Monthly budget</span>
            <span className="num text-[12px] text-white/45">$</span>
            <input type="number" min={0} step={500} value={capUsd ?? 0} onChange={(e) => setCapUsd(Number(e.target.value))}
              className="num w-[130px] rounded bg-white/10 px-2.5 py-1.5 text-[12px] text-white ring-1 ring-white/10 outline-none" />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="w-[92px] shrink-0 text-[11px] text-white/45">Consumed</span>
            <input type="number" min={0} max={100} step={1} value={consumedPct}
              onChange={(e) => setConsumedPct(clampPct(Number(e.target.value)))}
              className="num w-[72px] rounded bg-white/10 px-2.5 py-1.5 text-right text-[12px] text-white ring-1 ring-white/10 outline-none" />
            <span className="num text-[12px] text-white/45">% of budget</span>
            <span className={`num rounded-pill px-2 py-1 text-[10.5px] font-bold uppercase tracking-[.06em] ${effect === 'block' ? 'bg-lava/20 text-lava' : effect ? 'bg-amber/20 text-amber' : 'bg-white/10 text-white/55'}`}>
              now → {effect ? actionLabel(effect) : 'no cap · all tiers'}
            </span>
          </div>
          {/* Why nothing capped: consumed is below both thresholds. This is the
              exact confusion point - make it explicit. */}
          {!effect && (
            <div className="rounded-lg bg-white/[0.05] px-3 py-2 text-[11.5px] leading-[1.5] text-white/60 ring-1 ring-amber/25">
              <span className="font-semibold text-amber">No cap active</span> at {consumedPct}% consumed - routing follows complexity only (a complex prompt still goes to the Complex category). Raise <b className="text-white/80">Consumed</b> to ≥{minTrigger}% or lower a threshold below {consumedPct}% to engage a cap.
            </div>
          )}
          {capUsd != null && (
            <div>
              <div className="relative h-3 overflow-hidden rounded-pill bg-white/10">
                <div className="h-full rounded-pill bg-lava" style={{ width: `${consumedPct}%` }} />
                {/* threshold ticks */}
                {[downgradeAt, openOnlyAt].map((p, i) => (
                  <span key={i} className="absolute top-0 h-full w-px bg-white/60" style={{ left: `${p}%` }} />
                ))}
              </div>
              <div className="num mt-1.5 text-[11px] text-white/45">spent ${Math.round((capUsd * consumedPct) / 100).toLocaleString()} / ${capUsd.toLocaleString()} · near-real-time</div>
            </div>
          )}

          {/* Per-threshold ACTIONS - pick what happens at each spend level */}
          <div className="mt-1 flex flex-col gap-2">
            <span className={EB}>What happens as spend rises</span>
            <div className={`flex flex-wrap items-center gap-2 rounded-lg p-2.5 ring-1 transition ${activeAt === 'dg' ? 'bg-amber/10 ring-amber/50' : 'bg-black/20 ring-white/10'}`}>
              <span className="text-[11.5px] text-white/70">At ≥</span>
              <input type="number" min={0} max={100} value={downgradeAt} onChange={(e) => setDowngradeAt(clampPct(+e.target.value))} aria-label="First threshold percent"
                className="num w-[54px] rounded bg-white/10 px-2 py-1 text-right text-[12px] text-white ring-1 ring-white/10 outline-none" />
              <span className="text-[11.5px] text-white/60">% spent →</span>
              <ActionSelect value={downgradeAction} onChange={setDowngradeAction} />
              {activeAt === 'dg' && <span className="num rounded-pill bg-amber/25 px-1.5 py-0.5 text-[9.5px] font-bold uppercase text-amber">active now</span>}
            </div>
            <div className={`flex flex-wrap items-center gap-2 rounded-lg p-2.5 ring-1 transition ${activeAt === 'oo' ? 'bg-lava/10 ring-lava/50' : 'bg-black/20 ring-white/10'}`}>
              <span className="text-[11.5px] text-white/70">At ≥</span>
              <input type="number" min={0} max={100} value={openOnlyAt} onChange={(e) => setOpenOnlyAt(clampPct(+e.target.value))} aria-label="Second threshold percent"
                className="num w-[54px] rounded bg-white/10 px-2 py-1 text-right text-[12px] text-white ring-1 ring-white/10 outline-none" />
              <span className="text-[11.5px] text-white/60">% spent →</span>
              <ActionSelect value={openOnlyAction} onChange={setOpenOnlyAction} />
              {activeAt === 'oo' && <span className="num rounded-pill bg-lava/25 px-1.5 py-0.5 text-[9.5px] font-bold uppercase text-lava">active now</span>}
            </div>
          </div>
        </>
      ) : (
        <p className="text-[11.5px] text-white/45">Turn this on to tighten routing as spend rises - the demo's "budget routing" story. Set what happens at each spend threshold: cap at a cheaper tier, or block new requests.</p>
      )}
    </div>
  );
}

// App-level fallback: the gateway retries down an auto-derived chain (the cheapest of
// each category, Small -> Medium -> Complex) on error/timeout. No hand-ordering - the
// app IS the router, so it enforces this itself with no custom endpoint.
function FallbackForm({ fbOn, setFbOn, chain, byId }: {
  fbOn: boolean; setFbOn: (b: boolean) => void;
  chain: string[]; byId: Map<string, ModelDef>;
}) {
  return (
    <div className="flex flex-col gap-3">
      <label className="flex cursor-pointer items-center gap-2">
        <input type="checkbox" checked={fbOn} onChange={(e) => setFbOn(e.target.checked)} className="accent-lava" />
        <span className={EB}>Enable fallback</span>
        <span className="text-[12px] font-medium text-white/55">retry the next model when a call errors or times out</span>
      </label>
      {fbOn ? (
        <>
          <span className={EB}>Auto failover chain · cheapest of each category</span>
          <div className="flex flex-col gap-2">
            {chain.length < 2 && (
              <p className="rounded-lg bg-white/[0.05] px-3 py-2 text-[11.5px] leading-[1.5] text-white/60 ring-1 ring-amber/25">
                Need at least two categories of deployed models to form a fallback chain.
              </p>
            )}
            {chain.map((id, i) => {
              const m = byId.get(id);
              return (
                <div key={id} className="flex items-center gap-2 rounded-lg bg-black/20 p-2 ring-1 ring-white/10">
                  <span className={`num w-5 shrink-0 text-center text-[11px] font-bold ${i === 0 ? 'text-lava' : 'text-white/45'}`}>{i === 0 ? '①' : i + 1}</span>
                  <span className={`h-4 w-[3px] shrink-0 rounded ${TIER_DOT[m?.tier ?? 'small-oss']}`} />
                  <span className="num text-[12.5px] font-semibold text-white">{m?.short ?? id}</span>
                  {m && <span className="rounded-pill bg-white/10 px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-[.06em] text-white/55">{TIER_SHORT[m.tier]}</span>}
                </div>
              );
            })}
          </div>
          <p className="text-[11px] leading-[1.6] text-white/50">
            <span className="font-semibold text-white/70">How it works:</span> the gateway app IS the router, so if the routed model's call fails it retries down this chain (cheapest per category, ascending) and reports which one served. System pay-per-token endpoints can't carry native <span className="num">fallback_config</span>; this application-level failover works today with no custom endpoint.
          </p>
        </>
      ) : (
        <p className="text-[11.5px] leading-[1.6] text-white/45">Turn this on to make the gateway resilient: if the routed model errors or times out, it automatically retries the next model in the auto chain (cheapest of each category). Enforced on every route.</p>
      )}
    </div>
  );
}

// App-layer guardrails (Idea 2): the gateway app scans each prompt for PII + blocked
// keywords and either blocks the request or masks the matches before routing. Real and
// enforced by the app - works for any endpoint, no endpoint config.
function GuardrailsForm({ on, setOn, cfg, setCfg }: {
  on: boolean; setOn: (b: boolean) => void;
  cfg: { pii: boolean; mode: 'block' | 'mask'; keywords: string };
  setCfg: React.Dispatch<React.SetStateAction<{ pii: boolean; mode: 'block' | 'mask'; keywords: string }>>;
}) {
  return (
    <div className="flex flex-col gap-3">
      <label className="flex cursor-pointer items-center gap-2">
        <input type="checkbox" checked={on} onChange={(e) => setOn(e.target.checked)} className="accent-lava" />
        <span className={EB}>Enable guardrails</span>
        <span className="text-[12px] font-medium text-white/55">scan every prompt before it's routed</span>
      </label>
      {on ? (
        <>
          <label className="flex cursor-pointer items-center gap-2">
            <input type="checkbox" checked={cfg.pii} onChange={(e) => setCfg((c) => ({ ...c, pii: e.target.checked }))} className="accent-lava" />
            <span className="text-[12.5px] text-white/80">Detect PII</span>
            <span className="text-[11px] text-white/45">email · US SSN · phone · credit-card numbers</span>
          </label>
          <div className="flex flex-col gap-1.5">
            <span className={EB}>Blocked keywords · comma-separated</span>
            <input value={cfg.keywords} onChange={(e) => setCfg((c) => ({ ...c, keywords: e.target.value }))} aria-label="Blocked keywords"
              className="rounded bg-white/10 px-2.5 py-1.5 text-[12px] text-white ring-1 ring-white/10 outline-none placeholder:text-white/30" placeholder="confidential, internal-only" />
          </div>
          <div className="flex items-center gap-2">
            <span className={EB}>When matched</span>
            <div className="inline-flex rounded-pill bg-white/10 p-0.5 ring-1 ring-white/10">
              {(['block', 'mask'] as const).map((m) => (
                <button key={m} onClick={() => setCfg((c) => ({ ...c, mode: m }))} aria-pressed={cfg.mode === m}
                  className={`rounded-pill px-3 py-1 text-[11.5px] font-semibold capitalize transition ${cfg.mode === m ? 'bg-white text-ink' : 'text-white/65 hover:text-white'}`}>
                  {m === 'block' ? 'Block request' : 'Mask & proceed'}
                </button>
              ))}
            </div>
          </div>
          <p className="text-[11px] leading-[1.6] text-white/50">
            <span className="font-semibold text-white/70">Enforced by the gateway app</span>, not the endpoint: a match either refuses the request (no model called) or is redacted to <span className="num">[REDACTED-…]</span> before the prompt is classified and sent. Try a prompt with an email or <span className="num">4111 1111 1111 1111</span> to see it fire.
          </p>
        </>
      ) : (
        <p className="text-[11.5px] leading-[1.6] text-white/45">Turn this on to scan every prompt for PII and blocked keywords before it's routed. The app blocks or masks matches itself, so it works on any endpoint (including system pay-per-token ones the app SP can't configure).</p>
      )}
    </div>
  );
}

// App-layer rate limit (Idea 2): the gateway app caps requests per signed-in user per
// minute (in-process sliding window) and refuses over-limit requests before any model call.
function RateLimitForm({ on, setOn, cfg, setCfg }: {
  on: boolean; setOn: (b: boolean) => void;
  cfg: { perMin: number }; setCfg: React.Dispatch<React.SetStateAction<{ perMin: number }>>;
}) {
  return (
    <div className="flex flex-col gap-3">
      <label className="flex cursor-pointer items-center gap-2">
        <input type="checkbox" checked={on} onChange={(e) => setOn(e.target.checked)} className="accent-lava" />
        <span className={EB}>Enable rate limit</span>
        <span className="text-[12px] font-medium text-white/55">cap requests per user, per minute</span>
      </label>
      {on ? (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <span className="w-[92px] shrink-0 text-[11px] text-white/45">Requests / min</span>
            <input type="number" min={1} max={10000} value={cfg.perMin} onChange={(e) => setCfg({ perMin: Math.max(1, parseInt(e.target.value || '1', 10)) })}
              className="num w-[90px] rounded bg-white/10 px-2.5 py-1.5 text-[12px] text-white ring-1 ring-white/10 outline-none" />
            <span className="num text-[12px] text-white/45">per signed-in user</span>
          </div>
          <p className="text-[11px] leading-[1.6] text-white/50">
            <span className="font-semibold text-white/70">Enforced by the gateway app</span> per the signed-in identity (forwarded from the app). Over the limit, the gateway refuses the request before any model is called. Route this question repeatedly to watch it trip at {cfg.perMin}/min.
          </p>
        </>
      ) : (
        <p className="text-[11.5px] leading-[1.6] text-white/45">Turn this on to cap how many requests each user can send per minute. The app refuses over-limit requests itself, so it protects any endpoint without endpoint config.</p>
      )}
    </div>
  );
}

// ABAC access control: pick the requester group being simulated and the model tiers
// each group may use. Mirrors a Unity Catalog EXECUTE/ABAC policy; the gateway enforces
// it per request - a denied tier is filtered out of routing (or the request is blocked).
function AccessControlForm({ on, setOn, group, setGroup, tiers, setTiers }: {
  on: boolean; setOn: (b: boolean) => void;
  group: AccessGroup; setGroup: (g: AccessGroup) => void;
  tiers: Record<AccessGroup, Tier[]>;
  setTiers: React.Dispatch<React.SetStateAction<Record<AccessGroup, Tier[]>>>;
}) {
  const cur = tiers[group];
  const toggleTier = (t: Tier) =>
    setTiers((s) => {
      const has = s[group].includes(t);
      const next = has ? s[group].filter((x) => x !== t) : [...s[group], t];
      return { ...s, [group]: next };
    });
  return (
    <div className="flex flex-col gap-3">
      <label className="flex cursor-pointer items-center gap-2">
        <input type="checkbox" checked={on} onChange={(e) => setOn(e.target.checked)} className="accent-lava" />
        <span className={EB}>Enable access control</span>
        <span className="text-[12px] font-medium text-white/55">restrict which model tiers a group may use</span>
      </label>
      {on ? (
        <>
          <div className="flex flex-col gap-1.5">
            <span className={EB}>Requester group · simulate as</span>
            <div className="inline-flex flex-wrap gap-1 rounded-pill bg-white/10 p-0.5 ring-1 ring-white/10">
              {ACCESS_GROUPS.map((g) => (
                <button key={g} onClick={() => setGroup(g)} aria-pressed={group === g}
                  className={`rounded-pill px-3 py-1 text-[11.5px] font-semibold transition ${group === g ? 'bg-white text-ink' : 'text-white/65 hover:text-white'}`}>
                  {g}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <span className={EB}>{group} may use</span>
            <div className="flex flex-wrap gap-2">
              {[...TIER_ORDER].reverse().map((t) => {
                const active = cur.includes(t);
                return (
                  <button key={t} onClick={() => toggleTier(t)} aria-pressed={active}
                    className={`inline-flex items-center gap-1.5 rounded-pill px-3 py-1.5 text-[12px] font-semibold transition ${active ? 'bg-moss/20 text-[#93D3AB] ring-1 ring-moss/30' : 'bg-white/10 text-white/45 line-through'}`}>
                    <span className={`h-2 w-2 rounded-full ${TIER_DOT[t]}`} />{TIER_SHORT[t]}
                  </button>
                );
              })}
            </div>
          </div>
          <p className="text-[11px] leading-[1.6] text-white/50">
            <span className="font-semibold text-white/70">Enforced by the gateway</span>: a request from <b className="text-white/75">{group}</b> can only route to the ticked categories - a denied category (e.g. Complex) is filtered out before routing, and if nothing is permitted the request is blocked. In production this is a <span className="num">EXECUTE</span> / ABAC grant on the model endpoints by group. Try a complex prompt as <b className="text-white/75">Contractor</b> (Small only) to see Complex denied.
          </p>
        </>
      ) : (
        <p className="text-[11.5px] leading-[1.6] text-white/45">Turn this on to restrict model access by requester group (e.g. contractors → Small only, data scientists → all categories). The gateway filters the candidate models to the group's allowed categories before routing.</p>
      )}
    </div>
  );
}

function FeatureChip({ f, on, onToggle, onInspect, inspecting, locked = false }: { f: Feature; on: boolean; onToggle: () => void; onInspect: () => void; inspecting: boolean; locked?: boolean }) {
  // Auto-classifier mode: every feature is applied automatically, so the chip is green +
  // checked, not toggleable, and carries no Configure control.
  const shown = locked || on;
  return (
    <span className={`inline-flex items-center gap-1 rounded-pill py-1.5 pl-2.5 pr-1.5 text-[12.5px] font-semibold transition ${shown ? 'bg-moss/20 text-[#93D3AB]' : 'bg-white/10 text-white/55'} ${inspecting ? 'ring-2 ring-[#8FC1F0]/60' : ''}`}>
      <button onClick={locked ? undefined : onToggle} disabled={locked} className="flex items-center gap-1.5" aria-pressed={shown} title={locked ? 'Applied automatically in auto-classifier mode' : undefined}>
        <span className={`grid h-4 w-4 place-items-center rounded-full text-[9px] ${shown ? 'bg-moss text-white' : 'border border-white/25'}`}>{shown ? '✓' : ''}</span>
        {f.label}
      </button>
      {!locked && (
        <button
          onClick={onInspect}
          aria-expanded={inspecting}
          title="Configure this feature"
          className={`ml-1 inline-flex items-center gap-1 rounded-pill px-2 py-1 text-[10px] font-bold uppercase tracking-[.05em] transition ${inspecting ? 'bg-[#8FC1F0] text-ink' : 'bg-white/15 text-white/80 hover:bg-white/25 hover:text-white'}`}
        >
          <span className="text-[10px]">⚙</span>{inspecting ? 'Editing ▴' : 'Configure ▾'}
        </button>
      )}
    </span>
  );
}

// ---- Receipt adapters + migrated Live-gateway pieces --------------------

// A one-line plain-English rationale synthesized from the routing receipt (the real
// proxy returns no `reason` string; we build one from the fields it does return).
function routeReason(f: FinopsReceipt): string {
  const via = f.matchedRule
    ? `matched rule "${f.matchedRule}"`
    : f.bandLabel
      ? `scored complexity ${f.complexity} (${f.bandLabel})`
      : `scored complexity ${f.complexity}`;
  return `The router ${via} → needs ${f.requiredTierLabel}, and served it with ${f.servedBy.short} (${TIER_LABEL[f.servedBy.tier as Tier]}) at ${formatMoney(f.costUsd)}/query.`;
}

// Synthesize the "how it routed" trace list from receipt fields (the proxy returns no
// step trace on a single call - these mirror what each governance feature actually did).
function routeTrace(f: FinopsReceipt): { kind: string; text: string }[] {
  const t: { kind: string; text: string }[] = [];
  if (f.guardrail) t.push({ kind: 'feature', text: `Guardrail: ${f.guardrail.action} (${f.guardrail.categories})` });
  if (f.cacheHit) t.push({ kind: 'feature', text: `Semantic cache hit${f.similarity != null ? ` · ${Math.round(f.similarity * 100)}% match` : ''} → served at $0` });
  t.push({ kind: 'route', text: f.matchedRule ? `Matched criteria "${f.matchedRule}" → needs ${f.requiredTierLabel}` : `Complexity ${f.complexity}${f.bandLabel ? ` (${f.bandLabel})` : ''} → needs ${f.requiredTierLabel}` });
  if (f.budget) t.push({ kind: 'feature', text: `Budget ${Math.round(f.budget.consumedPct)}% of $${f.budget.capUsd.toLocaleString()}${f.budget.ceiling !== 'frontier' ? ` · capped at ${TIER_SHORT[f.budget.ceiling as Tier] ?? f.budget.ceiling}` : ''}` });
  if (f.compression && f.compression.savedTokens > 0) t.push({ kind: 'feature', text: `Prompt compressed −${f.compression.savedPct}% (${f.compression.savedTokens} tokens)` });
  if (f.optimization?.enabled) t.push({ kind: 'feature', text: `Output shaped to ≤${f.optimization.targetWords} words` });
  if (f.fallback?.fired) t.push({ kind: 'route', text: `Primary failed → served by ${f.servedBy.short}` });
  t.push({ kind: 'route', text: `Routed to ${f.servedBy.short} (${TIER_LABEL[f.servedBy.tier as Tier]}) → ${formatMoney(f.costUsd)}` });
  return t;
}


// The routing-receipt chip row: what the gateway did on this real call.
function ReceiptChips({ f, demoMode }: { f: FinopsReceipt; demoMode: boolean }) {
  const chip = 'inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-[10.5px] font-semibold uppercase tracking-[.06em] ring-1';
  const moss = 'bg-moss/15 text-[#93D3AB] ring-moss/30';
  const amber = 'bg-[#E3B876]/15 text-[#E3B876] ring-[#E3B876]/30';
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className={`${chip} bg-lava/15 text-[#FF9E7E] ring-lava/30`}>router picked</span>
      {f.cacheHit && <span className={`${chip} ${moss}`}>⚡ cache hit{f.similarity != null ? ` · ${Math.round(f.similarity * 100)}% match` : ''}</span>}
      {f.guardrail && <span className={`${chip} ${amber}`}>guardrail: {f.guardrail.action}</span>}
      {f.fallback?.fired && <span className={`${chip} ${amber}`}>fallback fired: {f.fallback.from} → {f.servedBy.short}</span>}
      {f.compression && f.compression.savedTokens > 0 && <span className={`${chip} ${moss}`}>compressed −{f.compression.savedPct}%</span>}
      {f.optimization?.enabled && <span className={`${chip} ${moss}`}>shaped ≤{f.optimization.targetWords}w{f.optimization.savedOutputTokens > 0 ? ` · −${formatTokens(f.optimization.savedOutputTokens)} tok` : ''}</span>}
      {f.budget && <span className={`${chip} ${amber}`}>budget {Math.round(f.budget.consumedPct)}%{f.budget.ceiling !== 'frontier' ? ` · cap ${TIER_SHORT[f.budget.ceiling as Tier] ?? f.budget.ceiling}` : ''}</span>}
      {demoMode && <span className={`${chip} bg-white/10 text-white/60 ring-white/10`}>demo mode</span>}
    </div>
  );
}

