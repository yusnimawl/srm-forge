"""Stage 1: closed-form filter that drops designs that cannot meet the requirements even under optimistic
assumptions (v0 spec §4.3). The torque bound is deliberately optimistic; its false-drop rate is checked against
stage 2 later."""
import math
from dataclasses import dataclass

from srmcore.materials.library import load_material
from srmcore.model.design import RadialSRMParams

from ..requirements import Requirements
from .estimates import J_PEAK, Mass, active_mass, peak_current, pole_chord

# Allowance on the saturation flux for mu0*H beyond Js and fringing.
FLUX_ALLOWANCE = 1.1


def torque_upper_bound(p: RadialSRMParams, i_peak: float) -> float:
    """Upper bound on the revolution-average torque (N·m) if every stroke converted the full rectangle
    ψ_sat·i_peak. The flux linking the coil is bounded by the stator pole body saturating at the stator material's
    saturation polarisation, taken at the bore chord (pole taper is ignored; the generator uses zero taper), and the
    phase carries turns_per_pole × poles-per-phase series turns. Each of the m·Nr strokes per revolution converts
    one rectangle."""
    stator = load_material(p.materials.stator)
    pole_area = pole_chord(p.bore_radius, p.stator_pole_arc) * p.stack_length * stator.stacking_factor
    series_turns = p.turns_per_pole * p.n_stator_poles / p.n_phases
    psi_sat = FLUX_ALLOWANCE * series_turns * stator.saturation_polarisation * pole_area
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
