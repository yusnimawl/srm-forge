"""FEM-backed checks of a map (spec §7.3, §8.3): extra solves at held-out points and at other band radii."""
import math

import numpy as np
from scipy.interpolate import PchipInterpolator

from ..fields.solution import SolveStatus
from ..mesh import build_machine_mesh
from ..mesh.machine import mesh_at_angle
from ..model.design import Design
from ..physics.build import machine_problem
from ..post.quantities import arkkio_torque_annulus
from ..solvers.factory import make_solver
from .checks import Check, _upper
from .grids import aligned_angle
from .point import solve_point
from .pool import default_workers, map_ordered
from .results import key_numbers
from .run import STATUS_NONCONVERGED, MapResult, _init_worker, require_complete, solve_currents_job
from .tables import angle_spline

PSI_TOLERANCE = 0.005            # of ψ_max
TORQUE_TOLERANCE = 0.017         # of peak torque; M5a worst held-out error 1.10 % (24/16 `full` map, 64 samples), x 1.5
BAND_RADIUS_TOLERANCE = 0.01     # of peak torque


def _coprime_step(m: int) -> int:
    """Smallest k >= m/φ coprime to m, so j·k mod m visits every column before repeating and spreads them."""
    k = max(1, math.ceil(m / ((1 + 5 ** 0.5) / 2)))
    while math.gcd(k, m) != 1:
        k += 1
    return k


def _held_out_samples(result: MapResult, tau: float, n_samples: int) -> list[tuple[float, float]]:
    """Angle mid-points (wrap interval included) × non-zero current mid-points, n_samples of them. Angle and
    current indices are spread separately, so a coarse subsample of the flattened product cannot alias onto
    a few current columns. The sample angles are interval mid-points, which fall on the band pitch for
    intervals spanning an even number of pitches; the mesh handles any angle."""
    ang = np.append(result.angles, result.angles[0] + tau)
    cur = result.currents[result.currents > 0]
    mid_a, mid_i = (ang[:-1] + ang[1:]) / 2, (cur[:-1] + cur[1:]) / 2
    n_a, n_i = len(mid_a), len(mid_i)
    if n_samples >= n_a * n_i:
        return [(float(a), float(i)) for a in mid_a for i in mid_i]
    k = _coprime_step(n_i)
    j = np.arange(n_samples)
    ia = np.round(j * (n_a - 1) / max(n_samples - 1, 1)).astype(int)
    return [(float(mid_a[a]), float(mid_i[(t * k) % n_i])) for a, t in zip(ia, j)]


def _band_radius_check(design: Design, static, result: MapResult, solver: str, peak: float) -> Check:
    m = design.machine
    tau = 2 * math.pi / m.n_rotor_poles
    th_a = aligned_angle(m, result.excited)
    i_max = float(result.currents[-1])
    adapter = make_solver(solver)
    gaps = (("airgap_rotor", m.rotor_outer_radius, m.band_inner_radius),
            ("airgap_stator", m.band_outer_radius, m.bore_radius))
    worst = 0.0
    for frac in (1 / 8, 1 / 4, 3 / 8):
        theta = th_a + frac * tau
        currents = {result.excited: i_max}
        point = solve_point(static, design, theta, currents, adapter, keep_field=True)
        if point.status is SolveStatus.NONCONVERGED:
            return Check("band_radius", "fail", float("nan"), BAND_RADIUS_TOLERANCE,
                         f"the solve at {math.degrees(theta):.2f}° and I_max did not converge")
        problem = machine_problem(mesh_at_angle(static, theta), design, currents)
        for name, r_in, r_out in gaps:
            el = np.flatnonzero(problem.element_region == problem.region_names.index(name))
            t_gap = arkkio_torque_annulus(problem, point.field, el, r_in, r_out)
            worst = max(worst, abs(t_gap - point.torque_arkkio) / peak)
    return _upper("band_radius", worst, BAND_RADIUS_TOLERANCE,
                  "Arkkio torque over each air-gap layer against the band at 3 angles and I_max, relative to peak torque")


def fem_checks(design: Design, result: MapResult, *, solver: str = "ngsolve", workers: int | None = None,
               n_samples: int = 64) -> tuple[Check, ...]:
    """Empty for the screening preset. Otherwise: `held_out_psi` and `held_out_torque` compare FEM solves at
    grid mid-points (angle mid-points × non-zero current mid-points, evenly subsampled to `n_samples`; 16
    samples under-read the worst error by up to 2.8x in M5a) with the
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
    workers = default_workers(workers, len(samples))
    static = build_machine_mesh(design)
    # solve_currents_job also computes L_inc, which these checks do not use; that cost is accepted.
    rows = map_ordered(solve_currents_job, [(a, {result.excited: i}) for a, i in samples], workers=workers,
                       initializer=_init_worker, initargs=(static, design, solver, 1 if workers > 1 else None))
    psi_spl = angle_spline(result.angles, result.psi[..., e], tau)
    t_spl = angle_spline(result.angles, result.torque_arkkio, tau)
    err_psi = err_t = 0.0
    used = 0
    for (a, i), row in zip(samples, rows):
        if row["status"] == STATUS_NONCONVERGED:
            continue
        used += 1
        psi_i = float(PchipInterpolator(result.currents, psi_spl(a))(i))
        t_i = float(PchipInterpolator(result.currents, t_spl(a))(i))
        err_psi = max(err_psi, abs(row["psi"][e] - psi_i) / key.psi_max)
        err_t = max(err_t, abs(row["torque_arkkio"] - t_i) / key.peak_torque)
    skipped = f", {len(samples) - used} non-converged skipped" if used < len(samples) else ""
    if used == 0:
        held = tuple(Check(n, "fail", float("nan"), tol, "every held-out solve was non-converged")
                     for n, tol in (("held_out_psi", PSI_TOLERANCE), ("held_out_torque", TORQUE_TOLERANCE)))
    else:
        held = (
            _upper("held_out_psi", err_psi, PSI_TOLERANCE,
                   f"FEM ψ against the map interpolant at {used} held-out points, relative to ψ_max{skipped}"),
            _upper("held_out_torque", err_t, TORQUE_TOLERANCE,
                   f"FEM torque against the map interpolant at {used} held-out points, relative to peak torque{skipped}"),
        )
    return held + (_band_radius_check(design, static, result, solver, key.peak_torque),)
