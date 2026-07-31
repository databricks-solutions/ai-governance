import { cn } from "@/lib/cn";
import type { ReactNode, ButtonHTMLAttributes } from "react";

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "outline" }) {
  const base =
    "inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const variants = {
    primary: "bg-navy text-white hover:bg-navy-700",
    outline: "border border-navy/20 text-navy hover:border-navy/50",
    ghost: "text-navy hover:bg-navy/5",
  };
  return <button className={cn(base, variants[variant], className)} {...props} />;
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("rounded-2xl border border-navy/10 bg-white p-6", className)}>{children}</div>
  );
}

export function Pill({ children, tone = "navy" }: { children: ReactNode; tone?: "navy" | "lava" | "muted" }) {
  const tones = {
    navy: "bg-navy/5 text-navy",
    lava: "bg-lava/10 text-lava",
    muted: "bg-oat-200 text-muted",
  };
  return (
    <span className={cn("inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold", tones[tone])}>
      {children}
    </span>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted">
      <span className="h-px w-6 bg-lava" />
      {children}
    </div>
  );
}

export function StatusDot({ status }: { status: string }) {
  const map: Record<string, string> = { submitted: "bg-navy", draft: "bg-lava", agent: "bg-lava" };
  return <span className={cn("inline-block h-2 w-2 rounded-full", map[status] ?? "bg-navy-300")} />;
}
