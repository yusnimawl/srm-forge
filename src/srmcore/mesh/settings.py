"""Turn user mesh settings into concrete sizes. The preset numbers come from the M5a convergence study
(docs/m5a-convergence.md); `full` and `reference` are the screening knobs at a fixed scale. The preset
scale applies to preset-derived values only: explicit `region_sizes` and `refinement` are exact, and
the user `MeshSettings.scale` then multiplies everything."""
import dataclasses
import math
from dataclasses import dataclass

from ..model.design import MeshSettings, RadialSRMParams
from ..model.regions import REGION_SIZE_KEYS


@dataclass(frozen=True)
class _Preset:
    iron_factor: float
    band_aspect: float
    tip_factor: float
    scale: float = 1.0


_SCREENING = _Preset(iron_factor=0.08, band_aspect=3.0, tip_factor=3.0)
PRESETS: dict[str, _Preset] = {
    "screening": _SCREENING,
    "full": dataclasses.replace(_SCREENING, scale=2 ** -0.5),
    "reference": dataclasses.replace(_SCREENING, scale=0.25),
}
DEFAULT_GROWTH = 1.3


@dataclass(frozen=True)
class ResolvedMeshSettings:
    gap_size: float
    region_sizes: dict[str, float]
    refinement: dict[str, tuple[float, float]]
    band_divisions: int
    min_angle_deg: float
    band_min_angle_deg: float
    max_aspect_ratio: float

    @property
    def band_pitch(self) -> float:
        return 2 * math.pi / self.band_divisions


def resolve_mesh_settings(p: RadialSRMParams, s: MeshSettings) -> ResolvedMeshSettings:
    preset = PRESETS[s.preset]
    ps = preset.scale
    scale = s.scale
    iron = p.bore_radius * preset.iron_factor * ps
    # Every REGION_SIZE_KEYS entry gets an iron-scale default; shaft and airgap override it below.
    # The preset scale applies to these preset-derived values only; user overrides are exact
    # (before the user scale).
    sizes = {key: iron for key in REGION_SIZE_KEYS}
    sizes["shaft"] = 2 * iron
    sizes["airgap"] = p.air_gap / s.airgap_radial_layers * ps
    sizes.update(s.region_sizes)
    gap = sizes["airgap"]
    growth = 1 + (DEFAULT_GROWTH - 1) * ps
    refinement = {
        "pole_tip": (preset.tip_factor * gap, growth),
        "pole_root": (iron / 4, growth),
        # Grades the size away from the slot-mouth arcs where the airgap regions' fine size meets
        # the iron-scale background; internal only, not a user-overridable MeshSettings.refinement
        # tag. Without it, a forced-fine curve butting straight into a coarse interior produces
        # sliver triangles all along those arcs.
        "airgap_interface": (gap, growth),
    }
    if p.slot_liner_thickness > 0:
        # The liner strip is much thinner than the generic "iron"-scale element size, and with
        # no dedicated refinement it gets forced sliver triangles. `gap` is a floor so this never
        # asks for elements finer than the airgap.
        refinement["slot_liner"] = (max(p.slot_liner_thickness * ps, gap), growth)
    for tag, ref in s.refinement.items():
        refinement[tag] = (ref.size, ref.growth)
    if s.airgap_circumferential_divisions is not None:
        divisions = s.airgap_circumferential_divisions
    else:
        # lcm(Ns, 2*Nr), not lcm(Ns, Nr): puts the unaligned rotor position (half a rotor pitch
        # off the aligned position) on the band grid too, not just the aligned positions.
        base = math.lcm(p.n_stator_poles, 2 * p.n_rotor_poles)
        r_mid = (p.band_inner_radius + p.band_outer_radius) / 2
        target = 2 * math.pi * r_mid / (preset.band_aspect * gap / ps)
        divisions = base * math.ceil(target / base)
        if scale != 1 or ps != 1:
            divisions = base * max(1, round(divisions / (ps * scale) / base))
    if scale != 1:
        gap *= scale
        sizes = {k: v * scale for k, v in sizes.items()}
        refinement = {k: (size * scale, 1 + (g - 1) * scale) for k, (size, g) in refinement.items()}
    return ResolvedMeshSettings(
        gap_size=gap, region_sizes=sizes, refinement=refinement, band_divisions=divisions,
        min_angle_deg=s.min_angle_deg, band_min_angle_deg=s.band_min_angle_deg,
        max_aspect_ratio=s.max_aspect_ratio,
    )
