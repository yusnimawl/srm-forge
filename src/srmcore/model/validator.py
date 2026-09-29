"""Closed-form validation of designs and mesh settings (runs in milliseconds, before meshing)."""
import math

from .design import Design, MeshSettings, RadialSRMParams
from .errors import InputError, ValidationIssue
from .regions import REGION_SIZE_KEYS

# Provisional floor for spec §4.2's minimum web/pole-tip-width rule; see spec §10 open items for
# the final threshold (owner decision: absolute value and/or a multiple of lamination thickness).
MIN_WEB_WIDTH = 1.0e-3

# Plausible ranges in metres; values outside almost always mean wrong units (mm instead of m).
_UNIT_RANGES: dict[str, tuple[float, float]] = {
    "stator_outer_diameter": (0.01, 2.0),
    "rotor_outer_diameter": (0.005, 2.0),
    "air_gap": (1e-5, 0.01),
    "stack_length": (1e-3, 2.0),
    "shaft_diameter": (1e-3, 0.5),
    "stator_yoke_thickness": (1e-4, 0.1),
    "rotor_yoke_thickness": (1e-4, 0.1),
    "stator_fillet_radius": (1e-5, 0.02),
    "rotor_fillet_radius": (1e-5, 0.02),
    "slot_liner_thickness": (1e-5, 0.01),
    "coil_inner_clearance": (1e-5, 0.02),
}
_TOL = 1e-9

# All float fields of RadialSRMParams that a design supplies directly (not derived properties).
_PARAM_FLOAT_FIELDS = (
    "stator_outer_diameter", "rotor_outer_diameter", "air_gap", "stack_length",
    "shaft_diameter", "stator_pole_arc", "rotor_pole_arc",
    "stator_pole_taper", "rotor_pole_taper",
    "stator_yoke_thickness", "rotor_yoke_thickness",
    "stator_fillet_radius", "rotor_fillet_radius",
    "fill_factor", "slot_liner_thickness", "coil_inner_clearance",
)
_PARAM_OPTIONAL_FLOAT_FIELDS = ("lamination_thickness", "max_speed_rpm")


def _err(parameter: str, rule: str, message: str) -> ValidationIssue:
    return ValidationIssue(parameter, rule, message, "error")


def _warn(parameter: str, rule: str, message: str) -> ValidationIssue:
    return ValidationIssue(parameter, rule, message, "warning")


