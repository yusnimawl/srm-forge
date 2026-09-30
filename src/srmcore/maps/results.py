"""Standard results of a map: key numbers and secant inductance curves of the excited phase."""
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..model.design import RadialSRMParams
from .grids import aligned_angle
from .run import MapResult, require_complete
from .tables import angle_spline


@dataclass(frozen=True)
class KeyNumbers:
    la: float               # aligned secant inductance ψ/i at I_max, H
    lu: float               # unaligned secant inductance at I_max, H
    la_lu: float
    peak_torque: float      # max |Arkkio torque| over the grid, N·m
    psi_max: float          # excited ψ at the aligned angle and I_max, Wb-turns
    i_max: float            # A
    aligned_angle: float    # rad
    unaligned_angle: float  # rad


def key_numbers(result: MapResult, machine: RadialSRMParams) -> KeyNumbers:
    """Aligned and unaligned values come from the periodic angle spline, so they do not depend on grid indices."""
    require_complete(result)
    tau = 2 * math.pi / machine.n_rotor_poles
    th_a = aligned_angle(machine, result.excited)
    th_u = th_a + tau / 2
    i_max = float(result.currents[-1])
    psi = angle_spline(result.angles, result.psi[:, -1, result.circuits.index(result.excited)], tau)
    psi_a, psi_u = float(psi(th_a)), float(psi(th_u))
    return KeyNumbers(psi_a / i_max, psi_u / i_max, psi_a / psi_u, float(np.max(np.abs(result.torque_arkkio))),
                      psi_a, i_max, th_a, th_u)


def inductance_curves(result: MapResult, currents: Sequence[float] | None = None) -> np.ndarray:
    """Secant ψ/i of the excited circuit (angle, n_sel) at grid currents; default all non-zero grid currents."""
    require_complete(result)
    cur = result.currents
    if currents is None:
        idx = np.arange(1, len(cur))
    else:
        idx = np.array([int(np.argmin(np.abs(cur - c))) for c in currents], dtype=int)
        if not np.allclose(cur[idx], currents) or np.any(cur[idx] == 0):
            raise ValueError("currents must be non-zero grid currents")
    return result.psi[:, idx, result.circuits.index(result.excited)] / cur[idx]
