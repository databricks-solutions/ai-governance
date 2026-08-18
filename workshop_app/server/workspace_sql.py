"""Workspace SQL execution + REST helpers (ported from l200_demo/lib/db.py)."""
import time
from typing import Any

from databricks.sdk.service.sql import StatementState

from .config import get_warehouse_id, get_workspace_client

_MAX_WAIT = 50  # per-request poll cap (API allows "0s" or 5-50s)


def execute_sql(sql: str, timeout_seconds: int = 120) -> tuple[list[str], list[list[Any]]]:
    """Run SQL against the configured warehouse; return (columns, rows)."""
    w = get_workspace_client()
    request_wait = max(5, min(timeout_seconds, _MAX_WAIT))
    resp = w.statement_execution.execute_statement(
        warehouse_id=get_warehouse_id(), statement=sql, wait_timeout=f"{request_wait}s"
    )
    elapsed = request_wait
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        if elapsed >= timeout_seconds:
            raise RuntimeError(f"SQL timed out after {elapsed}s")
        time.sleep(2)
        elapsed += 2
        resp = w.statement_execution.get_statement(resp.statement_id)

    if resp.status.state == StatementState.FAILED:
        msg = resp.status.error.message if resp.status.error else "unknown error"
        raise RuntimeError(f"SQL failed: {msg}")
    if resp.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"Unexpected SQL state: {resp.status.state}")

    cols = []
    if resp.manifest and resp.manifest.schema and resp.manifest.schema.columns:
        cols = [c.name for c in resp.manifest.schema.columns]
    rows = resp.result.data_array if (resp.result and resp.result.data_array) else []
    return cols, rows


def fetchall(sql: str, timeout_seconds: int = 120) -> list[dict[str, Any]]:
    cols, rows = execute_sql(sql, timeout_seconds)
    return [dict(zip(cols, r)) for r in rows]


def test_connection() -> bool:
    try:
        execute_sql("SELECT 1 AS ok")
        return True
    except Exception:
        return False
