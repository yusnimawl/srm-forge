"""Job runner: one thread per lane, FIFO within a lane, progress kept in memory.

The main lane runs search, evaluate and validate; the quick lane runs animate, so an animation never waits behind
a map build."""
from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel

from srmapp.case import LIMIT_FIELDS, evaluate_design, reference_design, validate_case
from srmapp.evaluate import StageTwoGrid
from srmapp.pipeline import SearchSettings, run_search
from srmcore.model.design import RegionMaterials
from srmweb.config import Settings
from srmweb.quick import QuickLane
from srmweb.frames import frame_task
from srmweb.schemas import AnimateRequest, EvaluateRequest, SearchRequest, ValidateRequest
from srmweb.serialize import evaluation_json, search_result_json, to_json
from srmweb.store import ACTIVE, FINAL, RESUMABLE, Store  # noqa: F401  (status groups are defined in store)

Progress = dict

_log = logging.getLogger(__name__)

_STORE_INTERVAL_S = 1.0
_INITIAL = dict(status="running", designs_done=0, designs_total=0, points_done=0,
                points_total=0, message="")

STEPS: dict[str, tuple[str, ...]] = {
    "evaluate": ("queued", "mesh", "mapping", "winding", "saved"),
    "validate": ("queued", "map", "checks", "saved"),
    "animate": ("queued", "frames", "saved"),
    "search": ("queued", "sampling", "designs", "pareto", "saved"),
}
_ETA_MIN_FRACTION = 0.05
_NO_ETA_STEPS = ("designs",)   # the point counts restart with every design


def initial_progress(kind: str) -> dict:
    """Progress of a job that has not started: its step ids and the first step."""
    steps = list(STEPS.get(kind, ("queued", "saved")))
    return dict(_INITIAL, status="queued", steps=steps, step=steps[0])


class QueueFull(Exception):
    pass


class Reporter:
    """Latest progress of one running job plus its cancel flag."""

    def __init__(self, store: Store, job_id: str, kind: str = ""):
        self.store, self._job_id = store, job_id
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._fields = dict(initial_progress(kind), status="running")
        self._version = 0
        self._t0 = time.monotonic()
        self._last_write = float("-inf")

    def progress(self, **fields) -> None:
        with self._lock:
            self._fields.update(fields)
            self._version += 1
            due = time.monotonic() - self._last_write >= _STORE_INTERVAL_S
        if due:
            self.flush()

    def cancel(self) -> None:
        self._cancel.set()

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def snapshot(self) -> tuple[int, Progress]:
        with self._lock:
            elapsed = time.monotonic() - self._t0
            return self._version, dict(self._fields, elapsed_s=elapsed, eta_s=self._eta(elapsed))

    def _eta(self, elapsed: float) -> float | None:
        """Time left at the average pace so far, once 5 % of the points are done."""
        done, total = self._fields["points_done"], self._fields["points_total"]
        if total <= 0 or done < _ETA_MIN_FRACTION * total or self._fields["step"] in _NO_ETA_STEPS:
            return None
        return elapsed / done * (total - done)

    def flush(self) -> None:
        self._last_write = time.monotonic()
        self.store.set_progress(self._job_id, self.snapshot()[1])


LANE_OF = {"animate": "quick"}
LANES = ("main", "quick")


def lane_of(kind: str) -> str:
    return LANE_OF.get(kind, "main")


@dataclass(frozen=True)
class JobContext:
    settings: Settings
    quick: QuickLane


