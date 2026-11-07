"""Analytic rotor stress at 1.2 x max speed: the peak at the bore and at the pole root fillet (spec R5 section 9).
The yoke is a rotating annulus, loaded at the rim by the poles, that bends as a ring between the poles; the root
model and its constants are in docs/r5-sources.md section 5."""
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
# Corner exponent of the fillet factors: 1 - lambda of a free 270 degree corner, and its change per radian of taper.
_CORNER_EXPONENT, _CORNER_EXPONENT_SLOPE = 0.4555, 0.1
_RING_BEND_SHARE = 0.5
# Derived from the converged FE sweep, grade C (docs/r5-sources.md section 5): tools/rotor_stress_sweep.py fit.
_STEM_GAIN, _STEM_YOKE_SHARE, _STEM_PITCH_POWER, _SHOULDER_HEIGHT = 0.659, 0.473, 0.274, 0.196
_BORE_RIM_RELIEF, _BORE_BEND_GAIN = 0.059, 1.90
# Validity of those constants, the box of the sweep.
_FIT_POLES = (4, 16)
_FIT_SHAFT = (0.25, 0.45)       # shaft diameter / rotor diameter
_FIT_ARC = (1.0, 1.7)           # pole arc / Lawrenson limit 2 pi / (m Nr)
_FIT_YOKE = (0.5, 1.15)         # yoke thickness / pole tip chord
_FIT_TAPER = (-5.0, 10.0)       # degrees
_FIT_FILLET = (0.01, 0.3)       # fillet radius / pole width at the root
_FIT_MIN_SPAN = 0.1             # free ring half span / half pitch
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


def _rim_load(machine: RadialSRMParams, density: float, omega: float) -> float:
    """Radial tension at the yoke rim from the centrifugal pull of all rotor poles, Pa."""
    force = pole_force_per_depth(machine, density, omega)
    return machine.n_rotor_poles * force / (2 * math.pi * machine.rotor_yoke_outer_radius)


def _rim_hoop(a: float, b: float, density: float, omega: float, nu: float, rim_load: float) -> float:
    """Hoop stress at the rim b of a spinning annulus with a free bore a and a tensile load on the rim, Pa."""
    return density * omega**2 / 4 * ((1 - nu) * b**2 + (3 + nu) * a**2) + rim_load * (b**2 + a**2) / (b**2 - a**2)


def _ring_half_span(machine: RadialSRMParams) -> float:
    """Half angle of the free yoke arc between two poles, rad: half a pitch less the pole and half a fillet."""
    b = machine.rotor_yoke_outer_radius
    return (math.pi / machine.n_rotor_poles - math.asin(pole_half_width(machine, b) / b)
            - machine.rotor_fillet_radius / (2 * b))


def _ring_bending(machine: RadialSRMParams, force: float) -> tuple[float, float]:
    """Fibre stresses of the yoke as a ring of free arcs between poles too stiff to rotate, each pole pulling `force`:
    the inner fibre at mid span and the outer fibre at the arc end, both tensile, Pa. Mid-span axial force
    F / (2 sin(pi/N)), zero end rotation, Winkler-Bach stress of a rectangular section."""
    a, b = machine.shaft_radius, machine.rotor_yoke_outer_radius
    gamma = _ring_half_span(machine)
    axial_moment = force / (2 * math.sin(math.pi / machine.n_rotor_poles)) * (a + b) / 2
    t = b - a
    neutral = t / math.log(b / a)
    offset = (a + b) / 2 - neutral
    mid = axial_moment * (1 - math.sin(gamma) / gamma) * (neutral - a) / (t * offset * a)
    end = axial_moment * (math.sin(gamma) / gamma - math.cos(gamma)) * (b - neutral) / (t * offset * b)
    return mid, end


