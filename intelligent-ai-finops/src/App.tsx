import { useEffect } from 'react';
import { useSession, type TabId } from './store/session';
import { useConfig } from './api/useConfig';
import { Compare } from './tabs/Compare';
import { Pipeline } from './tabs/Pipeline';
import { Cost } from './tabs/Cost';
import { WhyDatabricks } from './tabs/WhyDatabricks';
import { Architecture } from './tabs/Architecture';
import { Styleguide } from './tabs/Styleguide';

// Tab order encodes the narrative (§1); labels are plain-language (no jargon).
const TABS: { id: TabId; index: string; label: string }[] = [
  { id: 'compare', index: '1', label: 'Compare models' },
  { id: 'pipeline', index: '2', label: 'Context routing' },
  { id: 'cost', index: '3', label: 'Cost & savings' },
  { id: 'why', index: '4', label: 'Why Databricks' },
  { id: 'arch', index: '5', label: 'How it works' },
];

export function App() {
  const { activeTab, setTab, seeded, seedSample } = useSession();
  const cfg = useConfig();

  // Seed a realistic demo session on first load so the Cost & savings tab isn't
  // empty. Costs are computed from the live rate card inside the store. (The
  // header no longer shows a running tally - the savings story lives on the
  // Cost & savings tab, where the traffic-scaled projection is the usable view.)
  useEffect(() => {
    if (cfg && cfg.models.length && !seeded) seedSample(cfg.models);
  }, [cfg, seeded, seedSample]);

  // Keyboard: 1–5 switch tabs (§9).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      const hit = TABS.find((t) => t.index === e.key);
      if (hit) setTab(hit.id);
      if (e.key === '`') setTab('styleguide'); // dev styleguide
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [setTab]);

  return (
    <div className="h-screen overflow-y-auto bg-paper">
      {/* Masthead - centered hero; scrolls away with the page (not pinned). */}
      <header className="bg-paper px-6 pb-5 pt-8 text-center">
        <div className="mx-auto max-w-[880px]">
          <h1 className="font-display text-[44px] font-bold leading-[1.04] tracking-[-.035em] text-ink max-[760px]:text-[30px]">
            Frontier intelligence, <span className="bg-gradient-to-r from-lava to-[#FF8A3D] bg-clip-text text-transparent">natively in your Lakehouse</span>
          </h1>
          <p className="mx-auto mt-4 max-w-[64ch] font-body text-[18px] font-normal leading-[1.5] text-ink-2 max-[760px]:text-[15px]">
            A routing layer sends every query to the <span className="font-semibold text-ink">cheapest model that clears your quality bar</span>,
            built entirely from <span className="font-semibold text-ink">what's already on Databricks</span>.
          </p>
        </div>
      </header>

      {/* Tabs - sticky so navigation stays reachable once the masthead scrolls off */}
      <div className="sticky top-0 z-20 flex items-center border-b border-line bg-paper/95 px-[26px] pb-[12px] pt-3 backdrop-blur-sm">
        <div className="flex flex-1 justify-center gap-2.5 overflow-x-auto py-0.5" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={activeTab === t.id}
              onClick={() => setTab(t.id)}
              className="group flex items-center gap-2.5 whitespace-nowrap rounded-pill bg-card px-[28px] py-[14px] text-[15px] font-semibold text-ink-2 shadow-lift transition-all duration-[200ms] hover:-translate-y-px hover:text-ink hover:shadow-lift-hi aria-selected:bg-gradient-to-r aria-selected:from-lava aria-selected:to-[#FF8A3D] aria-selected:text-white aria-selected:shadow-lift-hi aria-selected:hover:text-white"
            >
              <span className={`h-2 w-2 rounded-full transition ${activeTab === t.id ? 'bg-white' : 'bg-lava/60 group-hover:bg-lava'}`} />
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Stage - full width now that the rail is gone. Tabs stay MOUNTED (hidden
          when inactive) so prompts, model picks, results, and slider positions
          persist as you move between tabs and come back. */}
      <main className="px-[26px] pb-16 pt-4" role="tabpanel">
        <div className="mx-auto max-w-[1180px]">
          <div className={activeTab === 'compare' ? '' : 'hidden'}><Compare /></div>
          <div className={activeTab === 'pipeline' ? '' : 'hidden'}><Pipeline /></div>
          <div className={activeTab === 'cost' ? '' : 'hidden'}><Cost /></div>
          <div className={activeTab === 'why' ? '' : 'hidden'}><WhyDatabricks /></div>
          <div className={activeTab === 'arch' ? '' : 'hidden'}><Architecture /></div>
          {activeTab === 'styleguide' && <Styleguide />}
        </div>
      </main>
    </div>
  );
}
