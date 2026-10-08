import sqlite3

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
        s.put_result(j, {"x": float("nan")})
    s.put_result(j, {"x": 1})
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
    con.execute("PRAGMA user_version = 2")
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="database schema 2 != expected 1"):
        Store(p)
