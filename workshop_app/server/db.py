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

-- One row per (account, step). The whole workshop is tracked against one Salesforce
-- account id, so progress and the outcomes export flow straight into the sales app.
CREATE TABLE IF NOT EXISTS step_progress (
    customer_sfid TEXT       NOT NULL,      -- Salesforce account id
    step_id      TEXT        NOT NULL,
    pillar_id    TEXT        NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'not_started'
                 CHECK (status IN ('not_started', 'in_progress', 'done', 'failed')),
    last_result  JSONB,                      -- last Try-It / Verify output
    notes        TEXT,
    updated_by   TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_sfid, step_id)
);
CREATE INDEX IF NOT EXISTS ix_progress_sfid ON step_progress (customer_sfid);
"""


# Idempotent migration: earlier versions keyed step_progress on run_id. Rename the
# column to customer_sfid in place (the PK/index follow the column) so existing
# deployments keep their data. Safe to run every startup — no-op once migrated.
_MIGRATE = """
SET search_path TO workshop;
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'workshop' AND table_name = 'step_progress' AND column_name = 'run_id'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'workshop' AND table_name = 'step_progress' AND column_name = 'customer_sfid'
  ) THEN
    ALTER TABLE step_progress RENAME COLUMN run_id TO customer_sfid;
  END IF;
END $$;
"""


def init_schema() -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_MIGRATE)   # migrate legacy run_id column before ensuring schema
            cur.execute(_DDL)
        conn.commit()
