"""Requirements to scored candidates: generate, stage-1 filter, stage-2 evaluation, Pareto set (v0 spec §4)."""
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from srmcore.materials.library import load_material
from srmcore.maps.validation import GRADE_ALLOWANCE, JS_STEP
from srmcore.model.design import RegionMaterials

from .evaluate import Evaluation, StageTwoGrid, evaluate_stage2
from .pareto import pareto_mask
from .requirements import Requirements
from .sizing.estimates import J_LIMIT, J_PEAK
from .sizing.generator import sample_candidates
from .sizing.stage1 import stage1


@dataclass(frozen=True)
class SearchSettings:
    n_candidates: int = 200
    seed: int = 0
    shortlist: int = 40
    grid: StageTwoGrid = field(default_factory=StageTwoGrid)
    materials: RegionMaterials = RegionMaterials(stator="10JNEX900", rotor="10JNEX900")
    margin: float | None = None     # feasible when the worst of torque and power ratio is at least this; None: by grade
    j_peak: float = J_PEAK          # A/m², peak current density that sets each design's I_max (density mode)
    j_limit: float = J_LIMIT        # A/m², cooling limit on the conductor RMS current density
    preset: Literal["screening", "full"] = "full"   # mesh and grid fidelity of every candidate
    j_peak_max: float | None = None  # A/m², peak conductor current density cap in wire mode; None is 2 x j_limit

    @property
    def peak_cap(self) -> float:
        return 2 * self.j_limit if self.j_peak_max is None else self.j_peak_max

    @property
    def resolved_margin(self) -> float:
        """`margin`, or 1 + JS_STEP + the grade allowance of the worse of the stator and rotor B-H data
        (the material rows of the uncertainty budget): grade A 1.02, B 1.05, C 1.12."""
        if self.margin is not None:
            return self.margin
        worst = max(load_material(self.materials.stator).confidence, load_material(self.materials.rotor).confidence)
        return 1 + JS_STEP + GRADE_ALLOWANCE[worst]


@dataclass(frozen=True)
class SearchResult:
    requirements: Requirements
    sampled: int
    dropped: dict[str, int]
    stage1_rejected: int
    evaluations: tuple[Evaluation, ...]
    cancelled: bool

    def pareto(self, maximize=(False, True, True)) -> tuple[Evaluation, ...]:
        """Non-dominated feasible designs over (mass, power density, copper-only efficiency at base speed)."""
        ok = [e for e in self.evaluations if e.feasible]
        if not ok:
            return ()
        values = np.array([[e.mass_kg, e.power_density_kw_per_kg, e.efficiency_base] for e in ok])
        return tuple(e for e, keep in zip(ok, pareto_mask(values, maximize)) if keep)


def run_search(req: Requirements, settings: SearchSettings = SearchSettings(), *, solver: str = "ngsolve",
               workers: int | None = None, cache_dir=None,
               progress: Callable[[int, int], None] | None = None,
               point_progress: Callable[[int, int, int, int], None] | None = None,
               cancel: Callable[[], bool] | None = None) -> SearchResult:
    """`progress(done, total)` after each stage-2 design; `point_progress(design, designs, points_done, points)`
    while each design's map is built."""
    candidates, dropped = sample_candidates(req, settings.n_candidates, seed=settings.seed,
                                           materials=settings.materials, preset=settings.preset)
    margin = settings.resolved_margin
    scored = [(c, stage1(req, c.design.machine, margin, settings.j_peak, settings.peak_cap))
              for c in candidates]
    passing = [(c, s) for c, s in scored if s.passes]
    passing.sort(key=lambda cs: cs[1].torque_upper / cs[1].mass.iron, reverse=True)
    shortlist = passing[:settings.shortlist]
    evaluations: list[Evaluation] = []
    cancelled = False
    for done, (candidate, stage) in enumerate(shortlist, start=1):
        if cancel is not None and cancel():
            cancelled = True
            break
        on_point = None if point_progress is None else (
            lambda d, t, i=done, n=len(shortlist): point_progress(i, n, d, t))
        evaluation = evaluate_stage2(candidate, req, stage, grid=settings.grid, j_peak=settings.j_peak,
                                     j_limit=settings.j_limit, j_peak_max=settings.peak_cap,
                                     margin=margin, solver=solver, workers=workers,
                                     cache_dir=cache_dir, progress=on_point, cancel=cancel)
        if evaluation.status == "cancelled":
            cancelled = True
            break
        evaluations.append(evaluation)
        if progress is not None:
            progress(done, len(shortlist))
    return SearchResult(req, len(candidates), dropped, len(scored) - len(passing), tuple(evaluations), cancelled)
