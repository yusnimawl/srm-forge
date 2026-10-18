"""AC copper loss of a winding: skin effect from the phase current harmonics and proximity eddy loss from the
slot field harmonics (round-conductor formulas, each strand taken as a round wire of its equivalent diameter)."""
import math

import numpy as np
from scipy.special import jve

from srmcore.materials.library import load_material
from srmcore.model.design import RadialSRMParams

from .sizing.winding import Winding
from .wire import LitzWire, RectangularWire, RoundWire, Wire

MU0 = 4e-7 * math.pi


def strand_diameter(wire: Wire) -> float:
    """m, diameter of the round conductor that one strand of `wire` is treated as."""
    if isinstance(wire, LitzWire):
        return wire.strand_diameter
    if isinstance(wire, RectangularWire):
        # ponytail: equal-area round strand; the true eddy loss depends on orientation (w³h or wh³ against the
        # slot field), so this is only a mid estimate. Upgrade: per-orientation rectangular-conductor formula.
        return math.sqrt(4 * wire.copper_area / math.pi)
    return wire.diameter


def _strands_per_bundle(wire: Wire) -> int:
    return wire.strands if isinstance(wire, LitzWire) else 1


def skin_factor(d: float, omega: float, rho: float) -> float:
    """R_ac / R_dc of a round conductor of diameter `d` at angular frequency `omega` (exact Bessel form)."""
    ka = (1 - 1j) * (d / 2) * math.sqrt(omega * MU0 / (2 * rho))
    return float(np.real(ka / 2 * jve(0, ka) / jve(1, ka)))


def _harmonics(x: np.ndarray) -> np.ndarray:
    """Peak amplitudes of harmonics 0.. of one period of samples `x` (axis 0)."""
    amp = 2 * np.abs(np.fft.rfft(x, axis=0)) / len(x)
    if len(x) % 2 == 0:
        amp[-1] /= 2                                              # the Nyquist bin has no mirror image
    return amp


def ac_copper_loss(winding: Winding, wire: Wire | None, current: np.ndarray, period_s: float, b_coil: np.ndarray,
                   coil_side: np.ndarray, coil_areas: np.ndarray, machine: RadialSRMParams,
                   temperature_c: float) -> float | None:
    """W, skin plus proximity loss of all phases above the DC loss; None in density mode (`wire` None).
    `current` is one phase over one electrical period, `b_coil` (n_t, n_coil, 2) the coil-region field over the
    same period at the winding's own scale, `coil_areas` the area of each coil element (`coil_side` names them and
    is not needed: harmonics are taken per element and per component, so reversing and rotating fields count
    correctly). `temperature_c` is the single temperature of the AC terms and must equal the requirement's
    `winding_temperature_c`, the one `winding.resistance` was built at. Proximity counts the active length only (twice the stack length); end turns see no slot field."""
    if wire is None:
        return None
    rho = load_material(machine.materials.coil).resistivity_at(temperature_c)
    d = strand_diameter(wire)
    omega = 2 * math.pi / period_s
    i_h = _harmonics(current) / math.sqrt(2)                     # rms per harmonic
    skin = sum((skin_factor(d, h * omega, rho) - 1) * winding.resistance * i**2
               for h, i in enumerate(i_h) if h > 0)
    w = coil_areas / coil_areas.sum()
    b2 = np.sum(_harmonics(b_coil) ** 2, axis=2) @ w              # area-weighted mean of |B_x,h|² + |B_y,h|²
    n_strands = winding.turns * winding.strands * _strands_per_bundle(wire) * machine.n_stator_poles
    length = 2 * machine.stack_length
    prox = sum(n_strands * math.pi * length * d**4 * (h * omega) ** 2 * b2[h] / (128 * rho)
               for h in range(1, len(b2)))
    return float(machine.n_phases * skin + prox)
