"""Reference sizing law, documenting what the native Gmsh size fields in mesh/static.py compute.

size(x, y) = min(base_size_of_region_containing(x, y),
                  min over refinement features of size_min + (growth - 1) * dist(x, y, feature_points))

Base size on an interface between two regions is the min of the adjacent regions' sizes.
`mesh/static.py` implements this law with native Gmsh Distance/MathEval/Constant/Min fields (in
C++, for speed) rather than a Python `gmsh.model.mesh.setSizeCallback` callback. `size_at` stays as
a plain-Python reference for anyone checking the fields' behaviour by hand; it is not called by the
mesh builder itself.
"""
import numpy as np


def size_at(x: float, y: float, base: float, features: list[tuple[np.ndarray, float, float]]) -> float:
    h = base
    for points, size_min, growth in features:
        distance = float(np.min(np.hypot(points[:, 0] - x, points[:, 1] - y)))
        h = min(h, size_min + (growth - 1.0) * distance)
    return h
