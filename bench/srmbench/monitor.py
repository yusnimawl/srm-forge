"""Peak memory of the pool workers, sampled from a background thread."""

import sys
import threading

import psutil

SAMPLE_SECONDS = 0.5


class WorkerRam:
    """Context manager: samples every descendant of this process (plus this process when `workers == 1`,
    because a single-worker run solves in-process) and keeps the largest single-process resident set seen.
    On Windows the OS-reported peak working set of each process is read too, so a process that grew and shrank
    between two samples still counts."""

    def __init__(self, workers: int):
        self.workers = workers
        self.peak_bytes = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def peak_gb(self) -> float:
        return self.peak_bytes / 1e9

    def _sample(self) -> None:
        me = psutil.Process()
        try:
            procs = me.children(recursive=True)
        except psutil.Error:
            procs = []
        if self.workers == 1:
            procs.append(me)
        for p in procs:
            try:
                info = p.memory_info()
            except (psutil.Error, OSError):
                continue
            seen = info.rss
            if sys.platform == "win32":
                seen = max(seen, getattr(info, "peak_wset", 0))
            self.peak_bytes = max(self.peak_bytes, seen)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._sample()
            self._stop.wait(SAMPLE_SECONDS)

    def __enter__(self) -> "WorkerRam":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self._sample()
