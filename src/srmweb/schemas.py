"""Request models of the web API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from srmapp.requirements import Requirements
from srmcore.materials.library import available_materials, load_material


class SearchSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_candidates: int = Field(200, ge=1, le=2000)
    shortlist: int = Field(40, ge=1, le=200)
    seed: int = Field(0, ge=0)
    stator: str = "10JNEX900"
    rotor: str = "10JNEX900"
    preset: Literal["screening", "full"] = "full"
    margin: float | None = Field(None, gt=0)
    j_peak: float | None = Field(None, gt=0)
    j_limit: float | None = Field(None, gt=0)
    j_peak_max: float | None = Field(None, gt=0)

    @field_validator("stator", "rotor")
    @classmethod
    def _soft_magnetic(cls, name: str) -> str:
        if name not in available_materials():
            raise ValueError(f"unknown material {name!r}; available: {', '.join(available_materials())}")
        if load_material(name).kind != "soft_magnetic":
            raise ValueError(f"{name!r} is not a soft-magnetic material")
        return name


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: Requirements
    settings: SearchSettingsIn = SearchSettingsIn()
    grid: tuple[int, int] | None = None   # (angles, currents); overrides the preset grid, for tests
