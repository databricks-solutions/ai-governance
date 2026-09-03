import { useState } from 'react';

// Configurable / inspectable detail panels for the Unity Gateway governance
// features. Content is illustrative/demo - a clear picture of what each guardrail
// does, a path to wiring real system.ai_gateway config later. Rendered inside the
// gateway box when a feature's "Configure" is opened.
//
// Budgets and Routing policy are NOT here - they carry real routing state and are
// rendered inline by the Pipeline tab (BudgetForm / RoutingPolicyForm).

export function StageConfigPanel({ feature, stageName }: { feature: string; stageName: string }) {
  return (
    <ConfigCard title={stageName}>
      {feature === 'rate-limits' && <RateLimits />}
      {feature === 'guardrails' && <Guardrails />}
      {feature === 'inference-tables' && <InferenceTables />}
    </ConfigCard>
  );
}

// ---- shared bits --------------------------------------------------------
export function ConfigCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl bg-white/[0.04] p-5 text-white ring-1 ring-white/10">
      <div className="mb-3.5 flex items-center gap-2">
        <span className="rounded-pill bg-lava/15 px-2.5 py-1 font-body text-[9px] font-medium uppercase tracking-[.08em] text-lava">
          Unity Gateway
        </span>
        <h6 className="font-display text-[13px] font-semibold text-white">{title}</h6>
      </div>
      {children}
    </div>
  );
}

