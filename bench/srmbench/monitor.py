"""Peak memory of the pool workers, sampled from a background thread."""

import sys
import threading

import psutil

SAMPLE_SECONDS = 0.5


def parse_vm_hwm(status_text: str) -> int:
    """Peak resident set in bytes from the text of /proc/<pid>/status (VmHWM is in kB); 0 when absent."""
    for line in status_text.splitlines():
        if line.startswith("VmHWM:"):
            try:
                return int(line.split()[1]) * 1024
            except (IndexError, ValueError):
                return 0
    return 0


def _vm_hwm_bytes(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/status", encoding="ascii", errors="replace") as f:
            return parse_vm_hwm(f.read())
    except OSError:
        return 0


class WorkerRam:
    """Context manager: samples every descendant of this process and keeps the largest single-process
    resident set seen. This process is not sampled: its peak includes everything it did earlier (meshing).
    On Windows the OS-reported peak working set of each descendant is read too, so a process that grew and
    shrank between two samples still counts. On Linux the same holds for the kernel's VmHWM."""

    def __init__(self):
        self.peak_bytes = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def peak_gb(self) -> float:
        return self.peak_bytes / 1e9

    def _sample(self) -> None:
        try:
            procs = psutil.Process().children(recursive=True)
        except psutil.Error:
            return
        for p in procs:
            try:
                info = p.memory_info()
            except (psutil.Error, OSError):
                continue
            seen = info.rss
            if sys.platform == "win32":
                seen = max(seen, getattr(info, "peak_wset", 0))
            elif sys.platform.startswith("linux"):
                seen = max(seen, _vm_hwm_bytes(p.pid))
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
