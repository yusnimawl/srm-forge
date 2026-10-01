"""Stage 1: closed-form filter that drops designs that cannot meet the requirements even under optimistic
assumptions (v0 spec §4.3). The torque bound is deliberately optimistic; its false-drop rate is checked against
stage 2 later. The mass limit compares the iron only, so it never drops a design whose winding is not yet chosen."""
import math
from dataclasses import dataclass

from srmcore.materials.library import load_material
from srmcore.model.design import RadialSRMParams

from ..requirements import Requirements
from .estimates import J_LIMIT, J_PEAK, Mass, active_mass, pole_chord
from .winding import max_mmf

# Allowance on the saturation flux for mu0*H beyond Js and fringing.
FLUX_ALLOWANCE = 1.1


def torque_upper_bound(p: RadialSRMParams, mmf: float) -> float:
    """Upper bound on the revolution-average torque (N·m) if every stroke converted the full rectangle
    ψ_sat·i_peak at `mmf` peak ampere-turns per pole. The flux through a pole is bounded by the stator pole body
    saturating at the stator material's saturation polarisation, taken at the bore chord (pole taper is ignored;
    the generator uses zero taper), and a phase has Ns/m poles in series, so ψ_sat·i_peak = (Ns/m)·Φ_sat·mmf, which
    does not depend on the turns. Each of the m·Nr strokes per revolution converts one rectangle."""
    stator = load_material(p.materials.stator)
    pole_area = pole_chord(p.bore_radius, p.stator_pole_arc) * p.stack_length * stator.stacking_factor
    flux_sat = FLUX_ALLOWANCE * stator.saturation_polarisation * pole_area
    return p.n_phases * p.n_rotor_poles * (p.n_stator_poles / p.n_phases) * flux_sat * mmf / (2 * math.pi)


@dataclass(frozen=True)
class Stage1:
    mass: Mass             # at the reference winding; the limit compares the iron only (the winding is chosen later)
    mmf: float             # peak ampere-turns per pole the map must cover
    i_map: float           # A, map I_max at the reference turns
    torque_upper: float    # N·m
    passes: bool
    reason: str            # empty when the design passes


def stage1(req: Requirements, p: RadialSRMParams, margin: float = 1.0, j_peak: float = J_PEAK,
           j_limit: float = J_LIMIT) -> Stage1:
    mass = active_mass(p)
    mmf = max_mmf(p, req, j_peak, j_limit)
    upper = torque_upper_bound(p, mmf)
    reason = ""
    if req.max_mass_kg is not None and mass.iron > req.max_mass_kg:
        reason = f"iron mass {mass.iron:.2f} kg above the {req.max_mass_kg:.2f} kg limit"
    elif mmf == 0.0:
        reason = "no winding meets the wire, phase current and current-density limits"
    elif upper < margin * req.peak_torque_nm:
        reason = f"torque upper bound {upper:.1f} N·m below the required {margin * req.peak_torque_nm:.1f} N·m"
    return Stage1(mass, mmf, mmf / p.turns_per_pole, upper, reason == "", reason)
