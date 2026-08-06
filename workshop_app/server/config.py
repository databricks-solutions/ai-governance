"""Config loader + auth helpers (dual-mode: Databricks App vs local dev)."""
import os
from functools import lru_cache
from pathlib import Path

import yaml
from databricks.sdk import WorkspaceClient

IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))
_CONFIG_DIR = Path(__file__).parent.parent / "config"


@lru_cache(maxsize=1)
def get_config() -> dict:
    """Load config/workshop.yaml, preferring workshop.local.yaml if present.

    Environment variables injected by the bundle win over the file, so the values passed to
    `bundle deploy` are the single source of truth and nobody has to keep the YAML and the
    deploy command in sync. That duplication was previously a live footgun: the bundle
    created one schema while the app wrote to another.
    """
    override = os.environ.get("WORKSHOP_CONFIG")
    cfg = None
    for candidate in (override, _CONFIG_DIR / "workshop.local.yaml", _CONFIG_DIR / "workshop.yaml"):
        if candidate and Path(candidate).exists():
            with open(candidate) as f:
                cfg = yaml.safe_load(f) or {}
            break
    if cfg is None:
        raise FileNotFoundError("No workshop.yaml found in config/.")

    catalog = os.environ.get("WORKSHOP_CATALOG")
    schema = os.environ.get("WORKSHOP_SCHEMA")
    if catalog or schema:
        cfg.setdefault("catalog", {})
        if catalog:
            cfg["catalog"]["name"] = catalog
        if schema:
            cfg["catalog"]["schema"] = schema
    return cfg


@lru_cache(maxsize=1)
def get_steps() -> dict:
    with open(_CONFIG_DIR / "steps.yaml") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def get_accelerators() -> dict:
    with open(_CONFIG_DIR / "accelerators.yaml") as f:
        return yaml.safe_load(f)


def get_workspace_client() -> WorkspaceClient:
    if IS_DATABRICKS_APP:
        return WorkspaceClient()
    profile = os.environ.get("DATABRICKS_PROFILE", "DEFAULT")
    return WorkspaceClient(profile=profile)


def get_oauth_token() -> str:
    w = get_workspace_client()
    if w.config.token:
        return w.config.token
    headers = w.config.authenticate()
    if headers and "Authorization" in headers:
        return headers["Authorization"].removeprefix("Bearer ")
    raise RuntimeError("Could not resolve a bearer token from the SDK.")


def get_warehouse_id() -> str:
    """The SQL warehouse the app runs statements against.

    DATABRICKS_WAREHOUSE_ID wins: app.yaml binds it to the bundle's `sql-warehouse`
    resource, so the value passed to `bundle deploy --var="warehouse_id=..."` is
    authoritative. config/workshop.yaml is the local-development fallback.
    """
    wid = (os.environ.get("DATABRICKS_WAREHOUSE_ID")
           or get_config().get("workspace", {}).get("warehouse_id"))
    if not wid:
        raise RuntimeError(
            "No SQL warehouse configured. Deployed: pass "
            '--var="warehouse_id=<id>" to `bundle deploy`. Local: set '
            "workspace.warehouse_id in config/workshop.yaml or DATABRICKS_WAREHOUSE_ID."
        )
    return wid


def config_problems() -> list[str]:
    """Config values that must be set before the workshop will work.

    Checked at startup and exposed on /api/health so a misconfigured deploy is caught
    before a room full of people starts clicking Try It, rather than surfacing as a
    confusing per-step SQL error.
    """
    cfg = get_config()
    problems = []
    cat = cfg.get("catalog", {}) or {}
    if not cat.get("name"):
        problems.append(
            "catalog.name is empty in config/workshop.yaml — set it to a catalog that "
            "exists on this workspace (and pass the same value as the bundle's `catalog` "
            "variable so the schema is created in the right place)."
        )
    if not cat.get("schema"):
        problems.append("catalog.schema is empty in config/workshop.yaml.")
    try:
        get_warehouse_id()
    except RuntimeError as e:
        problems.append(str(e))
    return problems
