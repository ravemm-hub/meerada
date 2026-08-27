"""Local SQLite store for the free CLI — zero infrastructure required.

Stores metadata-only Traces (plus the in-tenant assembly context: session id and
explicit task id). The tenant salt lives in the local meta table and never
leaves this file. Postgres arrives via config in later phases.
"""

import secrets
import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

from handover.assemble import AttemptRecord
from handover.schema.trace import Trace

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    trace_id TEXT PRIMARY KEY,
    ts_start TEXT NOT NULL,
    session_id TEXT,
    explicit_task_id TEXT,
    trace_json TEXT NOT NULL
);
"""


class SqliteStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _meta(self, key: str, default_factory: str | None = None) -> str:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        if row is not None:
            return str(row[0])
        if default_factory is None:
            raise KeyError(key)
        self._conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (key, default_factory))
        self._conn.commit()
        return default_factory

    def salt(self) -> str:
        """Stable per-database salt, generated once. Never leaves this machine."""
        return self._meta("salt", secrets.token_hex(32))

    def tenant_id(self) -> UUID:
        return UUID(self._meta("tenant_id", str(uuid4())))

    def add_records(self, records: list[AttemptRecord]) -> int:
        rows = [
            (
                str(record.trace.trace_id),
                record.trace.ts_start.isoformat(),
                record.session_id,
                str(record.explicit_task_id) if record.explicit_task_id else None,
                record.trace.model_dump_json(),
            )
            for record in records
        ]
        self._conn.executemany(
            "INSERT OR REPLACE INTO records "
            "(trace_id, ts_start, session_id, explicit_task_id, trace_json) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def load_records(self) -> list[AttemptRecord]:
        rows = self._conn.execute(
            "SELECT session_id, explicit_task_id, trace_json FROM records ORDER BY ts_start"
        ).fetchall()
        return [
            AttemptRecord(
                trace=Trace.model_validate_json(trace_json),
                session_id=session_id,
                explicit_task_id=UUID(explicit) if explicit else None,
            )
            for session_id, explicit, trace_json in rows
        ]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM records").fetchone()[0])
