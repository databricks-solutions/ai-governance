import { Component, type ReactNode } from 'react';

// A safety net so a render error (e.g. a backend/contract drift after an
// incomplete redeploy) degrades to a friendly panel instead of blanking the app.
interface State { error: Error | null }

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="flex h-screen items-center justify-center bg-paper p-8">
        <div className="max-w-[520px] rounded-xl bg-card p-7 shadow-lift">
          <div className="mb-1.5 font-body text-[12px] text-lava">Intelligent AI FinOps</div>
          <h1 className="font-display text-[18px] font-semibold tracking-[-.015em]">Something went wrong</h1>
          <p className="mt-2.5 text-[13px] leading-[1.6] text-ink-2">
            The page hit an unexpected error - often a stale backend after a partial redeploy (the API
            contract changed but the server wasn't restarted). Reloading usually fixes it.
          </p>
          <pre className="num mt-3 overflow-x-auto whitespace-pre-wrap rounded bg-card-2 px-3 py-2.5 text-[11px] text-ink-3">
            {String(this.state.error.message || this.state.error)}
          </pre>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 rounded-pill bg-ink px-[18px] py-2.5 text-[13px] font-medium text-white transition hover:bg-[#3A322C]"
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
