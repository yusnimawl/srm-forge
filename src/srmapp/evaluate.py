"""Stage 2: FEM map of one candidate at its reference turns, then the winding chosen on the rescaled map and its
drive envelope and scores (v0 spec §4.4-4.6, v0a-2 spec §3). Peak-only and unvalidated: no losses beyond copper,
no thermal limit. Parallel paths and the RMS current-density limit: small-cycle spec."""
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from srmcore.maps import build_map
from srmcore.maps.results import KeyNumbers, key_numbers
from srmcore.model.design import Design

from .drive.envelope import Envelope
from .requirements import Requirements
from .sizing.estimates import J_LIMIT, J_PEAK, coil_side_area
from .sizing.generator import Candidate
from .sizing.stage1 import Stage1
from .sizing.winding import DENSITY_MAX_TURNS, Winding
from .turns import ScanPoint, choose_turns, requirement_ratios, rescale_turns, speed_grid, turns_scale  # noqa: F401

_NAN = float("nan")


@dataclass(frozen=True)
class StageTwoGrid:
    """Map grid; None takes the design's preset grid (30 x 20 for `full`)."""
    n_angles: int | None = None
    n_currents: int | None = None


@dataclass(frozen=True)
class Evaluation:
    id: str
    design: Design              # with the chosen turns per pole and copper fill once a winding is chosen
    status: str                 # "ok", "cancelled", "no_winding", or the name of the exception that stopped it
    error: str                  # failure message; with status "ok", notes such as a scan at its limit or a mass over the limit
    mass_kg: float              # iron plus the chosen winding's copper; iron only without a winding
    winding: Winding | None
    torque_ratio: float         # achieved / required, at base speed
    power_ratio: float          # achieved / required, worst over base..max speed
    peak_power_w: float
    power_density_kw_per_kg: float
    efficiency_base: float      # copper-only, at base speed
    feasible: bool
    envelope: Envelope | None
    key: KeyNumbers | None      # of the map at the chosen turns
    scan: tuple[ScanPoint, ...] = ()
    i_rms_a: float = _NAN       # A, worst phase RMS current over the speed grid, chosen winding
    j_rms: float = _NAN         # A/m², conductor RMS current density at i_rms_a


def _failed(candidate: Candidate, stage: Stage1, status: str, error: str) -> Evaluation:
    return Evaluation(candidate.id, candidate.design, status, error, stage.mass.iron, None,
                      _NAN, _NAN, _NAN, _NAN, _NAN, False, None, None)


def evaluate_stage2(candidate: Candidate, req: Requirements, stage: Stage1, *, grid: StageTwoGrid = StageTwoGrid(),
                    j_peak: float = J_PEAK, j_limit: float = J_LIMIT,
                    j_peak_max: float | None = None, margin: float = 1.0, max_turns: int = DENSITY_MAX_TURNS,
                    solver: str = "ngsolve", workers: int | None = None, cache_dir=None,
                    progress: Callable[[int, int], None] | None = None,
                    cancel: Callable[[], bool] | None = None) -> Evaluation:
    design = candidate.design
    machine = design.machine
    try:
        result = build_map(design, stage.i_map, solver=solver, workers=workers, n_angles=grid.n_angles,
                           n_currents=grid.n_currents, cache_dir=cache_dir, progress=progress, cancel=cancel)
    except Exception as exc:  # batch boundary: one bad design must not lose the search (not BaseException)
        return _failed(candidate, stage, type(exc).__name__, str(exc))
    if not result.complete:
        return _failed(candidate, stage, "cancelled", "map cancelled")
    cap = stage.j_peak_max if j_peak_max is None else j_peak_max
    choice = choose_turns(result, machine, req, j_peak=j_peak, j_limit=j_limit, j_peak_max=cap,
                          margin=margin, max_turns=max_turns)
    if choice.point is None:
        cap_text = f" (j_peak_max {cap / 1e6:.0f} A/mm2)" if req.wire_mode else ""
        return _failed(candidate, stage, "no_winding",
                       f"no turn count meets the wire, phase current and current-density limits{cap_text}")
    w, env = choice.point.winding, choice.envelope
    chosen = machine.model_copy(update={"turns_per_pole": w.turns,
                                        "fill_factor": w.turns * w.copper_area / coil_side_area(machine)})
    mass = stage.mass.iron + w.copper_mass
    peak_power = float(np.max(env.power))
    at_base = int(np.argmin(np.abs(env.speeds_rpm - req.base_speed_rpm)))
    key = key_numbers(rescale_turns(result, turns_scale(machine, w)), chosen)
    i_rms = float(np.max(env.i_rms))
    notes = []
    if not req.wire_mode and w.turns / w.paths >= max_turns:
        notes.append(f"turn scan reached its limit of {max_turns}; more turns may also be feasible")
    if not choice.feasible and choice.capped:
        notes.append("no winding is feasible and j_peak_max left out windings that fit the slot; "
                     "a higher cap might allow one")
    over_mass = req.max_mass_kg is not None and mass > req.max_mass_kg
    if over_mass:
        notes.append(f"mass {mass:.2f} kg above the {req.max_mass_kg:.2f} kg limit")
    return Evaluation(candidate.id, design.model_copy(update={"machine": chosen}), "ok", "; ".join(notes), mass, w,
                      choice.point.torque_ratio, choice.point.power_ratio, peak_power, peak_power / 1000 / mass,
                      float(env.efficiency[at_base]), choice.feasible and not over_mass, env, key, choice.scan,
                      i_rms, i_rms / (w.paths * w.copper_area))
