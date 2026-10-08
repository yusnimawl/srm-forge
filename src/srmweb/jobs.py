"""Single-thread job runner: one job at a time, FIFO, progress kept in memory."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable

from srmapp.evaluate import StageTwoGrid
from srmapp.pipeline import SearchSettings, run_search
from srmcore.model.design import RegionMaterials
from srmweb.config import Settings
from srmweb.schemas import SearchRequest
from srmweb.serialize import search_result_json
from srmweb.store import Store

Progress = dict

_log = logging.getLogger(__name__)

_STORE_INTERVAL_S = 1.0
_INITIAL = dict(status="running", designs_done=0, designs_total=0, points_done=0,
                points_total=0, message="")


class QueueFull(Exception):
    pass


class Reporter:
    """Latest progress of one running job plus its cancel flag."""

    def __init__(self, store: Store, job_id: str):
        self._store, self._job_id = store, job_id
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._fields = dict(_INITIAL)
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

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def snapshot(self) -> tuple[int, Progress]:
        with self._lock:
            return self._version, dict(self._fields, elapsed_s=time.monotonic() - self._t0)

    def flush(self) -> None:
        self._last_write = time.monotonic()
        self._store.set_progress(self._job_id, self.snapshot()[1])


class JobRunner:
    def __init__(self, store: Store, settings: Settings,
                 run_fn: Callable[[str, dict, Reporter], dict] | None = None):
        self._store, self._settings = store, settings
        self._run_fn = run_fn or (lambda kind, req, rep: run_job(kind, req, rep, settings))
        self._cond = threading.Condition()
        self._queue: deque[str] = deque()
        self._running: tuple[str, Reporter] | None = None
        self._stopping = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._store.mark_running_interrupted()
        queued = [j["id"] for j in reversed(self._store.list_jobs()) if j["status"] == "queued"]
        with self._cond:
            self._queue.extend(queued)
        self._thread = threading.Thread(target=self._loop, name="srmweb-jobs", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        with self._cond:
            self._stopping = True
            if self._running:
                self._running[1]._cancel.set()
            self._cond.notify_all()
        if self._thread is not None:
            self._thread.join(timeout)

    def submit(self, kind: str, request: dict) -> str:
        with self._cond:
            if len(self._queue) >= self._settings.queue_max:
                raise QueueFull(f"{len(self._queue)} jobs already queued")
            job_id = self._store.create_job(kind, request)
            self._queue.append(job_id)
            self._cond.notify()
        return job_id

    def cancel(self, job_id: str) -> bool:
        with self._cond:
            if self._running and self._running[0] == job_id:
                self._running[1]._cancel.set()
                return True
            if job_id in self._queue:
                self._queue.remove(job_id)
                self._store.set_status(job_id, "cancelled")
                return True
        return False

    def busy(self) -> bool:
        with self._cond:
            return self._running is not None

    def progress(self, job_id: str) -> tuple[int, Progress] | None:
        with self._cond:
            running = self._running
        if running and running[0] == job_id:
            return running[1].snapshot()
        return None

    def _loop(self) -> None:
        while True:
            with self._cond:
                while not self._queue and not self._stopping:
                    self._cond.wait()
                if self._stopping:
                    return
                job_id = self._queue.popleft()
                reporter = Reporter(self._store, job_id)
                self._running = (job_id, reporter)
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
                    self._running = None

    def _run(self, job_id: str, reporter: Reporter) -> None:
        job = self._store.get_job(job_id)
        if job is None:  # deleted while queued
            return
        self._store.set_status(job_id, "running")
        status, error = "done", None
        try:
            result = self._run_fn(job["kind"], job["request"], reporter)
            self._store.put_result(job_id, result)
            if result.get("cancelled"):
                status = "interrupted" if self._stopping else "cancelled"
        except Exception as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
        reporter.progress(status=status)
        reporter.flush()
        self._store.set_status(job_id, status, error=error)


def run_job(kind: str, request: dict, reporter: Reporter, settings: Settings) -> dict:
    if kind == "search":
        return run_search_job(request, reporter, settings)
    raise ValueError(f"unknown job kind {kind!r}")


def run_search_job(request: dict, reporter: Reporter, settings: Settings) -> dict:
    req = SearchRequest.model_validate(request)
    s = req.settings
    given = {k: getattr(s, k) for k in ("margin", "j_peak", "j_limit", "j_peak_max")
             if getattr(s, k) is not None}
    grid = {"grid": StageTwoGrid(*req.grid)} if req.grid else {}
    ss = SearchSettings(
        n_candidates=s.n_candidates, seed=s.seed, shortlist=s.shortlist, preset=s.preset,
        materials=RegionMaterials(stator=s.stator, rotor=s.rotor), **grid, **given)

    def on_design(done: int, total: int) -> None:
        reporter.progress(designs_done=done, designs_total=total, message=f"design {done}/{total}")

    def on_point(design: int, designs: int, done: int, total: int) -> None:
        reporter.progress(designs_done=design - 1, designs_total=designs, points_done=done,
                          points_total=total, message=f"design {design}/{designs}")

    reporter.progress(message="sampling candidates")
    result = run_search(req.requirements, ss, workers=settings.workers, cache_dir=settings.cache_dir,
                        progress=on_design, point_progress=on_point, cancel=reporter.cancelled)
    return search_result_json(result)
