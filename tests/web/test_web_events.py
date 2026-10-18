import json
import threading
import time

import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from srmweb.api import create_app
from srmweb.config import Settings
from srmweb.jobs import JobRunner

REQ = dict(peak_power_w=10000.0, peak_torque_nm=31.83, base_speed_rpm=3000.0,
           max_speed_rpm=6000.0)
BODY = {"kind": "search", "payload": {"requirements": REQ}}


@pytest.fixture
def gate():
    ev = threading.Event()
    yield ev
    ev.set()


@pytest.fixture
def make(tmp_path):
    clients = []

    def _make(run_fn):
        s = Settings("127.0.0.1", 8000, tmp_path / "a.db", tmp_path / "cache", 1,
                     None, 10, tmp_path)
        c = TestClient(create_app(
            s, runner_factory=lambda store, st: JobRunner(store, st, run_fn=run_fn)))
        c.__enter__()
        clients.append(c)
        return c

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


def _events(client, job_id, stop, limit=10):
    """Read (event, data) pairs until stop(event, data) is true or the stream closes."""
    out = []
    with client.stream("GET", f"/api/jobs/{job_id}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache"
        assert r.headers["x-accel-buffering"] == "no"
        name = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                out.append((name, json.loads(line[6:])))
                if stop(*out[-1]) or len(out) >= limit:
                    break
    return out


def _wait_points(client, job_id, n):
    end = time.time() + 10
    while time.time() < end:
        p = client.get(f"/api/jobs/{job_id}").json()["progress"]
        if p and p["points_done"] == n:
            return
        time.sleep(0.01)
    raise AssertionError("progress not reached")


def _wait_done(client, job_id):
    end = time.time() + 10
    while client.get(f"/api/jobs/{job_id}").json()["status"] != "done":
        assert time.time() < end
        time.sleep(0.01)


def test_events_sends_current_state_first(make, gate):
    def fn(kind, req, rep, ctx):
        rep.progress(points_done=7)
        gate.wait(10)
        return {}

    c = make(fn)
    j = c.post("/api/jobs", json=BODY).json()["id"]
    _wait_points(c, j, 7)
    # TestClient delivers the body only once the app finishes, so let the job end.
    threading.Timer(0.3, gate.set).start()
    ev = _events(c, j, lambda n, d: True)
    assert ev[0][0] == "progress"
    assert ev[0][1]["progress"]["points_done"] == 7


def test_events_end_on_done(make, gate):
    def fn(kind, req, rep, ctx):
        rep.progress(points_done=1)
        gate.wait(10)
        return {}

    c = make(fn)
    j = c.post("/api/jobs", json=BODY).json()["id"]
    _wait_points(c, j, 1)
    threading.Timer(0.3, gate.set).start()
    ev = _events(c, j, lambda n, d: n == "end")
    assert ev[0][0] == "progress"
    assert ev[-1][0] == "end"
    assert ev[-1][1]["status"] == "done"


def test_events_terminal_job_single_end(make):
    c = make(lambda kind, req, rep, ctx: {})
    j = c.post("/api/jobs", json=BODY).json()["id"]
    _wait_done(c, j)
    ev = _events(c, j, lambda n, d: False)
    assert [n for n, _ in ev] == ["end"]
    assert ev[0][1]["status"] == "done"


def test_events_404(make):
    assert make(lambda kind, req, rep, ctx: {}).get("/api/jobs/x/events").status_code == 404


def test_events_queued_then_running_then_end(make):
    gates = [threading.Event(), threading.Event()]
    calls = []

    def fn(kind, req, rep, ctx):
        calls.append(1)
        gates[len(calls) - 1].wait(10)
        return {}

    c = make(fn)
    first = c.post("/api/jobs", json=BODY).json()["id"]
    second = c.post("/api/jobs", json=BODY).json()["id"]
    try:
        threading.Timer(1.2, gates[0].set).start()
        threading.Timer(2.4, gates[1].set).start()
        ev = _events(c, second, lambda n, d: n == "end")
    finally:
        for g in gates:
            g.set()
    assert [(n, d["status"]) for n, d in ev] == [
        ("progress", "queued"), ("progress", "running"), ("end", "done")]


def test_events_tick_while_progress_is_idle(make, gate):
    """The clock keeps moving in a step that reports no new counts."""
    def fn(kind, req, rep, ctx):
        rep.progress(points_done=1)
        gate.wait(10)
        return {}

    c = make(fn)
    j = c.post("/api/jobs", json=BODY).json()["id"]
    _wait_points(c, j, 1)
    threading.Timer(2.6, gate.set).start()
    ev = _events(c, j, lambda n, d: n == "end", limit=50)
    elapsed = [d["progress"]["elapsed_s"] for n, d in ev if n == "progress"]
    assert len(elapsed) >= 3
    assert elapsed == sorted(elapsed) and elapsed[-1] - elapsed[0] >= 1.0
