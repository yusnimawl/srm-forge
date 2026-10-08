"""Curves read off a map at the chosen winding: secant inductance L(θ), the saturated aligned and unaligned
inductance against current, the saliency ratio k2 and the stator-pole flux density B_sp (the product B_sp·k2
is the figure of merit used to compare designs on one plot)."""
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy.interpolate import CubicSpline

from srmcore.maps.results import KeyNumbers
from srmcore.model.design import RadialSRMParams

from .sizing.winding import Winding

if TYPE_CHECKING:
    from .evaluate import MapArrays


@dataclass(frozen=True)
class MapCurves:
    currents: np.ndarray      # A, the map currents above zero
    inductance: np.ndarray    # (n_angles, n_currents) secant ψ/i, H
    la_sat: np.ndarray        # H per current, aligned
    lu: np.ndarray            # H per current, unaligned
    la_unsat: float           # H, `KeyNumbers.la`
    k2: np.ndarray            # 1 - lu / la_sat
    b_sp: np.ndarray          # T, mean flux density in the stator pole at the air-gap face
    b_sp_k2: np.ndarray       # T
    la_lu: np.ndarray         # la_sat / lu


def map_curves(arrays: "MapArrays", machine: RadialSRMParams, winding: Winding, key: KeyNumbers) -> MapCurves:
    """Aligned and unaligned values come from a periodic cubic spline in angle over one rotor pole pitch."""
    pitch = 2 * math.pi / machine.n_rotor_poles
    currents = arrays.currents[1:]
    inductance = arrays.psi[:, 1:] / currents
    # The grid stops short of one pitch; ψ repeats after it.
    angles = np.append(arrays.angles, arrays.angles[0] + pitch)
    spline = CubicSpline(angles, np.vstack([inductance, inductance[:1]]), bc_type="periodic")
    la_sat, lu = spline(key.aligned_angle), spline(key.unaligned_angle)
    n_series = winding.turns * (machine.n_stator_poles // machine.n_phases) / winding.paths
    a_face = (machine.rotor_outer_diameter / 2 + machine.air_gap) * machine.stator_pole_arc * machine.stack_length
    b_sp = la_sat * currents / (n_series * a_face)
    k2 = 1 - lu / la_sat
    return MapCurves(currents, inductance, la_sat, lu, key.la, k2, b_sp, b_sp * k2, la_sat / lu)
