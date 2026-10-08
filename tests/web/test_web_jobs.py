import json
import threading
import time

import pytest

from conftest import make_8_6
from srmapp.case import CaseInputs
from srmapp.requirements import Requirements
from srmcore.model.design import Design, MeshSettings
from srmweb import jobs
from srmweb.config import Settings
from srmweb.jobs import JobRunner, QueueFull, run_job
from srmweb.schemas import SearchRequest
from srmweb.store import Store


def _settings(tmp_path, queue_max=10, workers=2):
    return Settings("127.0.0.1", 8000, tmp_path / "a.db", tmp_path / "cache", workers,
                    None, queue_max, tmp_path)


def _wait(store, job_id, statuses, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if store.get_job(job_id)["status"] in statuses:
            return store.get_job(job_id)
        time.sleep(0.01)
    raise AssertionError(store.get_job(job_id))


@pytest.fixture
def make(tmp_path):
    runners = []

    def _make(run_fn, **kw):
        store = Store(tmp_path / "a.db")
        runner = JobRunner(store, _settings(tmp_path, **kw), run_fn)
        runner.start()
        runners.append(runner)
        return store, runner

    yield _make
    for r in runners:
        r.stop()
    assert not [t for t in threading.enumerate() if t.name == "srmweb-jobs"]


def test_job_runs_and_stores_result(make):
    store, runner = make(lambda kind, req, rep: {"ok": 1})
    j = runner.submit("search", {"a": 1})
    _wait(store, j, {"done"})
    assert store.get_result(j) == {"ok": 1}


def test_jobs_run_one_at_a_time_fifo(make):
    log, active = [], []

    def fake(kind, req, rep):
        active.append(req["n"])
        assert len(active) == 1
        log.append(req["n"])
        time.sleep(0.1)
        active.pop()
        return {}

    store, runner = make(fake)
    a, b = runner.submit("search", {"n": 1}), runner.submit("search", {"n": 2})
    _wait(store, b, {"done"})
    assert log == [1, 2]


def test_cancel_sets_cancelled(make):
    def fake(kind, req, rep):
        while not rep.cancelled():
            time.sleep(0.01)
        return {"cancelled": True}

    store, runner = make(fake)
    j = runner.submit("search", {})
    _wait(store, j, {"running"})
    assert runner.cancel(j)
    assert _wait(store, j, {"cancelled"})["status"] == "cancelled"
    assert store.get_result(j) == {"cancelled": True}
    assert not runner.cancel(j)


def test_cancel_queued_job_is_skipped(make):
    gate = threading.Event()
    ran = []

    def fake(kind, req, rep):
        ran.append(req["n"])
        gate.wait(5)
        return {}

    store, runner = make(fake)
    a = runner.submit("search", {"n": 1})
    _wait(store, a, {"running"})
    b = runner.submit("search", {"n": 2})
    assert runner.cancel(b)
    assert store.get_job(b)["status"] == "cancelled"
    gate.set()
    _wait(store, a, {"done"})
    time.sleep(0.2)
    assert ran == [1] and store.get_job(b)["status"] == "cancelled"


def test_failure_records_error_and_worker_survives(make):
    def fake(kind, req, rep):
        if req.get("bad"):
            raise ValueError("boom")
        return {"ok": 1}

    store, runner = make(fake)
    j = runner.submit("search", {"bad": True})
    got = _wait(store, j, {"failed"})
    assert got["error"] == "ValueError: boom"
    k = runner.submit("search", {})
    _wait(store, k, {"done"})


def test_queue_full(make):
    gate = threading.Event()
    store, runner = make(lambda k, r, rep: gate.wait(5) and {}, queue_max=1)
    a = runner.submit("search", {})
    _wait(store, a, {"running"})
    runner.submit("search", {})
    with pytest.raises(QueueFull):
        runner.submit("search", {})
    gate.set()


def test_restart_marks_interrupted_and_requeues(tmp_path):
    store = Store(tmp_path / "a.db")
    r = store.create_job("search", {})
    store.set_status(r, "running")
    q = store.create_job("search", {"n": 1})
    runner = JobRunner(store, _settings(tmp_path), lambda k, req, rep: {"n": req["n"]})
    runner.start()
    try:
        assert store.get_job(r)["status"] == "interrupted"
        _wait(store, q, {"done"})
        assert store.get_result(q) == {"n": 1}
    finally:
        runner.stop()


def test_progress_version_increments(make):
    gate, seen, seen2, gate2 = (threading.Event() for _ in range(4))

    def fake(kind, req, rep):
        rep.progress(points_done=1)
        seen.set()
        gate.wait(5)
        rep.progress(points_done=2)
        seen2.set()
        gate2.wait(5)
        return {}

    store, runner = make(fake)
    j = runner.submit("search", {})
    assert seen.wait(5)
    v1, p1 = runner.progress(j)
    assert p1["points_done"] == 1 and p1["status"] == "running" and "elapsed_s" in p1
    gate.set()
    assert seen2.wait(5)
    v2, p2 = runner.progress(j)
    assert v2 > v1 and p2["points_done"] == 2
    gate2.set()
    _wait(store, j, {"done"})
    assert runner.progress(j) is None
    assert store.get_job(j)["progress"]["points_done"] == 2


def test_job_deleted_while_queued_is_skipped(make):
    gate = threading.Event()
    store, runner = make(lambda k, r, rep: gate.wait(5) and {"n": r["n"]})
    a = runner.submit("search", {"n": 1})
    _wait(store, a, {"running"})
    b = runner.submit("search", {"n": 2})
    store.delete_job(b)
    c = runner.submit("search", {"n": 3})
    gate.set()
    _wait(store, c, {"done"})
    assert store.get_job(b) is None


def test_stop_interrupts_running_job(tmp_path):
    store = Store(tmp_path / "a.db")
    started = threading.Event()

    def fake(kind, req, rep):
        started.set()
        while not rep.cancelled():
            time.sleep(0.01)
        return {"cancelled": True}

    runner = JobRunner(store, _settings(tmp_path), fake)
    runner.start()
    j = runner.submit("search", {})
    assert started.wait(5)
    runner.stop()
    assert store.get_job(j)["status"] == "interrupted"
    assert store.get_result(j) == {"cancelled": True}


@pytest.mark.slow
def test_real_search_job_in_thread(make, tmp_path):
    req = {"requirements": dict(peak_power_w=630.0, peak_torque_nm=2.0, base_speed_rpm=3000.0,
                                max_speed_rpm=6000.0),
           "settings": dict(n_candidates=2, shortlist=1, preset="screening"),
           "grid": [4, 3]}
    SearchRequest.model_validate(req)
    store, runner = make(lambda kind, r, rep: run_job(kind, r, rep, runner._settings))
    j = runner.submit("search", req)
    got = _wait(store, j, {"done", "failed", "cancelled"}, timeout=1800)
    assert got["status"] == "done", got
    json.dumps(store.get_result(j), allow_nan=False)


def _inputs() -> dict:
    req = Requirements(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    design = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
    return CaseInputs(requirements=req, design=design).model_dump(mode="json")


def _real_runner(make, monkeypatch, evaluate=None, validate=None):
    """A runner that goes through run_job with `evaluate_design` / `validate_case` replaced."""
    if evaluate:
        monkeypatch.setattr(jobs, "evaluate_design", evaluate)
    if validate:
        monkeypatch.setattr(jobs, "validate_case", validate)
    holder = []
    store, runner = make(lambda kind, r, rep: run_job(kind, r, rep, holder[0]._settings))
    holder.append(runner)
    return store, runner


class _Ev:
    def __init__(self, status="ok"):
        self.status = status


def test_evaluate_job_records_map_time(make, monkeypatch):
    def fake(inputs, *, case_id, progress, cancel, **kw):
        assert case_id == "c1" and not cancel()
        progress(1, 3)
        time.sleep(0.05)
        progress(3, 3)
        return _Ev()

    monkeypatch.setattr(jobs, "evaluation_json", lambda ev: {"status": ev.status})
    store, runner = _real_runner(make, monkeypatch, evaluate=fake)
    j = runner.submit("evaluate", {"case_id": "c1", "inputs": _inputs()})
    got = _wait(store, j, {"done", "failed"})
    assert got["status"] == "done", got
    (seconds,) = store.recent_map_times("screening")
    assert 0.04 < seconds < 5
    assert got["progress"]["points_total"] == 3
    assert got["case_id"] == "c1"


def test_evaluate_job_records_the_scan_per_winding_mode(make, monkeypatch):
    def fake(inputs, *, progress, on_scan, **kw):
        progress(3, 3)
        on_scan()
        time.sleep(0.05)
        return _Ev()

    monkeypatch.setattr(jobs, "evaluation_json", lambda ev: {"status": ev.status})
    store, runner = _real_runner(make, monkeypatch, evaluate=fake)
    j = runner.submit("evaluate", {"case_id": "c1", "inputs": _inputs()})
    got = _wait(store, j, {"done", "failed"})
    assert got["status"] == "done" and got["progress"]["message"] == "choosing the winding"
    (seconds,) = store.recent_scan_times("auto")
    assert 0.04 < seconds < 5 and store.recent_scan_times("fixed") == []
    fixed = _inputs() | {"winding": {"turns": 10}}
    j = runner.submit("evaluate", {"case_id": "c1", "inputs": fixed})
    _wait(store, j, {"done", "failed"})
    assert len(store.recent_scan_times("fixed")) == 1


def test_cached_map_records_a_scan_but_no_map_time(make, monkeypatch):
    def fake(inputs, *, on_scan, **kw):
        on_scan()
        return _Ev()

    monkeypatch.setattr(jobs, "evaluation_json", lambda ev: {"status": ev.status})
    store, runner = _real_runner(make, monkeypatch, evaluate=fake)
    j = runner.submit("evaluate", {"case_id": "c1", "inputs": _inputs()})
    assert _wait(store, j, {"done", "failed"})["status"] == "done"
    assert len(store.recent_scan_times("auto")) == 1 and store.recent_map_times("screening") == []


def test_evaluation_of_a_deleted_case_is_not_attached(make, monkeypatch):
    monkeypatch.setattr(jobs, "evaluation_json", lambda ev: {"status": ev.status})
    store, runner = _real_runner(make, monkeypatch, evaluate=lambda inputs, **kw: _Ev())
    j = runner.submit("evaluate", {"case_id": "gone", "inputs": _inputs()})
    assert _wait(store, j, {"done", "failed"})["status"] == "done"
    assert store.case_result("gone", "evaluate") is None and store.get_result(j) == {"status": "ok"}


def test_partial_map_records_no_time(make, monkeypatch):
    def fake(inputs, *, progress, **kw):
        progress(1, 3)
        time.sleep(0.02)
        progress(2, 3)
        return _Ev()

    monkeypatch.setattr(jobs, "evaluation_json", lambda ev: {"status": ev.status})
    store, runner = _real_runner(make, monkeypatch, evaluate=fake)
    j = runner.submit("evaluate", {"case_id": "c1", "inputs": _inputs()})
    assert _wait(store, j, {"done", "failed"})["status"] == "done"
    assert store.recent_map_times("screening") == []


def test_evaluate_job_result_belongs_to_the_case(make, monkeypatch):
    monkeypatch.setattr(jobs, "evaluation_json", lambda ev: {"status": ev.status})
    store, runner = _real_runner(make, monkeypatch, evaluate=lambda inputs, **kw: _Ev())
    case = store.create_case(origin="edit", inputs={}, label="e", stale=True)
    j = runner.submit("evaluate", {"case_id": case, "inputs": _inputs()})
    _wait(store, j, {"done"})
    assert store.case_result(case, "evaluate") == {"status": "ok"}
    got = store.get_case(case)
    assert got["stale"] is False and got["job_id"] == j
    assert store.recent_map_times("screening") == []  # no map points were reported


def test_cancelled_evaluate_keeps_case_stale_and_records_no_time(make, monkeypatch):
    def fake(inputs, *, progress, **kw):
        progress(1, 3)
        progress(2, 3)
        return _Ev("cancelled")

    store, runner = _real_runner(make, monkeypatch, evaluate=fake)
    case = store.create_case(origin="edit", inputs={}, label="e", stale=True)
    j = runner.submit("evaluate", {"case_id": case, "inputs": _inputs()})
    _wait(store, j, {"cancelled"})
    assert store.get_case(case)["stale"] is True
    assert store.case_result(case, "evaluate") is None
    assert store.get_result(j) == {"cancelled": True}
    assert store.recent_map_times("screening") == []


def test_evaluate_job_value_error_fails_with_message(make, monkeypatch):
    def fake(inputs, **kw):
        raise ValueError("no winding fits")

    store, runner = _real_runner(make, monkeypatch, evaluate=fake)
    j = runner.submit("evaluate", {"case_id": "c", "inputs": _inputs()})
    assert _wait(store, j, {"failed"})["error"] == "ValueError: no winding fits"


def test_validate_job_stores_case_result(make, monkeypatch):
    store, runner = _real_runner(make, monkeypatch, validate=lambda inputs, **kw: {"label": None, "x": float("nan")})
    case = store.create_case(origin="edit", inputs={}, label="e", stale=True)
    j = runner.submit("validate", {"case_id": case, "inputs": _inputs()})
    got = _wait(store, j, {"done"})
    assert got["progress"]["message"] == "validating (about 1 h)"
    assert store.case_result(case, "validate") == {"label": None, "x": None}
    assert store.get_case(case)["stale"] is True  # validation does not evaluate


def test_job_with_bad_request_fails(make):
    store, runner = make(lambda kind, r, rep: run_job(kind, r, rep, runner._settings))
    j = runner.submit("evaluate", {"case_id": "c"})
    assert _wait(store, j, {"failed"})["error"].startswith("ValidationError")
    j = runner.submit("bogus", {})
    assert "unknown job kind" in _wait(store, j, {"failed"})["error"]
