"""Angle and current grids of a map (spec §7.2)."""
import math

import numpy as np

from ..mesh.band import snap_angle
from ..model.design import RadialSRMParams

# (angles, currents) per fidelity preset, following the mesh preset. Provisional until the M5 study.
GRID_SIZES = {"screening": (8, 8), "full": (30, 20), "reference": (60, 40)}


def angle_grid(machine: RadialSRMParams, band_divisions: int, n: int, cluster: float = 0.5) -> np.ndarray:
    """Up to n rotor angles over one rotor pole pitch [0, 2π/Nr), θ = 0 aligned, snapped to the band
    pitch. The warp θ = τ·(u − cluster·sin(2πu)/2π) is densest at alignment (spacing ratio between the
    unaligned and aligned ends is (1 + cluster)/(1 − cluster)). Snapping can merge neighbours, so fewer
    than n angles may come back."""
    tau = 2 * math.pi / machine.n_rotor_poles
    pitch = 2 * math.pi / band_divisions
    u = np.arange(n) / n
    theta = tau * (u - cluster * np.sin(2 * math.pi * u) / (2 * math.pi))
    steps = sorted({snap_angle(t, band_divisions)[1] for t in theta})
    return np.array([k * pitch for k in steps if k * pitch < tau - 1e-9])


def current_grid(i_max: float, n: int, exponent: float = 2.0) -> np.ndarray:
    """n currents from 0 to i_max, denser at low current: i_max·(k/(n−1))^exponent."""
    return i_max * (np.arange(n) / (n - 1)) ** exponent
