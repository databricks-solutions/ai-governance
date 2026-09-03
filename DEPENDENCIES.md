# Third-party dependency audit

This repository ships three distributables, each with its own dependency set:

- **`workshop_app/`** — the customer-facing AI Governance Workshop app (FastAPI backend +
  React/Vite frontend).
- **`intelligent-ai-finops/`** — a standalone "smart routing" FinOps Databricks App (FastAPI
  backend + React/Vite frontend).
- **`accelerators/`** — Databricks reference notebooks. Each notebook `%pip install`s its own
  dependencies at runtime, so the repo pins no notebook runtime dependencies; the top-level
  `pyproject.toml` only configures `ruff` for local linting.

Every dependency below is released under a permissive OSS license
(**MIT / BSD-3-Clause / ISC / Apache-2.0**). There are **no copyleft (GPL/LGPL/AGPL) and no
source-available/commercially-restricted** dependencies, so the repository is clean for
external distribution. Versions are the constraints declared in the manifests; exact resolved
versions are pinned in the lockfiles (`workshop_app/frontend/package-lock.json`,
`intelligent-ai-finops/package-lock.json`) and, for the intelligent-ai-finops backend, as exact
`==` pins in `intelligent-ai-finops/requirements.txt`.
Security and version updates are tracked automatically by Dependabot
(`.github/dependabot.yml`) for both `pip` and `npm`.

> **How to reproduce this audit.** Python: `pip install pip-licenses && pip-licenses` inside
> `workshop_app/` (and `intelligent-ai-finops/`). Frontend: `npx license-checker --summary`
> inside `workshop_app/frontend/` (and `intelligent-ai-finops/`). Frontend licenses below were
> confirmed against installed `node_modules/*/package.json`.

## workshop_app — Python backend

Source of truth: `workshop_app/pyproject.toml` and `workshop_app/requirements.txt`.

| Library | Constraint | License | Purpose | Source |
|---|---|---|---|---|
| fastapi | >=0.115 | MIT | HTTP API framework | https://github.com/fastapi/fastapi |
| uvicorn | >=0.32 | BSD-3-Clause | ASGI server | https://github.com/encode/uvicorn |
| databricks-sdk | >=0.38 | Apache-2.0 | Databricks REST/SDK client (all workspace calls) | https://github.com/databricks/databricks-sdk-py |
| pydantic | >=2.9 | MIT | Request/response validation | https://github.com/pydantic/pydantic |
| pyyaml | >=6.0 | MIT | Parse the YAML config that drives the app | https://github.com/yaml/pyyaml |
| python-multipart | >=0.0.12 | Apache-2.0 | Multipart form parsing (FastAPI uploads) | https://github.com/Kludex/python-multipart |
| reportlab | >=4.2 | BSD-3-Clause | Server-side PDF leave-behinds (brochure, prerequisites, outcomes) | https://github.com/MrBitBucket/reportlab-mirror |

## workshop_app — frontend (runtime)

Source of truth: `workshop_app/frontend/package.json` (`dependencies`).

| Package | Version | License | Purpose | Source |
|---|---|---|---|---|
| react | 19.2.3 | MIT | UI library | https://github.com/facebook/react |
| react-dom | 19.2.3 | MIT | React DOM renderer | https://github.com/facebook/react |
| lucide-react | 0.562.0 | ISC | Icon set | https://github.com/lucide-icons/lucide |
| clsx | 2.1.1 | MIT | Conditional className builder | https://github.com/lukeed/clsx |
| tailwind-merge | 3.4.0 | MIT | Merge conflicting Tailwind classes | https://github.com/dcastil/tailwind-merge |

## workshop_app — frontend (dev / build only)

Source of truth: `workshop_app/frontend/package.json` (`devDependencies`). Not shipped in the
served bundle; used only to build `frontend/dist`.

| Package | Version | License | Purpose | Source |
|---|---|---|---|---|
| vite | 8.0.1 | MIT | Build tool / dev server | https://github.com/vitejs/vite |
| @vitejs/plugin-react | 6.0.1 | MIT | React support for Vite | https://github.com/vitejs/vite-plugin-react |
| @tailwindcss/vite | 4.2.2 | MIT | Tailwind CSS Vite plugin | https://github.com/tailwindlabs/tailwindcss |
| typescript | 5.9.3 | Apache-2.0 | TypeScript compiler | https://github.com/microsoft/TypeScript |
| @types/node | 25.0.3 | MIT | Node.js type definitions | https://github.com/DefinitelyTyped/DefinitelyTyped |
| @types/react | 19.2.7 | MIT | React type definitions | https://github.com/DefinitelyTyped/DefinitelyTyped |
| @types/react-dom | 19.2.3 | MIT | React DOM type definitions | https://github.com/DefinitelyTyped/DefinitelyTyped |

## intelligent-ai-finops — Python backend

Source of truth: `intelligent-ai-finops/requirements.txt` (exact `==` pins).

