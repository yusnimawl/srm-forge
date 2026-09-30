"""Map runner: one excited circuit swept over an angle × current grid (spec §7.2, §8.1).

Every point is an independent solve from A = 0. Warm starts from the neighbouring current saved under
20 % of the Newton iterations on the 8/6, so points stay independent; each point is one job of the
process pool, highest current first because those solves take the most Newton iterations."""
import dataclasses
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator

from ..fields.solution import SolveStatus
from ..model.design import Design
from ..model.errors import MapFailed
from ..solvers.factory import make_solver
from ..solvers.settings import SolverAdapter
from .point import solve_point
from .pool import map_ordered

STATUS_OK, STATUS_FALLBACK, STATUS_NONCONVERGED, STATUS_NOT_RUN = 0, 1, 2, -1
_CODE = {SolveStatus.OK: STATUS_OK, SolveStatus.OK_WITH_FALLBACK: STATUS_FALLBACK,
         SolveStatus.NONCONVERGED: STATUS_NONCONVERGED}
# Spec §8.1: the map fails when more than this fraction of its points fail.
MAX_FAILED_FRACTION = 0.02
_FIELDS = ("psi", "torque_arkkio", "torque_virtual_work", "energy", "coenergy", "l_inc", "pole_force", "b_peak")


@dataclass(frozen=True, eq=False)
class MapResult:
    """ψ and torque of a design with `excited` carrying the current and the other circuits open; ψ holds
    every circuit's flux linkage. `status` uses the STATUS_* codes; `filled` marks points replaced by
    interpolation; unrun points (cancelled map) are STATUS_NOT_RUN with NaN data."""
    angles: np.ndarray                 # rad, θ = 0 aligned
    currents: np.ndarray               # A in the excited circuit
    circuits: tuple[str, ...]
    excited: str
    psi: np.ndarray                    # (n_angles, n_currents, n_circuits), Wb-turns
    torque_arkkio: np.ndarray          # (n_angles, n_currents), N·m
    torque_virtual_work: np.ndarray
    energy: np.ndarray                 # J
    coenergy: np.ndarray               # J
    l_inc: np.ndarray                  # (n_angles, n_currents, n_circuits), H: ∂ψ_k/∂i_excited, NaN where withheld
    pole_force: np.ndarray             # (n_angles, n_currents, n_poles, 2), N: [radial outward, tangential ccw]
    b_peak: np.ndarray                 # (n_angles, n_currents), T: peak |B| over the stator and rotor iron elements
    iterations: np.ndarray
    status: np.ndarray
    filled: np.ndarray
    complete: bool


def require_complete(result: MapResult) -> None:
    if not result.complete:
        raise ValueError("map is incomplete")


def solve_job(job) -> dict:
    """One point of the map, solved in a worker: `job` is (angle, current, excited)."""
    angle, current, excited = job
    p = solve_point(_WORKER["static"], _WORKER["design"], angle, {excited: current}, _WORKER["solver"],
                    with_l_inc=True)
    l_inc = np.full(len(p.circuits), np.nan) if p.l_inc is None else p.l_inc[:, p.circuits.index(excited)]
    return {"psi": p.psi, "torque_arkkio": p.torque_arkkio, "torque_virtual_work": p.torque_virtual_work,
            "energy": p.energy, "coenergy": p.coenergy, "l_inc": l_inc, "pole_force": p.pole_force, "b_peak": p.b_peak,
            "iterations": p.iterations, "status": _CODE[p.status]}


def apply_failure_policy(result: MapResult) -> MapResult:
    """Interpolate isolated NONCONVERGED points along current (PCHIP) and flag them, or raise MapFailed
    when more than 2 % of the points fail or the aligned angle or I_max has a failure."""
    failed = result.status == STATUS_NONCONVERGED
    n_failed = int(failed.sum())
    if n_failed == 0:
        return result
    reasons = []
    if n_failed / failed.size > MAX_FAILED_FRACTION:
        reasons.append(f"{n_failed} of {failed.size} points failed (limit 2 %)")
    if failed[np.isclose(result.angles, 0.0)].any():
        reasons.append("a point at the aligned position failed")
    if failed[:, -1].any():
        reasons.append("a point at I_max failed")
    if failed[:, 0].any():
        reasons.append("a point at zero current failed")
    if reasons:
        raise MapFailed(reasons, n_failed)
    data = {name: getattr(result, name).copy() for name in _FIELDS}
    for a in np.flatnonzero(failed.any(axis=1)):
        good, bad = ~failed[a], failed[a]
        for values in data.values():
            values[a][bad] = PchipInterpolator(result.currents[good], values[a][good], axis=0)(result.currents[bad])
    return dataclasses.replace(result, **data, filled=failed.copy())


_WORKER: dict = {}


def _init_worker(static, design, solver_name, threads) -> None:
    _WORKER.update(static=static, design=design, solver=make_solver(solver_name, threads))


def check_excited(excited: str) -> None:
    # Only phase A is aligned at θ = 0; the aligned angle of the other phases is not derived, so the
    # aligned-position check of the failure policy would be wrong for them.
    if excited != "A":
        raise ValueError(f"excited circuit {excited!r} is not supported yet: only phase A is aligned at θ=0")


def run_map(static, design: Design, angles: np.ndarray, currents: np.ndarray, solver_name: str = "ngsolve",
            excited: str = "A", workers: int = 1, progress: Callable[[int, int], None] | None = None,
            cancel: Callable[[], bool] | None = None) -> MapResult:
    circuits = tuple(chr(ord("A") + k) for k in range(design.machine.n_phases))
    check_excited(excited)
    if len(currents) < 2 or not np.all(np.isfinite(currents)) or np.any(np.diff(currents) <= 0):
        raise ValueError("currents must be strictly increasing with at least two values")
    make_solver(solver_name)                     # fail in the parent on an unknown solver or a missing extra
    n_a, n_i = len(angles), len(currents)
    inner = {"psi": (len(circuits),), "l_inc": (len(circuits),),
             "pole_force": (design.machine.n_stator_poles, 2)}
    data = {name: np.full((n_a, n_i, *inner.get(name, ())), np.nan) for name in _FIELDS}
    iterations = np.zeros((n_a, n_i), dtype=np.int32)
    status = np.full((n_a, n_i), STATUS_NOT_RUN, dtype=np.int8)
    # Longest solves first keeps the pool busy to the end; results are scattered back by grid index.
    order = sorted(((a, i) for a in range(n_a) for i in range(n_i)), key=lambda ai: (-ai[1], ai[0]))
    jobs = [(float(angles[a]), float(currents[i]), excited) for a, i in order]
    # Pool workers run single-threaded solvers; the pool supplies the parallelism.
    rows = map_ordered(solve_job, jobs, workers=workers, initializer=_init_worker,
                       initargs=(static, design, solver_name, 1 if workers > 1 else None),
                       cancel=cancel, progress=progress)
    for (a, i), row in zip(order, rows):
        if row is None:
            continue
        for name in _FIELDS:
            data[name][a, i] = row[name]
        iterations[a, i], status[a, i] = row["iterations"], row["status"]
    complete = all(row is not None for row in rows)
    result = MapResult(np.asarray(angles, float), np.asarray(currents, float), circuits, excited,
                       **data, iterations=iterations, status=status,
                       filled=np.zeros((n_a, n_i), dtype=bool), complete=complete)
    return apply_failure_policy(result) if complete else result
