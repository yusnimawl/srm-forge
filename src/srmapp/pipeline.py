"""Requirements to scored candidates: generate, stage-1 filter, stage-2 evaluation, Pareto set (v0 spec §4)."""
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

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
    margin: float = 1.0
    j_peak: float = J_PEAK          # A/m², peak current density that sets each design's I_max
    j_limit: float = J_LIMIT        # A/m², cooling limit on the conductor current density (wire mode)


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
               cancel: Callable[[], bool] | None = None) -> SearchResult:
    candidates, dropped = sample_candidates(req, settings.n_candidates, seed=settings.seed)
    scored = [(c, stage1(req, c.design.machine, settings.margin, settings.j_peak, settings.j_limit)) for c in candidates]
    passing = [(c, s) for c, s in scored if s.passes]
    passing.sort(key=lambda cs: cs[1].torque_upper / cs[1].mass.iron, reverse=True)
    shortlist = passing[:settings.shortlist]
    evaluations: list[Evaluation] = []
    cancelled = False
    for done, (candidate, stage) in enumerate(shortlist, start=1):
        if cancel is not None and cancel():
            cancelled = True
            break
        evaluation = evaluate_stage2(candidate, req, stage, grid=settings.grid, solver=solver, workers=workers,
                                     cache_dir=cache_dir, cancel=cancel)
        if evaluation.status == "cancelled":
            cancelled = True
            break
        evaluations.append(evaluation)
        if progress is not None:
            progress(done, len(shortlist))
    return SearchResult(req, len(candidates), dropped, len(scored) - len(passing), tuple(evaluations), cancelled)
