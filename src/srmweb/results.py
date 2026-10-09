"""Response models of the web API. Every float is `float | None` because NaN and inf arrive as null."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from srmapp.references import REFERENCES
from srmapp.requirements import Requirements
from srmapp.sizing.generator import REFERENCE_TURNS
from srmcore.model.design import Design, RadialSRMParams
from srmweb.schemas import JobOut

F = float | None
Vec = list[F]
Mat = list[list[F]]


class _Out(BaseModel):
    model_config = ConfigDict(extra="ignore")


class WindingOut(_Out):
    turns: int
    strands: int
    copper_area: F
    current: F
    resistance: F
    copper_mass: F
    wire: int | None = None
    paths: int = 1


class KeyNumbersOut(_Out):
    la: F
    lu: F
    la_lu: F
    peak_torque: F
    psi_max: F
    i_max: F
    aligned_angle: F
    unaligned_angle: F


class WaveformsOut(_Out):
    theta: Vec
    theta_el: Vec
    current: Mat
    psi: Mat
    voltage: Mat
    torque: Mat
    line: Mat


class EnvelopeOut(_Out):
    speeds_rpm: Vec
    torque: Vec
    power: Vec
    copper_loss: Vec
    theta_on: Vec
    theta_off: Vec
    work_torque: Vec
    work_loop: Vec
    i_rms: Vec
    theta_on_el: Vec
    theta_off_el: Vec
    efficiency: Vec
    line_mean: Vec | None = None
    line_rms: Vec | None = None
    power_factor: Vec | None = None
    waveforms: WaveformsOut | None = None


class MapArraysOut(_Out):
    angles: Vec
    currents: Vec
    psi: Mat
    torque: Mat


class MapCurvesOut(_Out):
    currents: Vec
    inductance: Mat
    la_sat: Vec
    lu: Vec
    la_unsat: F
    k2: Vec
    b_sp: Vec
    b_sp_k2: Vec
    la_lu: Vec


class ScanPointOut(_Out):
    winding: WindingOut
    torque_ratio: F
    power_ratio: F
    i_rms: F
    feasible: bool


class EvaluationOut(_Out):
    id: str
    design: Design
    status: str
    error: str
    mass_kg: F
    winding: WindingOut | None
    torque_ratio: F
    power_ratio: F
    peak_power_w: F
    power_density_kw_per_kg: F
    efficiency_base: F
    feasible: bool
    envelope: EnvelopeOut | None
    key: KeyNumbersOut | None
    scan: list[ScanPointOut] = []
    i_rms_a: F = None
    j_rms: F = None
    map: MapArraysOut | None = None
    curves: MapCurvesOut | None = None


class SearchResultOut(_Out):
    requirements: Requirements
    sampled: int
    dropped: dict[str, int]
    stage1_rejected: int
    cancelled: bool
    evaluations: list[EvaluationOut]
    pareto_ids: list[str]


class CheckOut(_Out):
    name: str
    status: str
    value: F
    limit: F
    detail: str


class BudgetRowOut(_Out):
    source: str
    rel: dict[str, F]
    note: str


class BudgetOut(_Out):
    values_2d: dict[str, F]
    values: dict[str, F]
    rows: list[BudgetRowOut]
    total: dict[str, F]


class ValidationOut(_Out):
    label: str | None
    checks: list[CheckOut]
    budget: BudgetOut
    engine_version: str
    material_grades: dict[str, str]
    reference_turns: int = REFERENCE_TURNS   # the turns per pole its absolute key numbers refer to


class MaterialOut(_Out):
    name: str
    grade: str
    thickness_mm: F
    js: F


class ReferenceOut(_Out):
    name: Literal[tuple(REFERENCES)]    # type: ignore[valid-type]
    machine: RadialSRMParams


class CaseSummaryOut(_Out):
    id: str
    label: str | None
    origin: str
    parent_case_id: str | None
    flag: str | None
    comment: str | None
    show_in_graphs: bool
    stale: bool
    created: str
    preset: str | None          # null when the (draft) inputs lack it
    poles: str | None           # "8/6"; null when the (draft) inputs lack them
    status: str | None          # of the newest evaluation
    torque_ratio: F
    power_ratio: F
    peak_power_w: F
    mass_kg: F
    power_density_kw_per_kg: F
    efficiency_base: F
    feasible: bool | None
    validated: bool


class CaseOut(CaseSummaryOut):
    inputs: dict[str, Any]      # a draft may hold inputs that do not validate; read as `CaseInputs`
    evaluation: EvaluationOut | None
    validation: ValidationOut | None
    jobs: list[JobOut]          # newest first
