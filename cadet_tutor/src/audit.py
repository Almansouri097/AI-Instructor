"""Local SQLite audit log of every retrieval: who asked what, and which documents came back.

The app wraps each request in `audit.context(user, level, mode)`; `retrieve.search`
then records every query made inside it, so no mode can skip the log.
The log is append-only from the app: nothing in the code updates or deletes rows.
"""
import contextlib
import contextvars
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from src import config

SCHEMA = """CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,          -- UTC, ISO 8601
    user TEXT NOT NULL,
    level INTEGER NOT NULL,    -- clearance used for the query
    mode TEXT NOT NULL,        -- ask / quiz / order / evaluate
    query TEXT NOT NULL,
    docs TEXT NOT NULL,        -- JSON list of retrieved document names
    labels TEXT NOT NULL,      -- JSON list of retrieved citation labels
    max_level INTEGER,         -- highest clearance level among retrieved chunks
    flags TEXT NOT NULL        -- JSON list, e.g. ["possible prompt injection in [doc, p.2]"]
)"""


@dataclass
class Who:
    user: str
    level: int
    mode: str


_current: contextvars.ContextVar[Who | None] = contextvars.ContextVar("audit_who", default=None)


@contextlib.contextmanager
def context(user: str, level: int, mode: str):
    """Attribute every query made inside this block to `user` in `mode`."""
    token = _current.set(Who(user, level, mode))
    try:
        yield
    finally:
        _current.reset(token)


def _connect() -> sqlite3.Connection:
    config.AUDIT_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.AUDIT_DB)
    con.execute(SCHEMA)
    return con


def record(query: str, level: int, hits: list, flags: list[str]) -> None:
    """Write one row. Queries made outside an audit context are logged as 'unknown'."""
    who = _current.get() or Who("unknown", level, "unknown")
    row = (
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        who.user, level, who.mode, query,
        json.dumps(sorted({h.doc for h in hits}), ensure_ascii=False),
        json.dumps([h.label for h in hits], ensure_ascii=False),
        max((h.level for h in hits), default=None),
        json.dumps(flags, ensure_ascii=False),
    )
    with contextlib.closing(_connect()) as con, con:
        con.execute("INSERT INTO audit (ts, user, level, mode, query, docs, labels, max_level, flags) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", row)


def rows(limit: int = 500) -> list[dict]:
    """Most recent entries first."""
    if not config.AUDIT_DB.exists():
        return []
    with contextlib.closing(_connect()) as con:
        con.row_factory = sqlite3.Row
        out = [dict(r) for r in con.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]
    for r in out:
        for key in ("docs", "labels", "flags"):
            r[key] = json.loads(r[key])
    return out
