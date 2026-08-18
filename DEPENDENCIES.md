# Third-party dependency audit

This repository ships two distributables, each with its own dependency set:

- **`workshop_app/`** — the customer-facing AI Governance Workshop app (FastAPI backend +
  React/Vite frontend).
- **`labs/`** — Databricks notebooks. Each notebook `%pip install`s its own dependencies at
  runtime, so the repo pins no lab runtime dependencies; the top-level `pyproject.toml` only
  configures `ruff` for local linting.

Every dependency below is released under a permissive OSS license
(**MIT / BSD-3-Clause / ISC / Apache-2.0**). There are **no copyleft (GPL/LGPL/AGPL) and no
source-available/commercially-restricted** dependencies, so the repository is clean for
external distribution. Versions are the constraints declared in the manifests; exact resolved
versions are pinned in the lockfiles (`workshop_app/frontend/package-lock.json`).
Security and version updates are tracked automatically by Dependabot
(`.github/dependabot.yml`) for both `pip` and `npm`.

> **How to reproduce this audit.** Python: `pip install pip-licenses && pip-licenses` inside
> `workshop_app/`. Frontend: `npx license-checker --summary` inside `workshop_app/frontend/`.
> Frontend licenses below were confirmed against installed `node_modules/*/package.json`.

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

## labs — notebooks

The labs pin no runtime dependencies in the repo — each notebook `%pip install`s what it needs
so it runs standalone on Databricks. The libraries the labs commonly install, all
permissively licensed:

| Library | License | Purpose | Source |
|---|---|---|---|
| databricks-sdk | Apache-2.0 | Databricks SDK for Python | https://github.com/databricks/databricks-sdk-py |
| mlflow | Apache-2.0 | ML lifecycle platform | https://github.com/mlflow/mlflow |
| openai | Apache-2.0 | OpenAI-compatible client (Gateway calls) | https://github.com/openai/openai-python |
| requests | Apache-2.0 | HTTP client | https://github.com/psf/requests |
| polars | MIT | DataFrame library | https://github.com/pola-rs/polars |

## Tooling (not distributed)

| Tool | License | Purpose | Source |
|---|---|---|---|
| ruff | MIT | Lint the lab notebook sources (`pyproject.toml`, run via `uvx`) | https://github.com/astral-sh/ruff |
