"""Loader for the workshop's plain-SQL queries.

The analytical queries the workshop runs live in `workshop_app/queries/*.sql` as plain,
copy-runnable SQL rather than buried in Python strings — so a customer can open the repo,
read exactly what the app asks their workspace, and paste any query straight into a SQL
editor. This module reads those files and fills in the few placeholders the app needs.

Placeholders use the `${name}` form. The app substitutes an already-safe value (a quoted
string literal via tests_registry._sql_str, or a validated integer). When you run a `.sql`
file by hand, replace each `${name}` with a literal — every file's header comment says what
goes where.
"""
import re
from functools import lru_cache
from pathlib import Path

_PLACEHOLDER_RE = re.compile(r"\$\{[A-Za-z0-9_]+\}")

_QUERIES_DIR = Path(__file__).parent.parent / "queries"


@lru_cache(maxsize=None)
def _read(name: str) -> str:
    path = _QUERIES_DIR / f"{name}.sql"
    if not path.exists():
        raise FileNotFoundError(f"No query file {name}.sql in {_QUERIES_DIR}")
    return path.read_text()


def load_query(name: str, **subs: str) -> str:
    """Return the SQL in queries/<name>.sql with ${key} placeholders replaced.

    Values must already be SQL-safe (a quoted literal or a validated integer) — this does a
    literal string replace and applies no quoting of its own. Every `${key}` in the file must
    be supplied, and every supplied key must appear in the file, so a rename can't silently
    leave a placeholder unfilled.
    """
    sql = _read(name)
    for key, value in subs.items():
        token = "${" + key + "}"
        if token not in sql:
            raise KeyError(f"Query {name}.sql has no placeholder {token}")
        sql = sql.replace(token, str(value))
    leftover = _PLACEHOLDER_RE.findall(sql)
    if leftover:
        raise KeyError(f"Query {name}.sql still has unfilled placeholder(s): {sorted(set(leftover))}")
    return sql
