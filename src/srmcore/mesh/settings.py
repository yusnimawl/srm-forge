"""Turn user mesh settings into concrete sizes. Preset numbers are provisional until the M5 convergence study."""
import math
from dataclasses import dataclass

from ..model.design import MeshSettings, RadialSRMParams


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
    sizes = {
        "stator_iron": iron, "rotor_iron": iron, "shaft": 2 * iron,
        "coil": iron, "slot_air": iron, "airgap": p.air_gap / s.airgap_radial_layers,
    }
    sizes.update(s.region_sizes)
    gap = sizes["airgap"]
    refinement = {
        "pole_tip": (preset.tip_factor * gap, DEFAULT_GROWTH),
        "pole_root": (iron / 4, DEFAULT_GROWTH),
    }
    for tag, ref in s.refinement.items():
        refinement[tag] = (ref.size, ref.growth)
    if s.airgap_circumferential_divisions is not None:
        divisions = s.airgap_circumferential_divisions
    else:
        base = math.lcm(p.n_stator_poles, p.n_rotor_poles)
        r_mid = (p.band_inner_radius + p.band_outer_radius) / 2
        target = 2 * math.pi * r_mid / (preset.band_aspect * gap)
        divisions = base * math.ceil(target / base)
    return ResolvedMeshSettings(
        gap_size=gap, region_sizes=sizes, refinement=refinement, band_divisions=divisions,
        min_angle_deg=s.min_angle_deg, band_min_angle_deg=s.band_min_angle_deg,
        max_aspect_ratio=s.max_aspect_ratio,
    )
