"""Per-pole force on the stator from the Maxwell stress in the air-gap band (spec §7.1)."""
import numpy as np

from ..fields.solution import FieldSolution
from ..model.constants import MU0
from ..physics.fem import triangle_areas
from ..physics.problem import Magnetostatic2D
from .quantities import _MIDPOINTS


def pole_forces(problem: Magnetostatic2D, solution: FieldSolution, n_stator_poles: int) -> np.ndarray:
    """Net force vector on stator pole k, N, stack length included, in the pole's radial/tangential frame
    at φ_k = k·2π/Ns: [radial outward, tangential counter-clockwise].

    The stress on the stator side of the band is f = f_r·r̂ + f_θ·θ̂ with f_r = -(B_r² - B_θ²)/(2μ0),
    f_θ = -B_r·B_θ/μ0. Each band element's x-y force joins the pole sector containing its centroid angle;
    like the Arkkio torque, ∫_band f dS / (r_out - r_in) stands in for the contour integral ∫ f r dθ."""
    if problem.band is None:
        raise ValueError("Pole forces need a moving band (problem.band is None)")
    el = problem.band.elements
    tri = problem.triangles[el]
    corners = problem.nodes[tri]                                       # (n, 3, 2)
    pitch = 2 * np.pi / n_stator_poles
    centroid = corners.mean(axis=1)
    pole = np.floor((np.arctan2(centroid[:, 1], centroid[:, 0]) + pitch / 2) / pitch).astype(int) % n_stator_poles
    bx, by = solution.b[el, 0], solution.b[el, 1]
    fx, fy = np.zeros(len(el)), np.zeros(len(el))
    for weights in _MIDPOINTS:
        p = np.einsum("j,njk->nk", weights, corners)
        r = np.hypot(p[:, 0], p[:, 1])
        b_r, b_t = (bx * p[:, 0] + by * p[:, 1]) / r, (-bx * p[:, 1] + by * p[:, 0]) / r
        f_r, f_t = -(b_r**2 - b_t**2) / (2 * MU0), -b_r * b_t / MU0
        fx += (f_r * p[:, 0] - f_t * p[:, 1]) / r / 3
        fy += (f_r * p[:, 1] + f_t * p[:, 0]) / r / 3
    area = triangle_areas(problem.nodes, tri)
    scale = problem.depth / (problem.band.outer_radius - problem.band.inner_radius)
    total = scale * np.column_stack([np.bincount(pole, fx * area, n_stator_poles),
                                     np.bincount(pole, fy * area, n_stator_poles)])
    phi = np.arange(n_stator_poles) * pitch
    c, sn = np.cos(phi), np.sin(phi)
    return np.column_stack([total[:, 0] * c + total[:, 1] * sn, -total[:, 0] * sn + total[:, 1] * c])
