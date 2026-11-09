"""Cooling correlations and fluid properties. Every constant is cited to docs/r5-sources.md."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

G = 9.80665  # m/s2, standard gravity (not a sourced property)


@dataclass(frozen=True)
class Fluid:
    density: float  # kg/m3
    specific_heat: float  # J/(kg K)
    conductivity: float  # W/(m K)
    viscosity: float  # dynamic, Pa s
    name: str

    @property
    def prandtl(self) -> float:
        return self.viscosity * self.specific_heat / self.conductivity


# 50 % water / ethylene glycol, MEGlobal guide, docs/r5-sources.md 6.7 (grade B).
# Each property is tabulated at its own temperatures; density and viscosity at 37.8,
# 65.6 and 93.3 degC, specific heat and conductivity at 40, 65 and 100 degC.
_WG50 = {
    "density": ((37.8, 65.6, 93.3), (1054.0, 1036.0, 1016.0)),
    "viscosity": ((37.8, 65.6, 93.3), (2.20e-3, 1.18e-3, 0.739e-3)),
    "specific_heat": ((40.0, 65.0, 100.0), (3534.0, 3611.0, 3718.0)),
    "conductivity": ((40.0, 65.0, 100.0), (0.417, 0.414, 0.406)),
}


def fluid(name: str, temperature_c: float) -> Fluid:
    """Coolant properties, linearly interpolated in the cited table (docs/r5-sources.md 6.7).

    Only "water_glycol_50" has all four properties; ATF and oil lack specific heat and
    conductivity (6.7), so any other name is refused. The range is where every property
    is tabulated: 40 to 93.3 degC.
    """
    if name != "water_glycol_50":
        raise ValueError(f"no cited properties for coolant {name!r} (docs/r5-sources.md 6.7)")
    lo = max(t[0] for t, _ in _WG50.values())
    hi = min(t[-1] for t, _ in _WG50.values())
    if not lo <= temperature_c <= hi:
        raise ValueError(f"{name} is tabulated from {lo} to {hi} degC only, got {temperature_c}")
    v = {k: float(np.interp(temperature_c, t, y)) for k, (t, y) in _WG50.items()}
    return Fluid(v["density"], v["specific_heat"], v["conductivity"], v["viscosity"], name)


def duct_h(fluid: Fluid, hydraulic_diameter: float, velocity: float, length: float) -> float:
    """Turbulent duct h, W/(m2 K): Gnielinski with the Filonenko friction factor.

    docs/r5-sources.md 6.1 (Jacimovic 2026 Eqs. 7 and 8), including [1 + (d/L)^(2/3)];
    phi_t is left out (it needs the wall temperature, ratio 1 to 10 in the source), which
    the 10 % scatter has to cover. Valid Re 1e4 to 1e6 (Eq. 7 starts at 1e4, the
    formula's author gives 1e6), Pr 0.5 to 500, L >= d. Laminar and transition are
    refused: the laminar Nu is not from a read source (6.1).
    """
    re = fluid.density * velocity * hydraulic_diameter / fluid.viscosity
    pr = fluid.prandtl
    if re < 1e4:
        raise ValueError(f"Re {re:.0f} below 1e4: laminar/transition has no read source (docs/r5-sources.md 6.1)")
    if re > 1e6:
        raise ValueError(f"Re {re:.3g} above the cited 1e6 limit (docs/r5-sources.md 6.1)")
    if not 0.5 <= pr <= 500:
        raise ValueError(f"Pr {pr:.3g} outside the cited 0.5 to 500")
    if length < hydraulic_diameter:
        raise ValueError("duct shorter than its hydraulic diameter (cited L >= d)")
    f = (0.79 * math.log(re) - 1.64) ** -2
    nu = (f / 8 * (re - 1000) * pr / (1 + 12.7 * math.sqrt(f / 8) * (pr ** (2 / 3) - 1))
          * (1 + (hydraulic_diameter / length) ** (2 / 3)))
    return nu * fluid.conductivity / hydraulic_diameter


# Air, Faiz 2009 Table III (docs/r5-sources.md 6.3), 20 to 60 degC.
_AIR_T = (20.0, 40.0, 60.0)
_AIR = {
    "k": (0.0257, 0.0271, 0.0285),  # W/(m K)
    "nu": (15.11e-6, 16.97e-6, 18.90e-6),  # m2/s
    "alpha": (23e-6, 25.87e-6, 28.81e-6),  # m2/s
    "pr": (0.713, 0.711, 0.709),
    "beta": (3.43e-3, 3.2e-3, 3.0e-3),  # 1/K
}


def air_properties(temperature_c: float) -> dict[str, float]:
    """Air k, nu, alpha, Pr, beta by linear interpolation of Faiz Table III; refused outside 20 to 60 degC."""
    if not _AIR_T[0] <= temperature_c <= _AIR_T[-1]:
        raise ValueError(f"air properties are cited for 20 to 60 degC only, got {temperature_c}")
    return {k: float(np.interp(temperature_c, _AIR_T, v)) for k, v in _AIR.items()}


def airgap_h(arc_length: float, velocity: float, air_temperature_c: float) -> float:
    """Air-gap h, W/(m2 K), Faiz 2009 Eq. (6) (docs/r5-sources.md 6.2, grade C).

    Nu = 0.664 Re^(1/2) Pr^(1/3), Re = L v / nu, L the stator pole and wedge arc length,
    v the rotor tooth speed. Romanazzi and Howey is not coded (Ta_m is not defined in the
    source). No range is printed; air properties are limited to 20 to 60 degC.
    """
    p = air_properties(air_temperature_c)
    re = arc_length * velocity / p["nu"]
    return 0.664 * math.sqrt(re) * p["pr"] ** (1 / 3) * p["k"] / arc_length


def natural_h(shape: str, size: float, surface_c: float, ambient_c: float) -> float:
    """Natural-convection h, W/(m2 K), Faiz 2009 Eqs. (1) to (4) (docs/r5-sources.md 6.3, grade C).

    shape "cylinder": horizontal cylinder of outer diameter `size` (Churchill and Chu form,
    0.6 + 0.387 Ra^(1/6) / [1 + (0.559/Pr)^(9/16)]^(8/27), squared). shape "plate": vertical
    plate of height `size` (0.825 in place of 0.6, 0.492 in place of 0.559); an end face of
    diameter D is a square of side 0.886 D (Eq. 5). Properties at the film temperature;
    refused outside the 20 to 60 degC table. No Ra range is printed.
    """
    p = air_properties(0.5 * (surface_c + ambient_c))
    ra = G * p["beta"] * abs(surface_c - ambient_c) * size ** 3 / (p["nu"] * p["alpha"])
    if shape == "cylinder":
        a, b = 0.6, 0.559
    elif shape == "plate":
        a, b = 0.825, 0.492
    else:
        raise ValueError(f"unknown shape {shape!r}")
    nu = (a + 0.387 * ra ** (1 / 6) / (1 + (b / p["pr"]) ** (9 / 16)) ** (8 / 27)) ** 2
    return nu * p["k"] / size
