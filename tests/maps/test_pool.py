import os

import pytest

from srmcore.maps.pool import map_ordered
from srmcore.model.errors import WorkerCrashed


def test_results_keep_item_order_in_process_and_in_a_pool():
    assert map_ordered(abs, [-1, -2, -3]) == [1, 2, 3]
    assert map_ordered(abs, [-1, -2, -3, -4], workers=2) == [1, 2, 3, 4]


def test_cancel_returns_none_for_unrun_items():
    seen = []
    out = map_ordered(abs, [-1, -2, -3], cancel=lambda: len(seen) >= 1, progress=lambda d, t: seen.append(d))
    assert out == [1, None, None]


def test_a_crashing_worker_is_retried_once_then_reported():
    with pytest.raises(WorkerCrashed) as e:
        map_ordered(os._exit, [1], workers=2)
    assert e.value.items == [0]


def _crash_once(item):
    marker, value = item
    if not os.path.exists(marker):
        open(marker, "w").close()
        os._exit(1)
    return value


def test_a_worker_crash_is_retried_and_the_result_is_complete(tmp_path):
    items = [(str(tmp_path / "marker"), v) for v in (10, 20, 30, 40)]
    assert map_ordered(_crash_once, items, workers=2) == [10, 20, 30, 40]


def test_pool_cancel_keeps_finished_results():
    out = map_ordered(abs, [-1, -2, -3, -4, -5, -6], workers=2, cancel=lambda: True)
    assert any(v is not None for v in out)
    assert all(v is None or v == abs(-(k + 1)) for k, v in enumerate(out))
