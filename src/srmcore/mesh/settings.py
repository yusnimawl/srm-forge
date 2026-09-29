"""Turn user mesh settings into concrete sizes. Preset numbers are provisional until the M5 convergence study."""
import math
from dataclasses import dataclass

from ..model.design import MeshSettings, RadialSRMParams
from ..model.regions import REGION_SIZE_KEYS


@dataclass(frozen=True)
class _Preset:
    iron_factor: float
    band_aspect: float
    tip_factor: float


PRESETS: dict[str, _Preset] = {
    "screening": _Preset(iron_factor=0.08, band_aspect=3.0, tip_factor=3.0),
    "full": _Preset(iron_factor=0.04, band_aspect=1.5, tip_factor=2.0),
    "reference": _Preset(iron_factor=0.02, band_aspect=1.0, tip_factor=1.5),
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
    iron = p.bore_radius * preset.iron_factor
    # Every REGION_SIZE_KEYS entry gets an iron-scale default; shaft and airgap override it below.
    sizes = {key: iron for key in REGION_SIZE_KEYS}
    sizes["shaft"] = 2 * iron
    sizes["airgap"] = p.air_gap / s.airgap_radial_layers
    sizes.update(s.region_sizes)
    gap = sizes["airgap"]
    refinement = {
        "pole_tip": (preset.tip_factor * gap, DEFAULT_GROWTH),
        "pole_root": (iron / 4, DEFAULT_GROWTH),
        # Grades the size away from the slot-mouth arcs where the airgap regions' fine size meets
        # the iron-scale background; internal only, not a user-overridable MeshSettings.refinement
        # tag. Without it, a forced-fine curve butting straight into a coarse interior produces
        # sliver triangles all along those arcs.
        "airgap_interface": (gap, DEFAULT_GROWTH),
    }
    if p.slot_liner_thickness > 0:
        # The liner strip is much thinner than the generic "iron"-scale element size, and with
        # no dedicated refinement it gets forced sliver triangles. `gap` is a floor so this never
        # asks for elements finer than the airgap.
        refinement["slot_liner"] = (max(p.slot_liner_thickness, gap), DEFAULT_GROWTH)
    for tag, ref in s.refinement.items():
        refinement[tag] = (ref.size, ref.growth)
    if s.airgap_circumferential_divisions is not None:
        divisions = s.airgap_circumferential_divisions
    else:
        # lcm(Ns, 2*Nr), not lcm(Ns, Nr): puts the unaligned rotor position (half a rotor pitch
        # off the aligned position) on the band grid too, not just the aligned positions.
        base = math.lcm(p.n_stator_poles, 2 * p.n_rotor_poles)
        r_mid = (p.band_inner_radius + p.band_outer_radius) / 2
        target = 2 * math.pi * r_mid / (preset.band_aspect * gap)
        divisions = base * math.ceil(target / base)
    return ResolvedMeshSettings(
        gap_size=gap, region_sizes=sizes, refinement=refinement, band_divisions=divisions,
        min_angle_deg=s.min_angle_deg, band_min_angle_deg=s.band_min_angle_deg,
        max_aspect_ratio=s.max_aspect_ratio,
    )