function SubHead({ children, badge }: { children: React.ReactNode; badge?: string }) {
  return (
    <div className="mb-2 flex items-center gap-2">
      <span className="font-body text-[10px] font-bold uppercase tracking-[.12em] text-white/45">{children}</span>
      {badge && <span className="rounded-pill bg-white/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[.06em] text-white/55">{badge}</span>}
    </div>
  );
}
function Num({ v, onChange, suffix }: { v: number; onChange: (n: number) => void; suffix?: string }) {
  return (
    <span className="flex items-center gap-1">
      <input type="number" value={v} onChange={(e) => onChange(+e.target.value)} className="num w-24 rounded bg-white/10 px-2 py-1 text-right text-[12px] text-white ring-1 ring-white/10 outline-none" />
      {suffix && <span className="num text-[10px] text-white/45">{suffix}</span>}
    </span>
  );
}
function Chip({ on, onClick, label }: { on: boolean; onClick: () => void; label: string }) {
  return (
    <button onClick={onClick} className={`flex items-center gap-1.5 rounded-pill px-2.5 py-1.5 text-[11.5px] font-medium transition ${on ? 'bg-moss/20 text-[#93D3AB] ring-1 ring-moss/40' : 'bg-white/10 text-white/55 ring-1 ring-white/10'}`}>
      <span className={`grid h-3.5 w-3.5 place-items-center rounded-full text-[8px] ${on ? 'bg-moss text-white' : 'border border-white/25'}`}>{on ? '✓' : ''}</span>
      {label}
    </button>
  );
}
function Switch({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} role="switch" aria-checked={on} className={`relative h-5 w-9 shrink-0 rounded-full transition ${on ? 'bg-lava' : 'bg-white/15'}`}>
      <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${on ? 'left-[18px]' : 'left-0.5'}`} />
    </button>
  );
}
function Code({ children }: { children: React.ReactNode }) {
  return <pre className="num mt-3 overflow-x-auto whitespace-pre-wrap rounded bg-black/40 px-4 py-3 text-[11px] leading-[1.7] text-[#D6CFC7] ring-1 ring-white/10">{children}</pre>;
}

// ---- Rate limits: all three scopes independently selectable -------------
type Scope = 'user' | 'group' | 'sp';
const SCOPE_META: Record<Scope, { label: string; sub: string; rpm: number }> = {
  user: { label: 'Per user', sub: 'each end user', rpm: 120 },
  group: { label: 'Per group', sub: 'an account group', rpm: 2000 },
  sp: { label: 'Per service principal', sub: 'app / automation identity', rpm: 5000 },
};
function RateLimits() {
  const [scopes, setScopes] = useState<Record<Scope, { on: boolean; rpm: number }>>({
    user: { on: true, rpm: SCOPE_META.user.rpm },
    group: { on: true, rpm: SCOPE_META.group.rpm },
    sp: { on: true, rpm: SCOPE_META.sp.rpm },
  });
  const set = (s: Scope, patch: Partial<{ on: boolean; rpm: number }>) => setScopes((cur) => ({ ...cur, [s]: { ...cur[s], ...patch } }));
  return (
    <div className="flex flex-col gap-3">
      <SubHead badge="all three enforceable">Rate limits by scope</SubHead>
      <div className="flex flex-col gap-2">
        {(['user', 'group', 'sp'] as Scope[]).map((s) => (
          <div key={s} className={`flex flex-wrap items-center gap-3 rounded-lg p-2.5 ring-1 transition ${scopes[s].on ? 'bg-white/[0.06] ring-white/15' : 'bg-white/[0.02] ring-white/10'}`}>
            <Switch on={scopes[s].on} onClick={() => set(s, { on: !scopes[s].on })} />
            <div className="min-w-[150px]">
              <div className="text-[12.5px] font-semibold text-white/85">{SCOPE_META[s].label}</div>
              <div className="text-[10.5px] text-white/40">{SCOPE_META[s].sub}</div>
            </div>
            <span className={`ml-auto flex items-center gap-1 ${scopes[s].on ? '' : 'opacity-40'}`}>
              <Num v={scopes[s].rpm} onChange={(n) => set(s, { rpm: n })} suffix="req / min" />
            </span>
          </div>
        ))}
      </div>
      <div className="num text-[11px] text-white/45">Each scope is enforced independently at the gateway, before any model runs. A request must clear every enabled limit.</div>
    </div>
  );
}

// ---- AI guardrails: PII + safety + keywords + topics (input & output) ----
// Mirrors Unity Gateway guardrail types (databricks.com/blog/how-safeguard-
// ai-workloads-unity-ai-gateway-guardrails): safety/content moderation, PII
// (mask or block), invalid-keyword blocking, and valid-topic restriction.
const PII_ENTITIES = ['EMAIL', 'PHONE', 'US_SSN', 'CREDIT_CARD', 'IBAN', 'IP_ADDRESS', 'PERSON', 'ADDRESS'];
const SAFETY_CATS = ['Violence', 'Hate / harassment', 'Sexual', 'Self-harm', 'Weapons', 'Criminal planning'];
function Guardrails() {
  const [safety, setSafety] = useState(true);
  const [cats, setCats] = useState<Record<string, boolean>>(Object.fromEntries(SAFETY_CATS.map((c) => [c, true])));
  const [piiOn, setPiiOn] = useState(true);
  const [piiMode, setPiiMode] = useState<'mask' | 'block'>('mask');
  const [pii, setPii] = useState<Record<string, boolean>>(Object.fromEntries(PII_ENTITIES.map((k) => [k, ['EMAIL', 'PHONE', 'US_SSN', 'CREDIT_CARD'].includes(k)])));
  const [keywords, setKeywords] = useState('competitor names, internal codenames');
  const [topics, setTopics] = useState('financial analysis, coding, data platform');
  const example =
    piiMode === 'block'
      ? 'Request contains US_SSN → BLOCKED at the gateway before any model runs.'
      : 'Email [EMAIL], SSN [US_SSN] — masked pre-egress, then routed.';
  return (
    <div className="flex flex-col gap-4">
      <div className="text-[11.5px] text-white/55">Guardrails run on <b className="text-white/80">both the input and the output</b>, at the gateway — the same policy for every model you route to.</div>

      {/* Safety / content moderation */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <SubHead badge="input & output">Safety — content moderation</SubHead>
          <Switch on={safety} onClick={() => setSafety((s) => !s)} />
        </div>
        <div className={`flex flex-wrap gap-2 ${safety ? '' : 'pointer-events-none opacity-40'}`}>
          {SAFETY_CATS.map((c) => (
            <Chip key={c} on={!!cats[c]} onClick={() => setCats((p) => ({ ...p, [c]: !p[c] }))} label={c} />
          ))}
        </div>
      </div>

      {/* PII detection */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <SubHead badge="input & output">PII detection</SubHead>
          <Switch on={piiOn} onClick={() => setPiiOn((s) => !s)} />
        </div>
        <div className={piiOn ? '' : 'pointer-events-none opacity-40'}>
          <div className="mb-2 inline-flex rounded-pill bg-white/10 p-0.5 ring-1 ring-white/10">
            {(['mask', 'block'] as const).map((m) => (
              <button key={m} onClick={() => setPiiMode(m)} className={`rounded-pill px-3 py-1 text-[11px] font-semibold capitalize transition ${piiMode === m ? 'bg-white text-ink' : 'text-white/60 hover:text-white'}`}>
                {m === 'mask' ? 'Mask' : 'Block request'}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {PII_ENTITIES.map((k) => (
              <Chip key={k} on={!!pii[k]} onClick={() => setPii((p) => ({ ...p, [k]: !p[k] }))} label={k} />
            ))}
          </div>
        </div>
      </div>

      {/* Invalid keywords + valid topics */}
      <div className="grid grid-cols-2 gap-3 max-[600px]:grid-cols-1">
        <div>
          <SubHead>Invalid keywords · block</SubHead>
          <textarea value={keywords} onChange={(e) => setKeywords(e.target.value)} rows={2}
            className="w-full resize-none rounded bg-white/10 px-2.5 py-2 text-[11.5px] leading-[1.5] text-white ring-1 ring-white/10 outline-none placeholder:text-white/30" placeholder="comma-separated terms to block" />
        </div>
        <div>
          <SubHead>Valid topics · restrict to</SubHead>
          <textarea value={topics} onChange={(e) => setTopics(e.target.value)} rows={2}
            className="w-full resize-none rounded bg-white/10 px-2.5 py-2 text-[11.5px] leading-[1.5] text-white ring-1 ring-white/10 outline-none placeholder:text-white/30" placeholder="comma-separated allowed topics" />
        </div>
      </div>

      <Code>{example}</Code>
    </div>
  );
}

// ---- Inference tables: enable + UC location + logged schema -------------
// Schema mirrors the AI Gateway inference-table columns
// (docs.databricks.com/aws/en/ai-gateway/inference-tables#inference-table-schema).
const INFERENCE_SCHEMA: [string, string, string][] = [
  ['request_date', 'DATE', 'Date of the request (partition column)'],
  ['databricks_request_id', 'STRING', 'Databricks-generated request id'],
  ['client_request_id', 'STRING', 'Optional client-supplied request id'],
  ['request_time', 'TIMESTAMP', 'When the gateway received the request'],
  ['status_code', 'INT', 'HTTP status of the model response'],
  ['sampling_fraction', 'DOUBLE', 'Fraction of traffic sampled into the table'],
  ['execution_duration_ms', 'BIGINT', 'End-to-end serving latency'],
  ['request', 'STRING', 'Raw JSON request payload'],
  ['response', 'STRING', 'Raw JSON response payload'],
  ['served_entity_id', 'STRING', 'Served endpoint / entity that answered'],
  ['logging_error_codes', 'ARRAY<STRING>', 'Any errors hit while logging the row'],
  ['requester', 'STRING', 'Identity (user / group / SP) that called'],
];
function InferenceTables() {
  const [on, setOn] = useState(true);
  const [catalog, setCatalog] = useState('finops');
  const [schema, setSchema] = useState('gateway');
  const [prefix, setPrefix] = useState('payload');
  const fq = `${catalog}.${schema}.${prefix}_*`;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <SubHead badge="auto-logged, no code">Log every request &amp; response</SubHead>
        <Switch on={on} onClick={() => setOn((s) => !s)} />
      </div>

      <div className={on ? '' : 'pointer-events-none opacity-40'}>
        <SubHead>Unity Catalog destination</SubHead>
        <div className="flex flex-wrap items-center gap-2">
          <LocInput label="Catalog" v={catalog} onChange={setCatalog} />
          <span className="text-white/35">.</span>
          <LocInput label="Schema" v={schema} onChange={setSchema} />
          <span className="text-white/35">.</span>
          <LocInput label="Table prefix" v={prefix} onChange={setPrefix} />
        </div>
        <div className="num mt-2 text-[11px] text-white/45">Writes to <span className="text-white/75">{fq}</span> · governed by Unity Catalog permissions.</div>
      </div>

      <div>
        <SubHead>Logged schema</SubHead>
        <div className="max-h-[220px] overflow-y-auto rounded-lg ring-1 ring-white/10">
          <table className="num w-full text-[11px]">
            <thead className="sticky top-0 bg-[#20140f]">
              <tr className="text-left text-white/45">
                <th className="px-3 py-1.5 font-semibold">column</th>
                <th className="px-3 py-1.5 font-semibold">type</th>
                <th className="px-3 py-1.5 font-semibold">description</th>
              </tr>
            </thead>
            <tbody>
              {INFERENCE_SCHEMA.map(([col, type, desc]) => (
                <tr key={col} className="border-t border-white/[0.07]">
                  <td className="px-3 py-1.5 font-semibold text-[#8FC1F0]">{col}</td>
                  <td className="px-3 py-1.5 text-white/55">{type}</td>
                  <td className="num px-3 py-1.5 text-white/70" style={{ fontFamily: 'inherit' }}>{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
function LocInput({ label, v, onChange }: { label: string; v: string; onChange: (s: string) => void }) {
  return (
    <span className="flex flex-col gap-0.5">
      <span className="text-[9px] font-bold uppercase tracking-[.08em] text-white/40">{label}</span>
      <input value={v} onChange={(e) => onChange(e.target.value)} aria-label={label}
        className="num w-[110px] rounded bg-white/10 px-2 py-1 text-[12px] text-white ring-1 ring-white/10 outline-none" />
    </span>
  );
}
