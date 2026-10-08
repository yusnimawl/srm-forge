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

SCHEMA_VERSION = 2

CASE_ORIGINS = ("candidate", "reference", "import", "edit")
RESULT_KINDS = ("search", "evaluate", "validate")

# Job status groups; the runner, the store and the routes all read these.
ACTIVE = ("queued", "running")
FINAL = ("done", "failed", "cancelled", "interrupted")
RESUMABLE = ("interrupted", "cancelled", "failed")

# Statements run one by one so that a whole (re)creation is a single transaction.
_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, request TEXT NOT NULL,
        status TEXT NOT NULL, progress TEXT, error TEXT,
        created TEXT NOT NULL, started TEXT, finished TEXT)""",
    """CREATE TABLE cases (
        id TEXT PRIMARY KEY, job_id TEXT, parent_case_id TEXT,
        origin TEXT NOT NULL,
        label TEXT, inputs TEXT NOT NULL, flag TEXT, comment TEXT,
        show_in_graphs INTEGER NOT NULL DEFAULT 0,
        stale INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL)""",
    """CREATE TABLE results (
        job_id TEXT, case_id TEXT,
        kind TEXT NOT NULL,
        body TEXT NOT NULL)""",
    "CREATE TABLE map_times (preset TEXT NOT NULL, seconds REAL NOT NULL,"
    " finished TEXT NOT NULL)",
    "CREATE TABLE scan_times (mode TEXT NOT NULL, seconds REAL NOT NULL, finished TEXT NOT NULL)",
    "CREATE INDEX results_job ON results (job_id)",
    "CREATE INDEX results_case ON results (case_id)",
    "CREATE INDEX cases_job ON cases (job_id)",
    "CREATE INDEX map_times_preset ON map_times (preset)",
    "CREATE INDEX scan_times_mode ON scan_times (mode)",
)

# v1 -> v2: cases and results change shape; search results are kept.
_V1_TO_V2_PRE = (
    "DROP TABLE cases",
    "DROP INDEX results_job",
    "ALTER TABLE results RENAME TO results_v1",
)
_V1_TO_V2_POST = (
    "INSERT INTO results (job_id, case_id, kind, body)"
    " SELECT job_id, NULL, 'search', body FROM results_v1 WHERE case_id IS NULL",
    "DROP TABLE results_v1",
)

_CASE_FIELDS = ("label", "flag", "comment", "show_in_graphs", "inputs", "stale")
_CASE_COLUMNS = ("id, job_id, parent_case_id, origin, label, inputs, flag, comment,"
                 " show_in_graphs, stale, created")

_COLUMNS = ("id, kind, request, status, progress, error, created, started, finished,"
            " json_extract(request, '$.case_id') AS case_id")


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


def _case(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["inputs"] = json.loads(d["inputs"])
    d["show_in_graphs"] = bool(d["show_in_graphs"])
    d["stale"] = bool(d["stale"])
    return d


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        with self._db() as con:
            found = con.execute("PRAGMA user_version").fetchone()[0]
            if found not in (0, 1, SCHEMA_VERSION):
                raise RuntimeError(
                    f"database schema {found} != expected {SCHEMA_VERSION}")
            con.execute("PRAGMA journal_mode = WAL")
            if found == SCHEMA_VERSION:
                return
            # An explicit BEGIN keeps the DDL inside the transaction, so a
            # failed migration rolls back and leaves the old file intact.
            con.execute("BEGIN")
            for sql in _V1_TO_V2_PRE if found == 1 else ():
                con.execute(sql)
            for sql in _SCHEMA:
                con.execute(sql)
            for sql in _V1_TO_V2_POST if found == 1 else ():
                con.execute(sql)
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
        elif status in FINAL:
            sets.append("finished = ?")
            args.append(_now())
        with self._db() as con:
            con.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?",
                        (*args, job_id))

    def set_progress(self, job_id: str, progress: dict):
        with self._db() as con:
            con.execute("UPDATE jobs SET progress = ? WHERE id = ?",
                        (_dumps(progress), job_id))

    def put_result(self, job_id: str | None, body: dict, *, kind: str,
                   case_id: str | None = None):
        if kind not in RESULT_KINDS:
            raise ValueError(f"unknown result kind {kind!r}")
        if kind == "evaluate" and case_id is not None:
            raise ValueError("an evaluation is attached to a case with attach_evaluation")
        with self._db() as con:
            con.execute(
                "INSERT INTO results (job_id, case_id, kind, body) VALUES (?, ?, ?, ?)",
                (job_id, case_id, kind, _dumps(body)))

    def attach_evaluation(self, case_id: str, job_id: str | None, body: dict) -> bool:
        """Store an evaluation as the case's and mark the case evaluated, but only while the case is stale: an
        evaluated case never changes. Otherwise (case evaluated or gone) the body is stored as the job's own
        result and False is returned."""
        text = _dumps(body)
        with self._db() as con:
            attached = con.execute("UPDATE cases SET stale = 0, job_id = ? WHERE id = ? AND stale = 1",
                                   (job_id, case_id)).rowcount > 0
            con.execute("INSERT INTO results (job_id, case_id, kind, body) VALUES (?, ?, 'evaluate', ?)",
                        (job_id, case_id if attached else None, text))
        return attached

    def get_result(self, job_id: str) -> dict | None:
        """The job's own result; case results are read with `case_result`."""
        with self._db() as con:
            row = con.execute(
                "SELECT body FROM results WHERE job_id = ? AND case_id IS NULL"
                " ORDER BY rowid DESC", (job_id,)).fetchone()
        return None if row is None else json.loads(row["body"])

    def case_result(self, case_id: str, kind: str) -> dict | None:
        with self._db() as con:
            row = con.execute(
                "SELECT body FROM results WHERE case_id = ? AND kind = ?"
                " ORDER BY rowid DESC", (case_id, kind)).fetchone()
        return None if row is None else json.loads(row["body"])

    def delete_job(self, job_id: str) -> bool:
        with self._db() as con:
            con.execute("DELETE FROM results WHERE job_id = ? AND case_id IS NULL",
                        (job_id,))
            return con.execute(
                "DELETE FROM jobs WHERE id = ?", (job_id,)).rowcount > 0

    def create_case(self, *, origin: str, inputs: dict, label: str,
                    parent_case_id: str | None = None, job_id: str | None = None,
                    stale: bool) -> str:
        if origin not in CASE_ORIGINS:
            raise ValueError(f"unknown case origin {origin!r}")
        case_id = str(uuid.uuid4())
        with self._db() as con:
            con.execute(
                "INSERT INTO cases (id, job_id, parent_case_id, origin, label,"
                " inputs, stale, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (case_id, job_id, parent_case_id, origin, label, _dumps(inputs),
                 int(stale), _now()))
        return case_id

    def get_case(self, case_id: str) -> dict | None:
        with self._db() as con:
            row = con.execute(
                f"SELECT {_CASE_COLUMNS} FROM cases WHERE id = ?", (case_id,)).fetchone()
        return None if row is None else _case(row)

    def list_cases(self) -> list[dict]:
        with self._db() as con:
            rows = con.execute(
                f"SELECT {_CASE_COLUMNS} FROM cases ORDER BY created DESC, rowid DESC"
            ).fetchall()
        return [_case(r) for r in rows]

    def update_case(self, case_id: str, **fields) -> bool:
        unknown = set(fields) - set(_CASE_FIELDS)
        if unknown:
            raise ValueError(f"cannot update case fields {sorted(unknown)}")
        if not fields:
            return self.get_case(case_id) is not None
        values = [_dumps(v) if k == "inputs" else int(v) if isinstance(v, bool) else v
                  for k, v in fields.items()]
        with self._db() as con:
            return con.execute(
                f"UPDATE cases SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                (*values, case_id)).rowcount > 0

    def delete_case(self, case_id: str) -> bool:
        with self._db() as con:
            con.execute("DELETE FROM results WHERE case_id = ?", (case_id,))
            return con.execute(
                "DELETE FROM cases WHERE id = ?", (case_id,)).rowcount > 0

    def case_jobs(self, case_id: str) -> list[dict]:
        """Jobs whose request names the case, newest first."""
        with self._db() as con:
            rows = con.execute(
                f"SELECT {_COLUMNS} FROM jobs"
                " WHERE json_extract(request, '$.case_id') = ?"
                " ORDER BY created DESC, rowid DESC", (case_id,)).fetchall()
        return [_job(r, with_request=False) for r in rows]

    def add_map_time(self, preset: str, seconds: float):
        with self._db() as con:
            con.execute("INSERT INTO map_times (preset, seconds, finished)"
                        " VALUES (?, ?, ?)", (preset, seconds, _now()))

    def recent_map_times(self, preset: str, n: int = 5) -> list[float]:
        """Newest first."""
        with self._db() as con:
            rows = con.execute(
                "SELECT seconds FROM map_times WHERE preset = ?"
                " ORDER BY finished DESC, rowid DESC LIMIT ?", (preset, n)).fetchall()
        return [r["seconds"] for r in rows]

    def add_scan_time(self, mode: str, seconds: float):
        with self._db() as con:
            con.execute("INSERT INTO scan_times (mode, seconds, finished) VALUES (?, ?, ?)",
                        (mode, seconds, _now()))

    def recent_scan_times(self, mode: str, n: int = 5) -> list[float]:
        """Seconds the winding choice took after a map, per winding mode ("auto" or "fixed"); newest first."""
        with self._db() as con:
            rows = con.execute(
                "SELECT seconds FROM scan_times WHERE mode = ?"
                " ORDER BY finished DESC, rowid DESC LIMIT ?", (mode, n)).fetchall()
        return [r["seconds"] for r in rows]

    def mark_running_interrupted(self) -> int:
        with self._db() as con:
            return con.execute(
                "UPDATE jobs SET status = 'interrupted', finished = ?"
                " WHERE status = 'running'", (_now(),)).rowcount
