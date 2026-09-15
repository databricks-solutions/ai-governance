"""V2: durable store on the app's Autoscaling Lakebase (Postgres + pgvector).

Backs three things across app restarts and replicas (not just one process):
  - the cost-overview cache (the multi-second system-tables scan) - `finops.cache`,
  - the router / fallback policy config - `finops.cache`,
  - the semantic cache (see semcache.py) - `finops.semcache` (a pgvector table).

Driver is **pg8000** (pure-Python, BSD-3-Clause) - deliberately not psycopg (LGPL),
so this ships in a permissively-licensed public repo. pg8000 has no built-in pool,
so this module keeps a tiny thread-safe idle pool + a cached OAuth token.

Auth is the App service principal via **Autoscaling** Lakebase OAuth: a credential
minted for the branch endpoint (`LAKEBASE_ENDPOINT`), passed as the Postgres password.
The SP authenticates as its own federated Postgres role (created once with
`databricks postgres create-role ... identity_type=SERVICE_PRINCIPAL`; see V2_SETUP.md).
If Lakebase is unreachable every call degrades to None and the caller falls back to
its in-process cache - the app never hard-fails.
"""
from __future__ import annotations

import json
import os
import ssl
import threading
import time
from collections import deque
from typing import Callable, TypeVar

# Autoscaling Lakebase: an ENDPOINT path (projects/<p>/branches/<b>/endpoints/<e>),
# not a flat instance name. Host is the endpoint's connection host.
_ENDPOINT = os.environ.get("LAKEBASE_ENDPOINT", "")
_HOST = os.environ.get("LAKEBASE_HOST", "")
_DB = os.environ.get("LAKEBASE_DB", "databricks_postgres")

_MAX_IDLE = 4
_MAX_CONN_AGE_S = 2400.0   # recycle a connection before the ~1h OAuth token expires
_TOKEN_TTL_S = 2400.0      # refresh the cached credential well before 1h
_COOLDOWN_S = 300.0        # circuit-breaker cooldown after a failure

_lock = threading.Lock()
_idle: deque = deque()     # (connection, created_ts) available for reuse
_degraded_until = 0.0
_available: bool | None = None
_tok = {"val": None, "exp": 0.0}
_w = None

T = TypeVar("T")


def _trip() -> None:
    global _degraded_until, _available
    _degraded_until = time.time() + _COOLDOWN_S
    _available = False


def _tripped() -> bool:
    return time.time() < _degraded_until


def _client():
    global _w
    if _w is None:
        from databricks.sdk import WorkspaceClient
        _w = WorkspaceClient()
    return _w


def _user() -> str:
    # The SP authenticates as its own client id (its federated Postgres role name).
    return os.environ.get("DATABRICKS_CLIENT_ID") or _client().current_user.me().user_name


def _token() -> str:
    now = time.time()
    with _lock:
        if not _tok["val"] or now > _tok["exp"]:
            cred = _client().postgres.generate_database_credential(endpoint=_ENDPOINT)
            _tok["val"] = cred.token
            _tok["exp"] = now + _TOKEN_TTL_S
        return _tok["val"]


def _new_conn():
    import pg8000.dbapi
    conn = pg8000.dbapi.connect(
        user=_user(), password=_token(), host=_HOST, port=5432,
        database=_DB, ssl_context=ssl.create_default_context(),
    )
    conn.autocommit = True
    return conn


def _acquire():
    """A reusable idle connection (younger than the token lifetime), else a new one."""
    with _lock:
        while _idle:
            conn, ts = _idle.popleft()
            if time.time() - ts < _MAX_CONN_AGE_S:
                return conn, ts
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    return _new_conn(), time.time()


def _release(conn, ts, ok: bool) -> None:
    if ok:
        with _lock:
            if len(_idle) < _MAX_IDLE:
                _idle.append((conn, ts))
                return
    try:
        conn.close()
    except Exception:  # noqa: BLE001
        pass


def with_conn(fn: Callable[[object], T]) -> T | None:
    """Run fn(cursor) on a pooled autocommit connection. Returns fn's result, or None
    if Lakebase is unavailable / the call errors (which trips the breaker). Single
    entry point so the pool, credential refresh, and breaker live in one place."""
    global _available
    if not (_ENDPOINT and _HOST) or _tripped():
        _available = False
        return None
    conn = None
    ts = 0.0
    try:
        conn, ts = _acquire()
        cur = conn.cursor()
        try:
            res = fn(cur)
        finally:
            cur.close()
        _release(conn, ts, True)
        _available = True
        return res
    except Exception:  # noqa: BLE001 - unreachable/slow → close, trip, degrade to in-process
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        _trip()
        return None


def get(key: str, max_age_s: float) -> dict | None:
    """Return the cached payload if present and fresher than max_age_s, else None."""
    def _q(cur):
        cur.execute(
            "SELECT payload, extract(epoch FROM now() - updated_at) FROM finops.cache WHERE key = %s",
            (key,))
        row = cur.fetchone()
        if row and row[1] is not None and float(row[1]) < max_age_s:
            payload = row[0]
            return json.loads(payload) if isinstance(payload, str) else payload
        return None
    return with_conn(_q)


def put(key: str, payload: dict) -> bool:
    """Persist a payload. Returns True if the write actually landed, False if
    Lakebase was unreachable (the caller can then report saved:false honestly)."""
    def _w(cur):
        cur.execute(
            "INSERT INTO finops.cache (key, payload, updated_at) VALUES (%s, %s::jsonb, now()) "
            "ON CONFLICT (key) DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()",
            (key, json.dumps(payload)))
        return True
    return with_conn(_w) is True


def available() -> bool:
    """Live ping (SELECT 1) through the pool; False fast when the breaker is tripped."""
    return with_conn(lambda cur: (cur.execute("SELECT 1"), cur.fetchone())[1][0]) == 1
