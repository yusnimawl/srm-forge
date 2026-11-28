"""Requirements to scored candidates: generate, stage-1 filter, stage-2 evaluation, Pareto set (v0 spec §4)."""
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import numpy as np

from srmcore.materials.library import load_material
from srmcore.maps.validation import GRADE_ALLOWANCE, JS_STEP
from srmcore.model.design import RegionMaterials

from .limits import SEARCH_REQUIRES_PASS, frequency_limit, hard_limits
from .evaluate import Evaluation, StageTwoGrid, evaluate_stage2
from .pareto import pareto_mask
from .requirements import Requirements
from .sizing.estimates import J_PEAK, J_PEAK_SCREEN, J_SCREEN
from .sizing.generator import POLE_SETS, sample_candidates
from .sizing.stage1 import BOUND_SHARE, stage1

if TYPE_CHECKING:
    from .thermal_fields import ThermalFields


@dataclass(frozen=True)
class SearchSettings:
    n_candidates: int = 200
    seed: int = 0
    shortlist: int = 40
    grid: StageTwoGrid = field(default_factory=StageTwoGrid)
    materials: RegionMaterials = RegionMaterials(stator="10JNEX900", rotor="10JNEX900")
    margin: float | None = None     # feasible when the worst of torque and power ratio is at least this; None: by grade
    j_peak: float = J_PEAK          # A/m², peak current density that sets each design's I_max (density mode)
    j_limit: float = J_SCREEN       # A/m², wide RMS screen of the winding scan; the thermal rating is the real limit
    preset: Literal["screening", "full"] = "full"   # mesh and grid fidelity of every candidate
    j_peak_max: float | None = None  # A/m², peak conductor current density cap in wire mode; None: J_PEAK_SCREEN
    thermal: bool = True            # rate every feasible design (continuous and peak per speed)
    n_speeds: int = 6               # speeds per rating
    pole_sets: tuple[tuple[int, int, int], ...] = POLE_SETS   # (stator poles, rotor poles, phases)
    per_pole_set: int | None = None  # feasible evaluations per pole set; None: no cap

    @property
    def peak_cap(self) -> float:
        return J_PEAK_SCREEN if self.j_peak_max is None else self.j_peak_max

    @property
    def resolved_margin(self) -> float:
        """`margin`, or 1 + JS_STEP + the grade allowance of the worse of the stator and rotor B-H data
        (the material rows of the uncertainty budget): grade A 1.02, B 1.05, C 1.12."""
        if self.margin is not None:
            return self.margin
        worst = max(load_material(self.materials.stator).confidence, load_material(self.materials.rotor).confidence)
        return 1 + JS_STEP + GRADE_ALLOWANCE[worst]


PEAK_BAND_NOTE = ("peak kW/kg is a band from rated to nominal: the peak-heat check (V4) measured one 14 s "
                  "copper-dominated pulse, so the cooling paths and a 30 s peak from warm have no measured check "
                  "(confirm step on the winner)")
NOT_RATED_NOTE = ("no design is recommended: the feasible designs are not thermally rated (thermal is off, or no rating "
                  "could be made), and the recommendation ranks rated designs")
MAX_SAME_FAILURES = 3   # evaluations failing with one status before the search stops


@dataclass(frozen=True)
class SearchResult:
    requirements: Requirements
    sampled: int
    dropped: dict[str, int]
    stage1_rejected: int
    evaluations: tuple[Evaluation, ...]
    cancelled: bool
    limit_rejected: dict[str, int] = field(default_factory=dict)   # candidates failing each hard limit
    dropped_pole_sets: dict[str, str] = field(default_factory=dict)   # "ns/nr" -> reason, removed before sampling
    stopped: str = ""   # why the search stopped early on repeated failures; empty when it did not

    def recommended(self) -> tuple[Evaluation, ...]:
        """Feasible designs with finite rated values, lightest first (ties: higher rated continuous kW/kg first)."""
        ok = [e for e in self.evaluations if e.feasible and math.isfinite(e.rated_continuous_kw_per_kg)
              and math.isfinite(e.rated_peak_kw_per_kg)]
        return tuple(sorted(ok, key=lambda e: (e.mass_kg, -e.rated_continuous_kw_per_kg)))

    def margin_sensitive(self) -> tuple[Evaluation, ...]:
        """Evaluated designs lighter than the first recommended one that fail only the rated set: their nominal
        check holds and no hard limit fails."""
        rec = self.recommended()
        if not rec:
            return ()
        return tuple(e for e in self.evaluations if e.mass_kg < rec[0].mass_kg and not e.feasible
                     and e.nominal_check is not None and e.nominal_check.holds
                     and not any(lim.status == "fail" for lim in e.limits))

    @property
    def recommendation(self) -> Evaluation | None:
        """The first recommended design, unless a lighter evaluated design holds the nominal check."""
        rec = self.recommended()
        return rec[0] if rec and not self.margin_sensitive() else None

    @property
    def notes(self) -> tuple[str, ...]:
        if self.recommended():
            return (PEAK_BAND_NOTE,)
        if any(e.feasible and not math.isfinite(e.rated_continuous_kw_per_kg) for e in self.evaluations):
            return (NOT_RATED_NOTE,)
        return ()

    def pareto(self, maximize=(True, True)) -> tuple[Evaluation, ...]:
        """Non-dominated feasible designs over (rated continuous, rated peak) kW/kg; unrated designs are left out."""
        ok = [e for e in self.evaluations if e.feasible and math.isfinite(e.rated_continuous_kw_per_kg)
              and math.isfinite(e.rated_peak_kw_per_kg)]
        if not ok:
            return ()
        values = np.array([[e.rated_continuous_kw_per_kg, e.rated_peak_kw_per_kg] for e in ok])
        return tuple(e for e, keep in zip(ok, pareto_mask(values, maximize)) if keep)


