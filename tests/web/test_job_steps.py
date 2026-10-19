import threading
import types
import time

import pytest

from srmapp.case import LIMIT_FIELDS
from srmweb import jobs
from srmweb.api import _job_out
from srmweb.config import Settings
from srmweb.jobs import STEPS, JobRunner, Reporter
from srmweb.store import Store

SEQUENCES = {
    "evaluate": ["queued", "mesh", "mapping", "winding", "saved"],
    "validate": ["queued", "map", "checks", "saved"],
    "animate": ["queued", "frames", "saved"],
    "control": ["queued", "compile", "simulate", "saved"],
    "search": ["queued", "sampling", "designs", "pareto", "saved"],
}


def _settings(tmp_path):
    return Settings("127.0.0.1", 8000, tmp_path / "a.db", tmp_path / "cache", 2, None, 10, tmp_path)


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

    def _make(run_fn):
        store = Store(tmp_path / "a.db")
        runner = JobRunner(store, _settings(tmp_path), run_fn)
        runner.start()
        runners.append(runner)
        return store, runner

    yield _make
    for r in runners:
        r.stop()


def test_step_ids_per_kind():
    assert {k: list(v) for k, v in STEPS.items()} == SEQUENCES


@pytest.mark.parametrize("kind", SEQUENCES)
def test_queued_job_has_steps_and_queued_step(make, kind):
    gate = threading.Event()
    store, runner = make(lambda k, r, rep, ctx: gate.wait(5) and {})
    blocker = runner.submit("animate" if kind == "animate" else "search", {})
    _wait(store, blocker, {"running"})
    j = runner.submit(kind, {})
    progress = _job_out(store.get_job(j), runner).progress
    assert progress["steps"] == SEQUENCES[kind]
    assert progress["step"] == "queued"
    gate.set()


@pytest.mark.parametrize("kind", SEQUENCES)
def test_job_passes_through_steps_in_order(make, kind):
    seen = []

    def run(k, req, rep, ctx):
        seen.append(rep.snapshot()[1]["step"])
        for step in SEQUENCES[k][1:-1]:
            rep.progress(step=step)
            seen.append(rep.snapshot()[1]["step"])
        return {}

    store, runner = make(run)
    store.attach_evaluation = lambda case_id, job_id, result: None
    j = runner.submit(kind, {"case_id": "c"})
    _wait(store, j, {"done"})
    seen.append(store.get_job(j)["progress"]["step"])
    assert seen == SEQUENCES[kind][:-1] + ["saved"]
    assert store.get_job(j)["progress"]["steps"] == SEQUENCES[kind]


def test_failed_job_keeps_its_step(make):
    def run(kind, req, rep, ctx):
        rep.progress(step="mapping")
        raise RuntimeError("boom")

    store, runner = make(run)
    j = runner.submit("evaluate", {})
    job = _wait(store, j, {"failed"})
    assert job["progress"]["step"] == "mapping"
    assert job["status"] == "failed"


def test_cancelled_job_keeps_its_step(make):
    def run(kind, req, rep, ctx):
        rep.progress(step="mapping")
        while not rep.cancelled():
            time.sleep(0.01)
        return {"cancelled": True}

    store, runner = make(run)
    j = runner.submit("evaluate", {})
    _wait(store, j, {"running"})
    time.sleep(0.05)
    runner.cancel(j)
    job = _wait(store, j, {"cancelled"})
    assert job["progress"]["step"] == "mapping"


def test_queue_position_per_lane(make):
    gate = threading.Event()
    store, runner = make(lambda k, r, rep, ctx: gate.wait(5) and {})
    run_main = runner.submit("evaluate", {})
    run_quick = runner.submit("animate", {})
    _wait(store, run_main, {"running"})
    _wait(store, run_quick, {"running"})
    m1, m2 = runner.submit("evaluate", {}), runner.submit("search", {})
    q1 = runner.submit("animate", {})

    def out(j):
        return _job_out(store.get_job(j), runner)

    assert [out(j).queue_position for j in (m1, m2, q1)] == [1, 2, 1]
    assert [out(j).lane for j in (m1, m2, q1)] == ["main", "main", "quick"]
    assert out(run_main).queue_position is None and out(run_main).lane == "main"
    assert out(run_quick).queue_position is None and out(run_quick).lane == "quick"
    runner.cancel(m1)
    assert out(m1).queue_position is None
    assert out(m2).queue_position == 1
    gate.set()
    _wait(store, m2, {"done"})
    assert out(m2).queue_position is None


def test_positions_after_restart(tmp_path):
    gate = threading.Event()
    store = Store(tmp_path / "a.db")
    first = JobRunner(store, _settings(tmp_path), lambda k, r, rep, ctx: gate.wait(5) and {})
    ids = [first.submit("evaluate", {}) for _ in range(3)]   # never started: all stay queued
    first.stop()
    second = JobRunner(Store(tmp_path / "a.db"), _settings(tmp_path), lambda k, r, rep, ctx: gate.wait(5) and {})
    second.start()
    try:
        _wait(second._store, ids[0], {"running"})
        outs = [_job_out(second._store.get_job(j), second) for j in ids]
        assert [o.queue_position for o in outs] == [None, 1, 2]
        assert outs[1].progress["step"] == "queued"
    finally:
        gate.set()
        second.stop()


