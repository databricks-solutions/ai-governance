import { useEffect, useMemo, useRef } from 'react';
import { useConfig } from '../api/useConfig';
import { useSession } from '../store/session';
import type { Tier } from '../api/types';

// Tab - Architecture ("How it works"). A generic request flow that works for ANY
// caller: multiple client types (a Databricks App, an external AI agent, an
// automation/service, a notebook or job) all hit ONE governed endpoint - the
// Unity Gateway - which applies every policy (auth, rate limits, guardrails,
// routing, budgets, traces, inference tables, usage) and routes to the cheapest
// model tier that clears the bar; the answer returns to the same caller. Packets
// travel the edges so it reads as live; the lane the last request landed on is
// highlighted.

// Which model lane each tier lands on.
const LANDED_NODE: Record<Tier, string> = { 'small-oss': 'small', 'large-oss': 'strong', frontier: 'front' };

const W = 1460, H = 660;

// Gateway box geometry. Wide enough that the longest capability bullet
// ("AI guardrails — PII, content safety, topics") never runs past the box edge.
const GX0 = 380, GX1 = 820, GY0 = 60, GY1 = 600;
const GCX = (GX0 + GX1) / 2, GCY = (GY0 + GY1) / 2;

// The capabilities the Gateway applies to every request (bulleted in the box).
const GATEWAY_FEATURES = [
  'Authentication',
  'Rate limiting — per user · group · SP',
  'AI guardrails — PII, content safety, topics',
  'Complexity routing — score → cheapest tier',
  'Budgets routing — cap the tier as spend rises',
  'Fallbacks & retries',
  'Traces (MLflow)',
  'Inference tables — request & response',
  'Usage & cost metrics',
];

interface Box { id: string; cx: number; cy: number; w: number; h: number; lab: string; sub: string; accent?: string }
interface Edge { x1: number; y1: number; x2: number; y2: number; mode: 'stream' | 'route' }

const ACCENT: Record<string, string> = {
  'small-oss': 'var(--moss)', 'large-oss': 'var(--amber)', frontier: 'var(--plum)', client: 'var(--line-hi)',
};

