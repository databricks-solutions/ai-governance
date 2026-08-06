#!/usr/bin/env bash
#
# Frontend build for the asset bundle (`artifacts.frontend.build` in databricks.yml).
#
# Why this is a script and not just `npm run build`:
#
#   1. `bundle deploy` runs the build UNCONDITIONALLY and with no timeout. On a machine where
#      the public npm registry is blocked — the default on a Databricks-managed laptop, see
#      .npmrc.example — a bare `npm install` retries until it hangs, so `bundle deploy` never
#      completes. That is worse than the problem the build step was added to solve.
#   2. So: if dist/ is already newer than every source file, this is a no-op. A prebuilt dist
#      deploys with no network access at all, which is what makes the bundle usable offline
#      and in CI alike.
#   3. If dist/ IS stale and the build cannot run, this fails LOUDLY and says why. The thing
#      we are protecting against is a silent deploy of a stale bundle — the app would serve
#      an old UI, or a blank page, with no error anywhere.
#
# Set FRONTEND_FORCE_BUILD=1 to rebuild even when dist looks current.

set -euo pipefail
cd "$(dirname "$0")"

entry="dist/index.html"

newest_src() {
  # Newest mtime among real inputs. package.json/lock included: a dependency bump must
  # invalidate dist even when no .tsx changed.
  find src index.html package.json package-lock.json vite.config.ts tsconfig.json \
    -type f -newer "$entry" 2>/dev/null | head -1
}

if [[ "${FRONTEND_FORCE_BUILD:-0}" != "1" && -f "$entry" ]] && [[ -z "$(newest_src)" ]]; then
  echo "frontend: dist/ is current (no source newer than $entry) — skipping build."
  exit 0
fi

if [[ -f "$entry" ]]; then
  echo "frontend: dist/ is STALE — these inputs are newer:"
  find src index.html package.json package-lock.json vite.config.ts tsconfig.json \
    -type f -newer "$entry" 2>/dev/null | sed 's/^/  /'
else
  echo "frontend: no dist/ yet — building."
fi

if ! npm install --no-audit --no-fund; then
  cat >&2 <<'MSG'

frontend: npm install FAILED, and dist/ is stale or missing.

The deploy is stopping here on purpose: shipping a stale dist means the app serves an old UI
(or a blank page) with no error, which is much harder to debug than this message.

If the public npm registry is blocked on this machine (the default on a Databricks-managed
laptop), configure the internal mirror first:

    cd frontend
    cp .npmrc.example .npmrc      # then paste a JFrog identity token into it
    npm install && npm run build

Then re-run the deploy. To ship a dist you have already built elsewhere, copy it into
frontend/dist/ — this script then detects it as current and skips the build.
MSG
  exit 1
fi

npm run build