| Library | Version | License | Purpose | Source |
|---|---|---|---|---|
| fastapi | 0.141.1 | MIT | HTTP API framework (serves `./dist` + `/api`) | https://github.com/fastapi/fastapi |
| uvicorn | 0.52.2 | BSD-3-Clause | ASGI server | https://github.com/encode/uvicorn |
| databricks-sdk | 0.133.0 | Apache-2.0 | Workspace auth + Model Serving access | https://github.com/databricks/databricks-sdk-py |
| pydantic | 2.13.4 | MIT | Request/response models | https://github.com/pydantic/pydantic |
| pyyaml | 6.0.3 | MIT | Parse `config/*.yaml` (model registry + routing policy) | https://github.com/yaml/pyyaml |
| requests | 2.34.2 | Apache-2.0 | HTTP calls to the FMAPI `/invocations` endpoint | https://github.com/psf/requests |
| mlflow-skinny | 3.15.2 | Apache-2.0 | Best-effort LLM-as-judge run logging | https://github.com/mlflow/mlflow |

## intelligent-ai-finops — frontend (runtime)

Source of truth: `intelligent-ai-finops/package.json` (`dependencies`).

| Package | Version | License | Purpose | Source |
|---|---|---|---|---|
| react | 18.3.1 | MIT | UI library | https://github.com/facebook/react |
| react-dom | 18.3.1 | MIT | React DOM renderer | https://github.com/facebook/react |
| zustand | 4.5.7 | MIT | Client state store (session) | https://github.com/pmndrs/zustand |
| @dnd-kit/core | 6.3.1 | MIT | Drag-and-drop (drop a question into the gateway) | https://github.com/clauderic/dnd-kit |
| @dnd-kit/sortable | 8.0.0 | MIT | Sortable helpers for dnd-kit | https://github.com/clauderic/dnd-kit |
| @dnd-kit/utilities | 3.2.2 | MIT | CSS/transform utilities for dnd-kit | https://github.com/clauderic/dnd-kit |

## intelligent-ai-finops — frontend (dev / build only)

Source of truth: `intelligent-ai-finops/package.json` (`devDependencies`). Not shipped in the
served bundle; used only to build `dist/`. (This app uses Tailwind v3 + PostCSS + Autoprefixer,
whereas `workshop_app` uses the Tailwind v4 `@tailwindcss/vite` plugin — both MIT.)

| Package | Version | License | Purpose | Source |
|---|---|---|---|---|
| vite | 5.4.21 | MIT | Build tool / dev server | https://github.com/vitejs/vite |
| @vitejs/plugin-react | 4.7.0 | MIT | React support for Vite | https://github.com/vitejs/vite-plugin-react |
| tailwindcss | 3.4.19 | MIT | Utility CSS | https://github.com/tailwindlabs/tailwindcss |
| postcss | 8.5.26 | MIT | CSS processing (Tailwind pipeline) | https://github.com/postcss/postcss |
| autoprefixer | 10.5.4 | MIT | CSS vendor prefixing | https://github.com/postcss/autoprefixer |
| typescript | 5.9.3 | Apache-2.0 | TypeScript compiler | https://github.com/microsoft/TypeScript |
| @types/react | 18.3.31 | MIT | React type definitions | https://github.com/DefinitelyTyped/DefinitelyTyped |
| @types/react-dom | 18.3.7 | MIT | React DOM type definitions | https://github.com/DefinitelyTyped/DefinitelyTyped |
| vitest | 2.1.9 | MIT | Unit test runner | https://github.com/vitest-dev/vitest |
| @playwright/test | 1.62.1 | Apache-2.0 | Browser test runner (dev/CI only) | https://github.com/microsoft/playwright |

## accelerators — reference notebooks

The accelerator notebooks pin no runtime dependencies in the repo — each notebook `%pip
install`s what it needs so it runs standalone on Databricks. The libraries they commonly
install, all permissively licensed:

| Library | License | Purpose | Source |
|---|---|---|---|
| databricks-sdk | Apache-2.0 | Databricks SDK for Python | https://github.com/databricks/databricks-sdk-py |
| databricks-mcp | Apache-2.0 | Databricks MCP client (tools/list, tools/call) | https://github.com/databricks/databricks-mcp |
| mlflow | Apache-2.0 | ML lifecycle platform | https://github.com/mlflow/mlflow |
| openai | Apache-2.0 | OpenAI-compatible client (Gateway calls) | https://github.com/openai/openai-python |
| requests | Apache-2.0 | HTTP client | https://github.com/psf/requests |
| polars | MIT | DataFrame library | https://github.com/pola-rs/polars |

## Tooling (not distributed)

| Tool | License | Purpose | Source |
|---|---|---|---|
| ruff | MIT | Lint the lab notebook sources (`pyproject.toml`, run via `uvx`) | https://github.com/astral-sh/ruff |
