"""Smoke tests for the Intelligent AI FinOps backend.

Deliberately dependency-light and offline (FINOPS_DEMO_MODE=true, set in conftest.py):
they boot the FastAPI app and exercise the always-available routes so a dependency bump
(fastapi / pydantic / databricks-sdk / mlflow-skinny) that breaks import or request
handling fails here instead of in front of a customer. They do NOT touch Model Serving,
a warehouse, or Lakebase — those paths are covered by live mode, not these tests.
"""
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_app_boots_with_expected_metadata():
    assert app.title == "Intelligent AI FinOps"


def test_core_routes_are_registered():
    paths = {getattr(r, "path", None) for r in app.routes}
    for expected in ("/api/health", "/api/config", "/v1/chat/completions"):
        assert expected in paths, f"route {expected} is not registered"


def test_health_endpoint_ok():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_config_endpoint_serves_model_registry():
    # /api/config reads config/*.yaml (pyyaml) and the pydantic-modelled registry — a good
    # canary that config loading and model serialization survive the dependency bumps.
    resp = client.get("/api/config")
    assert resp.status_code == 200
    body = resp.json()
    assert "models" in body and isinstance(body["models"], list)