def validate_params(p: RadialSRMParams) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    non_finite = False
    for name in _PARAM_FLOAT_FIELDS:
        if not math.isfinite(getattr(p, name)):
            issues.append(_err(name, "finite", "must be a finite number"))
            non_finite = True
    for name in _PARAM_OPTIONAL_FLOAT_FIELDS:
        value = getattr(p, name)
        if value is not None and not math.isfinite(value):
            issues.append(_err(name, "finite", "must be a finite number"))
            non_finite = True
    if non_finite:
        # A NaN/inf field makes every downstream comparison meaningless (they are
        # all silently False), so stop here rather than emit misleading secondary errors.
        return issues

    for name in ("n_stator_poles", "n_rotor_poles", "n_phases"):
        if getattr(p, name) < 2:
            issues.append(_err(name, "positive", "must be at least 2"))
    if p.turns_per_pole < 1:
        issues.append(_err("turns_per_pole", "positive", "must be at least 1"))
    if p.n_stator_poles == p.n_rotor_poles:
        issues.append(_err("n_rotor_poles", "phase_count", "rotor and stator pole numbers must differ"))
    elif min(p.n_stator_poles, p.n_rotor_poles, p.n_phases) >= 2:
        expected = p.n_stator_poles // math.gcd(p.n_stator_poles, p.n_rotor_poles)
        if p.n_phases != expected:
            issues.append(_err("n_phases", "phase_count",
                               f"{p.n_stator_poles}/{p.n_rotor_poles} implies {expected} phases, got {p.n_phases}"))

    for name in ("stator_outer_diameter", "rotor_outer_diameter", "air_gap", "stack_length",
                 "shaft_diameter", "stator_yoke_thickness", "rotor_yoke_thickness",
                 "stator_pole_arc", "rotor_pole_arc", "fill_factor"):
        if getattr(p, name) <= 0:
            issues.append(_err(name, "positive", "must be > 0"))
    for name in ("stator_fillet_radius", "rotor_fillet_radius", "slot_liner_thickness", "coil_inner_clearance"):
        if getattr(p, name) < 0:
            issues.append(_err(name, "non_negative", "must be >= 0"))

    for name, (lo, hi) in _UNIT_RANGES.items():
        value = getattr(p, name)
        if value > 0 and not (lo <= value <= hi):
            issues.append(_err(name, "units", f"{value} m is outside [{lo}, {hi}] m; lengths are in metres"))

    if p.fill_factor > 0.9:
        issues.append(_err("fill_factor", "range", "must be in (0, 0.9]"))
    for name in ("stator_pole_taper", "rotor_pole_taper"):
        if abs(getattr(p, name)) >= math.radians(15.0):
            issues.append(_err(name, "range", "taper magnitude must be below 15°"))

    if p.rotor_outer_diameter >= p.stator_outer_diameter:
        issues.append(_err("rotor_outer_diameter", "radial_stack", "rotor must be smaller than stator"))
    if p.rotor_yoke_outer_radius >= p.rotor_outer_radius:
        issues.append(_err("rotor_yoke_thickness", "radial_stack", "no room left for rotor poles"))
    if p.stator_yoke_inner_radius <= p.bore_radius:
        issues.append(_err("stator_yoke_thickness", "radial_stack", "no room left for stator poles"))

    for name in ("stator_yoke_thickness", "rotor_yoke_thickness"):
        if 0 < getattr(p, name) < MIN_WEB_WIDTH:
            issues.append(_err(name, "min_width", f"{getattr(p, name)} m < {MIN_WEB_WIDTH} m minimum web width"))
    stator_tip_chord = 2 * p.bore_radius * math.sin(p.stator_pole_arc / 2)
    if stator_tip_chord < MIN_WEB_WIDTH:
        issues.append(_err("stator_pole_arc", "min_width",
                           f"pole-tip chord {stator_tip_chord} m < {MIN_WEB_WIDTH} m minimum width"))
    rotor_tip_chord = 2 * p.rotor_outer_radius * math.sin(p.rotor_pole_arc / 2)
    if rotor_tip_chord < MIN_WEB_WIDTH:
        issues.append(_err("rotor_pole_arc", "min_width",
                           f"pole-tip chord {rotor_tip_chord} m < {MIN_WEB_WIDTH} m minimum width"))

    if p.n_phases >= 2 and p.n_rotor_poles >= 2:
        bs, br = p.stator_pole_arc, p.rotor_pole_arc
        limit = 2 * math.pi / (p.n_phases * p.n_rotor_poles)
        if min(bs, br) < limit - _TOL:
            which = "stator_pole_arc" if bs <= br else "rotor_pole_arc"
            issues.append(_err(which, "self_starting",
                               f"min(βs, βr) = {math.degrees(min(bs, br)):.3f}° < 2π/(m·Nr) = {math.degrees(limit):.3f}°"))
        pitch = 2 * math.pi / p.n_rotor_poles
        if bs + br >= pitch - _TOL:
            issues.append(_err("rotor_pole_arc", "pole_arc_sum",
                               f"βs + βr = {math.degrees(bs + br):.3f}° must be < 2π/Nr = {math.degrees(pitch):.3f}°"))
        if bs > br:
            issues.append(_warn("stator_pole_arc", "arc_order", "βs > βr (valid, but unusual)"))

    if p.lamination_thickness is not None:
        if not (1e-5 <= p.lamination_thickness <= 2e-3):
            issues.append(_err("lamination_thickness", "units", "must be within [1e-5, 2e-3] m"))
        elif p.max_speed_rpm is not None and p.max_speed_rpm > 0:
            f_max = p.n_rotor_poles * p.max_speed_rpm / 60.0
            if f_max > 1000.0 and p.lamination_thickness > 0.2e-3:
                issues.append(_warn("lamination_thickness", "lamination_frequency",
                                    f"{p.lamination_thickness * 1e3:.2f} mm at {f_max:.0f} Hz: use ≤ 0.2 mm"))
    if p.max_speed_rpm is not None and p.max_speed_rpm <= 0:
        issues.append(_err("max_speed_rpm", "positive", "must be > 0"))
    return issues


