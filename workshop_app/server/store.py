"""Progress store — a static JSON file on a Unity Catalog volume.

Replaces the old Lakebase (Postgres) store. The app is deployed once per workshop and tracks a
handful of steps for that one deployment; that does not need a database. Progress lives in a
single JSON file on a UC volume (created by the asset bundle), read into memory at startup and
rewritten on every update.

Why a volume, not a database: the customer ships this in their OWN workspace to try the
platform out, and a Postgres instance to provision — wait for AVAILABLE, grant CONNECT on,
keep running — is a barrier that buys nothing here. A volume is created by the same bundle,
carries the same Unity Catalog grants as the workshop schema, and has no separate lifecycle.

Durability model: single-writer, write-through. A Databricks App runs as one process, so an
in-memory dict is the source of truth for reads; every write updates it and rewrites the whole
file (it is tiny — one object per step). If the volume is briefly unreachable the
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

# {step_id: {pillar_id, status, last_result, notes, updated_by, outcome, poc, updated_at}}
# `status`/`last_result` track the interactive Try-It test; `outcome` ("done"|"na"|None) and
# `poc` (bool) are the hand-set outcome flags set from a step card or the outcomes checklist.
_MEM: dict[str, dict[str, Any]] = {}

# The imported workshop-recommendations doc (scope schema v2) from the internal app or the
# sheet-driven export: the four-decision plan, blocking prerequisites, recommended accelerator.
# Stored in its own volume file so it never mixes with the flat {step_id: record} progress map.
_RECS: dict[str, Any] = {}

# Sentinel so set_outcome can tell "leave this flag unchanged" from "clear it to None/False".
_UNSET = object()


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


def _recs_file_path() -> str:
    """Sibling of the progress file on the same volume, for the imported recommendations doc."""
    cat = get_config().get("catalog", {}) or {}
    catalog, schema = cat.get("name"), cat.get("schema")
    if not catalog or not schema:
        raise RuntimeError("catalog.name / catalog.schema must be set to locate the volume.")
    volume = _vol_cfg().get("name", "workshop_state")
    fname = _vol_cfg().get("recommendations_file", "recommendations.json")
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
                # New format is flat: {step_id: {status, pillar_id, ...}}. An older file may be
                # nested by account ({account_id: {step_id: {...}}}); flatten it (merge all
                # accounts, last writer wins) so an in-place upgrade does not lose progress.
                is_flat = all(isinstance(v, dict) and "status" in v for v in data.values())
                if is_flat:
                    _MEM.update(data)
                else:
                    for acct in data.values():
                        if isinstance(acct, dict):
                            for step_id, rec in acct.items():
                                if isinstance(rec, dict):
                                    _MEM[step_id] = rec
            log.info("Progress store loaded from %s (%d step(s)).", path, len(_MEM))
        except Exception as e:  # noqa: BLE001 — any failure just means we start empty
            log.info("Progress store starting empty (%s).", str(e)[:200])
        # Imported recommendations doc (best-effort; absent until a scope is imported).
        try:
            resp = get_workspace_client().files.download(_recs_file_path())
            raw = resp.contents.read()
            data = json.loads(raw) if raw else {}
            _RECS.clear()
            if isinstance(data, dict):
                _RECS.update(data)
        except Exception as e:  # noqa: BLE001
            log.info("No imported recommendations yet (%s).", str(e)[:200])


def _persist() -> None:
    """Rewrite the whole file. Caller must hold _LOCK. Never raises — a failed write is logged
    and the in-memory copy stays authoritative so the workshop continues uninterrupted."""
    try:
        path = _file_path()
        body = json.dumps(_MEM, separators=(",", ":")).encode("utf-8")
        get_workspace_client().files.upload(path, io.BytesIO(body), overwrite=True)
    except Exception as e:  # noqa: BLE001
        log.warning("Could not persist progress to the volume (kept in memory): %s", str(e)[:200])


def _persist_recs() -> None:
    """Rewrite the recommendations file. Caller holds _LOCK. Never raises (logged; memory wins)."""
    try:
        body = json.dumps(_RECS, separators=(",", ":")).encode("utf-8")
        get_workspace_client().files.upload(_recs_file_path(), io.BytesIO(body), overwrite=True)
    except Exception as e:  # noqa: BLE001
        log.warning("Could not persist recommendations to the volume (kept in memory): %s", str(e)[:200])


def get_recommendations() -> dict[str, Any]:
    """The imported workshop-recommendations doc (a copy), or {} if none imported yet."""
    with _LOCK:
        return json.loads(json.dumps(_RECS))


def set_recommendations(doc: dict[str, Any]) -> None:
    """Store the imported recommendations doc (the panel reads it back). Write-through."""
    with _LOCK:
        _RECS.clear()
        _RECS.update(doc or {})
        _persist_recs()


def get() -> dict[str, dict[str, Any]]:
    """{step_id: record} for this workshop. A copy, so callers cannot mutate the store."""
    with _LOCK:
        return json.loads(json.dumps(_MEM))


def save(
    step_id: str,
    pillar_id: str,
    status: str,
    result: dict | None = None,
    updated_by: str | None = None,
    notes: str | None = None,
) -> None:
    """Upsert one step. Write-through: update memory, then rewrite the file.

    COALESCE semantics match the old SQL: a progress-only update (result/notes = None) keeps
    the previous Try-It result and notes rather than clearing them.
    """
    with _LOCK:
        prev = _MEM.get(step_id, {})
        _MEM[step_id] = {
            "pillar_id": pillar_id,
            "status": status,
            "last_result": result if result is not None else prev.get("last_result"),
            "notes": notes if notes is not None else prev.get("notes"),
            "updated_by": updated_by if updated_by is not None else prev.get("updated_by"),
            # Manual outcome flags are never touched by a test run / status update — preserve them.
            "outcome": prev.get("outcome"),
            "poc": prev.get("poc", False),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _persist()


def set_outcome(
    step_id: str,
    pillar_id: str,
    outcome: Any = _UNSET,
    poc: Any = _UNSET,
    updated_by: str | None = None,
) -> None:
    """Set the hand-marked outcome flags for a step, independent of the interactive test.

    `outcome` is "done" | "na" | None — Done and N/A are mutually exclusive, and None clears
    both. `poc` flags the step for the POC follow-up. Either arg left unset is preserved
    (COALESCE), so toggling one control never clears the other, and the interactive
    `status`/`last_result` are left untouched. A step counts as achieved if EITHER the test ran
    `done` OR `outcome == "done"`.
    """
    with _LOCK:
        prev = _MEM.get(step_id, {})
        _MEM[step_id] = {
            "pillar_id": pillar_id,
            "status": prev.get("status", "not_started"),
            "last_result": prev.get("last_result"),
            "notes": prev.get("notes"),
            "updated_by": updated_by if updated_by is not None else prev.get("updated_by"),
            "outcome": prev.get("outcome") if outcome is _UNSET else outcome,
            "poc": prev.get("poc", False) if poc is _UNSET else bool(poc),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _persist()


def reset() -> int:
    """Clear all workshop progress and rewrite the (now empty) file — used to start the room
    fresh, e.g. re-running the workshop or clearing a demo deployment. Returns how many steps
    were cleared. Write-through like every other mutation; never raises (a failed persist keeps
    the cleared in-memory state and is logged)."""
    with _LOCK:
        n = len(_MEM)
        _MEM.clear()
        _persist()
        _RECS.clear()          # a fresh room drops the imported recommendations too
        _persist_recs()
        log.info("Progress store reset (%d step(s) cleared).", n)
        return n
