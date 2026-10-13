import multiprocessing as mp
import time

from srmbench.monitor import WorkerRam


def _allocate_and_sleep(mb: float, seconds: float) -> None:
    block = bytearray(int(mb * 1e6))
    for i in range(0, len(block), 4096):
        block[i] = 1
    time.sleep(seconds)


def test_worker_ram_sees_child_process():
    ctx = mp.get_context("spawn")
    with WorkerRam() as ram:
        child = ctx.Process(target=_allocate_and_sleep, args=(200, 2.0))
        child.start()
        child.join()
    assert ram.peak_gb >= 0.15


def test_worker_ram_tolerates_exit():
    ctx = mp.get_context("spawn")
    with WorkerRam() as ram:
        child = ctx.Process(target=_allocate_and_sleep, args=(1, 0.0))
        child.start()
        child.join()
    assert ram.peak_gb >= 0.0