class JobRunner:
    def __init__(self, store: Store, settings: Settings,
                 run_fn: Callable[[str, dict, Reporter, JobContext], dict] | None = None,
                 quick: QuickLane | None = None):
        self._store, self._settings = store, settings
        self.quick = quick or QuickLane()
        self._ctx = JobContext(settings, self.quick)
        self._run_fn = run_fn or run_job
        self._cond = threading.Condition()
        self._queue: dict[str, deque[str]] = {lane: deque() for lane in LANES}
        self._running: dict[str, tuple[str, Reporter] | None] = dict.fromkeys(LANES)
        self._stopping = False
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        self._store.mark_running_interrupted()
        with self._cond:
            for j in reversed(self._store.list_jobs()):
                if j["status"] == "queued":
                    self._queue[lane_of(j["kind"])].append(j["id"])
        for lane in LANES:
            name = "srmweb-jobs" if lane == "main" else f"srmweb-jobs-{lane}"
            thread = threading.Thread(target=self._loop, args=(lane,), name=name, daemon=True)
            self._threads.append(thread)
            thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        with self._cond:
            self._stopping = True
            for running in self._running.values():
                if running:
                    running[1].cancel()
            self._cond.notify_all()
        self.quick.stop()
        for thread in self._threads:
            thread.join(timeout)

    def queue_position(self, job_id: str) -> int | None:
        """1 = next in its lane; None when the job is not waiting."""
        with self._cond:
            for queue in self._queue.values():
                if job_id in queue:
                    return list(queue).index(job_id) + 1
        return None

    def submit(self, kind: str, request: dict) -> str:
        lane = lane_of(kind)
        with self._cond:
            if len(self._queue[lane]) >= self._settings.queue_max:
                raise QueueFull(f"{len(self._queue[lane])} jobs already queued")
            job_id = self._store.create_job(kind, request)
            self._store.set_progress(job_id, dict(initial_progress(kind), elapsed_s=0.0, eta_s=None))
            self._queue[lane].append(job_id)
            self._cond.notify_all()
        return job_id

    def cancel(self, job_id: str) -> bool:
        with self._cond:
            for running in self._running.values():
                if running and running[0] == job_id:
                    running[1].cancel()
                    return True
            for queue in self._queue.values():
                if job_id in queue:
                    queue.remove(job_id)
                    self._store.set_status(job_id, "cancelled")
                    return True
        return False

    def busy(self, lane: str = "main") -> bool:
        with self._cond:
            return self._running[lane] is not None

    def progress(self, job_id: str) -> tuple[int, Progress] | None:
        with self._cond:
            runs = list(self._running.values())
        for running in runs:
            if running and running[0] == job_id:
                return running[1].snapshot()
        return None

    def _loop(self, lane: str) -> None:
        while True:
            with self._cond:
                while not self._queue[lane] and not self._stopping:
                    self._cond.wait()
                if self._stopping:
                    return
                job_id = self._queue[lane].popleft()
                reporter = Reporter(self._store, job_id, self._kind_of(job_id))
                self._running[lane] = (job_id, reporter)
            try:
                self._run(job_id, reporter)
            except Exception as exc:  # a store error must not end the worker
                _log.exception("job %s failed outside its run function", job_id)
                try:
                    self._store.set_status(job_id, "failed", error=f"{type(exc).__name__}: {exc}")
                except Exception:
                    _log.exception("could not mark job %s failed", job_id)
            finally:
                with self._cond:
                    self._running[lane] = None

    def _kind_of(self, job_id: str) -> str:
        job = self._store.get_job(job_id)
        return "" if job is None else job["kind"]

    def _run(self, job_id: str, reporter: Reporter) -> None:
        job = self._store.get_job(job_id)
        if job is None:  # deleted while queued
            return
        self._store.set_status(job_id, "running")
        status, error = "done", None
        try:
            result = self._run_fn(job["kind"], job["request"], reporter, self._ctx)
            cancelled = bool(result.get("cancelled"))
            if cancelled:   # a cancelled evaluation must not mark its case as evaluated
                self._store.put_result(job_id, result, kind=job["kind"])
            elif job["kind"] == "evaluate":
                self._store.attach_evaluation(job["request"]["case_id"], job_id, result)
            else:   # an animation belongs to its job, not to the case
                case_id = None if job["kind"] == "animate" else job["request"].get("case_id")
                self._store.put_result(job_id, result, kind=job["kind"], case_id=case_id)
            if cancelled:
                status = "interrupted" if self._stopping else "cancelled"
        except Exception as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
        reporter.progress(status=status, **({"step": "saved"} if status == "done" else {}))
        reporter.flush()
        self._store.set_status(job_id, status, error=error)


def run_job(kind: str, request: dict, reporter: Reporter, ctx: JobContext) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown job kind {kind!r}")
    model, fn = KINDS[kind]
    return fn(model.model_validate(request), reporter, ctx)


