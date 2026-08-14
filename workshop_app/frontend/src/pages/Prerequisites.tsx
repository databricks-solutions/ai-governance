import { useEffect, useState } from "react";
import { CheckSquare, Square, FileDown, FileText, Loader2, Clock, AlertCircle } from "lucide-react";
import { api, type Prerequisites as Prereqs } from "@/lib/api";
import { useAccount } from "@/lib/account";
import PageHeader from "@/components/PageHeader";
import { cn } from "@/lib/cn";

// The pre-workshop checklist. Content is config-driven (config/prerequisites.yaml) so an SE can
// tailor it per customer without a code change.
//
// Ticking here is deliberately LOCAL-ONLY (browser localStorage, not the workshop progress
// store): these are the customer's platform tasks, done days before the session by people who
// never open this app.
// Recording them as workshop progress would inflate the outcomes JSON the sales app ingests
// with items nobody did in the room. The PDF is the artifact that actually travels.
const LS_KEY = "aigov_prereq_checked";

function loadChecked(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) || "{}");
  } catch {
    return {};
  }
}

export default function Prerequisites() {
  const { sfid } = useAccount();
  const [data, setData] = useState<Prereqs | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checked, setChecked] = useState<Record<string, boolean>>(loadChecked);

  useEffect(() => {
    api.prerequisites().then(setData).catch((e) => setError(String(e)));
  }, []);

  function toggle(id: string) {
    setChecked((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      try {
        localStorage.setItem(LS_KEY, JSON.stringify(next));
      } catch {
        // Private browsing or a full quota — ticking still works for this session.
      }
      return next;
    });
  }

  if (error) {
    return (
      <div>
        <PageHeader eyebrow="Before the workshop" title="Prerequisites" />
        <div className="mx-auto max-w-4xl px-8 py-12 lg:px-14">
          <p className="text-sm text-lava">Could not load the prerequisites: {error}</p>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="flex h-screen items-center justify-center text-muted">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading prerequisites…
      </div>
    );
  }

  const all = data.groups.flatMap((g) => g.items);
  const required = all.filter((i) => !i.optional);
  const doneRequired = required.filter((i) => checked[i.id]).length;

  return (
    <div>
      <PageHeader
        eyebrow="Before the workshop"
        title="Prerequisites"
        lead="What to have in place before the workshop, tagged by persona. The session needs as few as three people — an account admin, a business champion, and a technical champion. Long-lead items need an admin and take days, so start those about a week out."
      />
      <div className="mx-auto max-w-4xl px-8 py-12 lg:px-14">

      {/* Progress + PDF. The PDF is the point of this page: it gets sent to the customer's
          platform team a week out, printed, and ticked with a pen. */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-navy/10 bg-oat p-5">
        <div>
          <div className="text-sm font-semibold text-navy">
            {doneRequired} of {required.length} required items checked
          </div>
          <div className="mt-0.5 text-xs text-muted">
            Ticks are saved in this browser only — they are the customer's platform tasks, not
            workshop progress, so they stay out of the exported outcomes.
          </div>
        </div>
        {data.pdf_available ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <a
              href={api.brochurePdfUrl()}
              className="inline-flex items-center gap-2 rounded-full border border-navy/20 bg-white px-4 py-2 text-sm font-semibold text-navy hover:border-navy/40"
            >
              <FileText className="h-4 w-4" /> Workshop brochure (PDF)
            </a>
            <a
              href={api.prerequisitesPdfUrl(sfid.trim() || undefined)}
              className="inline-flex items-center gap-2 rounded-full bg-navy px-4 py-2 text-sm font-semibold text-white hover:bg-navy-700"
            >
              <FileDown className="h-4 w-4" /> Download checklist (PDF)
            </a>
          </div>
        ) : (
          <div className="flex items-start gap-2 text-xs text-muted">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-[#B7791F]" />
            <span>
              PDF export unavailable on this deployment.
              {data.pdf_unavailable_reason ? ` (${data.pdf_unavailable_reason})` : ""}
            </span>
          </div>
        )}
      </div>

      {data.lead_time_note && (
        <p className="mb-8 whitespace-pre-line text-sm leading-relaxed text-muted">{data.lead_time_note}</p>
      )}

      <div className="flex flex-col gap-8">
        {data.groups.map((g) => {
          const gDone = g.items.filter((i) => checked[i.id]).length;
          return (
            <section key={g.id}>
              <div className="mb-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h2 className="text-lg font-semibold text-navy">{g.title}</h2>
                {g.lead_time && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-lava/10 px-2 py-0.5 text-[11px] font-semibold text-lava">
                    <Clock className="h-3 w-3" /> {g.lead_time}
                  </span>
                )}
                <span className="text-xs text-navy-300">
                  {gDone}/{g.items.length}
                </span>
              </div>
              {g.intro && <p className="mb-3 text-sm leading-relaxed text-muted">{g.intro}</p>}

              <div className="overflow-hidden rounded-2xl border border-navy/10 bg-white">
                {g.items.map((item, idx) => {
                  const on = !!checked[item.id];
                  return (
                    <button
                      key={item.id}
                      onClick={() => toggle(item.id)}
                      className={cn(
                        "flex w-full items-start gap-3 p-4 text-left transition-colors hover:bg-oat/60",
                        idx > 0 && "border-t border-navy/[0.07]",
                      )}
                    >
                      {on ? (
                        <CheckSquare className="mt-0.5 h-5 w-5 shrink-0 text-lava" strokeWidth={2} />
                      ) : (
                        <Square className="mt-0.5 h-5 w-5 shrink-0 text-navy-300" strokeWidth={2} />
                      )}
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-baseline gap-2">
                          <span
                            className={cn(
                              "text-sm font-semibold",
                              on ? "text-navy/50 line-through" : "text-navy",
                            )}
                          >
                            {item.item}
                          </span>
                          {item.optional && (
                            <span className="rounded bg-navy/5 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
                              scope-dependent
                            </span>
                          )}
                        </div>
                        {item.why && <p className="mt-1 text-xs leading-relaxed text-muted">{item.why}</p>}
                        {item.who && (
                          <p className="mt-1 text-[11px] text-navy-300">
                            <span className="font-semibold">Persona:</span> {item.who}
                          </p>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            </section>
          );
        })}
        </div>
      </div>
    </div>
  );
}
