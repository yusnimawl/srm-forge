"""Stage 2: FEM map of one candidate at its reference turns, then the winding chosen on the rescaled map and its
drive envelope and scores (v0 spec §4.4-4.6, v0a-2 spec §3), and, with `thermal`, the winding checked against the
rated hot-spot limit and rated. Unvalidated. ψ includes the analytic end-winding inductance. Parallel paths and
the RMS current-density limit: small-cycle spec."""
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

import srmcore
from srmcore.maps import build_map
from srmcore.maps.end_winding import end_winding_inductance, with_end_winding
from srmcore.maps.results import KeyNumbers, key_numbers
from srmcore.model.design import Design

from . import __version__
from .curves import MapCurves, map_curves
from .drive.envelope import Envelope
from .requirements import Requirements
from .sizing.estimates import active_volume, J_LIMIT, J_PEAK, J_PEAK_SCREEN, coil_side_area, peak_cap_text
from .sizing.generator import Candidate
from .sizing.stage1 import Stage1
from .sizing.winding import DENSITY_MAX_TURNS, Winding
from .turns import _envelope, ScanCancelled, ScanPoint, choose_turns, requirement_ratios, rescale_turns, speed_grid, turns_scale  # noqa: F401

if TYPE_CHECKING:
    from .thermal import Rating, RequirementCheck
    from .thermal_fields import ThermalFields

_NAN = float("nan")
NOT_RATED = "not thermally rated"
END_IMAGE_FACTOR = 1.5    # midpoint of the free-air (1) and iron-image (2) end-winding bounds
MAX_THERMAL_CHECKS = 4    # ranked windings checked against the rated hot-spot limit per design, best first


@dataclass(frozen=True)
class StageTwoGrid:
    """Map grid; None takes the design's preset grid (`GRID_SIZES`, 48 x 20 for `full`)."""
    n_angles: int | None = None
    n_currents: int | None = None


@dataclass(frozen=True)
class MapArrays:
    """The map at the chosen turns, end winding included: ψ of the excited circuit only (Wb-turns) and Arkkio
    torque (N·m), both (n_angles, n_currents)."""
    angles: np.ndarray
    currents: np.ndarray
    psi: np.ndarray
    torque: np.ndarray


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
    map: MapArrays | None = None  # set with status "ok"
    curves: MapCurves | None = None  # set with status "ok"
    j_limit: float = J_LIMIT    # A/m², the RMS current-density limit the winding choice used
    srmapp_version: str = __version__   # the version that made the evaluation
    rating: "Rating | None" = None      # the chosen winding's thermal rating; None when not rated
    rated_continuous_kw_per_kg: float = _NAN   # lowest rated continuous power over base..max speed / mass
    rated_peak_kw_per_kg: float = _NAN         # the same for the rated peak
    srmcore_version: str = srmcore.__version__
    thermal_check: "RequirementCheck | None" = None   # the chosen winding's check; the first failing one when none holds
    active_volume_l: float = _NAN              # litres, stator outer cylinder with the end windings (`active_volume`)
    rated_continuous_kw_per_l: float = _NAN    # as rated_continuous_kw_per_kg, per litre
    rated_peak_kw_per_l: float = _NAN


def _failed(candidate: Candidate, stage: Stage1, status: str, error: str, j_limit: float) -> Evaluation:
    return Evaluation(candidate.id, candidate.design, status, error, stage.mass.iron, None,
                      _NAN, _NAN, _NAN, _NAN, _NAN, False, None, None, j_limit=j_limit)


def _rated_kw_per_kg(rating, req: Requirements, field: str, mass: float) -> float:
    """Lowest rated power (kW per `mass` unit: kg, or litres) over the rating speeds from the base speed up."""
    if rating is None:
        return _NAN
    return min(getattr(r, field) * r.rpm * 2 * math.pi / 60 for r in rating.rated if r.rpm >= req.base_speed_rpm) / 1000 / mass


