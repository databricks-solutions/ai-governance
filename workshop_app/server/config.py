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
    """Load config/workshop.yaml, preferring workshop.local.yaml if present."""
    override = os.environ.get("WORKSHOP_CONFIG")
    for candidate in (override, _CONFIG_DIR / "workshop.local.yaml", _CONFIG_DIR / "workshop.yaml"):
        if candidate and Path(candidate).exists():
            with open(candidate) as f:
                return yaml.safe_load(f)
    raise FileNotFoundError("No workshop.yaml found in config/.")


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
    wid = os.environ.get("DATABRICKS_WAREHOUSE_ID") or get_config().get("workspace", {}).get("warehouse_id")
    if not wid:
        raise RuntimeError("No SQL warehouse configured (workspace.warehouse_id or DATABRICKS_WAREHOUSE_ID).")
    return wid
