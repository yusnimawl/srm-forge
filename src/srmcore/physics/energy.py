"""Stored energy and co-energy of a solved field, identical for every solver adapter."""
import numpy as np

from .fem import triangle_areas
from .problem import Magnetostatic2D


def field_energies(problem: Magnetostatic2D, b: np.ndarray) -> tuple[float, float]:
    """(W, W') in joules: depth × Σ_elements area × ∫0^B H dB, and × ∫0^H B dH."""
    bm = np.hypot(b[:, 0], b[:, 1])
    area = triangle_areas(problem.nodes, problem.triangles)
    w = wc = 0.0
    for k, law in enumerate(problem.laws):
        idx = np.flatnonzero(problem.element_law == k)
        if len(idx) == 0:
            continue
        w += float(law.energy_density(bm[idx]) @ area[idx])
        wc += float(law.coenergy_density(bm[idx]) @ area[idx])
    return problem.depth * w, problem.depth * wc