def test_eta_none_below_five_percent(tmp_path):
    rep = Reporter(Store(tmp_path / "a.db"), "j", "evaluate")
    rep.progress(step="mapping", points_done=4, points_total=100)
    assert rep.snapshot()[1]["eta_s"] is None
    rep.progress(points_done=0)
    assert rep.snapshot()[1]["eta_s"] is None


def test_eta_is_elapsed_per_point_times_points_left(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(jobs.time, "monotonic", lambda: now[0])
    rep = Reporter(Store(tmp_path / "a.db"), "j", "evaluate")
    now[0] = 120.0
    rep.progress(step="mapping", points_done=10, points_total=100)
    assert rep.snapshot()[1]["eta_s"] == pytest.approx(20.0 / 10 * 90)
    rep.progress(points_done=100)
    assert rep.snapshot()[1]["eta_s"] == 0.0


class _Recorder(Reporter):
    """A reporter that remembers each distinct step it passes through."""

    def __init__(self, tmp_path):
        super().__init__(Store(tmp_path / "r.db"), "j", "")
        self.seen = ["queued"]

    def progress(self, **fields):
        super().progress(**fields)
        step = self.snapshot()[1]["step"]
        if not self.seen or self.seen[-1] != step:
            self.seen.append(step)


def _ns(**kw):
    return types.SimpleNamespace(**kw)


def _ctx(tmp_path, quick=None):
    return jobs.JobContext(_settings(tmp_path), quick)


def test_real_evaluate_job_steps(tmp_path, monkeypatch):
    def fake(inputs, *, progress, on_scan, **kw):
        progress(1, 3)
        progress(3, 3)
        on_scan()
        return _ns(status="ok")

    monkeypatch.setattr(jobs, "evaluate_design", fake)
    monkeypatch.setattr(jobs, "evaluation_json", lambda ev: {})
    rep = _Recorder(tmp_path)
    req = _ns(case_id="c", grid=None,
              inputs=_ns(design=_ns(mesh=_ns(preset="screening")), winding="auto"))
    jobs.run_evaluate_job(req, rep, _ctx(tmp_path))
    assert rep.seen == ["queued", "mesh", "mapping", "winding"]


def test_real_validate_job_steps(tmp_path, monkeypatch):
    def fake(inputs, *, on_checks, **kw):
        on_checks()
        return {}

    monkeypatch.setattr(jobs, "validate_case", fake)
    monkeypatch.setattr(jobs, "to_json", lambda v: {})
    rep = _Recorder(tmp_path)
    jobs.run_validate_job(_ns(inputs=None), rep, _ctx(tmp_path))
    assert rep.seen == ["queued", "map", "checks"]


def test_real_search_job_steps(tmp_path, monkeypatch):
    def fake(requirements, ss, *, progress, point_progress, **kw):
        point_progress(1, 2, 5, 40)
        progress(1, 2)
        point_progress(2, 2, 5, 40)
        progress(2, 2)
        return None

    monkeypatch.setattr(jobs, "run_search", fake)
    monkeypatch.setattr(jobs, "SearchSettings", lambda **kw: None)
    monkeypatch.setattr(jobs, "search_result_json", lambda r: {})
    rep = _Recorder(tmp_path)
    settings = _ns(n_candidates=1, seed=0, shortlist=1, preset="screening", stator="a", rotor="a", **{f: None for f in LIMIT_FIELDS})
    jobs.run_search_job(_ns(requirements=None, settings=settings, grid=None), rep, _ctx(tmp_path))
    assert rep.seen == ["queued", "sampling", "designs", "pareto"]


def test_real_animate_job_steps(tmp_path, monkeypatch):
    frame = _ns(psi=1.0, torque=0.0, status="ok", probes={"yoke": 0.5})
    quick = _ns(run=lambda fn, *a: frame)
    monkeypatch.setattr(jobs, "reference_design", lambda inputs: None)
    rep = _Recorder(tmp_path)
    req = _ns(inputs=_ns(design=_ns(machine=_ns(n_rotor_poles=6))), frames=3, coil_current=1.0, k=1.0,
              case_id="c", current_a=1.0)
    jobs.run_animate_job(req, rep, _ctx(tmp_path, quick))
    assert rep.seen == ["queued", "frames"]


@pytest.mark.parametrize(
    ("kind", "step"),
    [("evaluate", "winding"), ("search", "designs"), ("search", "pareto"), ("evaluate", "mesh")],
)
def test_eta_none_outside_point_counted_steps(tmp_path, monkeypatch, kind, step):
    now = [100.0]
    monkeypatch.setattr(jobs.time, "monotonic", lambda: now[0])
    rep = Reporter(Store(tmp_path / "a.db"), "j", kind)
    now[0] = 120.0
    rep.progress(step=step, points_done=100, points_total=100)
    assert rep.snapshot()[1]["eta_s"] is None


def test_eta_computed_in_frames_step(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(jobs.time, "monotonic", lambda: now[0])
    rep = Reporter(Store(tmp_path / "a.db"), "j", "animate")
    now[0] = 120.0
    rep.progress(step="frames", points_done=10, points_total=20)
    assert rep.snapshot()[1]["eta_s"] == pytest.approx(20.0)
