import { useState } from "react";
import { Database, Table2, BarChart3, Braces, ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

// Renders a test result's `detail` payload.
//
// Most governance tests return {sql, rows, ...}. Dumping that as raw JSON buried the two things
// the room actually wants — the query we ran against their workspace, and the answer — inside a
// wall of braces. So:
//
//   sql   -> its own labelled block. A platform team's first question is "what did you just run
//            on my warehouse?", and having the literal statement on screen answers it.
//   rows  -> a real table, with a bar-chart view when the shape suits it.
//   rest  -> collapsed JSON, still available but no longer the default.

type Row = Record<string, unknown>;

function isRows(v: unknown): v is Row[] {
  return Array.isArray(v) && v.length > 0 && v.every((r) => r && typeof r === "object" && !Array.isArray(r));
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    // Money-ish and rate-ish values need more precision than counts.
    if (Number.isInteger(v)) return v.toLocaleString();
    return Math.abs(v) < 0.01 ? v.toExponential(2) : v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** Numeric-looking value, including the strings the SQL API returns for numbers. */
function num(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v);
  return null;
}

function RowsTable({ rows }: { rows: Row[] }) {
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(r))));
  return (
    <div className="overflow-x-auto rounded-lg border border-navy/10 bg-white">
      <table className="w-full border-collapse text-left text-[12.5px]">
        <thead className="bg-oat">
          <tr>
            {cols.map((c) => (
              <th key={c} className="whitespace-nowrap px-3 py-1.5 text-[10.5px] font-semibold uppercase tracking-wide text-muted">
                {c.replace(/_/g, " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-navy/[0.06]">
              {cols.map((c) => {
                const n = num(r[c]);
                return (
                  <td
                    key={c}
                    className={cn(
                      "px-3 py-1.5 align-top text-navy/80",
                      n !== null ? "whitespace-nowrap text-right tabular-nums" : "",
                    )}
                  >
                    {fmt(r[c])}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Horizontal bars for the first numeric column, labelled by the first text column.
 * Only shown when the data is actually chartable: a label column, a numeric column, and few
 * enough rows to read. A chart of 40 bars is worse than the table.
 */
function RowsChart({ rows }: { rows: Row[] }) {
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(r))));
  const labelCol = cols.find((c) => rows.every((r) => num(r[c]) === null));
  // Fully-numeric, matching chartable()'s gate — a "some numeric" column can pick a
  // half-text column the gate never approved, mislabelling the chart and drawing zero bars.
  const valueCol = cols.find((c) => rows.every((r) => num(r[c]) !== null));
  if (!labelCol || !valueCol) return null;
  const max = Math.max(...rows.map((r) => Math.abs(num(r[valueCol]) ?? 0)));
  if (!(max > 0)) return null;
  return (
    <div className="rounded-lg border border-navy/10 bg-white p-3">
      <div className="mb-2 text-[10.5px] font-semibold uppercase tracking-wide text-muted">
        {valueCol.replace(/_/g, " ")} by {labelCol.replace(/_/g, " ")}
      </div>
      <div className="flex flex-col gap-1.5">
        {rows.slice(0, 15).map((r, i) => {
          const v = num(r[valueCol]) ?? 0;
          return (
            <div key={i} className="flex items-center gap-2 text-[11.5px]">
              <div className="w-[38%] shrink-0 truncate text-navy/75" title={String(r[labelCol])}>
                {fmt(r[labelCol])}
              </div>
              <div className="h-3.5 flex-1 overflow-hidden rounded bg-navy/[0.05]">
                <div
                  className="h-full rounded bg-lava/75"
                  style={{ width: `${Math.max(1.5, (Math.abs(v) / max) * 100)}%` }}
                />
              </div>
              <div className="w-20 shrink-0 text-right tabular-nums text-navy/70">{fmt(r[valueCol])}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function chartable(rows: Row[]): boolean {
  if (rows.length < 2 || rows.length > 25) return false;
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(r))));
  const hasLabel = cols.some((c) => rows.every((r) => num(r[c]) === null));
  const hasValue = cols.some((c) => rows.every((r) => num(r[c]) !== null));
  return hasLabel && hasValue;
}

export default function ResultDetail({ detail }: { detail: Record<string, unknown> }) {
  const [view, setView] = useState<"table" | "chart">("table");
  const [showJson, setShowJson] = useState(false);

  const sql = typeof detail.sql === "string" ? detail.sql : null;
  const rowsKey = ["rows", "assignments", "acl", "endpoints", "results"].find((k) => isRows(detail[k]));
  const rows = rowsKey ? (detail[rowsKey] as Row[]) : null;

  // Everything not promoted to its own view. `sql` is dropped because it is shown in full above.
  const rest: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(detail)) {
    if (k === "sql" || k === rowsKey) continue;
    rest[k] = v;
  }
  const hasRest = Object.keys(rest).length > 0;
  const canChart = !!rows && chartable(rows);

  return (
    <div className="mt-3 flex flex-col gap-3">
      {sql && (
        <div>
          <div className="mb-1 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted">
            <Database className="h-3 w-3" /> Query run against your workspace
          </div>
          <pre className="overflow-x-auto rounded-lg border border-navy/10 bg-navy/[0.03] p-3 text-[11.5px] leading-relaxed text-navy/85">
            {sql.trim()}
          </pre>
        </div>
      )}

      {rows && (
        <div>
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <div className="text-[10.5px] font-semibold uppercase tracking-wider text-muted">
              {rows.length} row{rows.length === 1 ? "" : "s"}
              {rowsKey !== "rows" ? ` · ${rowsKey}` : ""}
            </div>
            {canChart && (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setView("table")}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-semibold",
                    view === "table" ? "bg-navy text-white" : "text-muted hover:bg-navy/5",
                  )}
                >
                  <Table2 className="h-3 w-3" /> Table
                </button>
                <button
                  onClick={() => setView("chart")}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-semibold",
                    view === "chart" ? "bg-navy text-white" : "text-muted hover:bg-navy/5",
                  )}
                >
                  <BarChart3 className="h-3 w-3" /> Chart
                </button>
              </div>
            )}
          </div>
          {canChart && view === "chart" ? <RowsChart rows={rows} /> : <RowsTable rows={rows} />}
        </div>
      )}

      {hasRest && (
        <div>
          <button
            onClick={() => setShowJson((v) => !v)}
            className="inline-flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted hover:text-navy"
          >
            <Braces className="h-3 w-3" />
            {rows || sql ? "Full detail" : "Detail"}
            <ChevronDown className={cn("h-3 w-3 transition-transform", showJson && "rotate-180")} />
          </button>
          {showJson && (
            <pre className="mt-1.5 max-h-64 overflow-auto rounded-lg bg-navy/[0.03] p-3 text-[11.5px] leading-relaxed text-navy/80">
              {JSON.stringify(rest, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
