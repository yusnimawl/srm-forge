"""Pure sizing law used by the Gmsh size callback."""
import numpy as np


def size_at(x: float, y: float, base: float, features: list[tuple[np.ndarray, float, float]]) -> float:
    h = base
    for points, size_min, growth in features:
        distance = float(np.min(np.hypot(points[:, 0] - x, points[:, 1] - y)))
        h = min(h, size_min + (growth - 1.0) * distance)
    return h
