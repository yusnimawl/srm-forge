"""Design schemas. All lengths in metres, all angles in radians."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RegionMaterials(_Frozen):
    stator: str = "M19"
    rotor: str = "M19"
    shaft: str = "steel_1010"
    coil: str = "copper"


class RadialSRMParams(_Frozen):
    schema_version: Literal[1] = SCHEMA_VERSION
    n_stator_poles: int
    n_rotor_poles: int
    n_phases: int
    stator_outer_diameter: float
    rotor_outer_diameter: float
    air_gap: float
    stack_length: float
    shaft_diameter: float
    stator_pole_arc: float
    rotor_pole_arc: float
    stator_pole_taper: float = 0.0
    rotor_pole_taper: float = 0.0
    stator_yoke_thickness: float
    rotor_yoke_thickness: float
    stator_fillet_radius: float = 0.0
    rotor_fillet_radius: float = 0.0
    turns_per_pole: int
    fill_factor: float
    slot_liner_thickness: float
    coil_inner_clearance: float
    lamination_thickness: float | None = None
    max_speed_rpm: float | None = None
    materials: RegionMaterials = RegionMaterials()

    @property
    def stator_outer_radius(self) -> float:
        return self.stator_outer_diameter / 2

    @property
    def rotor_outer_radius(self) -> float:
        return self.rotor_outer_diameter / 2

    @property
    def bore_radius(self) -> float:
        return self.rotor_outer_radius + self.air_gap

    @property
    def shaft_radius(self) -> float:
        return self.shaft_diameter / 2

    @property
    def stator_yoke_inner_radius(self) -> float:
        return self.stator_outer_radius - self.stator_yoke_thickness

    @property
    def rotor_yoke_outer_radius(self) -> float:
        return self.shaft_radius + self.rotor_yoke_thickness

    @property
    def band_inner_radius(self) -> float:
        return self.rotor_outer_radius + self.air_gap / 3

    @property
    def band_outer_radius(self) -> float:
        return self.rotor_outer_radius + 2 * self.air_gap / 3


class EdgeRefinement(_Frozen):
    size: float
    growth: float = 1.3


class MeshSettings(_Frozen):
    preset: Literal["screening", "full", "reference"] = "full"
    airgap_radial_layers: int = 4
    airgap_circumferential_divisions: int | None = None
    region_sizes: dict[str, float] = Field(default_factory=dict)
    refinement: dict[Literal["pole_tip", "pole_root"], EdgeRefinement] = Field(default_factory=dict)
    skin_depth_layers: int | None = None
    min_angle_deg: float = 10.0
    band_min_angle_deg: float = 5.0
    max_aspect_ratio: float = 12.0
    # Radial thickness of an air ring outside the stator OD (spec §4.3); 0 = none. A = 0 then sits on the
    # ring's outer circle instead of the stator OD, which admits yoke-saturation leakage flux.
    outer_air_thickness: float = 0.0
    # Uniform refinement factor applied to every resolved length after preset and user values
    # (mesh convergence studies). Below 1 refines; values above 1 would coarsen the gap below the
    # validator's minimum layer count, so they are rejected.
    scale: float = Field(1.0, gt=0, le=1)


class Design(_Frozen):
    schema_version: Literal[1] = SCHEMA_VERSION
    machine: RadialSRMParams
    mesh: MeshSettings = MeshSettings()

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Design":
        return cls.model_validate_json(text)
