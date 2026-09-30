"""Ordered map over a process pool with one retry after a worker crash (spec §7.2, §8.1)."""
import os
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from multiprocessing import get_context

from ..model.errors import WorkerCrashed

# Each worker runs single-threaded numerics; the pool supplies the parallelism. Children read these at
# spawn time, so they stay set for the life of the process.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")


def default_workers(workers: int | None, n_jobs: int) -> int:
    """`workers`, or half the logical CPUs when None, clamped to [1, n_jobs] and the Windows pool limit of 61."""
    # ponytail: half the logical CPUs stands in for the physical core count; psutil is not a dependency.
    workers = workers if workers is not None else max(1, (os.cpu_count() or 2) // 2)
    return max(1, min(workers, n_jobs, 61))


def _pass(fn, items, results, pending, workers, initializer, initargs, cancel, progress) -> None:
    with ProcessPoolExecutor(workers, mp_context=get_context("spawn"), initializer=initializer,
                             initargs=initargs) as pool:
        futures = {pool.submit(fn, items[k]): k for k in pending}
        try:
            for future in as_completed(futures):
                k = futures[future]
                results[k] = future.result()         # raises BrokenProcessPool if a worker died
                pending.remove(k)
                if progress is not None:
                    progress(len(items) - len(pending), len(items))
                if cancel is not None and cancel():
                    pool.shutdown(wait=True, cancel_futures=True)
                    for f, j in futures.items():         # keep jobs that finished while shutting down
                        if j in pending and f.done() and not f.cancelled() and f.exception() is None:
                            results[j] = f.result()
                            pending.remove(j)
                    pending.clear()
                    return
        except BaseException:
            pool.shutdown(wait=False, cancel_futures=True)   # do not run the queued items
            raise


def map_ordered(fn: Callable, items: Iterable, *, workers: int = 1, initializer: Callable | None = None,
                initargs: tuple = (), cancel: Callable[[], bool] | None = None,
                progress: Callable[[int, int], None] | None = None) -> list:
    """fn over items, results in item order, None for items not run because `cancel` fired. `workers <= 1`
    runs in this process. A worker crash re-runs the unfinished items once in a fresh pool; a second crash
    raises WorkerCrashed."""
    items = list(items)
    results: list = [None] * len(items)
    if workers <= 1:
        if initializer is not None:
            initializer(*initargs)
        for k, item in enumerate(items):
            if cancel is not None and cancel():
                break
            results[k] = fn(item)
            if progress is not None:
                progress(k + 1, len(items))
        return results
    pending = list(range(len(items)))
    for attempt in range(2):
        try:
            _pass(fn, items, results, pending, workers, initializer, initargs, cancel, progress)
            return results
        except BrokenProcessPool:
            if attempt == 1:
                raise WorkerCrashed(sorted(pending)) from None
    raise AssertionError("unreachable")
