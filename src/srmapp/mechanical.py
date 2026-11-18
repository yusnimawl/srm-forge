"""Bearing friction and air-gap windage of a machine: the input (`BearingSetup`) and the loss at a speed.

Windage is `srmcore.thermal.windage` (measured smooth-cylinder drag, docs/r3-sources.md section 6); bearing friction
is `srmcore.post.bearing_friction` (constant mu, section 7). Both carry a band; `unfavourable` takes the high end.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from srmcore.materials.library import load_material
from srmcore.model.design import RadialSRMParams
from srmcore.post.bearing_friction import BEARING_MU, NOTE as FRICTION_NOTE, bearing_friction
from srmcore.thermal.windage import windage_loss

from .sizing.estimates import active_mass

G = 9.81

BearingType = Literal["deep_groove_ball", "angular_contact_ball", "self_aligning_ball", "cylindrical_roller",
                      "needle_full_complement", "needle_cage", "tapered_roller", "spherical_roller", "thrust_ball",
                      "spherical_thrust_roller"]
assert set(BearingType.__args__) == set(BEARING_MU)

PLACEHOLDER_NOTE = ("bearing type, size and load are placeholders (the bearing is not chosen): deep groove ball "
                    "bearings, bore equal to the shaft diameter, load equal to the rotor weight")


class BearingSetup(BaseModel):
    """Bearings of the rotor. Every field has a default, which is a placeholder until the bearing is chosen."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: BearingType = "deep_groove_ball"
    count: int = Field(default=2, ge=1)                       # bearings; they share the load
    bore_diameter_m: float | None = Field(default=None, gt=0)    # None = the shaft diameter
    radial_load_n: float | None = Field(default=None, ge=0)      # total; None = the rotor weight

    @property
    def placeholder(self) -> bool:
        """True while every field is its default (nothing about the bearing was chosen)."""
        return self == BearingSetup()


@dataclass(frozen=True)
class MechanicalLoss:
    windage_w: float
    friction_w: float
    windage_rel: tuple[float, float]     # band on windage_w: (low, high) relative to windage_w, minus 1
    friction_rel: tuple[float, float]
    notes: tuple[str, ...]

    @property
    def total_w(self) -> float:
        return self.windage_w + self.friction_w

    def total_rel(self) -> tuple[float, float]:
        """Band on the sum, relative to it, minus 1."""
        if not self.total_w > 0:
            return (0.0, 0.0)
        lo = self.windage_w * (1 + self.windage_rel[0]) + self.friction_w * (1 + self.friction_rel[0])
        hi = self.windage_w * (1 + self.windage_rel[1]) + self.friction_w * (1 + self.friction_rel[1])
        return (lo / self.total_w - 1.0, hi / self.total_w - 1.0)


def rotor_weight_n(machine: RadialSRMParams) -> float:
    """Weight of the rotor laminations and the shaft over the stack length, N (the shaft beyond the stack is not counted)."""
    shaft = load_material(machine.materials.shaft)
    shaft_kg = shaft.density * math.pi * machine.shaft_radius ** 2 * machine.stack_length
    return (active_mass(machine).rotor_iron + shaft_kg) * G


def mechanical_loss(machine: RadialSRMParams, bearing: BearingSetup, rpm: float, unfavourable: bool = False,
                    air_c: float = 60.0) -> MechanicalLoss:
    """Windage and bearing friction power at `rpm`; `unfavourable` takes the high end of each band."""
    wind = windage_loss(machine.rotor_outer_radius, machine.air_gap, machine.stack_length, rpm, air_c)
    bore = machine.shaft_diameter if bearing.bore_diameter_m is None else bearing.bore_diameter_m
    load = rotor_weight_n(machine) if bearing.radial_load_n is None else bearing.radial_load_n
    fr = bearing_friction(bearing.type, bore, load, rpm)
    notes = [*wind.notes, FRICTION_NOTE]
    if bearing.placeholder:
        notes.append(PLACEHOLDER_NOTE)
    if bearing.radial_load_n is None:
        notes.append("bearing load is the rotor weight over the stack length, shared by the bearings: no magnetic "
                     "pull, unbalance or belt load")
    if not wind.in_range:
        notes.append("windage is outside the measured range of its source (see the windage notes)")
    wr = (-wind.rel_low, wind.rel_high)
    fr_rel = (fr.power_low_w / fr.power_w - 1.0, fr.power_high_w / fr.power_w - 1.0) if fr.power_w > 0 else (0.0, 0.0)
    w, f = wind.power_w, fr.power_w
    if unfavourable:
        w, f = w * (1 + wr[1]), (fr.power_high_w if fr.power_w > 0 else 0.0)
    return MechanicalLoss(w, f, wr, fr_rel, tuple(dict.fromkeys(notes)))
