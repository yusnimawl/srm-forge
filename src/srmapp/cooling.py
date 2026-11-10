"""Cooling setup and the coefficients the thermal network takes from it.

Every number is from docs/r5-sources.md (sections named in the comments) and each budget
row (ROWS) has a nominal and an unfavourable end; `coefficients` picks the end per row.
An enabled option with no cited source raises MissingCoolingData.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from srmcore.materials.library import load_material
from srmcore.model.design import RadialSRMParams
from srmcore.thermal.correlations import (CRAGOE_CP_MAX, DIALA_DENSITY, Fluid, airgap_h, duct_h, fluid, natural_h,
                                          petroleum_oil_cp)
from srmcore.thermal.homogenise import MILTON_XI, hashin_shtrikman_lower, milton_k

ROWS = ("iron", "em_torque", "cross_wire", "liner", "contact", "air_gap", "cooling_h",
        "lamination_k", "thermal_mesh", "end_winding_model")

K_IRON_HI = 2.0                    # section 7 / spec §7: iron loss factor at the unfavourable end
TORQUE_FLOOR = 0.10                # spec §7: EM torque factor 1 + max(0.10, R4 total)
K_RESIN = (1.0, 0.6)               # 6.6 / 7: impregnation, nominal and unfavourable, W/(m K)
GAP_MM = (0.03, 0.08)              # 6.5 / 7: contact equivalent air gap, nominal and unfavourable, mm
K_LINER_LOW = 0.076                # 6.6 / 7: Faiz Table II, unfavourable liner, W/(m K)
# 6.6: Nomex 410, DuPont Table IV, thickness (mm) and conductivity (W/(m K)) at 150 degC.
NOMEX_MM = (0.05, 0.08, 0.13, 0.18, 0.25, 0.38, 0.51, 0.76)
NOMEX_K = (0.103, 0.114, 0.123, 0.143, 0.139, 0.149, 0.157, 0.175)
K_HOUSING = 177.0                  # 6.6: aluminium frame, Faiz Table II, W/(m K)
K_LAMINATION = (18.6, 18.6 * (1 - 0.25))   # 6.9: 18.6 and 18.6 x (1 - grade-C allowance 0.25)
JACKET_SCATTER = 0.9               # 7: jacket h at minus 10 % (Shah and Sekulic)
SLOT_OIL_SCATTER = 0.9             # 7: water-glycol slot channel, minus 10 %
SHAFT_SPRAY_SCATTER = 0.75         # 7: Hoffmann model, minus 25 %
SPRAY_H = {                        # 6.4: measured h range (low, high), W/(m2 K)
    "nozzle_hairpin": (190.0, 910.0),    # Shams Ghahfarokhi 2024, Fig. 5
    "shaft_spray": (3500.0, 4800.0),     # Hoffmann et al., Fig. 4 and 5, off the sump
}
AIR_FILM_C = 60.0                  # 6.3: top of the cited air table (Faiz Table III)
RE_MIN = 1e4                       # 6.1: Gnielinski in duct_h; below this no cited correlation


class MissingCoolingData(ValueError):
    """An enabled cooling option has no cited source (docs/r5-sources.md 6.4 and 6.7)."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Jacket(_Frozen):
    """Water jacket. Defaults are the owner placeholders of docs/r5-sources.md section 7."""
    channel_height: float = Field(default=4e-3, gt=0)    # m
    channel_width: float = Field(default=20e-3, gt=0)    # m
    passes: int = Field(default=4, ge=1)
    flow_m3s: float = Field(default=1.5e-4, gt=0)        # 9 L/min
    inlet_c: float = 65.0
    coolant: str = "water_glycol_50"


class EndSpray(_Frozen):
    """Oil spray on the end windings; the oil is Shell Diala S4 ZX-I (docs/r5-sources.md 6.7)."""
    inlet_c: float
    flow_m3s: float = Field(gt=0)
    rig: Literal["nozzle_hairpin", "shaft_spray"] = "nozzle_hairpin"   # neither rig is the owner's geometry


class ShaftOil(_Frozen):
    inlet_c: float
    flow_m3s: float = Field(gt=0)
    coolant: str = "atf"


class SlotOil(_Frozen):
    channel_height: float = Field(gt=0)
    channel_width: float = Field(gt=0)
    inlet_c: float
    flow_m3s: float = Field(gt=0)
    coolant: str = "water_glycol_50"


