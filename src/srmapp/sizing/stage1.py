"""Stage 1: closed-form filter that drops designs that cannot meet the requirements even under optimistic
assumptions (v0 spec §4.3). The torque bound is an upper bound on purpose, so the filter never drops a design
the FEM stage would keep."""
import math
from dataclasses import dataclass

from srmcore.materials.library import load_material
from srmcore.model.design import RadialSRMParams

from ..requirements import Requirements
from .estimates import J_PEAK, Mass, active_mass, peak_current, pole_chord


def torque_upper_bound(p: RadialSRMParams, i_peak: float) -> float:
    """Average torque (N·m) if every stroke converted the full rectangle ψ_sat·i_peak: the pole flux saturates at
    the material's saturation polarisation in the narrower of the stator and rotor poles, and the phase carries
    turns_per_pole × poles-per-phase series turns. Each of the m·Nr strokes per revolution converts one rectangle."""
    stator, rotor = load_material(p.materials.stator), load_material(p.materials.rotor)
    b_sat = min(stator.saturation_polarisation, rotor.saturation_polarisation)
    pole_width = min(pole_chord(p.bore_radius, p.stator_pole_arc), pole_chord(p.rotor_outer_radius, p.rotor_pole_arc))
    pole_area = pole_width * p.stack_length * min(stator.stacking_factor, rotor.stacking_factor)
    series_turns = p.turns_per_pole * p.n_stator_poles / p.n_phases
    psi_sat = series_turns * b_sat * pole_area
    return p.n_phases * p.n_rotor_poles * psi_sat * i_peak / (2 * math.pi)


@dataclass(frozen=True)
class Stage1:
    mass: Mass
    i_peak: float          # A
    torque_upper: float    # N·m
    passes: bool
    reason: str            # empty when the design passes


def stage1(req: Requirements, p: RadialSRMParams, margin: float = 1.0, j_peak: float = J_PEAK) -> Stage1:
    mass = active_mass(p)
    i_peak = peak_current(p, j_peak)
    upper = torque_upper_bound(p, i_peak)
    reason = ""
    if req.max_mass_kg is not None and mass.total > req.max_mass_kg:
        reason = f"mass {mass.total:.2f} kg above the {req.max_mass_kg:.2f} kg limit"
    elif upper < margin * req.peak_torque_nm:
        reason = f"torque upper bound {upper:.1f} N·m below the required {margin * req.peak_torque_nm:.1f} N·m"
    return Stage1(mass, i_peak, upper, reason == "", reason)
