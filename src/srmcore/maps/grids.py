"""Angle and current grids of a map (spec §7.2)."""
import math

import numpy as np

from ..mesh.band import snap_angle
from ..model.design import RadialSRMParams

# (angles, currents) per fidelity preset, following the mesh preset. Provisional until the M5 study.
GRID_SIZES = {"screening": (8, 8), "full": (30, 20), "reference": (60, 40)}


def angle_grid(machine: RadialSRMParams, band_divisions: int, n: int, cluster: float = 0.5,
               aligned: float = 0.0) -> np.ndarray:
    """Up to n rotor angles over one rotor pole pitch [0, 2π/Nr), snapped to the band pitch. `aligned` is
    the aligned angle of the excited phase (`aligned_angle`; 0 for phase A): the grid is the phase-A grid
    shifted by it, snapped, wrapped into [0, τ) and sorted. The warp θ = τ·(u − cluster·sin(2πu)/2π) is densest at alignment (spacing ratio between
    the unaligned and aligned ends is (1 + cluster)/(1 − cluster)). Snapping can merge neighbours, so
    fewer than n angles may come back."""
    tau = 2 * math.pi / machine.n_rotor_poles
    pitch = 2 * math.pi / band_divisions
    u = np.arange(n) / n
    theta = tau * (u - cluster * np.sin(2 * math.pi * u) / (2 * math.pi))
    steps = {snap_angle(t + aligned, band_divisions)[1] for t in theta}
    wrapped = {round((k * pitch) % tau, 12) for k in steps}
    # np.unique: an angle just below τ becomes 0.0 and could repeat an existing 0.0.
    return np.unique([0.0 if a > tau - 1e-9 else a for a in wrapped])


def current_grid(i_max: float, n: int, exponent: float = 2.0) -> np.ndarray:
    """n currents from 0 to i_max, denser at low current: i_max·(k/(n−1))^exponent."""
    return i_max * (np.arange(n) / (n - 1)) ** exponent


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
