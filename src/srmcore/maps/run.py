"""Serial map runner: one excited circuit swept over an angle × current grid (spec §7.2, §8.1).

Every point is an independent solve from A = 0. Warm starts from the neighbouring current saved under
20 % of the Newton iterations on the 8/6, so points stay independent and parallelise per angle."""
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

STATUS_OK, STATUS_FALLBACK, STATUS_NONCONVERGED, STATUS_NOT_RUN = 0, 1, 2, -1
_CODE = {SolveStatus.OK: STATUS_OK, SolveStatus.OK_WITH_FALLBACK: STATUS_FALLBACK,
         SolveStatus.NONCONVERGED: STATUS_NONCONVERGED}
# Spec §8.1: the map fails when more than this fraction of its points fail.
MAX_FAILED_FRACTION = 0.02
_FIELDS = ("psi", "torque_arkkio", "torque_virtual_work", "coenergy")


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
    coenergy: np.ndarray               # J
    iterations: np.ndarray
    status: np.ndarray
    filled: np.ndarray
    complete: bool


def solve_angle(static, design: Design, solver: SolverAdapter, angle: float, currents,
                excited: str) -> dict[str, np.ndarray]:
    """All currents at one angle: one array per MapResult field, first axis over currents."""
    points = [solve_point(static, design, angle, {excited: float(i)}, solver) for i in currents]
    return {
        "psi": np.array([p.psi for p in points]),
        "torque_arkkio": np.array([p.torque_arkkio for p in points]),
        "torque_virtual_work": np.array([p.torque_virtual_work for p in points]),
        "coenergy": np.array([p.coenergy for p in points]),
        "iterations": np.array([p.iterations for p in points]),
        "status": np.array([_CODE[p.status] for p in points], dtype=np.int8),
    }


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


def run_map(static, design: Design, angles: np.ndarray, currents: np.ndarray, solver_name: str = "ngsolve",
            excited: str = "A", progress: Callable[[int, int], None] | None = None,
            cancel: Callable[[], bool] | None = None) -> MapResult:
    circuits = tuple(chr(ord("A") + k) for k in range(design.machine.n_phases))
    # Only phase A is aligned at θ = 0; the aligned angle of the other phases is not derived, so the
    # aligned-position check of the failure policy would be wrong for them.
    if excited != "A":
        raise ValueError(f"excited circuit {excited!r} is not supported yet: only phase A is aligned at θ=0")
    if len(currents) < 2 or np.any(np.diff(currents) <= 0):
        raise ValueError("currents must be strictly increasing with at least two values")
    solver = make_solver(solver_name)
    n_a, n_i = len(angles), len(currents)
    data = {name: np.full((n_a, n_i, len(circuits)) if name == "psi" else (n_a, n_i), np.nan) for name in _FIELDS}
    iterations = np.zeros((n_a, n_i), dtype=np.int32)
    status = np.full((n_a, n_i), STATUS_NOT_RUN, dtype=np.int8)
    complete = True
    for a, angle in enumerate(angles):
        if cancel is not None and cancel():
            complete = False
            break
        row = solve_angle(static, design, solver, float(angle), currents, excited)
        for name in _FIELDS:
            data[name][a] = row[name]
        iterations[a], status[a] = row["iterations"], row["status"]
        if progress is not None:
            progress(a + 1, n_a)
    result = MapResult(np.asarray(angles, float), np.asarray(currents, float), circuits, excited,
                       **data, iterations=iterations, status=status,
                       filled=np.zeros((n_a, n_i), dtype=bool), complete=complete)
    return apply_failure_policy(result) if complete else result
