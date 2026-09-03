"""Load and merge config/models.yaml + config/policy.yaml (§4).

Prices and policy come from config - never hardcoded in a component or a route.
"""
import os
from functools import lru_cache
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _ROOT / "config"


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


@lru_cache(maxsize=1)
def load_config() -> dict:
    """Merged config the frontend reads via GET /api/config."""
    with open(_CONFIG_DIR / "models.yaml") as f:
        models = yaml.safe_load(f).get("models", [])
    with open(_CONFIG_DIR / "policy.yaml") as f:
        policy = yaml.safe_load(f)

    # Real $ per DBU (the workspace's Model Serving list/negotiated rate). Default
    # 0.07 = published AWS/GCP list rate (matches system.billing.list_prices).
    dbu_to_usd = _env_float("FINOPS_DBU_TO_USD", 0.07)

    return {
        "models": models,
        "policy": policy,
        "dbuToUsd": dbu_to_usd,
        "demoMode": _env_bool("FINOPS_DEMO_MODE", True),
        "judgeEnabled": _env_bool("FINOPS_JUDGE_ENABLED", True),
        "priceFootnote": (
            f"Prices = official Databricks FMAPI DBU rate card × ${dbu_to_usd:g}/DBU "
            f"(Model Serving list rate). Source: databricks.com/product/pricing."
        ),
    }
