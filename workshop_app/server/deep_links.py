"""Deep links into the Databricks workspace UI (subset ported from l200_demo)."""
from .config import get_config, get_workspace_client


def _host() -> str:
    host = get_workspace_client().config.host or ""
    return host.rstrip("/")


def serving_endpoint(name: str) -> str:
    return f"{_host()}/ml/endpoints/{name}"


def mcp_service(service: str) -> str:
    return f"{_host()}/ai-gateway/mcp-services/{service}"


def experiment(experiment_id: str) -> str:
    return f"{_host()}/ml/experiments/{experiment_id}"


def system_audit() -> str:
    return f"{_host()}/explore/data/system/access/audit"


def resolve(kind: str) -> str:
    """Resolve a deep_link name referenced in steps.yaml to a URL."""
    cfg = get_config()
    if kind == "serving_endpoint":
        return serving_endpoint(cfg.get("governed_endpoint", {}).get("name", ""))
    if kind == "mcp_service":
        return mcp_service(cfg.get("mcp", {}).get("builtin_service", ""))
    if kind == "experiment":
        exp = cfg.get("mlflow", {}).get("experiment_id", "")
        return experiment(exp) if exp else f"{_host()}/ml/experiments"
    if kind == "system_audit":
        return system_audit()
    if kind == "account_budgets":
        # Account console budgets live at the account level, not the workspace host.
        return "https://accounts.cloud.databricks.com/usage/budgets"
    return _host()
