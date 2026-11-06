"""Analytic rotor stress at 1.2 x max speed: the bore hoop stress of the yoke annulus and the stress at the
pole root (spec R5 section 9)."""
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from ..materials.schema import MechanicalData
from ..model.design import RadialSRMParams

SAFETY_FACTOR = 1.5
OVERSPEED = 1.2
STRENGTH_GRADE_ALLOWANCE = {"A": 0.0, "B": 0.03, "C": 0.10}   # provisional, as for the B-H grades

# Coefficients C1..C4 of Kt = sum C_i (2h/D)^(i-1), each as (constant, sqrt(h/r), h/r) terms;
# docs/r5-sources.md section 4 (Pilkey 2005 via AmesWeb, grade C).
_KT_LOW = ((1.006, 1.008, -0.044), (-0.115, -0.584, 0.315), (0.245, -1.006, -0.257), (-0.135, 0.582, -0.017))
_KT_HIGH = ((1.020, 1.009, -0.048), (-0.065, -0.165, -0.007), (-3.459, 1.266, -0.016), (3.505, -2.109, 0.069))
_KT_RANGE = (0.1, 20.0)
_GAUSS = np.polynomial.legendre.leggauss(32)


def _kt(x: float, two_h_over_d: float) -> float:
    s = math.sqrt(x)
    c = [a + b * s + g * x for a, b, g in (_KT_LOW if x <= 2.0 else _KT_HIGH)]
    return sum(ci * two_h_over_d**i for i, ci in enumerate(c))


def _flank_y(machine: RadialSRMParams, r: float) -> np.ndarray | float:
    """y of the pole flank where it crosses the circle of radius r (the pole sits on the +x axis)."""
    big = machine.rotor_outer_radius
    half = machine.rotor_pole_arc / 2
    fx, fy = big * math.cos(half), big * math.sin(half)
    dx, dy = -math.cos(machine.rotor_pole_taper), math.sin(machine.rotor_pole_taper)
    fd = fx * dx + fy * dy
    t = -fd - np.sqrt(fd**2 - big**2 + np.asarray(r)**2)
    return fy + t * dy


def pole_half_width(machine: RadialSRMParams, r: float) -> float:
    """Half width of the rotor pole where its flank crosses radius r, m."""
    return float(_flank_y(machine, r))


def pole_force_per_depth(machine: RadialSRMParams, density: float, omega: float) -> float:
    """Axial centrifugal resultant of one rotor pole outside the yoke radius, N/m of stack length:
    rho omega^2 times the integral of x dA, which in polar form is the integral of 2 r y(r) dr."""
    lo, hi = machine.rotor_yoke_outer_radius, machine.rotor_outer_radius
    r = (hi - lo) / 2 * _GAUSS[0] + (hi + lo) / 2
    return float(density * omega**2 * (hi - lo) / 2 * np.sum(_GAUSS[1] * 2 * r * _flank_y(machine, r)))


def _root_geometry(machine: RadialSRMParams) -> tuple[float, float]:
    """h/r and 2h/D of the pole root: d = pole width at the root, D = pole pitch at the root."""
    b = machine.rotor_yoke_outer_radius
    d = 2 * pole_half_width(machine, b)
    big_d = 2 * math.pi * b / machine.n_rotor_poles
    h = (big_d - d) / 2
    return h / machine.rotor_fillet_radius, 2 * h / big_d


def root_stress_concentration(machine: RadialSRMParams) -> float | None:
    """Kt of the root fillet; None without a fillet or when h/r is outside the printed range of the formula."""
    if machine.rotor_fillet_radius <= 0:
        return None
    x, t = _root_geometry(machine)
    return _kt(x, t) if _KT_RANGE[0] <= x <= _KT_RANGE[1] else None


@dataclass(frozen=True)
class RotorStress:
    status: Literal["ok", "no_strength_data", "no_fillet", "kt_out_of_range", "imported_iron"]
    note: str
    check_speed_rpm: float
    bore_stress: float | None         # Pa
    root_stress: float | None         # Pa, nominal x Kt; nominal when Kt is not available
    stress_concentration: float | None
    governing: Literal["bore", "pole_root"] | None
    criterion: Literal["von_mises", "max_principal"] | None
    usable_strength: float | None     # Pa, after the grade allowance
    safety_factor: float | None
    speed_limit_rpm: float | None     # highest max speed that keeps SAFETY_FACTOR


def rotor_stress(machine: RadialSRMParams, density: float, mechanical: MechanicalData | None,
                 max_speed_rpm: float, rotor_temperature_c: float | None = None) -> RotorStress:
    """Stress of the rotor at OVERSPEED x max_speed_rpm. `density` is the solid density: each lamination
    carries its own mass, so the stacking factor plays no part. Both stress points are uniaxial on a free
    surface, so von Mises and maximum principal stress are equal there and only the strength differs."""
    if max_speed_rpm <= 0:
        raise ValueError("max_speed_rpm must be positive")
    check_rpm = OVERSPEED * max_speed_rpm
    empty = dict(check_speed_rpm=check_rpm, bore_stress=None, root_stress=None, stress_concentration=None,
                 governing=None, criterion=None, usable_strength=None, safety_factor=None, speed_limit_rpm=None)
    if machine.iron is not None:
        return RotorStress("imported_iron", "analytic stress not available for imported rotor iron, FE stress is R10",
                           **empty)
    if mechanical is None:
        return RotorStress("no_strength_data", "the rotor material has no mechanical data", **empty)

    omega = check_rpm * 2 * math.pi / 60
    a, b, nu = machine.shaft_radius, machine.rotor_yoke_outer_radius, mechanical.poisson_ratio
    force = pole_force_per_depth(machine, density, omega)
    rim = machine.n_rotor_poles * force / (2 * math.pi * b)
    bore = density * omega**2 / 4 * ((3 + nu) * b**2 + (1 - nu) * a**2) + 2 * b**2 / (b**2 - a**2) * rim
    nominal = force / (2 * pole_half_width(machine, b))
    kt = root_stress_concentration(machine)
    root = nominal if kt is None else kt * nominal
    fields = dict(check_speed_rpm=check_rpm, bore_stress=bore, root_stress=root, stress_concentration=kt,
                  governing=None, criterion=None, usable_strength=None, safety_factor=None, speed_limit_rpm=None)

    notes = []
    if rotor_temperature_c is not None and (mechanical.temperature_c is None or rotor_temperature_c > mechanical.temperature_c):
        notes.append(f"strength is not known at the rotor temperature of {rotor_temperature_c:.0f} degC")
    if machine.rotor_fillet_radius <= 0:
        return RotorStress("no_fillet", "; ".join(["no root fillet, so no stress concentration factor"] + notes), **fields)
    if kt is None:
        x, _ = _root_geometry(machine)
        return RotorStress("kt_out_of_range", "; ".join(
            [f"h/r = {x:.3g} is outside the printed range {_KT_RANGE[0]} to {_KT_RANGE[1]} of the factor"] + notes), **fields)

    usable = mechanical.strength * (1 - STRENGTH_GRADE_ALLOWANCE[mechanical.strength_confidence])
    safety = usable / max(bore, root)
    fields.update(governing="bore" if bore >= root else "pole_root",
                  criterion="max_principal" if mechanical.brittle else "von_mises",
                  usable_strength=usable, safety_factor=safety,
                  speed_limit_rpm=max_speed_rpm * math.sqrt(safety / SAFETY_FACTOR))
    return RotorStress("ok", "; ".join(notes), **fields)
