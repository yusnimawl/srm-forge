"""SQLite store for jobs, cases and results.

Every call opens its own connection, so the job runner's worker thread and the
request handlers can use one Store concurrently.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, request TEXT NOT NULL,
    status TEXT NOT NULL, progress TEXT, error TEXT,
    created TEXT NOT NULL, started TEXT, finished TEXT);
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL, parent_case_id TEXT,
    origin TEXT NOT NULL, label TEXT, inputs TEXT NOT NULL, flag TEXT,
    comment TEXT, show_in_graphs INTEGER NOT NULL DEFAULT 1,
    stale INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS results (
    job_id TEXT NOT NULL, case_id TEXT, body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS results_job ON results (job_id);
CREATE INDEX IF NOT EXISTS cases_job ON cases (job_id);
"""

_FINAL = ("done", "failed", "cancelled", "interrupted")
_COLUMNS = "id, kind, request, status, progress, error, created, started, finished"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(obj) -> str:
    return json.dumps(obj, allow_nan=False)


def _job(row: sqlite3.Row, with_request: bool = True) -> dict:
    d = dict(row)
    d["progress"] = None if d["progress"] is None else json.loads(d["progress"])
    if with_request:
        d["request"] = json.loads(d["request"])
    else:
        d.pop("request")
    return d


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        with self._db() as con:
            found = con.execute("PRAGMA user_version").fetchone()[0]
            if found not in (0, SCHEMA_VERSION):
                raise RuntimeError(
                    f"database schema {found} != expected {SCHEMA_VERSION}")
            con.execute("PRAGMA journal_mode = WAL")
            con.executescript(_SCHEMA)
            con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @contextmanager
    def _db(self):
        with closing(sqlite3.connect(self.path, timeout=30)) as con:
            con.row_factory = sqlite3.Row
            with con:  # commit or roll back
                yield con

    def create_job(self, kind: str, request: dict) -> str:
        job_id = str(uuid.uuid4())
        with self._db() as con:
            con.execute(
                "INSERT INTO jobs (id, kind, request, status, created)"
                " VALUES (?, ?, ?, 'queued', ?)",
                (job_id, kind, _dumps(request), _now()))
        return job_id

    def get_job(self, job_id: str) -> dict | None:
        with self._db() as con:
            row = con.execute(
                f"SELECT {_COLUMNS} FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return None if row is None else _job(row)

    def list_jobs(self) -> list[dict]:
        with self._db() as con:
            rows = con.execute(
                f"SELECT {_COLUMNS} FROM jobs ORDER BY created DESC, rowid DESC"
            ).fetchall()
        return [_job(r, with_request=False) for r in rows]

    def set_status(self, job_id: str, status: str, *, error: str | None = None):
        sets, args = ["status = ?", "error = ?"], [status, error]
        if status == "running":
            sets.append("started = ?")
            args.append(_now())
        elif status in _FINAL:
            sets.append("finished = ?")
            args.append(_now())
        with self._db() as con:
            con.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?",
                        (*args, job_id))

    def set_progress(self, job_id: str, progress: dict):
        with self._db() as con:
            con.execute("UPDATE jobs SET progress = ? WHERE id = ?",
                        (_dumps(progress), job_id))

    def put_result(self, job_id: str, body: dict, case_id: str | None = None):
        text = _dumps(body)
        with self._db() as con:
            con.execute("INSERT INTO results (job_id, case_id, body) VALUES (?, ?, ?)",
                        (job_id, case_id, text))

    def get_result(self, job_id: str) -> dict | None:
        with self._db() as con:
            row = con.execute(
                "SELECT body FROM results WHERE job_id = ? ORDER BY rowid DESC",
                (job_id,)).fetchone()
        return None if row is None else json.loads(row["body"])

    def delete_job(self, job_id: str) -> bool:
        with self._db() as con:
            con.execute("DELETE FROM results WHERE job_id = ?", (job_id,))
            con.execute("DELETE FROM cases WHERE job_id = ?", (job_id,))
            return con.execute(
                "DELETE FROM jobs WHERE id = ?", (job_id,)).rowcount > 0

    def mark_running_interrupted(self) -> int:
        with self._db() as con:
            return con.execute(
                "UPDATE jobs SET status = 'interrupted', finished = ?"
                " WHERE status = 'running'", (_now(),)).rowcount
