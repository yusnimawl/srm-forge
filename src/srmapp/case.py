"""Inputs of one case: a design, its requirements and how it is wound and judged."""
from dataclasses import replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from srmcore.maps import EmValidation, build_map, em_validate
from srmcore.maps.dataset import provenance, provenance_hash
from srmcore.maps.grids import GRID_SIZES, aligned_angle, angle_grid, current_grid
from srmcore.mesh.settings import resolve_mesh_settings
from srmcore.model.design import Design
from srmcore.solvers.factory import make_solver

from .evaluate import Evaluation, StageTwoGrid, evaluate_stage2
from .pipeline import SearchSettings
from .requirements import Requirements
from .sizing.generator import REFERENCE_TURNS, Candidate
from .sizing.stage1 import Stage1, stage1
from .sizing.winding import Winding, fixed_winding


LIMIT_FIELDS = ("margin", "j_peak", "j_limit", "j_peak_max")   # optional SearchSettings limits a case may set


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
        optional = {k: v for k in LIMIT_FIELDS if (v := getattr(self, k)) is not None}
        return SearchSettings(materials=self.design.machine.materials, preset=self.design.mesh.preset, **optional)


def reference_design(inputs: CaseInputs) -> Design:
    """The design whose map serves every winding: `inputs.design` at REFERENCE_TURNS."""
    machine = inputs.design.machine.model_copy(update={"turns_per_pole": REFERENCE_TURNS})
    return inputs.design.model_copy(update={"machine": machine})


def _fixed(inputs: CaseInputs) -> Winding | None:
    """The user's winding, or None in Auto mode."""
    w = inputs.winding
    if w == "auto":
        return None
    return fixed_winding(inputs.design.machine, inputs.requirements, w.turns, w.strands, w.paths, w.wire,
                         inputs.search_settings().j_peak)


def map_request(inputs: CaseInputs) -> tuple[Design, float, Stage1]:
    """The reference design, the map's I_max at its turns and stage 1. A fixed winding's ampere-turns widen the
    range when it lies beyond what the search would allow. Raises ValueError when no winding fits (I_max 0)."""
    design = reference_design(inputs)
    s = inputs.search_settings()
    stage = stage1(inputs.requirements, design.machine, s.resolved_margin, s.j_peak, s.peak_cap)
    mmf = stage.mmf
    if (fixed := _fixed(inputs)) is not None:
        mmf = max(mmf, fixed.turns * fixed.coil_current)
    i_map = mmf / REFERENCE_TURNS
    if i_map <= 0:
        raise ValueError(stage.reason or "no winding fits")
    return design, i_map, stage


def evaluate_design(inputs: CaseInputs, *, case_id: str = "case", grid: StageTwoGrid = StageTwoGrid(),
                    solver: str = "ngsolve", workers: int | None = None, cache_dir=None, progress=None,
                    cancel=None, on_scan=None) -> Evaluation:
    """Stage 2 on this one design. A stage-1 rejection is a note ("stage 1: <reason>"), not a stop.
    `on_scan()` is called when the map is complete and the winding choice begins."""
    design, i_map, stage = map_request(inputs)
    s = inputs.search_settings()
    e = evaluate_stage2(Candidate(case_id, design), inputs.requirements, stage, grid=grid, j_peak=s.j_peak,
                        j_limit=s.j_limit, j_peak_max=s.peak_cap, margin=s.resolved_margin, solver=solver,
                        workers=workers, cache_dir=cache_dir, progress=progress, cancel=cancel,
                        only=_fixed(inputs), i_map=i_map, on_scan=on_scan)
    if stage.passes:
        return e
    note = f"stage 1: {stage.reason}"
    return replace(e, error=f"{note}; {e.error}" if e.error else note)


def validate_case(inputs: CaseInputs, *, solver: str = "ngsolve", workers: int | None = None,
                  cache_dir=None) -> EmValidation:
    """EM validation of the reference design's map (served from `cache_dir` after an evaluation)."""
    design, i_map, _ = map_request(inputs)
    result = build_map(design, i_map, solver=solver, workers=workers, cache_dir=cache_dir)
    return em_validate(design, result, solver=solver, workers=workers)


def map_cache_hit(inputs: CaseInputs, cache_dir, *, solver: str = "ngsolve") -> bool:
    """Whether `evaluate_design` finds its map in `cache_dir`. Mirrors the grids and provenance that
    `srmcore.maps.api.build_map` computes for a default grid and phase A."""
    design, i_map, _ = map_request(inputs)
    aligned = aligned_angle(design.machine, "A")
    n_angles, n_currents = GRID_SIZES[design.mesh.preset]
    divisions = resolve_mesh_settings(design.machine, design.mesh).band_divisions
    angles = angle_grid(design.machine, divisions, n_angles, aligned=aligned)
    prov = provenance(design, angles, current_grid(i_map, n_currents), "A", make_solver(solver))
    return Path(cache_dir, f"map_{provenance_hash(prov)}.h5").exists()
