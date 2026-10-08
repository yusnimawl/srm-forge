import sqlite3
from contextlib import closing

import pytest

from srmweb.store import Store


def test_roundtrip_and_order(tmp_path):
    s = Store(tmp_path / "a.db")
    a = s.create_job("search", {"n": 1})
    b = s.create_job("evaluate", {"n": 2})
    job = s.get_job(a)
    assert job["request"] == {"n": 1} and job["status"] == "queued"
    assert job["started"] is None and job["finished"] is None and job["created"]
    assert s.get_job("nope") is None
    jobs = s.list_jobs()
    assert [j["id"] for j in jobs] == [b, a] and "request" not in jobs[0]


def test_status_timestamps_and_progress(tmp_path):
    s = Store(tmp_path / "a.db")
    j = s.create_job("search", {})
    s.set_status(j, "running")
    assert s.get_job(j)["started"] and not s.get_job(j)["finished"]
    s.set_progress(j, {"points_done": 3})
    s.set_status(j, "failed", error="ValueError: x")
    got = s.get_job(j)
    assert got["finished"] and got["error"] == "ValueError: x"
    assert got["progress"] == {"points_done": 3}


def test_result_nan_and_delete(tmp_path):
    s = Store(tmp_path / "a.db")
    j = s.create_job("search", {})
    with pytest.raises(ValueError):
        s.put_result(j, {"x": float("nan")}, kind="search")
    s.put_result(j, {"x": 1}, kind="search")
    assert s.get_result(j) == {"x": 1}
    assert s.delete_job(j) is True and s.delete_job(j) is False
    assert s.get_result(j) is None and s.get_job(j) is None


def test_mark_running_interrupted(tmp_path):
    s = Store(tmp_path / "a.db")
    r, q = s.create_job("search", {}), s.create_job("search", {})
    s.set_status(r, "running")
    assert s.mark_running_interrupted() == 1
    assert s.get_job(r)["status"] == "interrupted" and s.get_job(r)["finished"]
    assert s.get_job(q)["status"] == "queued"


def test_schema_mismatch(tmp_path):
    p = tmp_path / "a.db"
    Store(p)
    con = sqlite3.connect(p)
    con.execute("PRAGMA user_version = 3")
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="database schema 3 != expected 2"):
        Store(p)


_V1_DDL = """
CREATE TABLE jobs (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, request TEXT NOT NULL,
    status TEXT NOT NULL, progress TEXT, error TEXT,
    created TEXT NOT NULL, started TEXT, finished TEXT);
CREATE TABLE cases (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL, parent_case_id TEXT,
    origin TEXT NOT NULL, label TEXT, inputs TEXT NOT NULL, flag TEXT,
    comment TEXT, show_in_graphs INTEGER NOT NULL DEFAULT 1,
    stale INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);
CREATE TABLE results (
    job_id TEXT NOT NULL, case_id TEXT, body TEXT NOT NULL);
CREATE INDEX results_job ON results (job_id);
CREATE INDEX cases_job ON cases (job_id);
"""


def _v1_file(path, extra=""):
    with closing(sqlite3.connect(path)) as con:
        con.executescript(_V1_DDL + extra)
        con.execute("INSERT INTO jobs (id, kind, request, status, created)"
                    " VALUES ('j1', 'search', '{\"n\": 1}', 'done', 't')")
        con.execute("INSERT INTO results (job_id, body) VALUES ('j1', '{\"x\": 1}')")
        con.execute("PRAGMA user_version = 1")
        con.commit()


def _version(path):
    with closing(sqlite3.connect(path)) as con:
        return con.execute("PRAGMA user_version").fetchone()[0]


def test_v1_database_migrates_and_keeps_runs(tmp_path):
    p = tmp_path / "v1.db"
    _v1_file(p)
    s = Store(p)
    assert _version(p) == 2
    assert s.get_job("j1")["request"] == {"n": 1}
    assert s.get_result("j1") == {"x": 1}
    with closing(sqlite3.connect(p)) as con:
        assert con.execute("SELECT kind FROM results WHERE job_id = 'j1'").fetchone()[0] == "search"
    c = s.create_case(origin="reference", inputs={}, label="r", stale=True)
    assert s.get_case(c)["show_in_graphs"] is False
    s.add_map_time("full", 1.0)
    Store(p)  # reopening a v2 file is a no-op
    assert s.get_result("j1") == {"x": 1}


def test_failed_migration_leaves_v1_file_intact(tmp_path):
    p = tmp_path / "v1.db"
    _v1_file(p, "CREATE TABLE map_times (preset TEXT);")  # blocks the v2 DDL
    with pytest.raises(sqlite3.Error):
        Store(p)
    assert _version(p) == 1
    with closing(sqlite3.connect(p)) as con:
        assert con.execute("SELECT body FROM results WHERE job_id = 'j1'").fetchone()
        assert "kind" not in [r[1] for r in con.execute("PRAGMA table_info(results)")]


