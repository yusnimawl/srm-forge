"""Inputs of one case: a design, its requirements and how it is wound and judged."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from srmcore.model.design import Design

from .pipeline import SearchSettings
from .requirements import Requirements
from .sizing.generator import REFERENCE_TURNS


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FixedWinding(_Frozen):
    turns: int = Field(ge=1, le=2000)
    strands: int = Field(1, ge=1, le=200)
    paths: int = Field(1, ge=1)
    wire: int | None = Field(None, ge=0)        # index into Requirements.wires; None in density mode


class CaseInputs(_Frozen):
    requirements: Requirements
    design: Design
    winding: Literal["auto"] | FixedWinding = "auto"
    margin: float | None = Field(None, gt=0)
    j_peak: float | None = Field(None, gt=0)
    j_limit: float | None = Field(None, gt=0)
    j_peak_max: float | None = Field(None, gt=0)

    @field_validator("design")
    @classmethod
    def _preset(cls, design: Design) -> Design:
        if design.mesh.preset not in ("screening", "full"):
            raise ValueError(f"mesh preset must be 'screening' or 'full', got {design.mesh.preset!r}")
        return design

    def search_settings(self) -> SearchSettings:
        """The search settings these inputs imply; unset limits keep the search defaults."""
        optional = {k: v for k in ("margin", "j_peak", "j_limit", "j_peak_max") if (v := getattr(self, k)) is not None}
        return SearchSettings(materials=self.design.machine.materials, preset=self.design.mesh.preset, **optional)


def reference_design(inputs: CaseInputs) -> Design:
    """The design whose map serves every winding: `inputs.design` at REFERENCE_TURNS."""
    machine = inputs.design.machine.model_copy(update={"turns_per_pole": REFERENCE_TURNS})
    return inputs.design.model_copy(update={"machine": machine})
