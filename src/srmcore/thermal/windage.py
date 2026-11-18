"""Air-gap windage of a smooth rotor cylinder from measured drag coefficients.

Source: S. H. Gorland, E. E. Kempke Jr. and S. Lumannick, "Experimental windage losses for close clearance rotating
cylinders in the turbulent flow regime", NASA TM X-52851, 1970 (docs/r3-sources.md section 6). A 12 inch cylinder, 5.9
inch long, ran in a stationary concentric housing at gaps of 0.0565, 0.116 and 0.236 inch, torque measured by a
reaction device so that no end-disc torque is in the data. The report defines (its Eq. 4 to 6)

    W = lambda * pi * rho * omega^3 * R^4 * L,    Re = omega R g / nu,

with R the rotor radius, L its length, g the radial gap and nu the kinematic viscosity. `TABLE_I` and `TABLE_II`
are the drag coefficient lambda against Re of the report's Tables I (gap 0.0565 inch) and II (gap 0.116 inch), as
printed. Nothing is fitted: lambda is interpolated between the printed rows of Table I, and the difference between
the two gaps (with the report's 5 % torque accuracy) is the band.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .correlations import air_properties

R_AIR = 287.05           # J/(kg K), dry air (ideal-gas density)
P_AMBIENT = 101_325.0    # Pa; the tests ran at 29.05 to 29.37 in Hg

# (Re, lambda x 1e-3), Table I, gap 0.0565 inch, gap/radius 0.0094.
TABLE_I = (
    (351, 9.209), (703, 5.732), (1070, 4.950), (1419, 4.500), (1775, 3.952), (2120, 3.779), (2494, 3.277),
    (2843, 3.222), (3193, 3.111), (3583, 2.956), (3943, 2.877), (4313, 2.770), (4661, 2.724), (5012, 2.669),
    (5365, 2.603), (5712, 2.556), (6113, 2.522), (6469, 2.494), (6938, 2.447), (7374, 2.445), (7788, 2.412),
    (8224, 2.393), (8623, 2.383), (9203, 2.394), (9742, 2.375), (10271, 2.373), (10810, 2.361), (11247, 2.337),
    (12096, 2.331), (12546, 2.337), (13100, 2.321), (13668, 2.315), (14268, 2.292), (14868, 2.285), (15437, 2.278),
    (16131, 2.261), (16768, 2.248), (17370, 2.243), (17886, 2.247), (18328, 2.245), (18989, 2.207), (19613, 2.147),
    (20149, 2.133), (20672, 2.094), (21006, 2.084), (21208, 2.052),
)
# (Re, lambda x 1e-3), Table II, gap 0.116 inch, gap/radius 0.0193.
TABLE_II = (
    (802, 7.377), (1531, 5.069), (2257, 4.189), (2972, 3.764), (3700, 3.469), (4398, 3.068), (5138, 2.968),
    (5870, 2.735), (6598, 2.727), (7281, 2.642), (8039, 2.499), (8782, 2.433), (9940, 2.355), (11345, 2.259),
    (12581, 2.225), (13596, 2.190), (14307, 2.173), (15516, 2.101), (16629, 2.092), (17862, 2.047), (18998, 2.043),
    (20097, 2.014), (21213, 1.989), (22221, 1.976),
)
RE_RANGE = (TABLE_I[0][0], TABLE_I[-1][0])
GAP_RATIO_TESTED = (0.0094, 0.0393)   # 0.0565, 0.116, 0.236 inch over R = 6.0 inch (the report: 0.01 to 0.04)
TORQUE_ACCURACY = 0.05                # "approximately 5 percent accurate" above 5000 rpm
SLOPE_LOW_RE = -0.5                   # log-log slope below the tables, "approximately -0.5" (vortex regime)
SLOPE_HIGH_RE = -0.22                 # "approximately -0.22 to -0.25" turbulent; the shallower end gives more loss

SALIENT_NOTE = ("windage is the smooth-cylinder value at the rotor outer radius: salient rotor poles add windage and "
                "no cited factor for them was found, so the loss and its band are a lower bound")
END_NOTE = "rotor end-face (disc) windage is not included: the measurements exclude it"


def _log_interp(table, re: float) -> float:
    x = np.log([r for r, _ in table])
    y = np.log([v for _, v in table])
    return float(np.exp(np.interp(math.log(re), x, y)))


def drag_coefficient(re: float) -> float:
    """lambda of Table I at `re`, log-log interpolated between its rows; beyond the table it follows the report's
    slopes (-0.5 below, -0.22 above) from the end row."""
    lo, hi = TABLE_I[0], TABLE_I[-1]
    if re < lo[0]:
        return lo[1] * 1e-3 * (re / lo[0]) ** SLOPE_LOW_RE
    if re > hi[0]:
        return hi[1] * 1e-3 * (re / hi[0]) ** SLOPE_HIGH_RE
    return _log_interp(TABLE_I, re) * 1e-3


def _gap_spread() -> float:
    """Largest relative difference between the two gaps' drag coefficients at the Re rows of Table II that lie inside
    the Re range of Table I."""
    return max(abs(v / _log_interp(TABLE_I, re) - 1.0) for re, v in TABLE_II if RE_RANGE[0] <= re <= RE_RANGE[1])


GAP_SPREAD = _gap_spread()
BAND_REL = GAP_SPREAD + TORQUE_ACCURACY   # symmetric band on the windage power


def air_density(temperature_c: float, pressure_pa: float = P_AMBIENT) -> float:
    return pressure_pa / (R_AIR * (temperature_c + 273.15))


@dataclass(frozen=True)
class Windage:
    power_w: float
    drag_coefficient: float
    reynolds: float
    gap_ratio: float
    rel_low: float          # band on power_w: [power_w (1 - rel_low), power_w (1 + rel_high)]
    rel_high: float
    in_range: bool          # Re inside the tables and gap/radius inside the tested range
    notes: tuple[str, ...]


def windage_loss(rotor_radius: float, gap: float, length: float, rpm: float, air_c: float = 60.0) -> Windage:
    """Windage power (W) of a smooth rotor cylinder of `rotor_radius`, active `length` and radial `gap` (m) at `rpm`,
    air at `air_c` degC (cited properties: 20 to 60 degC) and ambient pressure."""
    if not (rotor_radius > 0 and gap > 0 and length > 0):
        raise ValueError("rotor radius, gap and length must be positive")
    omega = rpm * 2 * math.pi / 60
    nu = air_properties(air_c)["nu"]
    rho = air_density(air_c)
    re = omega * rotor_radius * gap / nu
    ratio = gap / rotor_radius
    notes = [SALIENT_NOTE, END_NOTE, f"air at {air_c:g} degC and ambient pressure (the top of the cited property table)"]
    if rpm <= 0:
        return Windage(0.0, float("nan"), 0.0, ratio, BAND_REL, BAND_REL, True, tuple(notes))
    in_re = RE_RANGE[0] <= re <= RE_RANGE[1]
    in_gap = GAP_RATIO_TESTED[0] <= ratio <= GAP_RATIO_TESTED[1]
    if not in_re:
        notes.append(f"Re {re:.0f} is outside the measured range {RE_RANGE[0]} to {RE_RANGE[1]}: the report's slope is used")
    if not in_gap:
        notes.append(f"gap/radius {ratio:.4f} is outside the tested range {GAP_RATIO_TESTED[0]} to {GAP_RATIO_TESTED[1]}")
    lam = drag_coefficient(re)
    power = lam * math.pi * rho * omega ** 3 * rotor_radius ** 4 * length
    return Windage(power, lam, re, ratio, BAND_REL, BAND_REL, in_re and in_gap, tuple(notes))
