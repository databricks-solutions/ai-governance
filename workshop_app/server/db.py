"""Lakebase (Postgres) pool for workshop progress tracking.

Same pattern as the internal app: per-connection OAuth token minted by instance name,
lazy conninfo resolution at startup, search_path pinned to an app-owned schema.
"""
import os
import uuid

import psycopg
from psycopg_pool import ConnectionPool

from .config import get_config, get_workspace_client

_w = get_workspace_client()


def _lakebase_cfg() -> dict:
    return get_config().get("lakebase", {})


INSTANCE = os.environ.get("PGINSTANCE") or _lakebase_cfg().get("instance_name", "ai-governance-workshop")
SCHEMA = os.environ.get("PGSCHEMA") or _lakebase_cfg().get("schema", "workshop")


class OAuthConnection(psycopg.Connection):
    @classmethod
    def connect(cls, conninfo="", **kwargs):
        cred = _w.database.generate_database_credential(
            request_id=str(uuid.uuid4()), instance_names=[INSTANCE]
        )
        kwargs["password"] = cred.token
        return super().connect(conninfo, **kwargs)


def _host() -> str:
    host = os.environ.get("PGHOST")
    if host:
        return host
    return _w.database.get_database_instance(name=INSTANCE).read_write_dns


def _user() -> str:
    user = os.environ.get("PGUSER")
    if user:
        return user
    me = _w.current_user.me()
    if getattr(me, "emails", None):
        return me.emails[0].value
    return me.user_name


def _conninfo() -> str:
    return (
        f"dbname={os.environ.get('PGDATABASE', _lakebase_cfg().get('database', 'databricks_postgres'))} "
        f"user={_user()} host={_host()} port={os.environ.get('PGPORT', '5432')} "
        f"sslmode={os.environ.get('PGSSLMODE', 'require')} options='-csearch_path={SCHEMA}'"
    )


class _LazyPool(ConnectionPool):
    def __init__(self):
        super().__init__(conninfo="", connection_class=OAuthConnection,
                         min_size=1, max_size=10, max_lifetime=2700, open=False)

    def open(self, *args, **kwargs):
        if not self.conninfo:
            self.conninfo = _conninfo()
        return super().open(*args, **kwargs)


pool = _LazyPool()

_DDL = """
CREATE SCHEMA IF NOT EXISTS workshop;
SET search_path TO workshop;

-- One row per (workshop run, step). A "run" is keyed by a workspace/team label so
-- multiple teams can track progress independently on the same deployment.
CREATE TABLE IF NOT EXISTS step_progress (
    run_id       TEXT        NOT NULL,      -- team/workspace label
    step_id      TEXT        NOT NULL,
    pillar_id    TEXT        NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'not_started'
                 CHECK (status IN ('not_started', 'in_progress', 'done', 'failed')),
    last_result  JSONB,                      -- last Try-It / Verify output
    notes        TEXT,
    updated_by   TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, step_id)
);
CREATE INDEX IF NOT EXISTS ix_progress_run ON step_progress (run_id);
"""


def init_schema() -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_DDL)
        conn.commit()
