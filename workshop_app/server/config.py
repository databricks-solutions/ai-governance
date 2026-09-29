"""Config loader + auth helpers (dual-mode: Databricks App vs local dev)."""
from __future__ import annotations

import contextvars
import os
from functools import lru_cache
from pathlib import Path

import yaml
from databricks.sdk import WorkspaceClient

IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))
_CONFIG_DIR = Path(__file__).parent.parent / "config"

# The signed-in user's forwarded access token for the CURRENT request, set by the /test route
# from the `X-Forwarded-Access-Token` header (Databricks Apps user authorization). It lets a
# test call downstream services AS the user (on-behalf-of), not as the app's service principal.
# A ContextVar because a test function takes no request argument - the route sets it around the
# call and clears it after. Per-request only: user tokens expire in ~1h, so it is never cached.
_forwarded_user_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "forwarded_user_token", default=None)


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
    # The progress-volume name is a bundle variable too, so it must flow to the app the same
    # way catalog/schema do - otherwise `--var=progress_volume=...` creates one volume while
    # the app writes to the default-named path, and progress silently lands nowhere.
    volume = os.environ.get("WORKSHOP_VOLUME")
    if volume:
        cfg.setdefault("volume", {})
        cfg["volume"]["name"] = volume
    return cfg


@lru_cache(maxsize=1)
def get_steps() -> dict:
    with open(_CONFIG_DIR / "steps.yaml") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def get_accelerators() -> dict:
    with open(_CONFIG_DIR / "accelerators.yaml") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def get_prerequisites() -> dict:
    with open(_CONFIG_DIR / "prerequisites.yaml") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def get_brochure() -> dict:
    with open(_CONFIG_DIR / "brochure.yaml") as f:
        return yaml.safe_load(f)


def get_workspace_client() -> WorkspaceClient:
    if IS_DATABRICKS_APP:
        return WorkspaceClient()
    profile = os.environ.get("DATABRICKS_PROFILE", "DEFAULT")
    return WorkspaceClient(profile=profile)


def set_forwarded_token(token: str | None) -> contextvars.Token:
    """Record the current request's forwarded user token; returns a reset handle for the route."""
    return _forwarded_user_token.set(token or None)


def reset_forwarded_token(handle: contextvars.Token) -> None:
    _forwarded_user_token.reset(handle)


def has_user_token() -> bool:
    """True only when an on-behalf-of call would ACTUALLY run as the user - i.e. a forwarded
    token is present AND we are in the Databricks App runtime. Must match the condition in
    get_user_workspace_client(), or a caller (t_mcp_obo) could claim OBO it did not perform.
    """
    return bool(_forwarded_user_token.get()) and IS_DATABRICKS_APP


def get_user_workspace_client() -> WorkspaceClient:
    """A client authenticated AS the signed-in user (on-behalf-of), for calls that must run as
    the caller rather than the app service principal - e.g. MCP tool invocation. Falls back to
    the app-SP client when no forwarded token is present (local dev, or user authorization not
    enabled), so callers must check `has_user_token()` before *claiming* OBO in their result.
    """
    token = _forwarded_user_token.get()
    if token and IS_DATABRICKS_APP:
        host = (os.environ.get("DATABRICKS_HOST") or WorkspaceClient().config.host or "").rstrip("/")
        # auth_type="pat" forces the SDK to authenticate with ONLY this bearer token. Without it
        # the ambient app-SP OAuth env vars (DATABRICKS_CLIENT_ID/SECRET) ALSO match and the SDK
        # refuses with "more than one authorization method configured: oauth and pat".
        return WorkspaceClient(host=host, token=token, auth_type="pat")
    return get_workspace_client()


def governed_service_fqn() -> str:
    """The governed model service as a Unity Catalog FQN `<catalog>.<schema>.<service>`.

    `governed_endpoint.service` in config is either a bare service name (resolved against the
    workshop's own catalog.schema) or an already-qualified FQN such as `system.ai.<model>`
    (used verbatim). Returns "" when nothing is configured. This replaces the old flat v1
    serving-endpoint name - every governed step addresses this FQN on the Unity Gateway path.
    """
    cfg = get_config()
    ge = cfg.get("governed_endpoint", {}) or {}
    svc = (ge.get("service") or "").strip()
    if not svc:
        return ""
    if svc.count(".") >= 2:            # already fully qualified (e.g. system.ai.claude-...)
        return svc
    cat = (cfg.get("catalog", {}) or {}).get("name")
    sch = (cfg.get("catalog", {}) or {}).get("schema")
    if not (cat and sch):
        # Cannot build a fully qualified name without catalog/schema. Return "" rather than a
        # bare service name so callers report "not configured" instead of chasing a 404 on an
        # unqualified path. (Missing catalog is already surfaced by config_problems() on /health.)
        return ""
    return f"{cat}.{sch}.{svc}"


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

    DATABRICKS_WAREHOUSE_ID wins: the bundle sets it on the app from the `warehouse_id`
    variable (databricks.yml → apps.*.config.env), so the value passed to
    `bundle deploy --var="warehouse_id=..."` is authoritative. config/workshop.yaml is the
    local-development fallback.
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
            "catalog.name is empty in config/workshop.yaml - set it to a catalog that "
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
