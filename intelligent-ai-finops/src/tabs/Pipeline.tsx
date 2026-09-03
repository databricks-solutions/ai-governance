import { useEffect, useMemo, useState } from 'react';
import { DndContext, PointerSensor, useSensor, useSensors, useDraggable, useDroppable, type DragEndEvent } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { StageConfigPanel, ConfigCard } from '../components/StageConfigPanel';
import { QuestionLibrary } from '../components/QuestionLibrary';
import { RoutingSteps } from '../components/RoutingViz';
import { useSession } from '../store/session';
import { useConfig } from '../api/useConfig';
import type { Tier, Band, ModelDef } from '../api/types';
import { TIER_LABEL, TIER_SHORT, TIER_ORDER, TIER_META } from '../api/types';
import { formatMoney, formatScore } from '../lib/format';

// Client-side mirror of backend/routing.classify, so the gateway box can preview
// the complexity score and the band a prompt would land in as you type - the
// routing policy visibly reacts before you even run.
const HARD_RE = /why|prove|reconcile|design|architect|debug|justify|strategy|root.?cause/i;
const classifyClient = (p: string): number => {
  const t = p.trim();
  if (!t) return 0;
  return Math.min(99, Math.max(1, Math.round(12 + t.length * 0.55 + (HARD_RE.test(t) ? 30 : 0))));
};
// Resolve which band a complexity score lands in (nearest by range, else the top).
const resolveBandClient = (cx: number, bands: Band[]): Band | null => {
  const inRange = [...bands].sort((a, b) => a.min - b.min).find((b) => cx >= b.min && cx <= b.max);
  if (inRange) return inRange;
  return bands.length ? [...bands].sort((a, b) => b.max - a.max)[0] : null;
};

// Tab 2 - the Unity Gateway box. Drag a predefined question (or type your
// own) into the gateway; pick the 2-3 candidate models and tick the governance
// features; route it and see which model answered and what it cost ($$$).

const usd = (n: number) => formatMoney(n);

// Prompt-complexity buckets (from the gateway's 0-100 score), shared visual
// language with the Compare tab.
type Complexity = 'small' | 'medium' | 'complex';
const CX_META: Record<Complexity, { label: string; hex: string; blurb: string }> = {
  small: { label: 'Small', hex: '#93D3AB', blurb: 'Trivial lookups and short tasks - routes to a small open-weight model.' },
  medium: { label: 'Medium', hex: '#E3B876', blurb: 'Multi-step reasoning and analysis - routes to a large open-weight model.' },
  complex: { label: 'Complex', hex: '#B487D0', blurb: 'Open-ended architecture and strategy - routes to a frontier model.' },
};
const complexityOf = (cx: number): Complexity => (cx < 35 ? 'small' : cx < 75 ? 'medium' : 'complex');

type Persona = 'user' | 'admin';

// In the User persona the model choice is fixed (and grayed out) to a
// representative spread - a frontier flagship, a large-OSS, and a small-OSS - so
// an end user can't reconfigure routing. Only Admin can change models.
const USER_DEFAULT_IDS = ['databricks-claude-opus-5', 'databricks-qwen3-next-80b-a3b-instruct', 'databricks-gpt-oss-20b'];

interface Question { id: string; t: string; cx: number }
interface Feature { id: string; label: string; feature: string }
interface Chosen { id: string; short: string; tier: Tier }
interface BudgetEffect {
  applied: boolean; consumedPct: number; capUsd: number | null;
  frontierBarPct: number | null; downgraded: boolean; note: string; blocked?: boolean;
}
interface Result {
  chosen: Chosen; costUsd: number; latencyMs: number; judgeScore: number; complexity: number;
  bandLabel?: string | null; matchedRule?: string | null;
  inputTokens?: number; outputTokens?: number;
  requiredTier: Tier; baseRequiredTier?: Tier; reason: string; baseline: { short: string; costUsd: number };
  savingsUsd: number; savingsPct: number; appliedFeatures: string[]; budget?: BudgetEffect | null;
  routingOverheadUsd?: number; routerModel?: string; allInCostUsd?: number; cheaperThanBaselineX?: number | null;
  blocked?: boolean;
  answer?: string; judgeReason?: string;
  trace: { kind: string; text: string }[];
}

// A budget threshold's action: cap the ceiling at a tier, or block new requests.
type BudgetAction = Tier | 'block';

// A free-text routing rule: comma-separated keywords → a tier.
interface CriteriaRule { id: string; keywords: string; tier: Tier }

