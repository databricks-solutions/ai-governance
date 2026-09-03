import { Card, Pill, DarkButton, GhostButton, Figure, SearchField } from '../components/primitives';
import { useState } from 'react';

// Static styleguide route (BUILD-SPEC §8.1) - build and visually verify the
// primitives against the prototype BEFORE touching any tab.
export function Styleguide() {
  const [q, setQ] = useState('');
  return (
    <div className="mx-auto flex max-w-[900px] flex-col gap-7 py-2">
      <section>
        <h2 className="font-display text-[17px] font-semibold tracking-[-.015em]">Primitives</h2>
        <p className="mt-1.5 max-w-[80ch] text-[13px] text-ink-2">
          The seven hand-built primitives. Lava appears only on cost. Primary actions are the ink pill.
        </p>
      </section>

      {/* Cards */}
      <div>
        <div className="eyebrow mb-3">Card</div>
        <div className="grid grid-cols-3 gap-[18px]">
          <Card className="p-5">
            <div className="font-display text-[13px] font-semibold">Static card</div>
            <p className="mt-2 text-[12.5px] text-ink-2">White, radius 22px, soft lift. Shadow separates, not borders.</p>
          </Card>
          <Card hover className="p-5">
            <div className="font-display text-[13px] font-semibold">Hover card</div>
            <p className="mt-2 text-[12.5px] text-ink-2">Lifts −2px to lift-hi over 280ms on hover.</p>
          </Card>
          <Card className="bg-card-2 p-5">
            <div className="font-display text-[13px] font-semibold">Inset (card-2)</div>
            <p className="mt-2 text-[12.5px] text-ink-2">Quote blocks and insets inside cards.</p>
          </Card>
        </div>
      </div>

      {/* Pills */}
      <div>
        <div className="eyebrow mb-3">Pill</div>
        <Card className="flex flex-wrap items-center gap-2.5 p-5">
          <Pill variant="tier-frontier" dot>frontier</Pill>
          <Pill variant="tier-large" dot>large OSS</Pill>
          <Pill variant="tier-small" dot>small OSS</Pill>
          <Pill variant="neutral">neutral</Pill>
          <Pill variant="accent">best value</Pill>
        </Card>
      </div>

      {/* Buttons */}
      <div>
        <div className="eyebrow mb-3">Buttons</div>
        <Card className="flex flex-wrap items-center gap-3 p-5">
          <DarkButton>Run comparison</DarkButton>
          <GhostButton>Load reference pipeline</GhostButton>
          <DarkButton disabled>Disabled</DarkButton>
        </Card>
      </div>

      {/* Figures */}
      <div>
        <div className="eyebrow mb-3">Figure</div>
        <Card className="flex flex-wrap items-end gap-10 p-5">
          <Figure label="Spent" value="$0.0142" tone="lava" size="lg" />
          <Figure label="Latency" value="1.24s" size="md" />
          <Figure label="Judge" value="8.6" size="md" tone="ink-2" />
          <Figure label="Calls" value="3" size="sm" />
        </Card>
      </div>

      {/* SearchField */}
      <div>
        <div className="eyebrow mb-3">SearchField</div>
        <Card className="p-[18px]">
          <SearchField value={q} onChange={setQ} onSubmit={() => {}} placeholder="Ask anything…" buttonLabel="Run comparison" />
        </Card>
      </div>
    </div>
  );
}
