"""Request models of the web API."""
from __future__ import annotations

import json
import math
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from srmapp.case import CaseInputs
from srmapp.references import REFERENCES
from srmapp.requirements import Requirements
from srmcore.materials.library import available_materials, load_material
from srmsil.hil.config import HilModes
from srmsil.scenario import Scenario


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


class AnimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    inputs: CaseInputs
    current_a: float = Field(gt=0)
    coil_current: float = Field(gt=0)
    k: float = Field(gt=0)
    frames: int = Field(36, ge=12, le=72)


class ValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    inputs: CaseInputs


class LossesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_speeds: int = Field(6, ge=2, le=12)
    n_torques: int = Field(5, ge=1, le=10)


class LossesRequest(LossesBody):
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
    margin: float | None = None   # the feasibility margin the inputs imply, when they parse


class EstimateOut(BaseModel):
    new_map: bool
    seconds: float      # a new map (when new_map) plus the winding choice
    basis: Literal["history", "budget"]


class LossesEstimateOut(BaseModel):
    solves: int          # field solves: operating points x stroke angles
    per_solve_s: float
    seconds: float
    basis: Literal["history", "budget"]


class CompareRowOut(BaseModel):
    name: str
    unit: str
    before: float | None
    after: float | None


class CompareOut(BaseModel):
    parent_id: str | None
    parent_evaluated: bool
    rows: list[CompareRowOut]


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
    lane: Literal["main", "quick"]
    queue_position: int | None = None
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


class AnimateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_a: float = Field(gt=0)
    frames: int = Field(36, ge=12, le=72)


class FieldIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    angle: float = Field(ge=0, lt=2 * math.pi)
    current_a: float = Field(gt=0)


class ControlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    controller: str   # a reference name or an absolute folder path
    scenario: Scenario = Scenario()


class MotorIn(BaseModel):
    """`srmsil.tables.MotorData` as JSON."""
    model_config = ConfigDict(extra="forbid")

    angles: list[float]
    currents: list[float]
    psi: list[list[float]]
    torque: list[list[float]]
    resistance: float
    n_phases: int
    n_rotor_poles: int
    bus_voltage: float


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    motor: MotorIn
    controller: str
    scenario: Scenario


class TargetCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    controller: str
    case_id: str


class TargetCheckOut(BaseModel):
    ok: bool
    compiler: str
    log: str


class ControllerParamOut(BaseModel):
    name: str
    unit: str
    default: str


class ControllerOut(BaseModel):
    name: str
    params: list[ControllerParamOut]


class HilFlashIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    controller: str   # a reference name or an absolute folder path
    scenario: Scenario = Scenario()
    modes: HilModes = HilModes()


class HilFlashRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    motor: MotorIn
    controller: str
    scenario: Scenario
    modes: HilModes


class HilOpenIn(HilFlashIn):
    case_id: str


class HilSessionOut(BaseModel):
    case_id: str
    controller: str
    modes: HilModes
    scenario: Scenario
    emulator_hash: int
    controller_hash: int
    running: bool


class HilParamIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=23)
    value: float = Field(allow_inf_nan=False)


class HilParamOut(BaseModel):
    status: int                 # ctrl_param's return: 0 accepted, -1 unknown, -2 not changeable while running
    message: str | None = None


class HilCommandIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["torque", "speed"]
    value: float = Field(allow_inf_nan=False)   # N*m or rpm


class HilFlashResultOut(BaseModel):
    """The result of a finished `hil_flash` job: the end of the PlatformIO log of the upload."""
    case_id: str
    controller: str
    modes: HilModes
    firmware_hash: int
    log: str


class HilCaptureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_steps: int = Field(ge=100, le=200_000)    # emulator steps (srmsil.hil.proto.EMU_DT each)


class HilCaptureOut(BaseModel):
    capture_id: str
    valid: bool
    reason: str
    clipped: float


class ComparisonOut(BaseModel):
    """`srmsil.hil.compare.Comparison`; a difference is None when it is not finite."""
    d_torque_pct: float | None
    d_irms_pct: float | None
    d_ripple_pts: float | None
    passed: bool
    clock_ratio: float | None
    clock_measured: bool
    reason: str
