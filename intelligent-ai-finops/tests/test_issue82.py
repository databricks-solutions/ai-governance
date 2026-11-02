"""Regression tests for the backend bugs tracked in issue #82.

Offline like test_smoke.py: Lakebase, the embedding endpoint, and the SQL warehouse
are replaced with fakes, so these run without any workspace.
"""
from types import SimpleNamespace

import pytest

from backend import compress, datasource, gateway, judge, models, proxy, semcache


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    # No Lakebase in tests: with_conn returns None (the "unavailable" path) unless a
    # test swaps in its own fake.
    monkeypatch.setattr(semcache.lakebase, "with_conn", lambda fn: None)
    semcache._store.clear()
    yield
    semcache._store.clear()


EMB = [1.0, 0.0, 0.0]


def _put(prompt, served_id):
    semcache._put_local(prompt, EMB, {"answer": served_id}, {"servedId": served_id})


# ---- 1) semantic cache must not cross models --------------------------------------

def test_lookup_filters_by_served_model():
    _put("what is a lakehouse", "endpoint-a")
    assert semcache.lookup("what is a lakehouse", 0.9, embedding=EMB, served_ids=["endpoint-b"]) is None
    hit = semcache.lookup("what is a lakehouse", 0.9, embedding=EMB, served_ids=["endpoint-a"])
    assert hit and hit["meta"]["servedId"] == "endpoint-a"
    # No filter keeps the old behaviour.
    assert semcache.lookup("what is a lakehouse", 0.9, embedding=EMB) is not None


def test_durable_lookup_sql_filters_by_served_model(monkeypatch):
    seen = {}

    class Cur:
        def execute(self, sql, args):
            seen["sql"], seen["args"] = sql, args

        def fetchone(self):
            return None

    monkeypatch.setattr(semcache.lakebase, "with_conn", lambda fn: fn(Cur()))
    semcache._durable_lookup("q", EMB, 0.9, ["endpoint-a"])
    assert "meta->>'servedId' = ANY(%s::text[])" in seen["sql"]
    assert ["endpoint-a"] in seen["args"]
    # The two vector placeholders still line up with their arguments.
    assert seen["sql"].count("%s") == len(seen["args"])

    semcache._durable_lookup("q", EMB, 0.9)
    assert "servedId" not in seen["sql"]
    assert seen["sql"].count("%s") == len(seen["args"])


def test_passthrough_request_never_served_another_models_cache(monkeypatch):
    reg = models.registry()
    pinned, other = reg[0], reg[1]
    _put("explain unity catalog", other.id)
    monkeypatch.setattr(proxy, "load_config", lambda: {"demoMode": False})
    monkeypatch.setattr(proxy, "_saved_policy", lambda: {})
    monkeypatch.setattr(semcache, "embed", lambda text: EMB)
    captured = {}
    real_lookup = semcache.lookup

    def spy(*a, **kw):
        captured["served_ids"] = kw.get("served_ids")
        return real_lookup(*a, **kw)

    monkeypatch.setattr(semcache, "lookup", spy)

    class Stop(Exception):
        pass

    # A miss falls through to classification; stop there so no model is called.
    def stop(*a, **kw):
        raise Stop

    monkeypatch.setattr(semcache, "note_miss", stop)
    with pytest.raises(Stop):
        proxy.serve([{"role": "user", "content": "explain unity catalog"}], requested_model=pinned.id)
    assert captured["served_ids"] == [pinned.id]


# ---- 2) clear() must clear the durable tier too -----------------------------------

def test_clear_also_deletes_durable_rows(monkeypatch):
    executed = []
    monkeypatch.setattr(semcache.lakebase, "with_conn",
                        lambda fn: fn(SimpleNamespace(execute=lambda sql, *a: executed.append(sql))))
    _put("q", "endpoint-a")
    semcache.clear()
    assert semcache._store == []
    assert "DELETE FROM finops.semcache" in executed


# ---- 3) a slow warehouse must raise, not return [] --------------------------------

