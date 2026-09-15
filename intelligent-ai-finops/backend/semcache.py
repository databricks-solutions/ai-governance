"""V2 semantic cache - dedupe semantically-equivalent prompts to serve at ~$0/~0ms.

The biggest single FinOps lever: if a question (or a paraphrase of it) has already
been answered, return the stored answer instead of paying a model again. We embed
the prompt with a real Databricks embedding endpoint (default databricks-gte-large-en,
1024-dim), and on a new request find the nearest cached prompt by cosine similarity;
above the threshold it's a HIT (no model call, full answer cost saved).

Two tiers, mirroring the rest of the app:
  - in-process: a bounded, TTL'd list scanned with cosine similarity. Always works,
    so the cache is demoable live even when Lakebase is unreachable.
  - durable (pgvector on Autoscaling Lakebase): the shared/persistent L2, where
    embeddings live in a `vector(1024)` column (finops.semcache) and lookup is an ANN
    `<=>` cosine query. `put` writes both tiers; a `lookup` L1 miss falls through to
    L2 and hydrates L1 on a hit. So cached answers survive page reloads, app restarts,
    and replicas (the `entries` count in stats() is the shared durable row count). The
    hit/miss/savedUsd counters, by contrast, are per-instance session figures (in
    memory), not a cross-replica total. Degrades to L1 only if Lakebase is unreachable
    (same circuit breaker as the cost cache).

Everything degrades safely: if the embedding endpoint is unavailable, lookup returns
None and the proxy just serves normally (cache disabled), never hard-failing.
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
import time

from . import lakebase

_EMBED_ENDPOINT = os.environ.get("FINOPS_EMBED_ENDPOINT", "databricks-gte-large-en")
_MAX_ENTRIES = int(os.environ.get("FINOPS_SEMCACHE_MAX", "500"))
_TTL_S = float(os.environ.get("FINOPS_SEMCACHE_TTL_S", "3600"))
# Durable (L2) freshness window: longer than L1 (it persists across restarts) but
# still bounded so pgvector never serves a stale answer as fresh. Also drives the
# opportunistic prune on write, keeping finops.semcache from growing unbounded.
_DURABLE_TTL_S = float(os.environ.get("FINOPS_SEMCACHE_DURABLE_TTL_S", str(7 * 24 * 3600)))
_DEFAULT_THRESHOLD = 0.92

_lock = threading.Lock()
_store: list[dict] = []  # {prompt, emb, norm, response, meta, ts}
_stats = {"hits": 0, "misses": 0, "savedUsd": 0.0}


def embed(text: str) -> list[float] | None:
    """Embed one string via the Databricks embedding endpoint. Returns None on any
    failure so the caller degrades to a normal (uncached) serve."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        import requests
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        host = w.config.host.rstrip("/")
        auth = w.config.authenticate()
        url = f"{host}/serving-endpoints/{_EMBED_ENDPOINT}/invocations"
        resp = requests.post(url, headers=auth, json={"input": [text]}, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data") or []
        if data and isinstance(data[0], dict):
            return data[0].get("embedding")
    except Exception:  # noqa: BLE001 - cache is best-effort; never break a request
        return None
    return None


def _salient(text: str) -> frozenset:
    """Discriminative tokens whose change flips the answer even at ~0.99 cosine:
    numbers, quarters, years, amounts, percentages (e.g. "Q4"/"Q3", "2026"/"2025",
    "$400M"/"$500M", "112%"). Any token containing a digit. Two prompts with
    DIFFERENT salient sets are different questions and must NOT share a cache entry."""
    toks = re.findall(r"\S*\d\S*", (text or "").lower())
    return frozenset(t.strip(".,;:!?()[]{}\"'") for t in toks)


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v)) or 1.0


def _cosine(a: list[float], na: float, b: list[float], nb: float) -> float:
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


# ---- Durable tier (pgvector on Autoscaling Lakebase) ----------------------------
# The in-process store is L1 (fast, per-process). This L2 persists entries in
# finops.semcache so hits survive page reloads, app restarts, and replicas, and the
# saved-$ is real/cumulative. Everything degrades to L1 if Lakebase is unreachable.

def _salient_str(prompt: str) -> str:
    return ",".join(sorted(_salient(prompt)))


def _vec_literal(emb: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in emb) + "]"


def _durable_put(prompt: str, emb: list[float], response: dict, meta: dict) -> None:
    vec, sal = _vec_literal(emb), _salient_str(prompt)

    def _w(cur):
        # Dedup the exact prompt (refresh, don't accumulate duplicates) + prune the
        # expired tail, so the table stays bounded to roughly the TTL window of
        # distinct prompts instead of growing forever.
        cur.execute("DELETE FROM finops.semcache WHERE prompt = %s", (prompt,))
        cur.execute("DELETE FROM finops.semcache WHERE ts < now() - make_interval(secs => %s)", (_DURABLE_TTL_S,))
        cur.execute(
            "INSERT INTO finops.semcache (prompt, salient, embedding, response, meta) "
            "VALUES (%s, %s, %s::vector, %s::jsonb, %s::jsonb)",
            (prompt, sal, vec, json.dumps(response), json.dumps(meta)))
        return True
    lakebase.with_conn(_w)


