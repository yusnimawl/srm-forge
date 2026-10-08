"""Request models of the web API."""
from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from srmapp.case import CaseInputs
from srmapp.references import REFERENCES
from srmapp.requirements import Requirements
from srmcore.materials.library import available_materials, load_material


def soft_magnetic(name: str) -> str:
    """`name` when it is a soft-magnetic library material; ValueError otherwise."""
    if name not in available_materials():
        raise ValueError(f"unknown material {name!r}; available: {', '.join(available_materials())}")
    if load_material(name).kind != "soft_magnetic":
        raise ValueError(f"{name!r} is not a soft-magnetic material")
    return name


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
        return soft_magnetic(name)


Grid = tuple[Annotated[int, Field(ge=2, le=200)], Annotated[int, Field(ge=2, le=200)]]   # (angles, currents)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: Requirements
    settings: SearchSettingsIn = SearchSettingsIn()
    grid: Grid | None = None   # overrides the preset grid, for tests


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    inputs: CaseInputs
    grid: Grid | None = None


class ValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    inputs: CaseInputs


class EvaluateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid: Grid | None = None


class ValidateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: Any


class IssueOut(BaseModel):
    loc: list[str | int]
    msg: str


class IssuesOut(BaseModel):
    errors: list[IssueOut]
    warnings: list[IssueOut]


class EstimateOut(BaseModel):
    new_map: bool
    seconds: float | None = None
    basis: Literal["history", "budget"] | None = None


class JobCreated(BaseModel):
    job_id: str


class SearchJobIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["search"]
    payload: SearchRequest


class EvaluateJobIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["evaluate"]
    payload: EvaluateRequest


class ValidateJobIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["validate"]
    payload: ValidateRequest


JobIn = Annotated[SearchJobIn | EvaluateJobIn | ValidateJobIn, Field(discriminator="kind")]


class JobOut(BaseModel):
    id: str
    kind: str
    status: str
    active: bool
    resumable: bool
    case_id: str | None = None
    progress: dict | None = None
    error: str | None = None
    created: str
    started: str | None = None
    finished: str | None = None


class CandidateCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: Literal["candidate"]
    job_id: str
    candidate_id: str


class ReferenceCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: Literal["reference"]
    name: Literal[tuple(REFERENCES)]    # type: ignore[valid-type]
    requirements: Requirements
    preset: Literal["screening", "full"] = "full"


class EditCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: Literal["edit"]
    parent_case_id: str
    inputs: CaseInputs


CaseCreate = Annotated[CandidateCase | ReferenceCase | EditCase, Field(discriminator="origin")]


class CasePatch(BaseModel):
    """Fields left out (or null) stay as they are; `flag` is cleared with an empty string."""
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(None, max_length=120)
    flag: str | None = Field(None, max_length=40)
    comment: str | None = Field(None, max_length=2000)
    show_in_graphs: bool | None = None
    inputs: dict[str, Any] | None = None    # a draft's inputs, stored as sent; Evaluate validates them

    @field_validator("inputs")
    @classmethod
    def _strict_json(cls, inputs):
        if inputs is not None:
            json.dumps(inputs, allow_nan=False)
        return inputs
