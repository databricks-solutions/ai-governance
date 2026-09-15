"""Discover REAL agent tools from the workspace = Unity Catalog functions.

In Databricks, the agent-framework "tool" primitive is a UC function: a registered
function with a description and typed parameters that a model can call. This module
reads them from `information_schema` (routines + parameters) for a configured
catalog.schema and builds the same tool-schema shape the compressor prunes - so the
tool-selection story runs against the customer's OWN registered tools, not a demo
stub. Falls back to the sample catalog when none are configured/reachable, so the
app never hard-fails and still demos offline.

Configure with FINOPS_TOOLS_CATALOG / FINOPS_TOOLS_SCHEMA (a warehouse is already
configured for the cost tab and is reused here).
"""
from __future__ import annotations

import os
import time

_CATALOG = os.environ.get("FINOPS_TOOLS_CATALOG", "")
_SCHEMA = os.environ.get("FINOPS_TOOLS_SCHEMA", "")
_TTL = 300.0
_cache: tuple[float, list[dict], str] | None = None  # (ts, tools, source)

_TYPE_MAP = {
    "STRING": "string", "VARCHAR": "string", "CHAR": "string",
    "INT": "integer", "INTEGER": "integer", "BIGINT": "integer", "SMALLINT": "integer",
    "DOUBLE": "number", "FLOAT": "number", "DECIMAL": "number",
    "BOOLEAN": "boolean", "ARRAY": "array", "MAP": "object", "STRUCT": "object",
}


def _json_type(sql_type: str) -> str:
    return _TYPE_MAP.get((sql_type or "").upper().split("(")[0].split("<")[0].strip(), "string")


def _discover(warehouse_id: str, catalog: str, schema: str) -> list[dict]:
    """Read UC functions in catalog.schema and build tool schemas. Raises on failure."""
    from . import datasource
    routines = datasource._run(warehouse_id, f"""
        SELECT specific_name, routine_name, coalesce(comment,'') AS comment
        FROM {catalog}.information_schema.routines
        WHERE routine_schema = '{schema}'
    """)
    if not routines:
        return []
    params = datasource._run(warehouse_id, f"""
        SELECT specific_name, parameter_name, data_type, ordinal_position
        FROM {catalog}.information_schema.parameters
        WHERE specific_schema = '{schema}' AND parameter_name IS NOT NULL
        ORDER BY specific_name, ordinal_position
    """)
    by_fn: dict[str, list] = {}
    for p in params:
        by_fn.setdefault(p["specific_name"], []).append(p)
    tools = []
    for r in routines:
        props = {p["parameter_name"]: {"type": _json_type(p["data_type"])}
                 for p in by_fn.get(r["specific_name"], [])}
        tools.append({
            "name": r["routine_name"],
            "description": r["comment"] or r["routine_name"],
            "parameters": {"type": "object", "properties": props},
        })
    return sorted(tools, key=lambda t: t["name"])


def catalog() -> tuple[list[dict], str]:
    """Return (tools, source). Real UC functions when configured + reachable (source
    'uc:<catalog>.<schema>'), else the sample set (source 'sample'). Cached."""
    global _cache
    from . import compress
    if not (_CATALOG and _SCHEMA):
        return compress.SAMPLE_TOOLS, "sample"
    now = time.time()
    if _cache and now - _cache[0] < _TTL:
        return _cache[1], _cache[2]
    from .appconfig import load_config
    wid = load_config().get("warehouseId")
    if not wid:
        return compress.SAMPLE_TOOLS, "sample"
    try:
        tools = _discover(wid, _CATALOG, _SCHEMA)
        if tools:
            src = f"uc:{_CATALOG}.{_SCHEMA}"
            _cache = (now, tools, src)
            return tools, src
    except Exception:  # noqa: BLE001 - discovery is best-effort; fall back to sample
        pass
    return compress.SAMPLE_TOOLS, "sample"
