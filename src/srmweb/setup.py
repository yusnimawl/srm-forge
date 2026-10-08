"""Setup files: a case's inputs as a JSON document that can be saved, edited by hand and imported again.

Every section is optional in the file; `case_inputs_from_setup` needs the four that make up a case. Materials
live in the `materials` section only: `geometry.machine` is written without them and, if a file carries them
there, the `materials` section wins."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from srmapp.case import LIMIT_FIELDS, CaseInputs, FixedWinding
from srmapp.requirements import Requirements
from srmcore.model.design import Design, MeshSettings, RadialSRMParams, RegionMaterials
from srmweb.schemas import SearchSettingsIn

SECTIONS = ("requirements", "geometry", "materials", "winding")   # what a case needs, in report order
NO_MACHINE_MATERIALS = {"geometry": {"machine": {"materials"}}}   # `response_model_exclude` for a setup file


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GeometrySection(_Section):
    machine: RadialSRMParams
    preset: Literal["screening", "full"] = "full"


class WindingSection(_Section):
    mode: Literal["auto", "fixed"]
    fixed: FixedWinding | None = None
    margin: float | None = Field(None, gt=0)
    j_peak: float | None = Field(None, gt=0)
    j_limit: float | None = Field(None, gt=0)
    j_peak_max: float | None = Field(None, gt=0)

    @model_validator(mode="after")
    def _fixed_iff_fixed(self):
        if (self.mode == "fixed") != (self.fixed is not None):
            raise ValueError("'fixed' is required when mode is 'fixed' and not allowed otherwise")
        return self


class DriveSection(_Section):
    bus_voltage_v: float = Field(gt=0)
    phase_current_a: float | None = Field(None, gt=0)


class SetupFile(BaseModel):
    # The JSON key is "schema"; the attribute is `schema_` because `schema` shadows `BaseModel.schema`.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["srm-setup"] = Field(alias="schema")
    version: Literal[1]
    requirements: Requirements | None = None
    search: SearchSettingsIn | None = None
    geometry: GeometrySection | None = None
    materials: RegionMaterials | None = None
    winding: WindingSection | None = None
    drive: DriveSection | None = None


class ImportCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: Literal["import"]
    setup: SetupFile


def setup_from_case(inputs: CaseInputs, label: str) -> SetupFile:
    """Every section but `search`. `label` is not stored: the file name carries it."""
    machine, req = inputs.design.machine, inputs.requirements
    fixed = None if inputs.winding == "auto" else inputs.winding
    return SetupFile(
        schema_="srm-setup", version=1, requirements=req,
        geometry=GeometrySection(machine=machine, preset=inputs.design.mesh.preset),
        materials=machine.materials,
        winding=WindingSection(mode="auto" if fixed is None else "fixed", fixed=fixed,
                               **{k: getattr(inputs, k) for k in LIMIT_FIELDS}),
        drive=DriveSection(bus_voltage_v=req.bus_voltage_v, phase_current_a=req.phase_current_a))


def case_inputs_from_setup(s: SetupFile) -> CaseInputs:
    """The case a setup file describes; `drive` overrides the requirements' bus voltage and phase current.
    Raises ValueError("missing sections: ...") when a section a case needs is absent."""
    missing = [name for name in SECTIONS if getattr(s, name) is None]
    if missing:
        raise ValueError(f"missing sections: {', '.join(missing)}")
    req, w = s.requirements, s.winding
    if s.drive is not None:
        update = {"bus_voltage_v": s.drive.bus_voltage_v}
        if s.drive.phase_current_a is not None:
            update["phase_current_a"] = s.drive.phase_current_a
        req = req.model_copy(update=update)
    machine = s.geometry.machine.model_copy(update={"materials": s.materials})
    return CaseInputs(
        requirements=req, design=Design(machine=machine, mesh=MeshSettings(preset=s.geometry.preset)),
        winding=w.fixed if w.mode == "fixed" else "auto", **{k: getattr(w, k) for k in LIMIT_FIELDS})


def setup_loc(loc: list) -> list:
    """A `check_case` loc (relative to the case inputs) as the path of the same value in a setup file."""
    if loc[:3] == ["design", "machine", "materials"]:
        return ["materials", *loc[3:]]
    if loc[:2] == ["design", "machine"]:
        return ["geometry", "machine", *loc[2:]]
    if len(loc) == 2 and loc[0] == "winding":
        return ["winding", "fixed", loc[1]]
    return loc