def run_search(req: Requirements, settings: SearchSettings = SearchSettings(), *, solver: str = "ngsolve",
               workers: int | None = None, cache_dir=None,
               progress: Callable[[int, int], None] | None = None,
               point_progress: Callable[[int, int, int, int], None] | None = None,
               cancel: Callable[[], bool] | None = None,
               on_fields: "Callable[[str, ThermalFields], None] | None" = None) -> SearchResult:
    """`progress(done, total)` after each stage-2 design; `point_progress(design, designs, points_done, points)`
    while each design's map is built."""
    dropped_sets, pole_sets = {}, []
    for ns, nr, m in settings.pole_sets:
        lim = frequency_limit(nr, req)
        if lim.status == "fail":
            dropped_sets[f"{ns}/{nr}"] = lim.note
        else:
            pole_sets.append((ns, nr, m))
    candidates, dropped = sample_candidates(req, settings.n_candidates, seed=settings.seed, pole_sets=pole_sets,
                                           materials=settings.materials, preset=settings.preset)
    margin = settings.resolved_margin
    scored = [(c, stage1(req, c.design.machine, margin, settings.j_peak, settings.peak_cap))
              for c in candidates]
    passing, limit_rejected = [], {}
    for c, s in scored:
        if not s.passes:
            continue
        bad = [lim.name for lim in hard_limits(req, c.design.machine)
               if lim.status == "fail" or (lim.status == "not_run" and lim.name in SEARCH_REQUIRES_PASS)]
        for name in bad:
            limit_rejected[name] = limit_rejected.get(name, 0) + 1
        if not bad:
            passing.append((c, s))
    # Order only, nothing is dropped: likely designs first (the bound scaled by the measured share reaches the
    # required torque), each group lightest first, then round-robin over the pole sets.
    need = margin * req.peak_torque_nm
    queues: dict[tuple[int, int, int], list] = {}
    for cs in sorted(passing, key=lambda cs: (BOUND_SHARE * cs[1].torque_upper < need, cs[1].mass.total)):
        m = cs[0].design.machine
        queues.setdefault((m.n_stator_poles, m.n_rotor_poles, m.n_phases), []).append(cs)
    budget = min(settings.shortlist, len(passing))
    evaluations: list[Evaluation] = []
    feasible_in = dict.fromkeys(queues, 0)
    cancelled, stopped, failures = False, "", {}
    done = 0
    while done < budget and not (cancelled or stopped):
        live = [k for k, q in queues.items() if q and (settings.per_pole_set is None or feasible_in[k] < settings.per_pole_set)]
        if not live:
            break
        # lightest head first within a round
        for key in sorted(live, key=lambda k: queues[k][0][1].mass.total):
            if done == budget:
                break
            if cancel is not None and cancel():
                cancelled = True
                break
            candidate, stage = queues[key].pop(0)
            done += 1
            on_point = None if point_progress is None else (
                lambda d, t, i=done, n=budget: point_progress(i, n, d, t))
            evaluation = evaluate_stage2(candidate, req, stage, grid=settings.grid, j_peak=settings.j_peak,
                                         j_limit=settings.j_limit, j_peak_max=settings.peak_cap,
                                         margin=margin, solver=solver, workers=workers, scan_workers=workers,
                                         cache_dir=cache_dir, progress=on_point, cancel=cancel,
                                         thermal=settings.thermal, n_speeds=settings.n_speeds,
                                         fields_out=None if on_fields is None else (lambda f, c=candidate: on_fields(c.id, f)))
            if evaluation.status == "cancelled":
                cancelled = True
                break
            evaluations.append(evaluation)
            if evaluation.feasible:
                feasible_in[key] += 1
            if progress is not None:
                progress(done, budget)
            if evaluation.status not in ("ok", "no_winding"):
                failures[evaluation.status] = failures.get(evaluation.status, 0) + 1
                if failures[evaluation.status] == MAX_SAME_FAILURES:
                    stopped = (f"stopped after {MAX_SAME_FAILURES} evaluations failed with {evaluation.status}: "
                               f"{evaluation.error}")
                    break
    return SearchResult(req, len(candidates), dropped, len(scored) - len(passing), tuple(evaluations), cancelled, limit_rejected,
                        dropped_sets, stopped)