def _root_factors(machine: RadialSRMParams) -> tuple[float, float]:
    """The fillet factors of the pole tension and of the ring stress at the root."""
    a, b, r = machine.shaft_radius, machine.rotor_yoke_outer_radius, machine.rotor_fillet_radius
    d = 2 * pole_half_width(machine, b)
    taper = machine.rotor_pole_taper
    exponent = _CORNER_EXPONENT - _CORNER_EXPONENT_SLOPE * taper
    length = 1 / math.hypot(1 / d, 1 / (_STEM_YOKE_SHARE * (b - a)))
    pitch = 2 * math.pi * b / machine.n_rotor_poles
    stem = _STEM_GAIN * (pitch / d)**_STEM_PITCH_POWER * ((length / r)**exponent - 1)
    height = _SHOULDER_HEIGHT * d * math.tanh((machine.rotor_outer_radius - b) / (_SHOULDER_HEIGHT * d))
    x = height / r
    return stem, _kt(x, 0.0) * x**(-_CORNER_EXPONENT_SLOPE * taper)


def _root_peak(machine: RadialSRMParams, density: float, omega: float, nu: float) -> float:
    """Peak stress on the root fillet, Pa: the concentrated pole tension plus the concentrated ring stress."""
    a, b = machine.shaft_radius, machine.rotor_yoke_outer_radius
    force = pole_force_per_depth(machine, density, omega)
    stem, shoulder = _root_factors(machine)
    ring = (_rim_hoop(a, b, density, omega, nu, _rim_load(machine, density, omega))
            + _RING_BEND_SHARE * _ring_bending(machine, force)[1])
    return stem * force / (2 * pole_half_width(machine, b)) + shoulder * ring


def _outside_fit(machine: RadialSRMParams) -> str | None:
    """The first ratio outside the swept box, as a note; None inside."""
    a, b = machine.shaft_radius, machine.rotor_yoke_outer_radius
    big, n = machine.rotor_outer_radius, machine.n_rotor_poles
    limit = 2 * math.pi / (machine.n_phases * n)
    for name, value, (lo, hi) in (
            ("rotor poles", n, _FIT_POLES),
            ("shaft ratio", a / big, _FIT_SHAFT),
            ("pole arc ratio", machine.rotor_pole_arc / limit, _FIT_ARC),
            ("yoke ratio", (b - a) / (2 * big * math.sin(machine.rotor_pole_arc / 2)), _FIT_YOKE),
            ("taper in degrees", math.degrees(machine.rotor_pole_taper), _FIT_TAPER),
            ("fillet ratio", machine.rotor_fillet_radius / (2 * pole_half_width(machine, b)), _FIT_FILLET),
            ("free ring span ratio", _ring_half_span(machine) * n / math.pi, (_FIT_MIN_SPAN, 1.0))):
        if not lo - 1e-9 <= value <= hi + 1e-9:
            return f"{name} {value:.3g} is outside the validity range {lo} to {hi} of the root stress model"
    return None


def root_stress_concentration(machine: RadialSRMParams, poisson_ratio: float) -> float | None:
    """Root peak stress over the nominal pole stress, ring stress included; None without a fillet or outside the
    validity range of the model. Speed and density cancel."""
    if machine.rotor_fillet_radius <= 0 or _outside_fit(machine) is not None:
        return None
    nominal = pole_force_per_depth(machine, 1.0, 1.0) / (2 * pole_half_width(machine, machine.rotor_yoke_outer_radius))
    return _root_peak(machine, 1.0, 1.0, poisson_ratio) / nominal


