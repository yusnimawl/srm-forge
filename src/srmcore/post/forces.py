"""Per-pole force on the stator from the Maxwell stress in the air-gap band (spec §7.1)."""
import numpy as np

from ..fields.solution import FieldSolution
from ..model.constants import MU0
from ..physics.fem import triangle_areas
from ..physics.problem import Magnetostatic2D
from .quantities import _MIDPOINTS


def pole_forces(problem: Magnetostatic2D, solution: FieldSolution, n_stator_poles: int) -> np.ndarray:
    """[radial, tangential] force in N on each stator pole, stack length included.

    Radial is positive outward, tangential counter-clockwise; the components are the polar ones of the
    band stress, summed over the sector of pole k at angle k·2π/Ns, so Σ_k F_θ,k·r = -T. The stress on the stator
    side of the band is f_r = -(B_r² - B_θ²)/(2μ0), f_θ = -B_r·B_θ/μ0; like the Arkkio torque, ∫_band f dS / (r_out - r_in) stands in for the contour integral ∫ f r dθ.
    Each band element belongs to the pole sector containing its centroid angle."""
    if problem.band is None:
        raise ValueError("Pole forces need a moving band (problem.band is None)")
    el = problem.band.elements
    tri = problem.triangles[el]
    corners = problem.nodes[tri]                                       # (n, 3, 2)
    pitch = 2 * np.pi / n_stator_poles
    centroid = corners.mean(axis=1)
    pole = np.floor((np.arctan2(centroid[:, 1], centroid[:, 0]) + pitch / 2) / pitch).astype(int) % n_stator_poles
    bx, by = solution.b[el, 0], solution.b[el, 1]
    radial, tangential = np.zeros(len(el)), np.zeros(len(el))
    for weights in _MIDPOINTS:
        p = np.einsum("j,njk->nk", weights, corners)
        r = np.hypot(p[:, 0], p[:, 1])
        b_r, b_t = (bx * p[:, 0] + by * p[:, 1]) / r, (-bx * p[:, 1] + by * p[:, 0]) / r
        f_r, f_t = -(b_r**2 - b_t**2) / (2 * MU0), -b_r * b_t / MU0
        radial += f_r / 3
        tangential += f_t / 3
    area = triangle_areas(problem.nodes, tri)
    scale = problem.depth / (problem.band.outer_radius - problem.band.inner_radius)
    return scale * np.column_stack([np.bincount(pole, radial * area, n_stator_poles),
                                    np.bincount(pole, tangential * area, n_stator_poles)])
