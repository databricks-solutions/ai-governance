import { useEffect, useState } from 'react';
import { QUESTION_LIBRARY, QUESTION_DOMAINS, QUESTION_TIERS, type QTier } from '../data/questionLibrary';

// A rich modal picker for the v1 question library - domains down the left, the
// selected domain's Simple / Medium / Complex questions as cards on the right.
// Clicking a question hands it back and closes. Tier colour mirrors routing:
// Simple → small OSS (moss), Medium → large OSS (amber), Complex → frontier (plum).

const TIER_ACCENT: Record<QTier, { chip: string; bar: string; note: string }> = {
  Simple: { chip: 'bg-moss-wash text-moss', bar: 'bg-moss', note: 'routes to small OSS' },
  Medium: { chip: 'bg-amber-wash text-amber', bar: 'bg-amber', note: 'routes to large OSS' },
  Complex: { chip: 'bg-plum-wash text-plum', bar: 'bg-plum', note: 'routes to frontier' },
};

export function QuestionLibrary({ onPick, onClose }: { onPick: (q: string) => void; onClose: () => void }) {
  const [domain, setDomain] = useState(QUESTION_DOMAINS[0]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const q = QUESTION_LIBRARY[domain];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/25 p-6"
      onClick={onClose}
    >
      <div
        className="flex max-h-[82vh] w-full max-w-[1000px] overflow-hidden rounded-xl bg-paper shadow-lift-hi"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Domains */}
        <div className="w-[220px] shrink-0 border-r border-line bg-card p-4">
          <div className="eyebrow mb-3">Example questions</div>
          <div className="flex flex-col gap-1">
            {QUESTION_DOMAINS.map((d) => (
              <button
                key={d}
                onClick={() => setDomain(d)}
                aria-current={d === domain}
                className="rounded-lg px-3 py-2.5 text-left text-[13px] text-ink-2 transition hover:bg-paper aria-[current=true]:bg-ink aria-[current=true]:text-white"
              >
                {d}
              </button>
            ))}
          </div>
        </div>

        {/* Questions for the selected domain */}
        <div className="flex-1 overflow-y-auto p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="font-display text-[16px] font-semibold tracking-[-.015em]">{domain}</h3>
            <button onClick={onClose} aria-label="Close" className="text-[18px] leading-none text-ink-3 hover:text-ink">×</button>
          </div>

          <div className="flex flex-col gap-5">
            {QUESTION_TIERS.map((tier) => (
              <div key={tier}>
                <div className="mb-2 flex items-center gap-2">
                  <span className={`rounded-pill px-2.5 py-1 font-body text-[9.5px] font-medium uppercase tracking-[.08em] ${TIER_ACCENT[tier].chip}`}>{tier}</span>
                  <span className="text-[10.5px] text-ink-3">{TIER_ACCENT[tier].note}</span>
                </div>
                <div className="flex flex-col gap-2">
                  {q[tier].map((text, i) => (
                    <button
                      key={i}
                      onClick={() => {
                        onPick(text);
                        onClose();
                      }}
                      className="group flex gap-3 rounded-lg bg-card px-4 py-3 text-left shadow-lift transition hover:-translate-y-[1px] hover:shadow-lift-hi"
                    >
                      <span className={`mt-1 h-full w-[3px] shrink-0 rounded-[2px] ${TIER_ACCENT[tier].bar}`} />
                      <span className="text-[12.5px] leading-[1.55] text-ink-2 group-hover:text-ink">{text}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
