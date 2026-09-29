"""Per-point post-processing (spec §7.1): flux linkage per circuit, Arkkio torque, saturation report."""
from dataclasses import dataclass

import numpy as np

from ..fields.solution import FieldSolution
from ..model.constants import MU0
from ..model.design import RadialSRMParams
from ..physics.fem import element_flux_density, triangle_areas
from ..physics.problem import Magnetostatic2D

# Degree-2 rule on a triangle: the three edge midpoints, equal weights 1/3.
_MIDPOINTS = np.array([[0.5, 0.5, 0.0], [0.0, 0.5, 0.5], [0.5, 0.0, 0.5]])


def _linkage(problem: Magnetostatic2D, a: np.ndarray) -> np.ndarray:
    in_coil = np.flatnonzero(problem.element_coil >= 0)
    tri = problem.triangles[in_coil]
    integral = triangle_areas(problem.nodes, tri) * a[tri].mean(axis=1)
    per_side = np.bincount(problem.element_coil[in_coil], weights=integral,
                           minlength=len(problem.winding.coil_sides))
    return problem.depth * problem.winding.matrix.T @ per_side


def flux_linkage(problem: Magnetostatic2D, solution: FieldSolution) -> np.ndarray:
    """ψ_k = L·Σ_s C_sk·∫_s A dA per circuit, Wb-turns. ∫A dA on a P1 triangle = area × mean nodal A."""
    return _linkage(problem, solution.a)


def incremental_inductance(problem: Magnetostatic2D, sensitivity: np.ndarray) -> np.ndarray:
    """L_inc[k, j] = ∂ψ_k/∂i_j, H. ψ is linear in A, so column j is the flux linkage of the response dA/di_j."""
    return np.column_stack([_linkage(problem, sensitivity[:, j]) for j in range(sensitivity.shape[1])])


def arkkio_torque(problem: Magnetostatic2D, solution: FieldSolution) -> float:
    """T = L / (μ0·(r_out - r_in)) · ∫_band r·B_r·B_θ dS, N·m, positive counter-clockwise on the rotor."""
    if problem.band is None:
        raise ValueError("Arkkio torque needs a moving band (problem.band is None)")
    el = problem.band.elements
    tri = problem.triangles[el]
    bx, by = solution.b[el, 0], solution.b[el, 1]
    corners = problem.nodes[tri]                                  # (n, 3, 2)
    total = np.zeros(len(el))
    for weights in _MIDPOINTS:
        p = np.einsum("j,njk->nk", weights, corners)
        x, y = p[:, 0], p[:, 1]
        r = np.hypot(x, y)
        total += (bx * x + by * y) * (-bx * y + by * x) / r / 3   # r·B_r·B_θ
    integral = float(total @ triangle_areas(problem.nodes, tri))
    return problem.depth * integral / (MU0 * (problem.band.outer_radius - problem.band.inner_radius))


def virtual_work_torque(problem: Magnetostatic2D, solution: FieldSolution, delta: float = 1e-6) -> float:
    """Nodal-force torque T = -dΠ/dθ at fixed A, N·m, positive counter-clockwise on the rotor.

    Π = L·Σ area·w(|B|) - ∫J·A is the discrete energy functional, so W' = -Π at the solution. A virtual
    rotation of the rotor moves the band nodes by φ(r)·δ (φ = 1 at the rotor side, 0 at the stator side,
    linear between); every other element rotates rigidly or not at all and keeps its energy. The band is
    air without current, so only the field energy of the band elements varies. Central difference in δ."""
    if problem.band is None:
        raise ValueError("Virtual-work torque needs a moving band (problem.band is None)")
    band = problem.band
    el = band.elements
    tri = problem.triangles[el]
    a = solution.a[tri].reshape(-1)
    corners = problem.nodes[tri]                                       # (n, 3, 2)
    radius = np.hypot(corners[..., 0], corners[..., 1])
    phi = np.clip((band.outer_radius - radius) / (band.outer_radius - band.inner_radius), 0.0, 1.0)
    local_tri = np.arange(3 * len(el)).reshape(-1, 3)
    groups = [(law, np.flatnonzero(problem.element_law[el] == k)) for k, law in enumerate(problem.laws)]

    def band_energy(angle: float) -> float:
        c, s = np.cos(angle * phi), np.sin(angle * phi)
        moved = np.stack([corners[..., 0] * c - corners[..., 1] * s,
                          corners[..., 0] * s + corners[..., 1] * c], axis=-1).reshape(-1, 2)
        b = element_flux_density(moved, local_tri, a)
        bm = np.hypot(b[:, 0], b[:, 1])
        area = triangle_areas(moved, local_tri)
        return problem.depth * sum(float(law.energy_density(bm[idx]) @ area[idx]) for law, idx in groups if len(idx))

    return -(band_energy(delta) - band_energy(-delta)) / (2 * delta)


@dataclass(frozen=True)
class SaturationStats:
    peak: float
    p95: float
    p99: float


def _stats(bm: np.ndarray, area: np.ndarray) -> SaturationStats:
    order = np.argsort(bm)
    cum = np.cumsum(area[order]) / area.sum()
    pick = lambda q: float(bm[order][min(np.searchsorted(cum, q), len(bm) - 1)])  # noqa: E731
    return SaturationStats(peak=float(bm.max()), p95=pick(0.95), p99=pick(0.99))


def saturation_report(problem: Magnetostatic2D, solution: FieldSolution,
                      machine: RadialSRMParams) -> dict[str, SaturationStats]:
    """|B| peak and area-weighted 95th/99th percentiles per region, plus the iron split into poles and
    yokes by radius (stator yoke: r > stator_yoke_inner_radius; rotor yoke: r < rotor_yoke_outer_radius)."""
    bm = np.hypot(solution.b[:, 0], solution.b[:, 1])
    area = triangle_areas(problem.nodes, problem.triangles)
    centroid_r = np.hypot(*problem.nodes[problem.triangles].mean(axis=1).T)
    report: dict[str, SaturationStats] = {}
    groups: dict[str, np.ndarray] = {}
    for rid, name in enumerate(problem.region_names):
        groups[name] = problem.element_region == rid
    kind = np.array([problem.region_kind[n] for n in problem.region_names])[problem.element_region]
    stator, rotor = kind == "stator_iron", kind == "rotor_iron"
    groups["stator_yoke"] = stator & (centroid_r > machine.stator_yoke_inner_radius)
    groups["stator_poles"] = stator & (centroid_r <= machine.stator_yoke_inner_radius)
    groups["rotor_yoke"] = rotor & (centroid_r < machine.rotor_yoke_outer_radius)
    groups["rotor_poles"] = rotor & (centroid_r >= machine.rotor_yoke_outer_radius)
    for name, mask in groups.items():
        if mask.any():
            report[name] = _stats(bm[mask], area[mask])
    return report