def run_search_job(req: SearchRequest, reporter: Reporter, ctx: JobContext) -> dict:
    settings = ctx.settings
    s = req.settings
    given = {k: getattr(s, k) for k in LIMIT_FIELDS if getattr(s, k) is not None}
    grid = {"grid": StageTwoGrid(*req.grid)} if req.grid else {}
    ss = SearchSettings(
        n_candidates=s.n_candidates, seed=s.seed, shortlist=s.shortlist, preset=s.preset,
        materials=RegionMaterials(stator=s.stator, rotor=s.rotor), **grid, **given)

    def on_design(done: int, total: int) -> None:
        reporter.progress(step="pareto" if done == total else "designs", designs_done=done,
                          designs_total=total, message=f"design {done}/{total}")

    def on_point(design: int, designs: int, done: int, total: int) -> None:
        reporter.progress(step="designs", designs_done=design - 1, designs_total=designs, points_done=done,
                          points_total=total, message=f"design {design}/{designs}")

    reporter.progress(step="sampling", message="sampling candidates")
    result = run_search(req.requirements, ss, workers=settings.workers, cache_dir=settings.cache_dir,
                        progress=on_design, point_progress=on_point, cancel=reporter.cancelled)
    return search_result_json(result)


def run_evaluate_job(req: EvaluateRequest, reporter: Reporter, ctx: JobContext) -> dict:
    settings = ctx.settings
    t0 = time.monotonic()
    last = scan_start = None
    counts = (0, 0)

    def on_point(done: int, total: int) -> None:
        nonlocal last, counts
        last, counts = time.monotonic(), (done, total)
        reporter.progress(step="mapping" if done < total else "winding", points_done=done, points_total=total,
                          message="mapping" if done < total else "choosing the winding")

    def on_scan() -> None:   # the map is complete, built or cached
        nonlocal scan_start
        scan_start = time.monotonic()
        reporter.progress(step="winding", message="choosing the winding")

    reporter.progress(step="mesh", message="meshing")
    grid = {"grid": StageTwoGrid(*req.grid)} if req.grid else {}
    ev = evaluate_design(req.inputs, case_id=req.case_id, workers=settings.workers, cache_dir=settings.cache_dir,
                         progress=on_point, cancel=reporter.cancelled, on_scan=on_scan, **grid)
    if ev.status == "cancelled":
        return {"cancelled": True}
    if last is not None and counts[0] == counts[1]:  # a cached or partial map is no timing
        reporter.store.add_map_time(req.inputs.design.mesh.preset, last - t0)
    if scan_start is not None:
        mode = "auto" if req.inputs.winding == "auto" else "fixed"
        reporter.store.add_scan_time(mode, time.monotonic() - scan_start)
    return evaluation_json(ev)


def run_validate_job(req: ValidateRequest, reporter: Reporter, ctx: JobContext) -> dict:
    settings = ctx.settings
    reporter.progress(step="map", message="validating (about 1 h)")
    return to_json(validate_case(req.inputs, workers=settings.workers, cache_dir=settings.cache_dir,
                                 on_checks=lambda: reporter.progress(step="checks")))


def run_animate_job(req: AnimateRequest, reporter: Reporter, ctx: JobContext) -> dict:
    """Phase A from the unaligned to the aligned position, one cached field frame per angle."""
    n_r = req.inputs.design.machine.n_rotor_poles
    design = reference_design(req.inputs)
    angles = np.linspace(math.pi / n_r, 2 * math.pi / n_r, req.frames)
    psi, torque, status = [], [], []
    probes: dict[str, list[float]] = {}
    for n, angle in enumerate(angles, 1):
        if reporter.cancelled():
            return {"cancelled": True}
        reporter.progress(step="frames", points_done=n - 1, points_total=req.frames, message=f"frame {n}/{req.frames}")
        frame = ctx.quick.run(frame_task, design, float(angle), req.coil_current, ctx.settings.cache_dir)
        psi.append(frame.psi * req.k)
        torque.append(frame.torque)
        status.append(frame.status)
        for zone, value in frame.probes.items():
            probes.setdefault(zone, []).append(value)
    reporter.progress(points_done=req.frames, points_total=req.frames, message=f"frame {req.frames}/{req.frames}")
    return {"case_id": req.case_id, "current_a": req.current_a, "angles": [float(a) for a in angles],
            "psi": psi, "torque": torque, "status": status, "probes": probes}


KINDS: dict[str, tuple[type[BaseModel], Callable[[BaseModel, Reporter, JobContext], dict]]] = {
    "search": (SearchRequest, run_search_job),
    "evaluate": (EvaluateRequest, run_evaluate_job),
    "validate": (ValidateRequest, run_validate_job),
    "animate": (AnimateRequest, run_animate_job),
}
