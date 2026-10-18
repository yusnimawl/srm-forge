"""Material records (spec §5.1). SI units: B in T, H in A/m, lengths in m, density in kg/m³,
resistivity in Ω·m, temperatures in °C."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Provenance(_Frozen):
    source: str
    page: str | None = None
    date: str | None = None
    method: str | None = None
    temperature_c: float | None = None
    annealed: bool | None = None
    anneal_recipe: str | None = None
    typical: bool | None = None


class BHTable(_Frozen):
    """Measured single-valued B-H points of the bare steel (no stacking factor applied)."""
    h: tuple[float, ...]
    b: tuple[float, ...]
    temperature_c: float = 20.0

    @model_validator(mode="after")
    def _paired(self) -> "BHTable":
        if len(self.h) != len(self.b):
            raise ValueError(f"h has {len(self.h)} points but b has {len(self.b)}")
        if len(self.h) < 3:
            raise ValueError("a B-H table needs at least 3 points")
        return self


class LossPoint(_Frozen):
    """Measured sinusoidal core loss: peak flux density b (T), frequency f (Hz), loss in W/kg."""
    b: float = Field(gt=0)
    f: float = Field(gt=0)
    w_per_kg: float = Field(gt=0)


class LossData(_Frozen):
    """Sinusoidal core-loss table of a lamination steel plus the conductivity used for the classical term."""
    points: tuple[LossPoint, ...]
    provenance: Provenance
    confidence: Literal["A", "B", "C"]
    frequency_range: tuple[float, float]
    conductivity: float = Field(gt=0)   # S/m
    conductivity_source: str

    @model_validator(mode="after")
    def _enough_points(self) -> "LossData":
        if len(self.points) < 6:
            raise ValueError(f"loss data needs at least 6 points, got {len(self.points)}")
        if len({p.f for p in self.points}) < 2:
            raise ValueError("loss data needs at least 2 distinct frequencies")
        lo, hi = self.frequency_range
        if not 0 < lo < hi:
            raise ValueError("frequency_range must satisfy 0 < low < high")
        return self


class _Sourced(_Frozen):
    """Every numeric property carries a *_source string; placeholders are listed and say PROVISIONAL."""
    density: float = Field(gt=0)
    density_source: str
    # Unknown until a supplier quote exists; spec §5.1 needs it for the cost objective (sub-project #6).
    cost_per_kg: float | None = Field(default=None, ge=0)
    cost_source: str | None = None
    provisional_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _provisional_sources(self) -> "_Sourced":
        for field in self.provisional_fields:
            source = getattr(self, f"{field}_source", None)
            if source is None or "PROVISIONAL" not in source:
                raise ValueError(f"provisional field {field!r} needs a {field}_source containing 'PROVISIONAL'")
        return self


class SoftMagneticMaterial(_Sourced):
    kind: Literal["soft_magnetic"] = "soft_magnetic"
    name: str
    grade: str
    variant: str
    parent_grade: str | None = None
    thickness: float | None = Field(default=None, gt=0)
    supplier: str | None = None
    provenance: Provenance
    confidence: Literal["A", "B", "C"]
    bh: BHTable
    stacking_factor: float = Field(gt=0, le=1)
    stacking_factor_source: str
    saturation_polarisation: float = Field(gt=0)
    saturation_polarisation_source: str
    digitisation_error: float | None = Field(default=None, ge=0, lt=0.5)   # relative B error of a digitised curve
    loss: LossData | None = None


class ConductorMaterial(_Sourced):
    kind: Literal["conductor"] = "conductor"
    name: str
    provenance: Provenance
    resistivity: float = Field(gt=0)
    reference_temperature_c: float = 20.0
    temperature_coefficient: float
    insulation_class: str | None = None
    max_temperature_c: float | None = None

    def resistivity_at(self, temperature_c: float) -> float:
        return self.resistivity * (1 + self.temperature_coefficient * (temperature_c - self.reference_temperature_c))


Material = Annotated[SoftMagneticMaterial | ConductorMaterial, Field(discriminator="kind")]
