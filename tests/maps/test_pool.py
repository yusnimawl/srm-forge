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
