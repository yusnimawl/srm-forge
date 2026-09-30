"""Closed-form estimates of active mass, winding resistance and peak current (v0 spec §4).

Poles are treated as parallel-sided bars of the chord width at the pole face, so iron areas are estimates
(fillets, tapers and the slot corners are ignored). The end winding is a racetrack approximation."""
import math
from dataclasses import dataclass

from srmcore.materials.library import load_material
from srmcore.model.design import RadialSRMParams

# Default peak current density in the conductor, A/m². Provisional: a thermal model replaces it.
J_PEAK = 20e6


@dataclass(frozen=True)
class Mass:
    stator_iron: float   # kg
    rotor_iron: float
    copper: float

    @property
    def total(self) -> float:
        return self.stator_iron + self.rotor_iron + self.copper


def pole_chord(radius: float, arc: float) -> float:
    return 2 * radius * math.sin(arc / 2)


def _slot_width(p: RadialSRMParams) -> float:
    """Mean circumferential slot width between two stator poles."""
    r_mid = (p.bore_radius + p.stator_yoke_inner_radius) / 2
    return 2 * math.pi * r_mid / p.n_stator_poles - pole_chord(p.bore_radius, p.stator_pole_arc)


def coil_side_area(p: RadialSRMParams) -> float:
    """Copper-bearing area of one coil side: half of the slot, less liner and inner clearance."""
    height = p.stator_yoke_inner_radius - p.bore_radius
    width = _slot_width(p) - 2 * p.slot_liner_thickness
    depth = height - p.slot_liner_thickness - p.coil_inner_clearance
    return max(width, 0.0) * max(depth, 0.0) / 2


def mean_turn_length(p: RadialSRMParams) -> float:
    """Two straight runs plus two semicircular ends around a pole and half a slot either side."""
    return 2 * p.stack_length + math.pi * (pole_chord(p.bore_radius, p.stator_pole_arc) + _slot_width(p) / 2)


def conductor_area(p: RadialSRMParams) -> float:
    """Cross-section of one conductor: the filled coil side shared among the turns of a pole."""
    return p.fill_factor * coil_side_area(p) / p.turns_per_pole


def peak_current(p: RadialSRMParams, j_peak: float = J_PEAK) -> float:
    return j_peak * conductor_area(p)


def _iron_areas(p: RadialSRMParams) -> tuple[float, float]:
    """Cross-section areas (m²) of stator and rotor iron, without the stacking factor."""
    rb, ryi = p.bore_radius, p.stator_yoke_inner_radius
    stator = (math.pi * (p.stator_outer_radius**2 - ryi**2)
              + p.n_stator_poles * pole_chord(rb, p.stator_pole_arc) * (ryi - rb))
    ro, rj = p.rotor_outer_radius, p.rotor_yoke_outer_radius
    rotor = (math.pi * (rj**2 - p.shaft_radius**2)
             + p.n_rotor_poles * pole_chord(ro, p.rotor_pole_arc) * (ro - rj))
    return stator, rotor


def active_mass(p: RadialSRMParams) -> Mass:
    stator_area, rotor_area = _iron_areas(p)
    stator_mat, rotor_mat = load_material(p.materials.stator), load_material(p.materials.rotor)
    copper = load_material(p.materials.coil)
    copper_volume = (p.n_stator_poles * p.turns_per_pole * conductor_area(p) * mean_turn_length(p))
    return Mass(stator_iron=stator_mat.density * stator_mat.stacking_factor * stator_area * p.stack_length,
                rotor_iron=rotor_mat.density * rotor_mat.stacking_factor * rotor_area * p.stack_length,
                copper=copper.density * copper_volume)


def phase_resistance(p: RadialSRMParams, temperature_c: float = 100.0) -> float:
    """Series resistance of one phase at `temperature_c`."""
    copper = load_material(p.materials.coil)
    rho = copper.resistivity * (1 + copper.temperature_coefficient * (temperature_c - copper.reference_temperature_c))
    turns_phase = p.turns_per_pole * p.n_stator_poles / p.n_phases
    return rho * turns_phase * mean_turn_length(p) / conductor_area(p)
