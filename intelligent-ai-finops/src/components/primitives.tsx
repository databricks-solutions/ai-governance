import React from 'react';
import type { Tier } from '../api/types';

// The hand-built primitives (BUILD-SPEC §5). No component library - the visual
// identity is the deliverable. Every card is white, radius --r-xl, separated by
// shadow not borders. Lava is only ever cost or a routing decision.

function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(' ');
}

// ---- Card ---------------------------------------------------------------
export function Card({
  className,
  hover = false,
  children,
  ...rest
}: React.HTMLAttributes<HTMLDivElement> & { hover?: boolean }) {
  return (
    <div
      className={cx(
        'bg-card rounded-xl shadow-lift',
        hover && 'transition-[box-shadow,transform] duration-[280ms] ease-soft hover:shadow-lift-hi hover:-translate-y-[2px]',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

// ---- Pill ---------------------------------------------------------------
type PillVariant = 'tier-frontier' | 'tier-large' | 'tier-small' | 'neutral' | 'accent';

const PILL_VARIANT: Record<PillVariant, string> = {
  'tier-frontier': 'bg-plum-wash text-plum',
  'tier-large': 'bg-amber-wash text-amber',
  'tier-small': 'bg-moss-wash text-moss',
  neutral: 'bg-paper text-ink-2',
  accent: 'bg-lava-wash text-lava',
};

export function Pill({
  variant = 'neutral',
  dot = false,
  className,
  children,
}: {
  variant?: PillVariant;
  dot?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  const dotColor =
    variant === 'tier-frontier'
      ? 'bg-plum'
      : variant === 'tier-large'
        ? 'bg-amber'
        : variant === 'tier-small'
          ? 'bg-moss'
          : 'bg-ink-3';
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 font-body text-[10px] font-medium uppercase tracking-[.06em]',
        PILL_VARIANT[variant],
        className,
      )}
    >
      {dot && <span className={cx('h-1.5 w-1.5 shrink-0 rounded-full', dotColor)} />}
      {children}
    </span>
  );
}

export function tierPillVariant(tier: Tier): PillVariant {
  return tier === 'frontier' ? 'tier-frontier' : tier === 'large-oss' ? 'tier-large' : 'tier-small';
}

// ---- DarkButton - the ONLY primary action style -------------------------
export function DarkButton({
  className,
  children,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cx(
        'rounded-pill bg-ink px-[18px] py-2.5 text-[13px] font-medium text-white shadow-lift',
        'transition duration-[180ms] hover:bg-[#3A322C] disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-ink',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

// ---- GhostButton - white card bg, lift, no border -----------------------
export function GhostButton({
  className,
  children,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cx(
        'rounded-pill bg-card px-[18px] py-2.5 text-[13px] font-medium text-ink-2 shadow-lift',
        'transition duration-[180ms] hover:text-ink hover:shadow-lift-hi disabled:cursor-not-allowed disabled:opacity-45',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

// ---- Figure - mono number with a small uppercase label above ------------
export function Figure({
  label,
  value,
  size = 'md',
  tone = 'ink',
  className,
}: {
  label: string;
  value: React.ReactNode;
  size?: 'sm' | 'md' | 'lg';
  tone?: 'ink' | 'ink-2' | 'lava';
  className?: string;
}) {
  const sizeCls = size === 'lg' ? 'text-[26px]' : size === 'sm' ? 'text-[14px]' : 'text-[18px]';
  const toneCls = tone === 'lava' ? 'text-lava' : tone === 'ink-2' ? 'text-ink-2' : 'text-ink';
  // Larger figures get tighter tracking per §3.
  const track = size === 'lg' ? 'tracking-[-.045em]' : 'tracking-[-.03em]';
  return (
    <div className={className}>
      <div className="eyebrow">{label}</div>
      <div className={cx('num mt-1.5 font-medium leading-none', sizeCls, toneCls, track)}>{value}</div>
    </div>
  );
}

// ---- SearchField - paper-filled 999px row + inline dark button ----------
export function SearchField({
  value,
  onChange,
  onSubmit,
  placeholder,
  buttonLabel = 'Run',
  disabled = false,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  placeholder?: string;
  buttonLabel?: string;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 rounded-pill bg-paper py-1.5 pl-5 pr-1.5">
      <input
        className="flex-1 border-none bg-transparent py-3 text-[14.5px] outline-none placeholder:text-ink-3"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !disabled) onSubmit();
        }}
      />
      <DarkButton className="shrink-0 px-[26px] py-3" onClick={onSubmit} disabled={disabled}>
        {buttonLabel}
      </DarkButton>
    </div>
  );
}
