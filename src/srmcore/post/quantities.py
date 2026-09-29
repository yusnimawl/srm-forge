"""Per-point post-processing (spec §7.1): flux linkage per circuit."""
import numpy as np

from ..fields.solution import FieldSolution
from ..physics.fem import triangle_areas
from ..physics.problem import Magnetostatic2D


def flux_linkage(problem: Magnetostatic2D, solution: FieldSolution) -> np.ndarray:
    """ψ_k = L·Σ_s C_sk·∫_s A dA per circuit, Wb-turns. ∫A dA on a P1 triangle = area × mean nodal A."""
    in_coil = np.flatnonzero(problem.element_coil >= 0)
    tri = problem.triangles[in_coil]
    integral = triangle_areas(problem.nodes, tri) * solution.a[tri].mean(axis=1)
    per_side = np.bincount(problem.element_coil[in_coil], weights=integral,
                           minlength=len(problem.winding.coil_sides))
    return problem.depth * problem.winding.matrix.T @ per_side
