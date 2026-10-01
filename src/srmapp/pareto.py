"""Non-dominated sorting."""
from collections.abc import Sequence

import numpy as np


def pareto_mask(values: np.ndarray, maximize: Sequence[bool]) -> np.ndarray:
    """True for rows no other row dominates. Columns flagged in `maximize` are better when larger, the rest
    when smaller; identical rows are all kept."""
    v = np.asarray(values, float)
    if v.size == 0:
        return np.zeros(0, dtype=bool)
    v = v * np.where(np.asarray(maximize), 1.0, -1.0)
    mask = np.ones(len(v), dtype=bool)
    for k in range(len(v)):
        dominated_by = np.all(v >= v[k], axis=1) & np.any(v > v[k], axis=1)
        mask[k] = not dominated_by.any()
    return mask
