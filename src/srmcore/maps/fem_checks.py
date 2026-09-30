"""FEM-backed checks of a map (spec §7.3, §8.3): extra solves at held-out points and at other band radii."""
import math
import os

import numpy as np
from scipy.interpolate import PchipInterpolator

from ..mesh import build_machine_mesh
from ..mesh.machine import mesh_at_angle
from ..model.design import Design
from ..physics.build import machine_problem
from ..post.quantities import arkkio_torque_annulus
from ..solvers.factory import make_solver
from .checks import Check, _upper
from .grids import aligned_angle
from .point import solve_point
from .pool import map_ordered
from .results import key_numbers
from .run import MapResult, _init_worker, require_complete, solve_currents_job
from .tables import angle_spline

PSI_TOLERANCE = 0.005            # of ψ_max
TORQUE_TOLERANCE = 0.01          # of peak torque
BAND_RADIUS_TOLERANCE = 0.01     # of peak torque


def _held_out_samples(result: MapResult, tau: float, n_samples: int) -> list[tuple[float, float]]:
    ang = np.append(result.angles, result.angles[0] + tau)
    cur = result.currents[result.currents > 0]
    mid_a, mid_i = (ang[:-1] + ang[1:]) / 2, (cur[:-1] + cur[1:]) / 2
    candidates = [(float(a), float(i)) for a in mid_a for i in mid_i]
    if len(candidates) <= n_samples:
        return candidates
    return [candidates[k] for k in np.linspace(0, len(candidates) - 1, n_samples).round().astype(int)]


def _band_radius_check(design: Design, result: MapResult, solver: str, peak: float) -> Check:
    m = design.machine
    tau = 2 * math.pi / m.n_rotor_poles
    th_a = aligned_angle(m, result.excited)
    i_max = float(result.currents[-1])
    static = build_machine_mesh(design)
    adapter = make_solver(solver)
    gaps = (("airgap_rotor", m.rotor_outer_radius, m.band_inner_radius),
            ("airgap_stator", m.band_outer_radius, m.bore_radius))
    worst = 0.0
    for frac in (1 / 8, 1 / 4, 3 / 8):
        theta = th_a + frac * tau
        currents = {result.excited: i_max}
        point = solve_point(static, design, theta, currents, adapter, keep_field=True)
        problem = machine_problem(mesh_at_angle(static, theta), design, currents)
        for name, r_in, r_out in gaps:
            el = np.flatnonzero(problem.element_region == problem.region_names.index(name))
            t_gap = arkkio_torque_annulus(problem, point.field, el, r_in, r_out)
            worst = max(worst, abs(t_gap - point.torque_arkkio) / peak)
    return _upper("band_radius", worst, BAND_RADIUS_TOLERANCE,
                  "Arkkio torque over each air-gap layer against the band at 3 angles and I_max, relative to peak torque")


def fem_checks(design: Design, result: MapResult, *, solver: str = "ngsolve", workers: int | None = None,
               n_samples: int = 16) -> tuple[Check, ...]:
    """Empty for the screening preset. Otherwise: `held_out_psi` and `held_out_torque` compare FEM solves at
    grid mid-points (angle mid-points × non-zero current mid-points, evenly subsampled to `n_samples`) with the
    periodic-spline × PCHIP interpolant of the map; `band_radius` compares the torque from the two air-gap
    layers with the band torque."""
    if design.mesh.preset == "screening":
        return ()
    require_complete(result)
    m = design.machine
    tau = 2 * math.pi / m.n_rotor_poles
    e = result.circuits.index(result.excited)
    key = key_numbers(result, m)
    samples = _held_out_samples(result, tau, n_samples)
    workers = workers if workers is not None else max(1, (os.cpu_count() or 2) // 2)
    workers = max(1, min(workers, len(samples), 61))
    rows = map_ordered(solve_currents_job, [(a, {result.excited: i}) for a, i in samples], workers=workers,
                       initializer=_init_worker,
                       initargs=(build_machine_mesh(design), design, solver, 1 if workers > 1 else None))
    psi_spl = angle_spline(result.angles, result.psi[..., e], tau)
    t_spl = angle_spline(result.angles, result.torque_arkkio, tau)
    err_psi = err_t = 0.0
    for (a, i), row in zip(samples, rows):
        psi_i = float(PchipInterpolator(result.currents, psi_spl(a))(i))
        t_i = float(PchipInterpolator(result.currents, t_spl(a))(i))
        err_psi = max(err_psi, abs(row["psi"][e] - psi_i) / key.psi_max)
        err_t = max(err_t, abs(row["torque_arkkio"] - t_i) / key.peak_torque)
    return (
        _upper("held_out_psi", err_psi, PSI_TOLERANCE, f"FEM ψ against the map interpolant at {len(samples)} held-out points, relative to ψ_max"),
        _upper("held_out_torque", err_t, TORQUE_TOLERANCE, f"FEM torque against the map interpolant at {len(samples)} held-out points, relative to peak torque"),
        _band_radius_check(design, result, solver, key.peak_torque),
    )