const TIER_DOT: Record<Tier, string> = { frontier: 'bg-plum', 'large-oss': 'bg-amber', 'small-oss': 'bg-moss' };
// Uppercase label on the dark stage (the light .eyebrow util is too dark here).
const EB = 'font-body text-[11.5px] font-bold uppercase tracking-[.12em] text-white/60';
// Bold, coloured section header (box titles), matching the Compare tab.
const SECTION = 'font-display text-[13px] font-bold uppercase tracking-[.15em] text-[#7FB6F2]';

export function Pipeline() {
  const cfg = useConfig();
  const { logRun, setLastRouting } = useSession();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [features, setFeatures] = useState<Feature[]>([]);
  const [custom, setCustom] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  const [inspect, setInspect] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [persona, setPersona] = useState<Persona>('admin'); // admin sees governance + budget + policy editor; user sees a simple ask
  const [cxInfo, setCxInfo] = useState(false); // complexity-legend popover

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
  // Manual complexity override: null = use the classifier; a number pins it.
  const [manualCx, setManualCx] = useState<number | null>(null);

  // Setting a fresh question (pill / example library / clear) drops any manual
  // complexity pin so the new prompt is re-scored by the classifier.
  const setPrompt = (q: string) => { setCustom(q); setManualCx(null); setResult(null); };
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

  // Default model picks: opus-5 for frontier (the flagship), cheapest for the two
  // OSS tiers - a visible routing spread.
  useEffect(() => {
    if (!cfg || selected.length) return;
    // Defaults: frontier → opus-5; large-OSS → glm-5.3; small-OSS → cheapest in the
    // tier (by representative per-query cost, 800 in / 400 out).
    const perQ = (m: ModelDef) => 800 * m.price_in_per_1m + 400 * m.price_out_per_1m;
    const pick = (t: Tier) => cfg.models.filter((m) => m.tier === t).sort((a, b) => perQ(a) - perQ(b))[0]?.id;
    const pin = (id: string, t: Tier) => cfg.models.find((m) => m.id === id)?.id ?? pick(t);
    setSelected([pin('databricks-claude-opus-5', 'frontier'), pin('databricks-glm-5-3', 'large-oss'), pick('small-oss')].filter(Boolean) as string[]);
  }, [cfg, selected.length]);

  const models = cfg?.models ?? [];
  const byId = useMemo(() => new Map(models.map((m) => [m.id, m])), [models]);
  // Curated questions carry a hand-tuned complexity (drives the pill colour). Use
  // it as the authoritative score when that exact question is the prompt, so the
  // pill colour, the "would route to" preview, and the actual route all agree -
  // the crude length heuristic over-scores short-but-simple asks otherwise.
  const knownCx = useMemo(() => new Map(questions.map((q) => [q.t, q.cx])), [questions]);
  const effectiveCxFor = (text: string) => knownCx.get(text.trim()) ?? classifyClient(text);

  // User persona locks the model set to the fixed defaults (Admin edits freely).
  useEffect(() => {
    if (persona !== 'user' || !models.length) return;
    const ids = USER_DEFAULT_IDS.filter((id) => byId.has(id));
    if (ids.length) setSelected(ids);
  }, [persona, models.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // Show just 3 impactful example questions - one at each end of the complexity
  // range and one in the middle - so the routing spread (small → large → frontier)
  // is obvious without a wall of chips.
  const shownQuestions = useMemo(() => {
    const sorted = [...questions].sort((a, b) => a.cx - b.cx);
    if (sorted.length <= 3) return sorted;
    const picks = [0, 0.5, 1].map((f) => sorted[Math.round(f * (sorted.length - 1))]);
    return Array.from(new Set(picks));
  }, [questions]);

  // One model per tier - the dropdowns pick which model represents each tier.
  const setTierModel = (t: Tier, id: string) =>
    setSelected((prev) => {
      const others = prev.filter((x) => byId.get(x)?.tier !== t);
      return id ? [...others, id] : others;
    });
  const toggleFeature = (id: string) =>
    setEnabled((e) => { const n = new Set(e); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const onDragEnd = (e: DragEndEvent) => {
    if (e.over?.id !== 'gateway-question' || !String(e.active.id).startsWith('q:')) return;
    const q = questions.find((x) => `q:${x.id}` === String(e.active.id));
    if (q) setPrompt(q.t);
  };

  const route = async () => {
    const text = custom.trim();
    if (!text || selected.length < 1 || busy) return;
    setBusy(true);
    setResult(null);
    try {
      // Governance TICKS are the switches: a feature only affects the route when
      // it's enabled. Budget applies only if the "Budgets" tick is on; the
      // customer's routing policy (bands / criteria) applies only if the "Routing
      // policy" tick is on - otherwise the gateway falls back to the platform's
      // default complexity thresholds.
      const budgetActive = persona === 'admin' && enabled.has('budget');
      const policyActive = enabled.has('routing-policy');
      const budget = budgetActive
        ? { applied: true, consumedPct, capUsd: capUsd ?? undefined, downgradeAtPct: downgradeAt, openOnlyAtPct: openOnlyAt, downgradeAction, openOnlyAction }
        : null;
      const bandPayload = policyActive ? bands.map((b) => ({ label: b.label, min: b.min, max: b.max, tier: b.tier })) : [];
      const policy = policyActive ? { mode: policyMode, rules: policyRules.map((r) => ({ keywords: r.keywords, tier: r.tier })) } : null;
      // Complexity: a manual pin wins; else the curated score for a known question;
      // else the length heuristic. Sent explicitly so the backend routes on the
      // SAME score the UI previewed (no silent re-classification divergence).
      const cx = manualCx ?? effectiveCxFor(text);
      const body = { models: selected, features: [...enabled], prompt: text, budget, bands: bandPayload, policy, complexity: cx };
      const r: Result = await fetch('/api/gateway/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }).then((res) => res.json());
      setResult(r);
      if (r.costUsd != null && r.chosen) {
        logRun({
          source: 'gateway',
          modelShort: r.chosen.short,
          tier: r.chosen.tier,
          costUsd: r.costUsd,
          baselineUsd: r.baseline.costUsd,
          inputTokens: r.inputTokens ?? 0,
          outputTokens: r.outputTokens ?? 0,
          latencyMs: r.latencyMs,
          optimized: false,
          promptSnippet: text,
        });
      }
      // Feed the Architecture tab: this routed model becomes the "live" request.
      if (r.chosen) setLastRouting({ model: r.chosen.short, tier: r.chosen.tier, costUsd: r.costUsd, complexity: r.complexity, source: 'gateway' });
    } finally {
      setBusy(false);
    }
  };

  const activeQuestionText = custom;
  // Live preview of where the current prompt would route under the user's policy.
  // Effective complexity = the manual pin if set, else the classifier's score.
  const classifierCx = useMemo(() => effectiveCxFor(custom), [custom, knownCx]); // eslint-disable-line react-hooks/exhaustive-deps
  const effectiveCx = manualCx ?? classifierCx;
  // Preview respects the "Routing policy" tick: when it's off, the gateway uses
  // the platform default thresholds, so preview those (not the custom bands).
  const routingPolicyOn = enabled.has('routing-policy');
  const previewBand = useMemo<Band | null>(() => {
    if (routingPolicyOn) return resolveBandClient(effectiveCx, bands);
    const th = cfg?.policy.thresholds;
    if (!th) return null;
    const tier: Tier = effectiveCx < th.small_max ? 'small-oss' : effectiveCx < th.large_max ? 'large-oss' : 'frontier';
    const label = tier === 'small-oss' ? 'Simple' : tier === 'large-oss' ? 'Standard' : 'Complex';
    return { id: 'default', label, min: 0, max: 100, tier };
  }, [effectiveCx, bands, routingPolicyOn, cfg]);
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
                  ? "Type or drop in a question, pick the models you'd let it choose from, and tick the governance features - each has a Configure panel (rate limits, guardrails, budgets routing, complexity routing, inference tables). The gateway routes to the cheapest model that clears the bar; turn on a budget and that bar tightens as spend rises."
                  : 'Ask a question and pick which models the gateway may choose from. It routes to the cheapest model that still clears the quality bar, automatically.'}
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
              {/* Question slot - always editable; previews the score + band live */}
              <QuestionSlot custom={custom} onCustom={(v) => { setCustom(v); setResult(null); }} onClear={() => setPrompt('')} cx={effectiveCx} autoCx={classifierCx} band={previewBand} manual={manualCx} onManual={setManualCx} locked={persona === 'user'} />

              {/* Models - one column per tier (side by side), each a labelled dropdown */}
              <div>
                <div className="mb-2.5 flex items-center gap-2">
                  <span className={EB}>Models to route across</span>
                  <span className="num text-[11.5px] text-white/50">{selected.length} selected · one per tier</span>
                  {persona === 'user' && <span className="rounded-pill bg-white/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[.06em] text-white/45">🔒 set by admin</span>}
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
                          <select
                            value={current}
                            onChange={(e) => setTierModel(t, e.target.value)}
                            disabled={persona === 'user'}
                            aria-label={`${TIER_LABEL[t]} model`}
                            className={`num w-full appearance-none rounded-lg bg-black/30 px-3.5 py-2.5 pr-9 text-[13px] font-semibold text-white ring-1 ring-white/10 outline-none transition ${persona === 'user' ? 'cursor-not-allowed opacity-45' : 'cursor-pointer hover:bg-black/40'}`}
                          >
                            <option value="" className="text-ink">none</option>
                            {tierModelsList.map((m) => (
                              <option key={m.id} value={m.id} className="text-ink">{m.short}</option>
                            ))}
                          </select>
                          <span className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-[11px] text-white/45">▾</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Governance features - Admin only */}
              {persona === 'admin' && (
              <div>
                <div className={`${EB} mb-2`}>Governance features · tick to apply, <span className="text-[#8FC1F0]">Configure</span> to inspect &amp; edit</div>
                <div className="flex flex-wrap gap-2">
                  {features.map((f) => (
                    <FeatureChip key={f.id} f={f} on={enabled.has(f.id)} onToggle={() => toggleFeature(f.id)} onInspect={() => setInspect((cur) => (cur === f.id ? null : f.id))} inspecting={inspect === f.id} />
                  ))}
                </div>
              </div>
              )}

              <div className="flex flex-wrap gap-2.5">
                <button
                  onClick={route}
                  disabled={busy || !activeQuestionText.trim() || selected.length < 1}
                  className="rounded-pill bg-lava px-[22px] py-2.5 text-[13px] font-semibold text-white shadow-lift transition hover:bg-[#e22e1a] disabled:cursor-not-allowed disabled:opacity-45"
                >
                  {busy ? 'Routing…' : 'Route through the gateway'}
                </button>
                <button
                  onClick={() => { setPrompt(''); setInspect(null); }}
                  disabled={busy}
                  className="rounded-pill bg-white/10 px-[22px] py-2.5 text-[13px] font-medium text-white/80 ring-1 ring-white/10 transition hover:bg-white/15 hover:text-white disabled:cursor-not-allowed disabled:opacity-45"
                >
                  Reset
                </button>
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
              ) : (
                <StageConfigPanel feature={inspectFeature.feature} stageName={inspectFeature.label} />
              )
            )}
          </div>
        </section>

        {/* Box 3 - blocked by budget policy (no model called) */}
        {result && result.blocked && (
          <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[26px] text-white shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4" style={{ animationDelay: '.12s' }}>
            <div className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-lava opacity-[.14] blur-3xl" />
            <div className="relative flex flex-col gap-4">
              <div className={SECTION}>Result</div>
              <div className="flex items-start gap-3 rounded-2xl bg-lava/10 p-5 ring-1 ring-lava/40">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-lava/25 text-[18px]">🛑</span>
                <div>
                  <div className="font-display text-[15px] font-bold text-lava">Blocked by budget policy</div>
                  <p className="mt-1.5 text-[12.5px] leading-[1.6] text-white/75">{result.reason}</p>
                  <div className="num mt-3 flex flex-col gap-1.5 text-[11.5px] leading-[1.7]">
                    {result.trace.map((e, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <span className={e.kind === 'feature' ? 'text-moss' : e.kind === 'route' ? 'text-lava' : 'text-white/45'}>{e.kind === 'feature' ? '✓' : '→'}</span>
                        <span className="text-white/70">{e.text}</span>
                      </div>
                    ))}
                  </div>
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
                  <span>judge {formatScore(result.judgeScore)}/10</span>
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

            {/* The model's actual answer + quality score, once routed. */}
            {result.answer && (
              <div className="rounded-2xl bg-white/[0.04] p-5 ring-1 ring-white/10">
                <div className="mb-2.5 flex flex-wrap items-center gap-2">
                  <h6 className="font-display text-[12px] font-semibold text-white">Response</h6>
                  <span className="num text-[11px] text-white/45">from {result.chosen.short}</span>
                  <span className="num ml-auto rounded-pill bg-[#2272B4]/25 px-2.5 py-1 text-[11px] font-bold text-[#8FC1F0] ring-1 ring-[#2272B4]/40">Quality {formatScore(result.judgeScore)}/10</span>
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

// Always an editable textarea (drop a question in, type, paste, backspace, edit
// freely). Below it, a live preview of the complexity score and the band the
// prompt would land in - the classifier scores it, or pin it yourself.
function QuestionSlot({ custom, onCustom, onClear, cx, autoCx, band, manual, onManual, locked = false }: { custom: string; onCustom: (v: string) => void; onClear: () => void; cx: number; autoCx: number; band: Band | null; manual: number | null; onManual: (n: number | null) => void; locked?: boolean }) {
  const { setNodeRef, isOver } = useDroppable({ id: 'gateway-question' });
  const has = custom.trim().length > 0;
  const tier = band?.tier;
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
      {has && (
        <div className="mt-2.5 border-t border-white/10 pt-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className={EB}>Would route to</span>
            {band && tier && (
              <span className="inline-flex items-center gap-1.5 rounded-pill bg-black/30 px-2.5 py-1 text-[11.5px] font-semibold text-white/85 ring-1 ring-white/10">
                <span className="h-2 w-2 rounded-full" style={{ background: TIER_META[tier].hex }} />
                {band.label} → {TIER_SHORT[tier]}
              </span>
            )}
          </div>
          {/* Complexity control: Simple ↔ Complex. The thumb is the value used
              (yours if set, else the classifier's); the ▲ below marks what the
              classifier thinks. In the User persona it's locked to the classifier's
              score - only Admin can pin it. */}
          <div className="mt-3 flex items-center gap-2.5">
            <span className="text-[10px] font-bold uppercase tracking-[.12em] text-white/45">Simple</span>
            <div className="relative flex-1">
              <input
                type="range" min={0} max={100} value={cx}
                onChange={(e) => { if (!locked) onManual(+e.target.value); }}
                onPointerDown={(e) => e.stopPropagation()}
                disabled={locked}
                aria-label="Set complexity"
                className={`block h-1.5 w-full accent-lava ${locked ? 'cursor-not-allowed opacity-50' : ''}`}
              />
              {!locked && (
                <span
                  className="pointer-events-none absolute top-full mt-0.5 text-[8px] leading-none text-white/55"
                  style={{ left: `${autoCx}%`, transform: 'translateX(-50%)' }}
                  title={`Classifier estimate: ${autoCx}`}
                >
                  ▲
                </span>
              )}
            </div>
            <span className="text-[10px] font-bold uppercase tracking-[.12em] text-white/45">Complex</span>
            <span className="num w-7 text-right text-[12px] font-semibold text-white">{cx}</span>
            {locked ? (
              <span className="rounded-pill bg-white/10 px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-[.08em] text-white/50">🔒 auto</span>
            ) : (
              <>
                <span className={`rounded-pill px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-[.08em] ${manual != null ? 'bg-lava/20 text-lava' : 'bg-white/10 text-white/50'}`}>{manual != null ? 'manual' : 'auto'}</span>
                {manual != null && <button onClick={() => onManual(null)} className="text-[10.5px] text-white/50 transition hover:text-white" aria-label="Back to auto complexity">↺ auto</button>}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Persona radio - User (simple ask) vs Admin (governance + budget).
function PersonaToggle({ persona, onChange }: { persona: Persona; onChange: (p: Persona) => void }) {
  return (
    <div role="radiogroup" aria-label="Persona" className="inline-flex items-center gap-1 rounded-pill bg-white/10 p-1 ring-1 ring-white/10">
      {(['user', 'admin'] as Persona[]).map((p) => (
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
              <span className="font-semibold text-amber">No cap active</span> at {consumedPct}% consumed - routing follows complexity only (a complex prompt still goes to frontier). Raise <b className="text-white/80">Consumed</b> to ≥{minTrigger}% or lower a threshold below {consumedPct}% to engage a cap.
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

function FeatureChip({ f, on, onToggle, onInspect, inspecting }: { f: Feature; on: boolean; onToggle: () => void; onInspect: () => void; inspecting: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-pill py-1.5 pl-2.5 pr-1.5 text-[12.5px] font-semibold transition ${on ? 'bg-moss/20 text-[#93D3AB]' : 'bg-white/10 text-white/55'} ${inspecting ? 'ring-2 ring-[#8FC1F0]/60' : ''}`}>
      <button onClick={onToggle} className="flex items-center gap-1.5" aria-pressed={on}>
        <span className={`grid h-4 w-4 place-items-center rounded-full text-[9px] ${on ? 'bg-moss text-white' : 'border border-white/25'}`}>{on ? '✓' : ''}</span>
        {f.label}
      </button>
      <button
        onClick={onInspect}
        aria-expanded={inspecting}
        title="Configure this feature"
        className={`ml-1 inline-flex items-center gap-1 rounded-pill px-2 py-1 text-[10px] font-bold uppercase tracking-[.05em] transition ${inspecting ? 'bg-[#8FC1F0] text-ink' : 'bg-white/15 text-white/80 hover:bg-white/25 hover:text-white'}`}
      >
        <span className="text-[10px]">⚙</span>{inspecting ? 'Editing ▴' : 'Configure ▾'}
      </button>
    </span>
  );
}