export function Architecture() {
  const cfg = useConfig();
  const { lastRouting } = useSession();
  const packetRefs = useRef<(SVGCircleElement | null)[]>([]);
  const landedNodeId = lastRouting ? LANDED_NODE[lastRouting.tier] : null;

  const laneLabel = (t: Tier) => {
    const m = cfg?.models.filter((x) => x.tier === t).sort((a, b) => a.price_out_per_1m - b.price_out_per_1m)[0];
    return m?.short ?? t;
  };

  const { clients, models, response, edges, packets } = useMemo(() => {
    const CW = 194, CH = 62;
    const clients: Box[] = [
      { id: 'app', cx: 132, cy: 130, w: CW, h: CH, lab: 'Databricks App', sub: 'in-platform UI', accent: 'client' },
      { id: 'agent', cx: 132, cy: 258, w: CW, h: CH, lab: 'AI agent', sub: 'in-platform or external', accent: 'client' },
      { id: 'svc', cx: 132, cy: 386, w: CW, h: CH, lab: 'Automation / service', sub: 'calls the REST API', accent: 'client' },
      { id: 'nb', cx: 132, cy: 514, w: CW, h: CH, lab: 'Notebook or job', sub: 'batch or interactive', accent: 'client' },
    ];
    const MW = 188, MH = 62;
    const models: Box[] = [
      { id: 'small', cx: 968, cy: 165, w: MW, h: MH, lab: laneLabel('small-oss'), sub: 'simple', accent: 'small-oss' },
      { id: 'strong', cx: 968, cy: 330, w: MW, h: MH, lab: laneLabel('large-oss'), sub: 'medium', accent: 'large-oss' },
      { id: 'front', cx: 968, cy: 495, w: MW, h: MH, lab: laneLabel('frontier'), sub: 'complex', accent: 'frontier' },
    ];
    const response: Box = { id: 'resp', cx: 1300, cy: 330, w: 184, h: 76, lab: 'Response', sub: 'to the same caller' };

    const edges: Edge[] = [];
    // clients → gateway (stream): into the gateway's left edge, near each client's y.
    clients.forEach((c) => edges.push({ x1: c.cx + c.w / 2, y1: c.cy, x2: GX0, y2: Math.max(GY0 + 40, Math.min(GY1 - 40, c.cy)), mode: 'stream' }));
    // gateway → models (route, lava): the routing decision.
    models.forEach((m) => edges.push({ x1: GX1, y1: GCY, x2: m.cx - m.w / 2, y2: m.cy, mode: 'route' }));
    // models → response (stream): converge to the response node.
    models.forEach((m) => edges.push({ x1: m.cx + m.w / 2, y1: m.cy, x2: response.cx - response.w / 2, y2: response.cy, mode: 'stream' }));

    // one or two packets per edge, sparse.
    const packets: { edge: number; off: number; mode: 'stream' | 'route' }[] = [];
    edges.forEach((e, i) => (e.mode === 'stream' ? [0.15] : [0.4]).forEach((off) => packets.push({ edge: i, off, mode: e.mode })));
    return { clients, models, response, edges, packets };
  }, [cfg]); // eslint-disable-line react-hooks/exhaustive-deps

  // Continuous packet animation via rAF.
  useEffect(() => {
    let raf = 0, start = 0;
    const frame = (ts: number) => {
      if (!start) start = ts;
      const t = (ts - start) / 1000;
      packets.forEach((pk, i) => {
        const c = packetRefs.current[i];
        const e = edges[pk.edge];
        if (!c || !e) return;
        const speed = pk.mode === 'stream' ? 0.34 : 0.26;
        const p = (t * speed + pk.off) % 1;
        c.setAttribute('cx', String(e.x1 + (e.x2 - e.x1) * p));
        c.setAttribute('cy', String(e.y1 + (e.y2 - e.y1) * p));
      });
      raf = requestAnimationFrame(frame);
    };
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      packets.forEach((pk, i) => { const c = packetRefs.current[i]; const e = edges[pk.edge]; if (c && e) { c.setAttribute('cx', String(e.x1)); c.setAttribute('cy', String(e.y1)); } });
      return;
    }
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [packets, edges]);

  // Return path: response → back to the invoking client (dashed arc along the bottom).
  const returnPath = `M ${response.cx} ${response.cy + response.h / 2} C ${response.cx} ${H - 12}, 132 ${H - 12}, 132 ${clients[3].cy + clients[3].h / 2}`;

  const renderBox = (n: Box, opts?: { landed?: boolean }) => {
    const left = n.cx - n.w / 2, top = n.cy - n.h / 2;
    const accent = n.accent ? ACCENT[n.accent] : 'rgba(255,255,255,0.18)';
    const landed = !!opts?.landed;
    const label = landed && lastRouting ? lastRouting.model : n.lab;
    return (
      <g key={n.id}>
        <rect x={left} y={top} width={n.w} height={n.h} rx={10} fill={landed ? '#31150F' : '#221D18'} stroke={landed ? 'var(--lava)' : accent} strokeWidth={landed ? 2.8 : 1.8} />
        {n.accent && n.accent !== 'client' && <rect x={left} y={top} width={5.5} height={n.h} rx={2.5} fill={accent} />}
        <text x={left + 15} y={n.cy - 4} fontSize={15} fontWeight={800} fill="#ffffff">{label}</text>
        <text x={left + 15} y={n.cy + 16} fontSize={11.5} fontWeight={600} fill={landed ? 'var(--lava)' : 'rgba(255,255,255,0.6)'}>{landed ? 'routed here' : n.sub}</text>
      </g>
    );
  };

  return (
    <div className="relative animate-[fadeUp_.5s_ease_both] overflow-hidden rounded-[26px] bg-ink p-[26px] pl-8 text-white shadow-lift-3d-hi max-[720px]:rounded-2xl max-[720px]:p-4 max-[720px]:pl-5">
      <div className="pointer-events-none absolute -right-32 -top-24 h-96 w-96 rounded-full bg-lava opacity-[.10] blur-3xl" />
      <div className="pointer-events-none absolute -left-16 top-1/2 h-44 w-44 -translate-y-1/2 rounded-full bg-lava opacity-[.13] blur-3xl" />
      <div className="pointer-events-none absolute inset-y-0 left-0 w-[3px] bg-gradient-to-b from-lava to-[#FF8A3D]" />
      <div className="relative flex flex-col gap-[18px]">
        <div>
          <div className="mb-2 font-body text-[11px] font-semibold uppercase tracking-[.22em] text-lava">Architecture</div>
          <h2 className="font-display text-[clamp(20px,2.4vw,28px)] font-bold tracking-[-.02em] text-white">One governed endpoint for every caller</h2>
          <p className="mt-2 max-w-[90ch] text-[13px] text-white/65">
            Any client - a Databricks App, an AI agent, an automation, a notebook - calls the <span className="font-semibold text-white">same Unity Gateway endpoint</span>.
            The gateway applies every policy (auth, rate limits, guardrails, budgets, tracing, inference tables, usage) and routes each request to the
            cheapest model that clears your quality bar. The answer returns to the caller that invoked it.
          </p>
        </div>

        <div className="overflow-x-auto rounded-xl bg-white/[0.03] p-4 ring-1 ring-white/10">
          <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full min-w-[900px]" role="img" aria-label="Unity Gateway request architecture">
            {/* Platform band around gateway → response (the governed platform; clients can be external) */}
            <rect x={GX0 - 26} y={30} width={W - (GX0 - 26) - 12} height={H - 60} rx={14} fill="var(--lava)" opacity={0.06} stroke="var(--lava)" strokeOpacity={0.3} strokeWidth={1} strokeDasharray="6 6" />
            <text x={GX0 - 10} y={49} fontSize={10} fontWeight={700} fill="var(--lava)" opacity={0.75} style={{ letterSpacing: '.6px' }}>
              DATABRICKS DATA INTELLIGENCE PLATFORM · UNITY CATALOG GOVERNED
            </text>

            {/* Column labels */}
            <text x={132} y={20} textAnchor="middle" fontSize={13.5} fontWeight={800} fill="rgba(255,255,255,0.78)" style={{ letterSpacing: '.6px' }}>CALLERS</text>
            <text x={968} y={92} textAnchor="middle" fontSize={9.5} fontWeight={800} fill="rgba(255,255,255,0.5)" style={{ letterSpacing: '.4px' }}>MODEL SERVING</text>

            {/* Model-serving lane band */}
            <rect x={968 - 188 / 2 - 14} y={110} width={188 + 28} height={470} rx={12} fill="rgba(255,255,255,0.04)" stroke="rgba(255,255,255,0.14)" strokeWidth={1} />

            {/* Return path: response → caller */}
            <path d={returnPath} fill="none" stroke="rgba(255,255,255,0.22)" strokeWidth={1.6} strokeDasharray="2 7" className="motion-safe:animate-[dashflow_.6s_linear_infinite]" markerEnd="url(#arrow)" />
            <text x={(response.cx + 132) / 2} y={H - 18} textAnchor="middle" fontSize={11} fontWeight={600} fill="rgba(255,255,255,0.45)">response returns to the invoking client</text>
            <defs>
              <marker id="arrow" markerWidth="8" markerHeight="8" refX="5" refY="4" orient="auto"><path d="M0,0 L6,4 L0,8 Z" fill="rgba(255,255,255,0.4)" /></marker>
            </defs>

            {/* Forward edges */}
            {edges.map((e, i) => (
              <line key={i} x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2}
                stroke={e.mode === 'route' ? 'rgba(255,54,33,0.6)' : 'rgba(255,255,255,0.2)'}
                strokeWidth={e.mode === 'route' ? 2 : 1.6}
                strokeDasharray={e.mode === 'route' ? '5 5' : '2 7'}
                className="motion-safe:animate-[dashflow_.6s_linear_infinite]" />
            ))}

            {/* Packets */}
            {packets.map((pk, i) => (
              <circle key={i} ref={(el) => (packetRefs.current[i] = el)} r={pk.mode === 'stream' ? 2.4 : 3.4} fill={pk.mode === 'stream' ? 'rgba(255,255,255,0.5)' : 'var(--lava)'} />
            ))}

            {/* Gateway centerpiece - title + bulleted capabilities */}
            <rect x={GX0} y={GY0} width={GX1 - GX0} height={GY1 - GY0} rx={14} fill="#2A140E" stroke="var(--lava)" strokeWidth={2.4} />
            <text x={GCX} y={GY0 + 34} textAnchor="middle" fontSize={19} fontWeight={800} fill="#ffffff">Unity Gateway</text>
            <text x={GCX} y={GY0 + 55} textAnchor="middle" fontSize={11.5} fontWeight={600} fill="rgba(255,255,255,0.6)">one governed endpoint · every request, every model</text>
            <line x1={GX0 + 20} y1={GY0 + 72} x2={GX1 - 20} y2={GY0 + 72} stroke="rgba(255,255,255,0.14)" />
            {GATEWAY_FEATURES.map((f, i) => {
              const y = GY0 + 100 + i * 44;
              return (
                <g key={i}>
                  <circle cx={GX0 + 30} cy={y - 4} r={3} fill="var(--lava)" />
                  <text x={GX0 + 44} y={y} fontSize={13.5} fontWeight={600} fill="rgba(255,255,255,0.86)">{f}</text>
                </g>
              );
            })}

            {/* Nodes */}
            {clients.map((c) => renderBox(c))}
            {models.map((m) => renderBox(m, { landed: m.id === landedNodeId }))}
            {renderBox(response)}
          </svg>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap items-center gap-5 text-[11px] text-white/65">
          <span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-white/50" /> request / response stream</span>
          <span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-lava" /> routing decision</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-[3px] rounded-[2px] bg-moss" /> small OSS</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-[3px] rounded-[2px] bg-amber" /> large OSS</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-[3px] rounded-[2px] bg-plum" /> frontier</span>
        </div>
      </div>
    </div>
  );
}