class _FakeSE:
    def __init__(self, states, rows=None):
        self.states = list(states)
        self.rows = rows
        self.cancelled = False

    def _resp(self):
        from databricks.sdk.service.sql import StatementState
        state = StatementState[self.states.pop(0)]
        done = state == StatementState.SUCCEEDED
        return SimpleNamespace(
            statement_id="s1",
            status=SimpleNamespace(state=state, error=SimpleNamespace(message="boom")),
            result=SimpleNamespace(data_array=self.rows) if done else None,
            manifest=SimpleNamespace(schema=SimpleNamespace(columns=[SimpleNamespace(name="n")])),
        )

    def execute_statement(self, **kw):
        return self._resp()

    def get_statement(self, sid):
        return self._resp()

    def cancel_execution(self, sid):
        self.cancelled = True


def _patch_ws(monkeypatch, se):
    import databricks.sdk
    monkeypatch.setattr(databricks.sdk, "WorkspaceClient", lambda: SimpleNamespace(statement_execution=se))
    monkeypatch.setattr(datasource.time, "sleep", lambda s: None)


def test_run_polls_until_succeeded(monkeypatch):
    se = _FakeSE(["PENDING", "RUNNING", "SUCCEEDED"], rows=[["7"]])
    _patch_ws(monkeypatch, se)
    assert datasource._run("wh", "select 7") == [{"n": "7"}]


def test_run_raises_and_cancels_on_timeout(monkeypatch):
    se = _FakeSE(["PENDING"] * 5)
    _patch_ws(monkeypatch, se)
    monkeypatch.setattr(datasource, "_SQL_TIMEOUT_S", 0)
    with pytest.raises(TimeoutError):
        datasource._run("wh", "select 1")
    assert se.cancelled


def test_run_raises_on_failed_statement(monkeypatch):
    _patch_ws(monkeypatch, _FakeSE(["FAILED"]))
    with pytest.raises(RuntimeError, match="FAILED"):
        datasource._run("wh", "select 1")


# ---- 4) rate-limit map must evict idle users --------------------------------------

def test_rate_limiter_evicts_idle_users(monkeypatch):
    gateway._RL.clear()
    clock = [1000.0]
    monkeypatch.setattr(gateway.time, "time", lambda: clock[0])
    monkeypatch.setattr(gateway, "_RL_LAST_SWEEP", 0.0)
    for i in range(50):
        gateway._rate_check(f"user{i}", 60)
    assert len(gateway._RL) == 50
    clock[0] += 61
    gateway._rate_check("fresh", 60)
    assert list(gateway._RL) == ["fresh"]
    # Limiting itself is unchanged.
    for _ in range(2):
        gateway._rate_check("fresh", 3)
    assert gateway._rate_check("fresh", 3) == (False, 3)


# ---- 5) compression stats stay consistent -----------------------------------------

@pytest.mark.parametrize("text", ["", "ok", "Hi.", "Could you please really just explain this?  Thanks"])
def test_compression_stats_consistent(text):
    r = compress.compress_prompt(text)
    assert r["savedPct"] >= 0
    assert r["savedTokens"] == r["tokensBefore"] - r["tokensAfter"]
    if r["savedTokens"] == 0:
        assert r["savedPct"] == 0


# ---- 6) judge must not read an unrelated ratio as the score ------------------------

@pytest.mark.parametrize("text,expected", [
    ('{"score": 8, "reason": "good"}', 8.0),
    ('{"score": 7, "reason": "covers 3/10 steps', 7.0),
    ("Score: 9", 9.0),
    ("Rating: 6/10", 6.0),
    ("8/10", 8.0),
    ("The answer covers 3/10 of the required steps.", None),
    ("It handles 2/10 edge cases and is otherwise fine", None),
])
def test_judge_score_extraction(text, expected):
    assert judge._extract_score_reason(text)[0] == expected


# ---- Lakebase driver: pg8000 must match the installed scramp ----------------------

def test_pg8000_only_uses_scramp_functions_that_exist():
    # scramp 1.5.0 removed make_channel_binding; pg8000 1.31.5 still called it on every
    # connect, so Lakebase silently degraded to in-process (with_conn swallows errors).
    # This catches that class of break offline, without a database.
    import ast
    import inspect

    import pg8000.core
    import scramp

    tree = ast.parse(inspect.getsource(pg8000.core))
    used = {n.attr for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "scramp"}
    assert used, "expected pg8000.core to reference scramp"
    assert not [a for a in used if not hasattr(scramp, a)]
