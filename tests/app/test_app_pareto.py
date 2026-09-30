import numpy as np

from srmapp.pareto import pareto_mask


def test_dominated_point_is_removed():
    v = np.array([[1.0, 1.0], [2.0, 2.0], [3.0, 1.0]])
    assert pareto_mask(v, (True, True)).tolist() == [False, True, True]


def test_minimise_and_maximise_mix():
    # mass down, power up
    v = np.array([[10.0, 5.0], [8.0, 5.0], [8.0, 7.0], [12.0, 9.0]])
    assert pareto_mask(v, (False, True)).tolist() == [False, False, True, True]


def test_duplicates_are_kept():
    v = np.array([[1.0, 1.0], [1.0, 1.0]])
    assert pareto_mask(v, (True, True)).tolist() == [True, True]


def test_single_and_empty():
    assert pareto_mask(np.array([[1.0, 2.0, 3.0]]), (True, True, True)).tolist() == [True]
    assert pareto_mask(np.empty((0, 2)), (True, True)).tolist() == []