class CoolingSetup(_Frozen):
    jacket: Jacket | None = Jacket()
    end_spray: EndSpray | None = None
    shaft_oil: ShaftOil | None = None
    slot_oil: SlotOil | None = None
    housing_thickness: float = Field(default=8e-3, gt=0)    # m, owner placeholder
    ambient_c: float = 40.0
    impregnation_conductivity: float | None = Field(default=None, gt=0)   # None = cited nominal
    contact_gap: float | None = Field(default=None, gt=0)                 # m; None = cited nominal

    @property
    def placeholder(self) -> bool:
        """True while an owner placeholder (ambient, housing, or a jacket dimension or flow) is in use."""
        d, j = CoolingSetup(), self.jacket
        return (self.ambient_c == d.ambient_c or self.housing_thickness == d.housing_thickness
                or (j is not None and any(getattr(j, f) == getattr(Jacket(), f)
                                          for f in ("channel_height", "channel_width", "passes", "flow_m3s"))))


@dataclass(frozen=True)
class Coefficients:
    iron_factor: float
    torque_factor: float
    k_cross_wire: float            # W/(m K), winding across the wires
    k_liner: float
    liner_thickness: float         # m
    k_impregnation: float
    contact_gap: float             # m
    k_housing: float
    k_lamination: float
    h_air_gap: float               # W/(m2 K)
    h_end_frame: float             # natural convection, horizontal cylinder (stator OD)
    h_end_face: float              # natural convection, vertical plate (end faces)
    h_jacket: float | None
    jacket_fluid: Fluid | None
    jacket_flow_m3s: float | None
    jacket_inlet_c: float | None
    h_end_spray: float | None
    spray_inlet_c: float | None
    spray_flow_m3s: float | None
    spray_rho_cp: float | None     # J/(m3 K), oil at the spray inlet
    h_slot_oil: float | None
    slot_fluid: Fluid | None
    slot_flow_m3s: float | None
    slot_inlet_c: float | None
    notes: tuple[str, ...]


def _duct(coolant: str, inlet_c: float, h: float, w: float, flow: float, length: float, what: str):
    try:
        f = fluid(coolant, inlet_c)
        dh = 2 * h * w / (h + w)
        return f, duct_h(f, dh, flow / (h * w), length)
    except ValueError as e:
        raise MissingCoolingData(f"{what}: no cited source for these conditions ({e})") from e


