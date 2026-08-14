"""Progress store — a static JSON file on a Unity Catalog volume.

Replaces the old Lakebase (Postgres) store. A workshop tracks a handful of steps against one
Account ID; that does not need a database. Progress lives in a single JSON file on a UC volume
(created by the asset bundle), read into memory at startup and rewritten on every update.

Why a volume, not a database: the customer ships this in their OWN workspace to try the
platform out, and a Postgres instance to provision — wait for AVAILABLE, grant CONNECT on,
keep running — is a barrier that buys nothing here. A volume is created by the same bundle,
carries the same Unity Catalog grants as the workshop schema, and has no separate lifecycle.

Durability model: single-writer, write-through. A Databricks App runs as one process, so an
in-memory dict is the source of truth for reads; every write updates it and rewrites the whole
file (it is tiny — one object per account per step). If the volume is briefly unreachable the
workshop keeps running on the in-memory copy and the next write retries the persist. Losing
saved progress is recoverable; losing the app is not — so nothing here ever raises to a caller.
"""
from __future__ import annotations

import io
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from .config import get_config, get_workspace_client

log = logging.getLogger("uvicorn.error")

# One lock guards both the in-memory map and the file write, so a concurrent Try-It from two
# attendees can never interleave a half-serialized file.
_LOCK = threading.RLock()

# {customer_sfid: {step_id: {pillar_id, status, last_result, notes, updated_by, updated_at}}}
_MEM: dict[str, dict[str, dict[str, Any]]] = {}


def _vol_cfg() -> dict:
    return get_config().get("volume", {}) or {}


def _file_path() -> str:
    """`/Volumes/<catalog>/<schema>/<volume>/<file>` — same catalog/schema the bundle uses.

    Catalog/schema come from config (which the bundle pins via env), so the file always lands
    in the schema the bundle created the volume in — the two cannot drift apart.
    """
    cat = get_config().get("catalog", {}) or {}
    catalog, schema = cat.get("name"), cat.get("schema")
    if not catalog or not schema:
        raise RuntimeError(
            "catalog.name / catalog.schema must be set to locate the progress volume."
        )
    volume = _vol_cfg().get("name", "workshop_state")
    fname = _vol_cfg().get("file", "progress.json")
    return f"/Volumes/{catalog}/{schema}/{volume}/{fname}"


def load() -> None:
    """Read the progress file into memory. Best-effort: a missing/unreachable file starts empty.

    Called once at startup. A NOT_FOUND on the very first deploy is the normal case — the file
    is created lazily on the first save — so it is logged at info, not warning.
    """
    with _LOCK:
        try:
            path = _file_path()
            resp = get_workspace_client().files.download(path)
            raw = resp.contents.read()
            data = json.loads(raw) if raw else {}
            _MEM.clear()
            if isinstance(data, dict):
                _MEM.update(data)
            log.info("Progress store loaded from %s (%d account(s)).", path, len(_MEM))
        except Exception as e:  # noqa: BLE001 — any failure just means we start empty
            log.info("Progress store starting empty (%s).", str(e)[:200])


def _persist() -> None:
    """Rewrite the whole file. Caller must hold _LOCK. Never raises — a failed write is logged
    and the in-memory copy stays authoritative so the workshop continues uninterrupted."""
    try:
        path = _file_path()
        body = json.dumps(_MEM, separators=(",", ":")).encode("utf-8")
        get_workspace_client().files.upload(path, io.BytesIO(body), overwrite=True)
    except Exception as e:  # noqa: BLE001
        log.warning("Could not persist progress to the volume (kept in memory): %s", str(e)[:200])


def get(customer_sfid: str) -> dict[str, dict[str, Any]]:
    """{step_id: record} for one account. A copy, so callers cannot mutate the store."""
    with _LOCK:
        return json.loads(json.dumps(_MEM.get(customer_sfid, {})))


def save(
    customer_sfid: str,
    step_id: str,
    pillar_id: str,
    status: str,
    result: dict | None = None,
    updated_by: str | None = None,
    notes: str | None = None,
) -> None:
    """Upsert one (account, step). Write-through: update memory, then rewrite the file.

    COALESCE semantics match the old SQL: a progress-only update (result/notes = None) keeps
    the previous Try-It result and notes rather than clearing them.
    """
    with _LOCK:
        acct = _MEM.setdefault(customer_sfid, {})
        prev = acct.get(step_id, {})
        acct[step_id] = {
            "pillar_id": pillar_id,
            "status": status,
            "last_result": result if result is not None else prev.get("last_result"),
            "notes": notes if notes is not None else prev.get("notes"),
            "updated_by": updated_by,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _persist()
