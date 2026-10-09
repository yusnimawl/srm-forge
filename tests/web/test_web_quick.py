import math
import threading
import time

import pytest

from srmweb.quick import LaneTimeout, QuickLane


@pytest.fixture
def lane():
    q = QuickLane(spawn=False)
    yield q
    q.stop()


def _start(target, *args):
    t = threading.Thread(target=target, args=args)
    t.start()
    return t


def test_tasks_run_in_arrival_order(lane):
    order, gate = [], threading.Event()

    def task(i):
        gate.wait(5)
        order.append(i)

    threads = []
    for i in range(3):
        threads.append(_start(lane.run, task, i))
        time.sleep(0.1)
    gate.set()
    for t in threads:
        t.join(5)
    assert order == [0, 1, 2]


def test_task_exception_reaches_the_caller(lane):
    def boom():
        raise ValueError("bad")

    with pytest.raises(ValueError, match="bad"):
        lane.run(boom)


def test_queued_task_times_out_and_never_runs(lane):
    gate, ran = threading.Event(), []
    first = _start(lane.run, gate.wait, 5)
    time.sleep(0.1)
    with pytest.raises(LaneTimeout):
        lane.run(ran.append, 1, timeout=0.2)
    gate.set()
    first.join(5)
    time.sleep(0.2)
    assert ran == []


def test_request_runs_between_the_tasks_of_a_loop(lane):
    order, gates = [], [threading.Event() for _ in range(3)]
    started = threading.Event()

    def step(i):
        if i == 0:
            started.set()
        gates[i].wait(5)
        order.append(f"L{i + 1}")

    def loop():
        for i in range(3):
            lane.run(step, i)

    looper = _start(loop)
    assert started.wait(5)
    request = _start(lane.run, order.append, "R")
    time.sleep(0.2)
    for g in gates:
        g.set()
    looper.join(5)
    request.join(5)
    assert order == ["L1", "R", "L2", "L3"]


@pytest.mark.slow
def test_timeout_kills_the_worker_and_the_next_task_runs():
    lane = QuickLane(spawn=True)
    try:
        t0 = time.monotonic()
        with pytest.raises(LaneTimeout):
            lane.run(time.sleep, 30, timeout=3)
        assert time.monotonic() - t0 < 10
        assert lane.run(math.sqrt, 4.0, timeout=60) == 2.0
    finally:
        lane.stop()
