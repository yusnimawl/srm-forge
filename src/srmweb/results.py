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


class SpeedDetailOut(_Out):
    envelope_nm: F = None
    continuous_nm: F = None
    peak_nm: F = None
    hot_spot_c: F = None
    hot_spot_at: str = ""
    peak_hot_spot_c: F = None
    peak_hot_spot_at: str = ""
    rotor_c: F = None
    rotor_peak_c: F = None
    bore_c: F = None
    bore_peak_c: F = None
    start_nm: F = None
    note: str = ""


class SpeedRatingOut(_Out):
    rpm: F
    nominal_continuous_nm: F
    nominal_peak_nm: F
    rated_continuous_nm: F
    rated_peak_nm: F
    hot_spot_c: F          # at the rated continuous torque
    hot_spot_at: str
    peak_hot_spot_c: F
    peak_hot_spot_at: str
    nominal: SpeedDetailOut | None = None
    rated: SpeedDetailOut | None = None


class BudgetShareOut(_Out):
    row: str
    rpm: F
    hot_spot_rise_k: F


class GapCaseOut(_Out):
    centrifugal: F = None
    rotor_thermal: F = None
    stator_thermal: F = None
    closure: F = None
    note: str = ""


class GapOut(_Out):
    cases: dict[str, GapCaseOut] = {}
    air_gap_m: F = None


class StressOut(_Out):
    status: str
    safety_factor: F = None
    governing: str | None = None
    speed_limit_rpm: F = None
    check_speed_rpm: F = None
    note: str = ""


class CoolingOut(_Out):
    kind: str
    placeholder: bool
    ambient_c: F = None
    housing_thickness: F = None
    jacket: dict[str, Any] | None = None
    end_spray: dict[str, Any] | None = None
    shaft_oil: dict[str, Any] | None = None
    slot_oil: dict[str, Any] | None = None


class RatingOut(_Out):
    speeds: list[SpeedRatingOut]
    limit_c: F
    insulation_class: str
    stress_status: str
    stress_safety_factor: F
    notes: list[str]
    shares: list[BudgetShareOut] = []
    gap: GapOut | None = None
    stress: StressOut | None = None
    torque_factor: F = None
    cooling: CoolingOut | None = None
    srmapp_version: str | None = None


class ThermalCheckOut(_Out):
    holds: bool
    rpm: F = None
    continuous_hot_c: Vec = []
    peak_hot_c: Vec = []
    notes: list[str] = []
    reason: str = ""
    which: str = ""
    hot_c: F = None


class VerdictOut(_Out):
    holds: bool | None = None
    rpm: F = None
    margin_pct: F = None
    which: str | None = None
    binds: str | None = None
    hot_spot_c: F = None
    hot_spot_at: str | None = None
    reason: str | None = None
    text: str = ""


class ThermalSpeedOut(_Out):
    rpm: F
    need_continuous_nm: F = None
    need_peak_nm: F = None
    binds_continuous: str = ""
    binds_peak: str = ""
    hot_spot_text: str = ""
    headroom_k: F = None


class ThermalSummaryOut(_Out):
    verdict: VerdictOut
    speeds: list[ThermalSpeedOut] = []
    least_margin_rpm: F = None
    iron_band: Vec | None = None


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
    j_limit: F = None
    srmapp_version: str | None = None   # null for evaluations stored before it was recorded
    rating: RatingOut | None = None   # null when not rated and for evaluations stored before ratings
    rated_continuous_kw_per_kg: F = None
    rated_peak_kw_per_kg: F = None
    srmcore_version: str | None = None
    thermal_check: ThermalCheckOut | None = None
    thermal_summary: ThermalSummaryOut | None = None
    thermal_fields: str | None = None   # key of the temperature-field file; null when not rated and before R5d
    active_volume_l: F = None
    rated_continuous_kw_per_l: F = None
    rated_peak_kw_per_l: F = None
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


class RegionLossOut(_Out):
    hysteresis: F
    classical: F
    excess: F


class OperatingLossOut(_Out):
    speed_rpm: F
    torque_nm: F
    reached: bool
    power_w: F
    copper_dc_w: F
    copper_ac_w: F
    iron: dict[str, RegionLossOut]
    iron_w: F
    efficiency: F
    iron_uncertainty_rel: F
    beyond_fit_range: bool
    theta_on: F
    theta_off: F
    current_limit: F
    stroke_key: str
    cut_edge_rel: tuple[F, F] | None = None
    cut_edge_factor: dict[str, F] | None = None
    windage_w: F = None             # None for results made before friction and windage were added
    friction_w: F = None
    mechanical_rel: tuple[F, F] | None = None


class FindingOut(_Out):
    id: str
    level: Literal["warn", "note", "ok", "missing"]
    topic: str
    text: str
    value: F = None
    unit: str = ""


class ReportOut(_Out):
    findings: list[FindingOut]
    versions: dict[str, str]
    generated: str
    animation_job_id: str | None = None
    animation_current_a: F = None


class LossesOut(_Out):
    points: list[OperatingLossOut]
    speeds_rpm: Vec
    torque_fractions: Vec
    winding_temperature_c: F
    n_angles: int
    angle_convergence_rel: F
    srmapp_version: str
    notes: list[str]
    cut_process: str | None = None
    bearing_placeholder: bool | None = None


class BWaveformOut(_Out):
    t: Vec
    b_r: Vec
    b_t: Vec
    region: str
    side: Literal["stator", "rotor"]


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


class DxfImportOut(_Out):
    case: CaseOut
    warnings: list[dict[str, Any]]      # `{"loc", "msg"}`
