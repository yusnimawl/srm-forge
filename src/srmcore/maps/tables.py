"""Products derived from a map: ∂ψ/∂θ and the inverse drive tables i(θ, ψ), T(θ, ψ) (spec §7.3)."""
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline, PchipInterpolator

from .run import MapResult, require_complete


def angle_spline(angles: np.ndarray, values: np.ndarray, period: float) -> CubicSpline:
    """Periodic cubic spline over one period, angle on axis 0; the first sample closes the loop at angle + period."""
    angles = np.asarray(angles, float)
    values = np.asarray(values, float)
    return CubicSpline(np.append(angles, angles[0] + period), np.concatenate([values, values[:1]]),
                       axis=0, bc_type="periodic")


def dpsi_dtheta(result: MapResult, period: float) -> np.ndarray:
    """∂ψ/∂θ (angle, current, circuit), Wb-turns/rad, at the map angles."""
    require_complete(result)
    return angle_spline(result.angles, result.psi, period)(result.angles, 1)


@dataclass(frozen=True, eq=False)
class DriveTables:
    """i(θ, ψ) and T(θ, ψ) of the excited circuit on a common ψ grid. `current` and `torque` are NaN where ψ
    exceeds ψ(θ, I_max) and on non-monotone angles; `flat` marks points with ∂ψ/∂i below `eps`."""
    angles: np.ndarray
    psi_grid: np.ndarray               # (n_psi,)
    current: np.ndarray                # (n_angles, n_psi), A
    torque: np.ndarray                 # (n_angles, n_psi), N·m (Arkkio)
    flat: np.ndarray                   # (n_angles, n_psi) bool
    monotone: np.ndarray               # (n_angles,) bool: ψ strictly increasing in current
    roundtrip_error: float             # NaN if no point is defined; else max |ψ(θ, i(θ, ψ)) − ψ| / ψ_max over defined points


def drive_tables(result: MapResult, n_psi: int | None = None, eps: float | None = None) -> DriveTables:
    require_complete(result)
    e = result.circuits.index(result.excited)
    cur, psi = result.currents, result.psi[..., e]
    if cur[0] != 0:
        raise ValueError("the first current must be 0")
    n_psi = n_psi or 2 * len(cur)
    # The aligned row is found by the largest ψ at I_max, so it does not depend on the angle-grid layout; this
    # agrees with `aligned_angle` for a valid map. Its ψ values at uniform currents make the grid dense in ψ
    # where the curve flattens.
    a0 = int(np.argmax(psi[:, -1]))
    if not np.all(np.diff(psi[a0]) > 0):
        raise ValueError("ψ(i) at the aligned angle is not strictly increasing")
    grid = PchipInterpolator(cur, psi[a0])(np.linspace(cur[0], cur[-1], n_psi))
    if eps is None:
        eps = 1e-3 * psi[a0, 1] / cur[1]
    n_a = len(result.angles)
    i_tab, t_tab = np.full((n_a, n_psi), np.nan), np.full((n_a, n_psi), np.nan)
    flat = np.zeros((n_a, n_psi), dtype=bool)
    monotone = np.all(np.diff(psi, axis=1) > 0, axis=1)
    err = None
    for a in np.flatnonzero(monotone):
        ok = grid <= psi[a, -1]
        i = PchipInterpolator(psi[a], cur)(grid[ok])
        psi_i = PchipInterpolator(cur, psi[a])
        i_tab[a, ok] = i
        t_tab[a, ok] = PchipInterpolator(cur, result.torque_arkkio[a])(i)
        flat[a, ok] = psi_i(i, 1) < eps
        e_a = float(np.max(np.abs(psi_i(i) - grid[ok])))
        err = e_a if err is None else max(err, e_a)
    return DriveTables(result.angles, grid, i_tab, t_tab, flat, monotone,
                       np.nan if err is None else err / float(np.max(np.abs(grid))))
