"""A FIFO lane for short interactive tasks (field snapshots, animation frames).

Tasks run one at a time in a single spawned worker process, so a solve that overruns its time limit can be killed
(`Pool.terminate`) and the next task gets a fresh process. Callers block in `run`; a task that is still queued when
its limit passes never runs."""
import multiprocessing
import os
import queue
import threading
import time
from typing import Any


class LaneTimeout(Exception):
    pass


def _init_lane() -> None:
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"


class _Task:
    def __init__(self, fn, args, deadline: float):
        self.fn, self.args, self.deadline = fn, args, deadline
        self.done = threading.Event()
        self.abandoned = False
        self.value: Any = None
        self.error: BaseException | None = None


class QuickLane:
    def __init__(self, timeout_s: float = 120.0, spawn: bool = True):
        self.timeout_s, self._spawn = timeout_s, spawn
        self._queue: queue.Queue[_Task | None] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._pool = None
        self._running = False
        self._stopped = False

    def run(self, fn, *args, timeout: float | None = None) -> Any:
        limit = self.timeout_s if timeout is None else timeout
        task = _Task(fn, args, time.monotonic() + limit)
        with self._lock:
            if self._stopped:
                raise RuntimeError("the quick lane is stopped")
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, name="srmweb-quick", daemon=True)
                self._thread.start()
            self._queue.put(task)
        if not task.done.wait(limit):
            task.abandoned = True
            raise LaneTimeout(f"no result within {limit:g} s")
        if task.error is not None:
            raise task.error
        return task.value

    def busy(self) -> bool:
        return self._running or not self._queue.empty()

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            self._queue.put(None)
        self._kill_pool()

    def _kill_pool(self) -> None:
        pool, self._pool = self._pool, None
        if pool is not None:
            pool.terminate()

    def _loop(self) -> None:
        while (task := self._queue.get()) is not None:
            if task.abandoned or time.monotonic() >= task.deadline:
                continue
            self._running = True
            try:
                task.value = self._execute(task)
            except BaseException as exc:  # noqa: BLE001  (re-raised in the caller)
                task.error = exc
            finally:
                self._running = False
                task.done.set()

    def _execute(self, task: _Task) -> Any:
        if not self._spawn:
            return task.fn(*task.args)
        if self._pool is None:
            self._pool = multiprocessing.get_context("spawn").Pool(1, initializer=_init_lane)
        pending = self._pool.apply_async(task.fn, task.args)
        try:
            return pending.get(max(0.0, task.deadline - time.monotonic()))
        except multiprocessing.TimeoutError:
            self._kill_pool()
            raise LaneTimeout("task timed out") from None
