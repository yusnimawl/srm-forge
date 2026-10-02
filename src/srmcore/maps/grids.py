"""Angle and current grids of a map (spec §7.2)."""
import math

import numpy as np

from ..mesh.band import snap_angle
from ..model.design import RadialSRMParams

# (angles, power-law currents; the La current is added on top) per fidelity preset, following the mesh
# preset. Sizes from the M5a angle-interpolation study.
GRID_SIZES = {"screening": (40, 8), "full": (48, 20), "reference": (120, 40)}

# Strength and width (fraction of the rotor pole pitch) of the density bumps at the pole corners, from the
# M5a angle-interpolation study (docs/m5a-convergence.md).
CORNER_AMPLITUDE = 2.0
CORNER_WIDTH = 0.015

# La and Lu are secant inductances at this fraction of I_max, so they do not depend on the grid spacing.
LA_CURRENT_FRACTION = 0.05


def angle_grid(machine: RadialSRMParams, band_divisions: int, n: int, aligned: float = 0.0) -> np.ndarray:
    """Up to n rotor angles over one rotor pole pitch [0, 2π/Nr), snapped to the band pitch. `aligned` is
    the aligned angle of the excited phase (`aligned_angle`; 0 for phase A): the grid is the phase-A grid
    shifted by it, snapped, wrapped into [0, τ) and sorted. The density peaks at the pole corners
    (alignment, overlap start and end), where the torque switches on and off: the cubic angle spline cannot
    follow that cliff on a coarse grid. Snapping can merge neighbours, so fewer than n angles may come
    back."""
    tau = 2 * math.pi / machine.n_rotor_poles
    pitch = 2 * math.pi / band_divisions
    bs, br = machine.stator_pole_arc, machine.rotor_pole_arc
    theta_f, theta_c = abs(br - bs) / 2, (bs + br) / 2
    corners = [0.0, theta_f, theta_c, tau - theta_c, tau - theta_f]
    x = np.linspace(0.0, tau, 20001)
    rho = np.ones_like(x)
    for c in corners:
        for k in (-1, 0, 1):
            rho += CORNER_AMPLITUDE * np.exp(-0.5 * ((x - c - k * tau) / (CORNER_WIDTH * tau)) ** 2)
    cdf = np.concatenate([[0.0], np.cumsum((rho[1:] + rho[:-1]) / 2 * np.diff(x))])
    theta = np.interp(np.arange(n) / n, cdf / cdf[-1], x)
    steps = {snap_angle(t + aligned, band_divisions)[1] for t in theta}
    wrapped = {round((k * pitch) % tau, 12) for k in steps}
    # np.unique: an angle just below τ becomes 0.0 and could repeat an existing 0.0.
    return np.unique([0.0 if a > tau - 1e-9 else a for a in wrapped])


def current_grid(i_max: float, n: int, exponent: float = 2.0) -> np.ndarray:
    """The n power-law currents i_max·(k/(n−1))^exponent, denser at low current, plus the La current
    LA_CURRENT_FRACTION·i_max (where `key_numbers` reads La and Lu), sorted and without duplicates."""
    nodes = i_max * (np.arange(n) / (n - 1)) ** exponent
    i_la = LA_CURRENT_FRACTION * i_max
    if np.isclose(nodes, i_la, rtol=1e-9, atol=0).any():
        return nodes
    return np.union1d(nodes, [i_la])


def aligned_angle(machine: RadialSRMParams, excited: str) -> float:
    """Rotor angle at which the excited phase is aligned: (k·ε) mod τ for phase letter index k (A = 0),
    stroke angle ε = 2π/(m·Nr) and rotor pole pitch τ = 2π/Nr."""
    tau = 2 * math.pi / machine.n_rotor_poles
    eps = tau / machine.n_phases
    k = ord(excited) - ord("A") if len(excited) == 1 else -1
    if not 0 <= k < machine.n_phases:
        last = chr(ord("A") + machine.n_phases - 1)
        raise ValueError(f"phase {excited!r} is not a phase of this machine (A..{last})")
    return (k * eps) % tau
