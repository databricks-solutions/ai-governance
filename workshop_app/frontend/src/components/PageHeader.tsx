import type { ReactNode } from "react";
import { Eyebrow } from "@/components/ui";

export default function PageHeader({
  part,
  title,
  lead,
  children,
}: {
  part: string;
  title: string;
  lead?: string;
  children?: ReactNode;
}) {
  return (
    <header className="border-b border-navy/10 bg-oat px-8 pb-10 pt-14 lg:px-14">
      <div className="mx-auto max-w-4xl">
        <Eyebrow>Part {part}</Eyebrow>
        <h1 className="text-4xl font-bold text-navy lg:text-5xl">{title}</h1>
        {lead && <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted">{lead}</p>}
        {children}
      </div>
    </header>
  );
}

export function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1.5 font-semibold text-navy underline decoration-lava decoration-2 underline-offset-4 hover:text-lava"
    >
      {children}
    </a>
  );
}