def test_case_roundtrip_and_update(tmp_path):
    s = Store(tmp_path / "a.db")
    parent = s.create_case(origin="candidate", inputs={"a": 1}, label="p", stale=False)
    c = s.create_case(origin="edit", inputs={"a": [1, 2]}, label="e",
                      parent_case_id=parent, stale=True)
    got = s.get_case(c)
    assert got["inputs"] == {"a": [1, 2]} and got["parent_case_id"] == parent
    assert got["stale"] is True and got["show_in_graphs"] is False
    assert got["job_id"] is None and got["flag"] is None and got["created"]
    assert s.get_case("nope") is None
    assert [x["id"] for x in s.list_cases()] == [c, parent]
    assert s.update_case(c, label="x", flag="good", comment="hi",
                         show_in_graphs=True, inputs={"b": 2}, stale=False) is True
    got = s.get_case(c)
    assert (got["label"], got["flag"], got["comment"]) == ("x", "good", "hi")
    assert got["show_in_graphs"] is True and got["stale"] is False
    assert got["inputs"] == {"b": 2}
    with pytest.raises(ValueError):
        s.update_case(c, origin="import")
    assert s.get_case(c)["origin"] == "edit"
    assert s.update_case("nope", label="x") is False


def test_evaluate_result_clears_stale_and_sets_job(tmp_path):
    s = Store(tmp_path / "a.db")
    c = s.create_case(origin="edit", inputs={}, label="e", stale=True)
    j = s.create_job("evaluate", {"case_id": c})
    s.put_result(j, {"v": 1}, kind="evaluate", case_id=c)
    got = s.get_case(c)
    assert got["stale"] is False and got["job_id"] == j
    assert s.case_result(c, "evaluate") == {"v": 1}
    assert s.case_result(c, "validate") is None
    s.put_result(None, {"v": 2}, kind="validate", case_id=c)
    s.put_result(j, {"v": 3}, kind="evaluate", case_id=c)
    assert s.case_result(c, "evaluate") == {"v": 3}
    assert s.case_result(c, "validate") == {"v": 2}


def test_get_result_ignores_case_results(tmp_path):
    s = Store(tmp_path / "a.db")
    c = s.create_case(origin="edit", inputs={}, label="e", stale=True)
    j = s.create_job("evaluate", {})
    s.put_result(j, {"case": 1}, kind="evaluate", case_id=c)
    assert s.get_result(j) is None
    s.put_result(j, {"run": 1}, kind="search")
    assert s.get_result(j) == {"run": 1}


def test_delete_job_keeps_cases(tmp_path):
    s = Store(tmp_path / "a.db")
    j = s.create_job("evaluate", {})
    c = s.create_case(origin="edit", inputs={}, label="e", job_id=j, stale=False)
    s.put_result(j, {"case": 1}, kind="evaluate", case_id=c)
    s.put_result(j, {"run": 1}, kind="search")
    assert s.delete_job(j) is True
    assert s.get_result(j) is None
    assert s.get_case(c)["job_id"] == j
    assert s.case_result(c, "evaluate") == {"case": 1}


def test_delete_case_removes_its_results(tmp_path):
    s = Store(tmp_path / "a.db")
    c = s.create_case(origin="edit", inputs={}, label="e", stale=True)
    s.put_result(None, {"v": 1}, kind="validate", case_id=c)
    assert s.delete_case(c) is True and s.delete_case(c) is False
    assert s.get_case(c) is None and s.case_result(c, "validate") is None


def test_case_jobs(tmp_path):
    s = Store(tmp_path / "a.db")
    c = s.create_case(origin="edit", inputs={}, label="e", stale=True)
    a = s.create_job("evaluate", {"case_id": c})
    s.create_job("evaluate", {"case_id": "other"})
    s.create_job("search", {})
    b = s.create_job("validate", {"case_id": c})
    assert [j["id"] for j in s.case_jobs(c)] == [b, a]


def test_recent_map_times(tmp_path):
    s = Store(tmp_path / "a.db")
    for i in range(7):
        s.add_map_time("full", float(i))
    s.add_map_time("screening", 99.0)
    assert s.recent_map_times("full") == [6.0, 5.0, 4.0, 3.0, 2.0]
    assert s.recent_map_times("full", 2) == [6.0, 5.0]
    assert s.recent_map_times("screening") == [99.0]
    assert s.recent_map_times("reference") == []


def test_unknown_origin_and_kind_rejected(tmp_path):
    s = Store(tmp_path / "a.db")
    with pytest.raises(ValueError, match="origin"):
        s.create_case(origin="bogus", inputs={}, label="x", stale=True)
    with pytest.raises(ValueError, match="result kind"):
        s.put_result("j", {}, kind="bogus")