def _durable_lookup(prompt: str, emb: list[float], th: float) -> dict | None:
    """Nearest neighbour in the durable table with the SAME salient set (the
    numbers/dates guard) AND within the durable TTL, scored by cosine similarity
    (1 - pgvector `<=>`). The TTL filter mirrors L1's freshness so L2 never serves a
    stale answer as fresh."""
    vec, sal = _vec_literal(emb), _salient_str(prompt)

    def _q(cur):
        cur.execute(
            "SELECT prompt, response, meta, 1 - (embedding <=> %s::vector) AS sim "
            "FROM finops.semcache WHERE salient = %s AND ts > now() - make_interval(secs => %s) "
            "ORDER BY embedding <=> %s::vector LIMIT 1",
            (vec, sal, _DURABLE_TTL_S, vec))
        return cur.fetchone()
    row = lakebase.with_conn(_q)
    if row and row[3] is not None and float(row[3]) >= th:
        resp = row[1] if isinstance(row[1], dict) else json.loads(row[1])
        meta = row[2] if isinstance(row[2], dict) else json.loads(row[2])
        return {"response": resp, "meta": meta, "similarity": round(float(row[3]), 4), "prompt": row[0]}
    return None


def _put_local(prompt: str, emb: list[float], response: dict, meta: dict) -> None:
    entry = {"prompt": prompt, "emb": emb, "norm": _norm(emb), "salient": _salient(prompt),
             "response": response, "meta": meta, "ts": time.time()}
    with _lock:
        _store.append(entry)
        if len(_store) > _MAX_ENTRIES:
            del _store[0:len(_store) - _MAX_ENTRIES]  # evict oldest


def lookup(prompt: str, threshold: float | None = None,
           embedding: list[float] | None = None) -> dict | None:
    """Find the nearest cached prompt by cosine similarity. Returns the stored hit
    (response + meta + similarity) when the best match clears the threshold, else
    None. Reuses a precomputed `embedding` if the caller already has one."""
    th = threshold if threshold is not None else _DEFAULT_THRESHOLD
    emb = embedding if embedding is not None else embed(prompt)
    if not emb:
        return None
    qn = _norm(emb)
    q_sal = _salient(prompt)
    now = time.time()
    best = None
    best_sim = -1.0
    with _lock:
        # Drop expired entries lazily as we scan.
        live = [e for e in _store if now - e["ts"] < _TTL_S]
        if len(live) != len(_store):
            _store[:] = live
        for e in _store:
            # Discriminator guard: skip entries whose numbers/dates/amounts differ from
            # the query - "Q4 2026" and "Q3 2026" embed at ~0.99 but are different asks.
            if e.get("salient") != q_sal:
                continue
            sim = _cosine(emb, qn, e["emb"], e["norm"])
            if sim > best_sim:
                best_sim, best = sim, e
    if best is not None and best_sim >= th:
        return {"response": best["response"], "meta": best["meta"],
                "similarity": round(best_sim, 4), "prompt": best["prompt"]}
    # L1 miss → try the durable L2 (survives restarts/replicas). Hydrate L1 on a hit
    # so the next same-process lookup is instant.
    d = _durable_lookup(prompt, emb, th)
    if d is not None:
        _put_local(prompt, emb, d["response"], d["meta"])
        return d
    return None


def put(prompt: str, response: dict, meta: dict, embedding: list[float] | None = None) -> None:
    """Store a served answer keyed by its prompt embedding: in-process L1 (bounded +
    TTL'd) plus the durable pgvector L2 so the hit survives reloads/restarts."""
    emb = embedding if embedding is not None else embed(prompt)
    if not emb:
        return
    _put_local(prompt, emb, response, meta)
    _durable_put(prompt, emb, response, meta)


def note_hit(saved_usd: float) -> None:
    with _lock:
        _stats["hits"] += 1
        _stats["savedUsd"] += max(0.0, saved_usd)


def note_miss() -> None:
    with _lock:
        _stats["misses"] += 1


def stats() -> dict:
    with _lock:
        hits, misses = _stats["hits"], _stats["misses"]
        total = hits + misses
        l1 = len(_store)
    durable = lakebase.with_conn(lambda cur: (cur.execute("SELECT count(*) FROM finops.semcache"), cur.fetchone())[1][0])
    return {
        "hits": hits, "misses": misses,
        "hitRate": round(hits / total * 100, 1) if total else 0.0,
        "savedUsd": round(_stats["savedUsd"], 6),
        "entries": durable if durable is not None else l1,
        "backend": "lakebase-pgvector" if durable is not None else "in-process",
        "embedEndpoint": _EMBED_ENDPOINT,
        "threshold": _DEFAULT_THRESHOLD,
    }


def clear() -> None:
    """Reset the cache and stats (used by the demo's 'clear cache' control)."""
    with _lock:
        _store.clear()
        _stats.update({"hits": 0, "misses": 0, "savedUsd": 0.0})
