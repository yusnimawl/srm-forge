"""Pure sizing law used by the Gmsh size callback."""
import numpy as np
from scipy.spatial import cKDTree


def size_at(x: float, y: float, base: float, features: list[tuple[np.ndarray, float, float]]) -> float:
    h = base
    for points, size_min, growth in features:
        distance = float(np.min(np.hypot(points[:, 0] - x, points[:, 1] - y)))
        h = min(h, size_min + (growth - 1.0) * distance)
    return h


class SizeField:
    """KD-tree accelerated equivalent of size_at, for the Gmsh size callback."""

    def __init__(self, features: list[tuple[np.ndarray, float, float]]):
        self._items = [(cKDTree(points), size_min, growth) for points, size_min, growth in features if len(points)]

    def __call__(self, x: float, y: float, base: float) -> float:
        h = base
        for tree, size_min, growth in self._items:
            distance, _ = tree.query((x, y))
            h = min(h, size_min + (growth - 1.0) * float(distance))
        return h