def coefficients(setup: CoolingSetup, machine: RadialSRMParams, rpm: float,
                 unfavourable: frozenset[str], em_torque_total: float | None,
                 fill: float | None = None) -> Coefficients:
    """Numbers for the thermal network. A row in `unfavourable` takes its unfavourable end.

    `fill` is the winding's copper fill (default `machine.fill_factor`). Raises
    MissingCoolingData for shaft oil, oil in a duct, a laminar jacket or slot channel.
    """
    bad = unfavourable - set(ROWS)
    if bad:
        raise ValueError(f"unknown rows: {sorted(bad)}")
    u = lambda row: row in unfavourable  # noqa: E731
    notes = ["air-gap correlation has no cited scatter", "end-space correlation has no cited scatter "
             "(Boglietti's routes need an air speed no source gives); air properties at a 60 degC film",
             "thermal_mesh and end_winding_model: not yet measured (R5e)",
             f"end-frame and end-face h are taken at an assumed surface temperature of {2 * AIR_FILM_C - setup.ambient_c:g} degC "
             "(an assumption, not cited)"]
    fill = machine.fill_factor if fill is None else fill

    if setup.shaft_oil is not None:
        raise MissingCoolingData("shaft oil cooling: no cited source was found for its h (docs/r5-sources.md 6.4)")

    # Resin and liner share the spec row "liner" (section 7).
    resin = K_RESIN[u("liner")] if setup.impregnation_conductivity is None else (
        min(setup.impregnation_conductivity, K_RESIN[1]) if u("liner") else setup.impregnation_conductivity)
    t_mm = machine.slot_liner_thickness * 1e3
    if not NOMEX_MM[0] <= t_mm <= NOMEX_MM[-1]:
        notes.append(f"liner thickness {t_mm:.3g} mm is outside DuPont Table IV; the nearest end value of Table IV is used")
    k_liner = K_LINER_LOW if u("liner") else float(np.interp(t_mm, NOMEX_MM, NOMEX_K))
    k_cu = load_material("copper").thermal.conductivity     # 2: library value, 391.1
    xi = next((v for k, v in MILTON_XI.items() if math.isclose(k, fill, abs_tol=1e-9)), None)
    if u("cross_wire") or xi is None:
        k_wire = hashin_shtrikman_lower(fill, k_cu, resin)
        if not u("cross_wire"):
            notes.append(f"cross-wire: xi is cited at fill 0.37 only, Hashin-Shtrikman used at {fill:.3g}")
    else:
        k_wire = milton_k(fill, k_cu, resin, xi)

    nominal_gap = GAP_MM[0] * 1e-3 if setup.contact_gap is None else setup.contact_gap
    gap = max(nominal_gap, GAP_MM[1] * 1e-3) if u("contact") else nominal_gap

    arc = machine.stator_pole_arc * machine.bore_radius     # 6.2: stator pole arc length
    v = rpm * 2 * math.pi / 60 * machine.rotor_outer_radius
    h_gap = airgap_h(arc, v, AIR_FILM_C)
    d = machine.stator_outer_diameter
    surface = 2 * AIR_FILM_C - setup.ambient_c
    if not setup.ambient_c < AIR_FILM_C:
        raise MissingCoolingData("ambient at or above the 60 degC air film: no cited air properties")
    h_frame = natural_h("cylinder", d, surface, setup.ambient_c)
    h_face = natural_h("plate", 0.886 * d, surface, setup.ambient_c)   # 6.3 Eq. 5

    jk = dict(h_jacket=None, jacket_fluid=None, jacket_flow_m3s=None, jacket_inlet_c=None)
    if (j := setup.jacket) is not None:
        length = j.passes * math.pi * (machine.stator_outer_diameter + setup.housing_thickness)
        f, h = _duct(j.coolant, j.inlet_c, j.channel_height, j.channel_width, j.flow_m3s, length, "jacket")
        jk = dict(h_jacket=h * (JACKET_SCATTER if u("cooling_h") else 1.0), jacket_fluid=f,
                  jacket_flow_m3s=j.flow_m3s, jacket_inlet_c=j.inlet_c)
    sp = dict(h_end_spray=None, spray_inlet_c=None, spray_flow_m3s=None, spray_rho_cp=None)
    if (s := setup.end_spray) is not None:
        lo, hi = SPRAY_H[s.rig]
        h = lo * (SHAFT_SPRAY_SCATTER if s.rig == "shaft_spray" else 1.0) if u("cooling_h") else 0.5 * (lo + hi)
        try:
            cp = petroleum_oil_cp(DIALA_DENSITY, s.inlet_c) * (1 - CRAGOE_CP_MAX if u("cooling_h") else 1.0)
        except ValueError as e:
            raise MissingCoolingData(f"end spray: {e}") from e
        sp = dict(h_end_spray=h, spray_inlet_c=s.inlet_c, spray_flow_m3s=s.flow_m3s, spray_rho_cp=DIALA_DENSITY * cp)
        notes.append("spray oil density is the 20 degC value: no cited expansion, so the oil rise reads a few % low")
        notes.append(f"end spray h is the {s.rig} rig's measured range; that rig is not this geometry")
    so = dict(h_slot_oil=None, slot_fluid=None, slot_flow_m3s=None, slot_inlet_c=None)
    if (o := setup.slot_oil) is not None:
        if o.coolant != "water_glycol_50":
            raise MissingCoolingData(f"slot oil with coolant {o.coolant!r}: no cited oil properties "
                                     "(docs/r5-sources.md 6.4 and 6.7)")
        f, h = _duct(o.coolant, o.inlet_c, o.channel_height, o.channel_width, o.flow_m3s,
                     machine.stack_length, "slot oil")
        so = dict(h_slot_oil=h * (SLOT_OIL_SCATTER if u("cooling_h") else 1.0), slot_fluid=f,
                  slot_flow_m3s=o.flow_m3s, slot_inlet_c=o.inlet_c)

    return Coefficients(
        iron_factor=K_IRON_HI if u("iron") else 1.0,
        torque_factor=1.0 + max(TORQUE_FLOOR, em_torque_total or 0.0) if u("em_torque") else 1.0,
        k_cross_wire=k_wire, k_liner=k_liner, liner_thickness=machine.slot_liner_thickness,
        k_impregnation=resin, contact_gap=gap, k_housing=K_HOUSING,
        k_lamination=K_LAMINATION[u("lamination_k")], h_air_gap=h_gap, h_end_frame=h_frame,
        h_end_face=h_face, **jk, **sp, **so, notes=tuple(notes))