def evaluate_stage2(candidate: Candidate, req: Requirements, stage: Stage1, *, grid: StageTwoGrid = StageTwoGrid(),
                    j_peak: float = J_PEAK, j_limit: float = J_LIMIT,
                    j_peak_max: float | None = None, margin: float = 1.0, max_turns: int = DENSITY_MAX_TURNS,
                    solver: str = "ngsolve", workers: int | None = None, cache_dir=None,
                    progress: Callable[[int, int], None] | None = None,
                    cancel: Callable[[], bool] | None = None, only: Winding | None = None,
                    i_map: float | None = None, on_scan: Callable[[], None] | None = None,
                    scan_workers: int | None = 1,
                    scan_progress: Callable[[int, int], None] | None = None, thermal: bool = True, n_speeds: int = 6,
                    thermal_progress: Callable[[str, int, int], None] | None = None, rate_failed: bool = False,
                    fields_out: "Callable[[ThermalFields], None] | None" = None) -> Evaluation:
    """`only` evaluates that one winding instead of scanning; `i_map` replaces `stage.i_map` as the map's I_max;
    `on_scan` is called once the map is complete (built or cached), before the winding is chosen. The winding scan
    runs on `scan_workers` processes (None: half the logical CPUs) and reports `scan_progress(done, total)`;
    `cancel` also stops it, with status "cancelled". With `thermal`, up to `MAX_THERMAL_CHECKS` EM-feasible windings
    are checked best-first against the rated hot-spot limit; the first that holds is chosen and rated in full
    (`thermal_progress(step, done, total)`: "windings", "strokes", "thermal"). None holding leaves the best EM winding,
    infeasible; with `rate_failed` that best winding is rated in full anyway. `fields_out` receives the temperature
    fields of every rating made. A refusal (no loss or thermal data) keeps the EM choice, unrated; any later error fails the evaluation."""
    design = candidate.design
    machine = design.machine
    try:
        result = build_map(design, stage.i_map if i_map is None else i_map, solver=solver, workers=workers, n_angles=grid.n_angles,
                           n_currents=grid.n_currents, cache_dir=cache_dir, progress=progress, cancel=cancel)
    except Exception as exc:  # batch boundary: one bad design must not lose the search (not BaseException)
        return _failed(candidate, stage, type(exc).__name__, str(exc), j_limit)
    if not result.complete:
        return _failed(candidate, stage, "cancelled", "map cancelled", j_limit)
    if on_scan is not None:
        on_scan()
    # L_end scales with turns², so the correction at the reference turns stays exact under rescale_turns.
    l_end = end_winding_inductance(machine, image_factor=END_IMAGE_FACTOR)
    result = with_end_winding(result, l_end)
    cap = stage.j_peak_max if j_peak_max is None else j_peak_max
    try:
        choice = choose_turns(result, machine, req, j_peak=j_peak, j_limit=j_limit, j_peak_max=cap,
                              margin=margin, max_turns=max_turns, only=only, workers=scan_workers,
                              progress=scan_progress, cancel=cancel)
    except ScanCancelled:
        return _failed(candidate, stage, "cancelled", "winding scan cancelled", j_limit)
    if choice.point is None:
        cap_text = f" ({peak_cap_text(cap)})" if req.wire_mode and math.isfinite(cap) else ""
        return _failed(candidate, stage, "no_winding",
                       f"no turn count meets the wire, phase current and current-density limits{cap_text}", j_limit)
    point, env, feasible, rating, held = choice.point, choice.envelope, choice.feasible, None, None
    notes = []
    if not thermal:
        notes.append(NOT_RATED)
    elif not choice.ranked:
        notes.append(f"no winding is EM-feasible; {NOT_RATED}")
    else:
        from . import thermal as th   # thermal imports this module
        from .cooling import TORQUE_FLOOR
        # The rated set asks for (1 + TORQUE_FLOOR) x the required torque (no em_budget here), so a winding whose EM
        # ratio is below that can hardly hold; check those last (stable sort: best-first inside each group).
        checks = sorted(choice.ranked, key=lambda s: s.worst < 1.0 + TORQUE_FLOOR)[:MAX_THERMAL_CHECKS]

        def context(cand):
            return th.thermal_context(req, design, result, cand.winding, solver=solver, workers=workers,
                                      cache_dir=cache_dir, cancel=cancel, progress=thermal_progress)
        refused = False
        try:
            ctx = context(checks[0])
        except InterruptedError:
            return _failed(candidate, stage, "cancelled", "thermal check cancelled", j_limit)
        except ValueError as exc:   # refusals (MissingLossData, MissingCoolingData, no thermal data) come before any solve
            notes.append(f"{exc}; {NOT_RATED}")
            refused = True
        if not refused:
            try:
                first = None
                for done, cand in enumerate(checks):
                    if done:
                        ctx = context(cand)
                    check = th.check_requirement(ctx, n_speeds)
                    if check.holds:
                        held = check
                        point, rating = cand, th.rate_context(ctx, n_speeds=n_speeds, progress=thermal_progress,
                                                           fields_out=fields_out)
                        env = _envelope(result, machine, req, cand.winding, speed_grid(req), j_limit)
                        break
                    first = first or check
                    if thermal_progress is not None:
                        thermal_progress("windings", done + 1, len(checks))
                    if cancel is not None and cancel():
                        return _failed(candidate, stage, "cancelled", "thermal check cancelled", j_limit)
                else:
                    feasible, held, point = False, first, checks[0]   # the winding the note and a failed rating describe
                    env = _envelope(result, machine, req, point.winding, speed_grid(req), j_limit)
                    left = (f"; checked {len(checks)} of {len(choice.ranked)} EM-feasible windings"
                            if len(choice.ranked) > len(checks) else "")
                    notes.append(f"no winding holds the rated hot-spot limit (best winding: {first.rpm:.0f} rpm, "
                                 f"{first.reason}{left})")
                    if rate_failed:
                        if len(checks) > 1:
                            ctx = context(checks[0])
                        rating = th.rate_context(ctx, n_speeds=n_speeds, progress=thermal_progress, fields_out=fields_out)
            except InterruptedError:
                return _failed(candidate, stage, "cancelled", "thermal check cancelled", j_limit)
            except Exception as exc:  # batch boundary, as for the map: a failed solve must not lose the search
                return _failed(candidate, stage, type(exc).__name__, str(exc), j_limit)
    w = point.winding
    chosen = machine.model_copy(update={"turns_per_pole": w.turns,
                                        "fill_factor": w.turns * w.copper_area / coil_side_area(machine)})
    mass = stage.mass.iron + w.copper_mass
    peak_power = float(np.max(env.power))
    at_base = int(np.argmin(np.abs(env.speeds_rpm - req.base_speed_rpm)))
    k = turns_scale(machine, w)
    scaled = rescale_turns(result, k)
    key = key_numbers(scaled, chosen)
    column = scaled.circuits.index(scaled.excited)
    arrays = MapArrays(scaled.angles, scaled.currents, scaled.psi[..., column], scaled.torque_arkkio)
    i_rms = float(np.max(env.i_rms))
    if not req.wire_mode and w.turns / w.paths >= max_turns:
        notes.append(f"turn scan reached its limit of {max_turns}; more turns may also be feasible")
    if env.waveforms is not None:
        cont = env.speeds_rpm[np.all(env.waveforms.current > 0, axis=1)]
        if cont.size:
            notes.append("continuous conduction at " + ", ".join(f"{r:g}" for r in cont) + " r/min: the drive model has "
                         "no mutual coupling, so the margin at these speeds is not measured")
    if not choice.feasible and choice.capped:
        notes.append(f"no winding is feasible and the {peak_cap_text(cap)} left out windings that fit the slot; "
                     + ("an explicit j_peak_max above it might allow one" if cap == J_PEAK_SCREEN else
                        "a higher cap might allow one"))
    litres = active_volume(chosen) * 1000
    over_mass = req.max_mass_kg is not None and mass > req.max_mass_kg
    if over_mass:
        notes.append(f"mass {mass:.2f} kg above the {req.max_mass_kg:.2f} kg limit")
    return Evaluation(candidate.id, design.model_copy(update={"machine": chosen}), "ok", "; ".join(notes), mass, w,
                      point.torque_ratio, point.power_ratio, peak_power, peak_power / 1000 / mass,
                      float(env.efficiency[at_base]), feasible and not over_mass, env, key, choice.scan,
                      i_rms, i_rms / (w.paths * w.copper_area), arrays,
                      map_curves(arrays, chosen, w, key, l_end * k * k), j_limit, rating=rating,
                      rated_continuous_kw_per_kg=_rated_kw_per_kg(rating, req, "continuous_nm", mass),
                      rated_peak_kw_per_kg=_rated_kw_per_kg(rating, req, "peak_nm", mass),
                      thermal_check=held, active_volume_l=litres,
                      rated_continuous_kw_per_l=_rated_kw_per_kg(rating, req, "continuous_nm", litres),
                      rated_peak_kw_per_l=_rated_kw_per_kg(rating, req, "peak_nm", litres))
