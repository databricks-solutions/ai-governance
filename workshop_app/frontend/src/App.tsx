import { useEffect, useState } from "react";
import { ShieldCheck, Home, Layers, Lock, DollarSign, Loader2, Rocket, HelpCircle, ListChecks } from "lucide-react";
import { cn } from "@/lib/cn";
import { api, groupCounts, type Workshop, type Accelerators, type ProgressMap } from "@/lib/api";
import Intro from "@/pages/Intro";
import PillarPage from "@/pages/PillarPage";
import Faq from "@/pages/Faq";
import Prerequisites from "@/pages/Prerequisites";

const PILLAR_ICONS: Record<string, typeof Layers> = { choice: Layers, cost: DollarSign, control: Lock };

// Customer-facing (external) repo — for feedback links in the sidebar.
const REPO_URL = "https://github.com/databricks-solutions/ai-governance";

export default function App() {
  return <Shell />;
}

function Shell() {
  const [route, setRoute] = useState<string>("intro");
  const [workshop, setWorkshop] = useState<Workshop | null>(null);
  const [accel, setAccel] = useState<Accelerators | null>(null);
  const [progress, setProgress] = useState<ProgressMap>({});

  useEffect(() => {
    api.workshop().then(setWorkshop).catch(() => setWorkshop(null));
    api.accelerators().then(setAccel).catch(() => setAccel(null));
  }, []);

  function refreshProgress() {
    api.progress().then(setProgress).catch(() => setProgress({}));
  }
  useEffect(refreshProgress, []);

  // Nav badges count achieved steps over applicable (N/A excluded), matching the pillar pages.
  function groupProgress(steps: { id: string }[]): { done: number; total: number } {
    const { done, applicable } = groupCounts(steps, progress);
    return { done, total: applicable };
  }

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-72 shrink-0 flex-col border-r border-navy/10 bg-navy px-6 py-8 text-white lg:flex">
        <button onClick={() => setRoute("intro")} className="mb-8 flex items-center gap-2.5 text-left">
          <ShieldCheck className="h-6 w-6" strokeWidth={2} />
          <div className="leading-tight">
            <div className="text-sm font-semibold">AI Governance</div>
            <div className="text-xs text-white/50">Hands-on workshop</div>
          </div>
        </button>

        <nav className="flex flex-col gap-1">
          <NavItem active={route === "intro"} onClick={() => setRoute("intro")} icon={Home} label="Walkthrough" />
          <NavItem active={route === "prereqs"} onClick={() => setRoute("prereqs")} icon={ListChecks} label="Prerequisites" />
          {workshop?.pillars.map((p) => {
            const { done, total } = groupProgress(p.steps);
            const Icon = PILLAR_ICONS[p.id] ?? Layers;
            return (
              <NavItem
                key={p.id}
                active={route === p.id}
                onClick={() => setRoute(p.id)}
                icon={Icon}
                label={p.title}
                badge={total ? `${done}/${total}` : undefined}
                complete={total > 0 && done === total}
              />
            );
          })}

          {accel && (
            <>
              <div className="mt-4 mb-1 px-3 text-[10px] font-semibold uppercase tracking-wider text-white/40">
                Accelerators
              </div>
              {accel.accelerators.map((a) => {
                const { done, total } = groupProgress(a.steps);
                return (
                  <NavItem
                    key={a.id}
                    active={route === a.id}
                    onClick={() => setRoute(a.id)}
                    icon={Rocket}
                    label={a.title}
                    badge={total ? `${done}/${total}` : undefined}
                    complete={total > 0 && done === total}
                  />
                );
              })}
            </>
          )}

          <div className="mt-4 border-t border-white/10 pt-3">
            <NavItem active={route === "faq"} onClick={() => setRoute("faq")} icon={HelpCircle} label="FAQ" />
          </div>
        </nav>

        <div className="mt-auto text-xs text-white/40">
          <div className="flex flex-col gap-1.5">
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="hover:text-white/80">
              Repository ↗
            </a>
            <a href={`${REPO_URL}/issues/new?labels=enhancement&title=${encodeURIComponent("[Feature] ")}`} target="_blank" rel="noreferrer" className="hover:text-white/80">
              Submit feature request ↗
            </a>
            <a href={`${REPO_URL}/issues/new?labels=bug&title=${encodeURIComponent("[Bug] ")}`} target="_blank" rel="noreferrer" className="hover:text-white/80">
              File an issue ↗
            </a>
          </div>
          <div className="mt-3 h-px w-8 bg-lava" />
          <div className="mt-3">Choice · Cost · Control</div>
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        {!workshop && (
          <div className="flex h-screen items-center justify-center text-muted">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading workshop…
          </div>
        )}
        {route === "faq" && <Faq />}
        {route === "prereqs" && (
          <Prerequisites
            pillars={workshop?.pillars}
            accelerators={accel?.accelerators}
            progress={progress}
            onProgressChange={refreshProgress}
          />
        )}
        {workshop && route === "intro" && (
          <Intro
            intro={workshop.intro}
            pillars={workshop.pillars}
            accelOverview={accel?.overview}
            accelerators={accel?.accelerators}
            progress={progress}
            go={setRoute}
          />
        )}
        {workshop &&
          workshop.pillars.map(
            (p) =>
              route === p.id && (
                <PillarPage key={p.id} pillar={p} progress={progress} onProgressChange={refreshProgress} />
              ),
          )}
        {accel &&
          accel.accelerators.map(
            (a) =>
              route === a.id && (
                <PillarPage key={a.id} pillar={a} progress={progress} onProgressChange={refreshProgress} />
              ),
          )}
      </main>
    </div>
  );
}

function NavItem({
  active,
  onClick,
  icon: Icon,
  label,
  badge,
  complete,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof Home;
  label: string;
  badge?: string;
  complete?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition-colors",
        active ? "bg-white/10 font-semibold" : "text-white/70 hover:bg-white/5",
      )}
    >
      <Icon className="h-4.5 w-4.5" strokeWidth={2} />
      <span className="flex-1">{label}</span>
      {badge && (
        <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-semibold", complete ? "bg-lava/20 text-lava" : "bg-white/10 text-white/60")}>
          {badge}
        </span>
      )}
    </button>
  );
}
