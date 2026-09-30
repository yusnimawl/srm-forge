"""Overlap map: phases A and B excited together over the A→B handover window (spec §7.2, §8.1)."""
import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from ..model.design import Design, RadialSRMParams
from ..model.errors import MapFailed
from ..solvers.factory import make_solver
from .checks import Check
from .grids import aligned_angle
from .pool import map_ordered
from .run import STATUS_NONCONVERGED, STATUS_NOT_RUN, _init_worker, solve_currents_job

COUPLING_LIMIT = 0.02
RECIPROCITY_LIMIT = 1e-3


@dataclass(frozen=True, eq=False)
class OverlapResult:
    """ψ and torque with phases A and B both excited. Angles are unwrapped and may equal τ. `l_inc` holds
    ∂ψ_{A,B}/∂i_{A,B} (rows: ψ of A, B; columns: i_A, i_B), NaN where withheld. Unrun points (cancelled map)
    are STATUS_NOT_RUN with NaN data."""
    angles: np.ndarray                 # rad
    currents_a: np.ndarray             # A
    currents_b: np.ndarray             # A
    circuits: tuple[str, ...]
    psi: np.ndarray                    # (n_angles, n_ia, n_ib, n_circuits), Wb-turns
    torque_arkkio: np.ndarray          # (n_angles, n_ia, n_ib), N·m
    l_inc: np.ndarray                  # (n_angles, n_ia, n_ib, 2, 2), H
    status: np.ndarray                 # (n_angles, n_ia, n_ib)
    complete: bool


def overlap_window(machine: RadialSRMParams) -> tuple[float, float] | None:
    """Rotor angles [start, τ] of the A→B handover overlap: start = (θ_B − (βs + βr)/2) mod τ. None when
    (βs + βr)/2 does not exceed the stroke angle ε = 2π/(m·Nr), i.e. the poles never overlap across a handover."""
    tau = 2 * math.pi / machine.n_rotor_poles
    half = (machine.stator_pole_arc + machine.rotor_pole_arc) / 2
    if half <= tau / machine.n_phases:
        return None
    return (aligned_angle(machine, "B") - half) % tau, tau


def _require_zero_start(currents_a, currents_b) -> None:
    """The coupling checks compare against the single-phase columns at current 0."""
    if len(currents_a) < 1 or len(currents_b) < 1 or currents_a[0] != 0 or currents_b[0] != 0:
        raise ValueError("both current grids must start at 0")


def run_overlap_map(static, design: Design, angles: np.ndarray, currents_a: np.ndarray, currents_b: np.ndarray,
                    solver_name: str = "ngsolve", workers: int = 1,
                    progress: Callable[[int, int], None] | None = None,
                    cancel: Callable[[], bool] | None = None) -> OverlapResult:
    """One job per point, each solved from A = 0. Any NONCONVERGED point of a complete map raises MapFailed;
    nothing is filled."""
    make_solver(solver_name)                     # fail in the parent on an unknown solver or a missing extra
    _require_zero_start(currents_a, currents_b)
    circuits = tuple(chr(ord("A") + k) for k in range(design.machine.n_phases))
    shape = (len(angles), len(currents_a), len(currents_b))
    psi = np.full((*shape, len(circuits)), np.nan)
    torque = np.full(shape, np.nan)
    l_inc = np.full((*shape, 2, 2), np.nan)
    status = np.full(shape, STATUS_NOT_RUN, dtype=np.int8)
    order = sorted(np.ndindex(shape), key=lambda k: (-(k[1] + k[2]), k[0]))       # heaviest solves first
    jobs = [(float(angles[a]), {"A": float(currents_a[i]), "B": float(currents_b[j])}) for a, i, j in order]
    rows = map_ordered(solve_currents_job, jobs, workers=workers, initializer=_init_worker,
                       initargs=(static, design, solver_name, 1 if workers > 1 else None),
                       cancel=cancel, progress=progress)
    for k, row in zip(order, rows):
        if row is None:
            continue
        if row["circuits"] != circuits:
            raise ValueError(f"solved circuits {row['circuits']} differ from {circuits}")
        psi[k], torque[k], status[k] = row["psi"], row["torque_arkkio"], row["status"]
        l_inc[k] = row["l_inc"][:2, :2]
    complete = all(row is not None for row in rows)
    if complete and (n_failed := int((status == STATUS_NONCONVERGED).sum())):
        raise MapFailed([f"{n_failed} of {status.size} overlap points failed (no failures allowed)"], n_failed)
    return OverlapResult(np.asarray(angles, float), np.asarray(currents_a, float), np.asarray(currents_b, float),
                         circuits, psi, torque, l_inc, status, complete)


def coupling_checks(overlap: OverlapResult) -> tuple[Check, ...]:
    """Mutual effects between the two excited phases, over points where both currents are positive. A
    non-finite value reports the failing status."""
    if not overlap.complete:
        raise ValueError("incomplete")
    _require_zero_start(overlap.currents_a, overlap.currents_b)
    both = (overlap.currents_a > 0)[:, None] & (overlap.currents_b > 0)[None, :]
    psi_a, psi_b = overlap.psi[..., 0], overlap.psi[..., 1]
    # Each phase against itself with the other phase open (current index 0).
    dev_psi = np.concatenate([(np.abs(psi_a - psi_a[:, :, :1])[:, both] / np.max(psi_a)).ravel(),
                              (np.abs(psi_b - psi_b[:, :1, :])[:, both] / np.max(psi_b)).ravel()])
    t = overlap.torque_arkkio
    dev_t = np.abs(t - t[:, :, :1] - t[:, :1, :])[:, both] / np.max(np.abs(t))
    lab = overlap.l_inc[:, both]
    recip = np.abs(lab[..., 0, 1] - lab[..., 1, 0]) / np.max(np.abs(overlap.l_inc[..., 0, 0]))

    def check(name, values, limit, detail, bad):
        value = float(np.max(values)) if values.size else 0.0
        if not np.isfinite(value):
            return Check(name, bad, value, limit, detail + " (non-finite value)")
        return Check(name, bad if value > limit else "pass", value, limit, detail)
    return (check("coupling_psi", dev_psi, COUPLING_LIMIT,
                  "ψ of each phase with the other excited against the other open, relative to its peak; warn means "
                  "single-phase superposition is not enough to drive the machine", "warn"),
            check("coupling_torque", dev_t, COUPLING_LIMIT,
                  "T(iA, iB) − T(iA, 0) − T(0, iB) relative to peak torque", "warn"),
            check("reciprocity", recip, RECIPROCITY_LIMIT, "|L_AB − L_BA| relative to max |L_AA|", "fail"))
