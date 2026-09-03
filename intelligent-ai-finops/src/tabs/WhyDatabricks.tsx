import type { ReactNode } from 'react';

// Tab 4 - Why Databricks. Ported from the existing app's benefit-tile design
// (hero + 8 tiles), restyled into v2's warm-paper system. The sharpest point
// leads: you define the routing policy, not a vendor.

// Minimal line-icons (currentColor), neutral ink - no tier colour, no lava
// (which is reserved for cost). The feature tile gets an ink ring instead.
const Icon = ({ d }: { d: string }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]">
    {d.split('|').map((p, i) => <path key={i} d={p} />)}
  </svg>
);
const PATHS = {
  sliders: 'M4 21v-7|M4 10V3|M12 21v-9|M12 8V3|M20 21v-5|M20 12V3|M1 14h6|M9 8h6|M17 16h6',
  layers: 'M12 2 2 7l10 5 10-5-10-5|M2 17l10 5 10-5|M2 12l10 5 10-5',
  shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
  lock: 'M5 11h14v10H5z|M8 11V7a4 4 0 0 1 8 0v4',
  dollar: 'M12 1v22|M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6',
  unlock: 'M5 11h14v10H5z|M8 11V7a4 4 0 0 1 7.9-1',
  loop: 'M17 2l4 4-4 4|M3 11V9a4 4 0 0 1 4-4h14|M7 22l-4-4 4-4|M21 13v2a4 4 0 0 1-4 4H3',
  budget: 'M3 3v18h18|M7 15l4-4 4 3 5-6',
};

interface Tile {
  icon: keyof typeof PATHS;
  flag?: string;
  title: string;
  body: ReactNode;
  feature?: boolean;
}

const TILES: Tile[] = [
  {
    icon: 'sliders',
    flag: 'The key difference',
    title: 'You define the routing policy - not a vendor',
    body: (
      <>Managed "auto" routers hide their logic and optimize for the vendor's economics. Here the policy lives in <b>your</b> app: route by complexity, cost, team budget, data sensitivity, or latency SLA - any rule your organization runs on. Databricks gives you the primitives and the choice.</>
    ),
    feature: true,
  },
  { icon: 'layers', title: 'One endpoint for every model', body: <>Frontier models and open-source models (Qwen, Llama, GPT-OSS) are served through a single, consistent Model Serving interface. Adding, swapping, or A/B-testing a model is a config change - your application code never changes.</> },
  { icon: 'shield', title: 'Governance & security built in', body: <>Every call goes through the Unity Gateway: Unity Catalog access control, per-user and per-group rate limits, and dollar budgets - one place to manage and audit all AI spend.</> },
  { icon: 'lock', title: 'One credential, not a drawer of vendor keys', body: <>Every model is reached through the same governed interface, so you manage a single access path under Unity Catalog instead of provisioning, rotating, and securing a separate API key per external vendor.</> },
  { icon: 'dollar', title: 'Real cost attribution, per team & model', body: <>Token usage, latency and cost are logged to governed system tables (<code className="num text-[11px] text-white/90">system.ai_gateway.usage</code>, <code className="num text-[11px] text-white/90">system.serving.*</code>), so savings are measurable and spend is attributable per team - not estimated from vendor invoices.</> },
  { icon: 'unlock', title: 'No lock-in', body: <>Open-source models mean no dependency on a single vendor's pricing or availability. Route the easy majority of traffic to open models you control, and reserve frontier models for the requests that truly need them.</> },
  { icon: 'loop', title: 'A continuous improvement loop', body: <>Because every routing decision and outcome is logged in one place, you can measure quality vs. cost over time and tune the policy on <b>your</b> own data - proving and improving savings continuously.</> },
  { icon: 'budget', title: 'Spend controls that actually enforce', body: <>Unity Gateway budgets are evaluated in <b>near-real-time</b> and scoped to a team - so you can throttle, downgrade, or cap spend the moment a budget is crossed, not 6–24 hours later.</> },
];

// Reddish (lava) side tint shared by every box - a soft left glow + accent bar.
function SideGlow() {
  return (
    <>
      <div className="pointer-events-none absolute -left-16 top-1/2 h-44 w-44 -translate-y-1/2 rounded-full bg-lava opacity-[.13] blur-3xl" />
      <div className="pointer-events-none absolute inset-y-0 left-0 w-[3px] bg-gradient-to-b from-lava to-[#FF8A3D]" />
    </>
  );
}

export function WhyDatabricks() {
  return (
    <div className="flex flex-col gap-[18px] text-white">
      {/* Hero - its own black box */}
      <section className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[26px] pl-8 shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4 max-[720px]:pl-5">
        <SideGlow />
        <div className="relative">
          <div className="mb-2 font-body text-[11px] font-semibold uppercase tracking-[.22em] text-lava">Why Databricks</div>
          <h2 className="max-w-[46ch] font-display text-[clamp(22px,2.8vw,32px)] font-bold leading-[1.1] tracking-[-.025em]">
            Your models, your routing rules, your data - on one governed platform
          </h2>
          <p className="mt-3 max-w-[86ch] text-[14px] leading-[1.6] text-white/65">
            Routing every query to a frontier model is the expensive default. Databricks lets you
            right-size each request across frontier and open-source models behind a single endpoint - 
            and, crucially, lets <b className="font-semibold text-white">you</b> decide how routing works instead of accepting a vendor's
            black-box logic.
          </p>
        </div>
      </section>

      {/* Tiles - each its own separate black box with the reddish side tint */}
      <div className="grid grid-cols-2 gap-[18px] max-[1080px]:grid-cols-1">
        {TILES.map((t, i) => (
          <section
            key={t.title}
            style={{ animationDelay: `${i * 60}ms` }}
            className={`relative flex animate-[fadeUp_.45s_ease_both] flex-col overflow-hidden rounded-2xl bg-ink p-5 pl-6 shadow-lift-3d-hi ring-1 ring-white/10 transition-all duration-[280ms] hover:-translate-y-[3px] hover:ring-lava/40 ${t.feature ? 'md:col-span-2' : ''}`}
          >
            <SideGlow />
            {t.flag && (
              <span className="absolute right-4 top-4 rounded-pill bg-gradient-to-r from-lava to-[#FF8A3D] px-2.5 py-1 font-body text-[9px] font-bold uppercase tracking-[.09em] text-white shadow-lift">
                {t.flag}
              </span>
            )}
            <div className="relative mb-3 grid h-9 w-9 place-items-center rounded-full bg-lava/15 text-lava">
              <Icon d={PATHS[t.icon]} />
            </div>
            <h3 className="relative font-display text-[13.5px] font-semibold tracking-[-.01em] text-white">{t.title}</h3>
            <p className="relative mt-2 text-[12.5px] leading-[1.6] text-white/65">{t.body}</p>
          </section>
        ))}
      </div>

      <p className="num px-1 text-[10.5px] text-ink-3">
        Dollar figures use the official Databricks FMAPI DBU rate card × the workspace $/DBU rate
        (see config). See the two routing tabs for the policies running end to end.
      </p>
    </div>
  );
}
