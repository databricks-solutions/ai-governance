# Puts the finops app root on sys.path so `from backend.main import app` resolves when
# pytest is invoked from this directory (the backend is a package, not an installed dist).
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Smoke tests run fully offline — no Model Serving, warehouse, or Lakebase calls.
os.environ.setdefault("FINOPS_DEMO_MODE", "true")