def validate_mesh_settings(s: MeshSettings, p: RadialSRMParams) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    non_finite = False
    for key, size in s.region_sizes.items():
        if not math.isfinite(size):
            issues.append(_err(f"region_sizes.{key}", "finite", "must be a finite number"))
            non_finite = True
    for tag, ref in s.refinement.items():
        if not math.isfinite(ref.size):
            issues.append(_err(f"refinement.{tag}.size", "finite", "must be a finite number"))
            non_finite = True
        if not math.isfinite(ref.growth):
            issues.append(_err(f"refinement.{tag}.growth", "finite", "must be a finite number"))
            non_finite = True
    for name in ("min_angle_deg", "band_min_angle_deg", "max_aspect_ratio"):
        if not math.isfinite(getattr(s, name)):
            issues.append(_err(name, "finite", "must be a finite number"))
            non_finite = True
    if non_finite:
        # As in validate_params: a NaN/inf value makes every downstream comparison
        # meaningless, so stop here rather than emit misleading secondary errors.
        return issues

    if s.airgap_radial_layers < 4:
        issues.append(_err("airgap_radial_layers", "min_layers", "at least 4 element layers across the air gap"))
    elif "airgap" in s.region_sizes:
        airgap_size = s.region_sizes["airgap"]
        limit = p.air_gap / s.airgap_radial_layers
        if airgap_size > 0 and airgap_size > limit * (1 + 1e-12):
            issues.append(_err("region_sizes.airgap", "min_layers",
                               f"{airgap_size} m gives fewer than {s.airgap_radial_layers} element "
                               f"layers across the {p.air_gap} m air gap"))
    if s.airgap_circumferential_divisions is not None:
        # lcm(Ns, 2*Nr), not lcm(Ns, Nr): the extra factor of 2 puts the unaligned rotor position
        # (pi/Nr, half a rotor pitch off the aligned position) on the band grid too, not just the
        # aligned positions (multiples of a full rotor pitch).
        base = math.lcm(p.n_stator_poles, 2 * p.n_rotor_poles)
        n = s.airgap_circumferential_divisions
        if n < base or n % base != 0:
            issues.append(_err("airgap_circumferential_divisions", "band_divisions",
                               f"must be a positive multiple of lcm(Ns, 2*Nr) = {base}"))
    for key, size in s.region_sizes.items():
        if key not in REGION_SIZE_KEYS:
            issues.append(_err(f"region_sizes.{key}", "unknown_region", f"allowed: {sorted(REGION_SIZE_KEYS)}"))
        elif size <= 0:
            issues.append(_err(f"region_sizes.{key}", "positive", "must be > 0"))
    for tag, ref in s.refinement.items():
        if ref.size <= 0:
            issues.append(_err(f"refinement.{tag}.size", "positive", "must be > 0"))
        if ref.growth < 1.0:
            issues.append(_err(f"refinement.{tag}.growth", "range", "must be >= 1.0"))
    if s.skin_depth_layers is not None:
        issues.append(_err("skin_depth_layers", "not_implemented", "skin-depth layers arrive with sub-project #2"))
    if not (0 < s.min_angle_deg < 60):
        issues.append(_err("min_angle_deg", "range", "must be in (0, 60)"))
    if not (0 < s.band_min_angle_deg < 60):
        issues.append(_err("band_min_angle_deg", "range", "must be in (0, 60)"))
    if s.max_aspect_ratio <= 1:
        issues.append(_err("max_aspect_ratio", "range", "must be > 1"))
    return issues


def require_valid(design: Design) -> list[ValidationIssue]:
    issues = validate_params(design.machine) + validate_mesh_settings(design.mesh, design.machine)
    if any(i.severity == "error" for i in issues):
        raise InputError(issues)
    return [i for i in issues if i.severity == "warning"]