@dataclass(frozen=True)
class RotorStress:
    status: Literal["ok", "no_strength_data", "no_fillet", "kt_out_of_range", "imported_iron"]
    note: str
    check_speed_rpm: float
    bore_stress: float | None         # Pa
    root_stress: float | None         # Pa, peak on the fillet; the nominal pole stress when the factor is not available
    stress_concentration: float | None   # root_stress over the nominal pole stress, ring stress included
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
    rim = _rim_load(machine, density, omega)
    relief = 1 - _BORE_RIM_RELIEF * machine.n_rotor_poles * pole_half_width(machine, b) / (math.pi * b)
    bore = (density * omega**2 / 4 * ((3 + nu) * b**2 + (1 - nu) * a**2) + 2 * b**2 / (b**2 - a**2) * rim * relief
            + _BORE_BEND_GAIN * _ring_bending(machine, force)[0])
    nominal = force / (2 * pole_half_width(machine, b))
    kt = root_stress_concentration(machine, nu)
    root = nominal if kt is None else kt * nominal
    fields = dict(check_speed_rpm=check_rpm, bore_stress=bore, root_stress=root, stress_concentration=kt,
                  governing=None, criterion=None, usable_strength=None, safety_factor=None, speed_limit_rpm=None)

    notes = []
    if rotor_temperature_c is not None and (mechanical.temperature_c is None or rotor_temperature_c > mechanical.temperature_c):
        notes.append(f"strength is not known at the rotor temperature of {rotor_temperature_c:.0f} degC")
    if machine.rotor_fillet_radius <= 0:
        return RotorStress("no_fillet", "; ".join(["no root fillet, so no stress concentration factor"] + notes), **fields)
    if kt is None:
        return RotorStress("kt_out_of_range", "; ".join([_outside_fit(machine)] + notes), **fields)

    usable = mechanical.strength * (1 - STRENGTH_GRADE_ALLOWANCE[mechanical.strength_confidence])
    safety = usable / max(bore, root)
    fields.update(governing="bore" if bore >= root else "pole_root",
                  criterion="max_principal" if mechanical.brittle else "von_mises",
                  usable_strength=usable, safety_factor=safety,
                  speed_limit_rpm=max_speed_rpm * math.sqrt(safety / SAFETY_FACTOR))
    return RotorStress("ok", "; ".join(notes), **fields)


def _disc_rim_displacement(a: float, b: float, density: float, omega: float, nu: float, youngs_modulus: float,
                           rim_load: float) -> float:
    """Radial displacement at the rim of a spinning annulus with a free bore a and a tensile load on the rim b,
    plane stress: u = (b/E)(sigma_theta(b) - nu p) with the rotating-annulus hoop stress at b plus the Lame term."""
    return b / youngs_modulus * (_rim_hoop(a, b, density, omega, nu, rim_load) - nu * rim_load)


@dataclass(frozen=True)
class GapClosure:
    centrifugal: float               # m, disc plus pole elongation at the pole tip
    rotor_thermal: float | None      # m, None without expansion data
    stator_thermal: float | None     # m
    closure: float | None            # m, rotor growth minus bore growth; None without expansion data
    note: str


def gap_closure(machine: RadialSRMParams, density: float, mechanical: MechanicalData,
                rotor_expansion: float | None, stator_expansion: float | None, rpm: float,
                rotor_temperature_c: float, stator_temperature_c: float, reference_c: float = 20.0) -> GapClosure:
    """Growth of the rotor tip radius minus the growth of the stator bore, m (positive closes the gap), at the
    actual speed `rpm`: the caller applies any overspeed. Pole width comes from the flank, so the elongation
    is the integral of sigma(r)/E with sigma(r) = rho omega^2 / w(r) times the integral of r' w(r') from r to the tip."""
    if rpm <= 0:
        raise ValueError("rpm must be positive")
    omega = rpm * 2 * math.pi / 60
    a, b, big = machine.shaft_radius, machine.rotor_yoke_outer_radius, machine.rotor_outer_radius
    nu, young = mechanical.poisson_ratio, mechanical.youngs_modulus
    disc = _disc_rim_displacement(a, b, density, omega, nu, young, _rim_load(machine, density, omega))

    def width_moment(r: float) -> float:
        s = (big - r) / 2 * _GAUSS[0] + (big + r) / 2
        return float((big - r) / 2 * np.sum(_GAUSS[1] * s * 2 * _flank_y(machine, s)))

    r = (big - b) / 2 * _GAUSS[0] + (big - b) / 2 + b
    sigma = np.array([density * omega**2 * width_moment(ri) / (2 * float(_flank_y(machine, ri))) for ri in r])
    centrifugal = disc + float((big - b) / 2 * np.sum(_GAUSS[1] * sigma)) / young

    rotor_thermal = None if rotor_expansion is None else rotor_expansion * (rotor_temperature_c - reference_c) * big
    stator_thermal = (None if stator_expansion is None
                      else stator_expansion * (stator_temperature_c - reference_c) * machine.bore_radius)
    missing = [n for n, v in (("rotor", rotor_expansion), ("stator", stator_expansion)) if v is None]
    closure = None if missing else centrifugal + rotor_thermal - stator_thermal
    note = f"no thermal expansion for the {' and '.join(missing)} material" if missing else ""
    return GapClosure(centrifugal, rotor_thermal, stator_thermal, closure, note)
