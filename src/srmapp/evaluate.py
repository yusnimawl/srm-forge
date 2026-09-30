"""Stage 2: reduced FEM map of one candidate plus the drive envelope and its scores (v0 spec §4.4-4.6).
Peak-only and unvalidated: no losses beyond copper, no thermal limit."""
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from srmcore.maps import build_map
from srmcore.maps.results import KeyNumbers, key_numbers
from srmcore.model.design import Design
from srmcore.model.errors import InputError, MapFailed, MeshRejected, WorkerCrashed

from .drive.envelope import Envelope, envelope
from .requirements import Requirements
from .sizing.estimates import phase_resistance
from .sizing.generator import Candidate
from .sizing.stage1 import Stage1

_NAN = float("nan")


@dataclass(frozen=True)
class StageTwoGrid:
    """Reduced map grid. The default 12 x 5 was chosen from the v0a grid study in docs/m4-handoff.md."""
    n_angles: int = 12
    n_currents: int = 5


def speed_grid(req: Requirements, n: int = 12) -> np.ndarray:
    """Speeds in rpm from 10 % of base to the maximum; base and maximum speed are members exactly."""
    base, top = req.base_speed_rpm, req.max_speed_rpm
    return np.unique(np.concatenate([base * np.array([0.1, 0.25, 0.5]), np.linspace(base, top, n)]))


def requirement_ratios(env: Envelope, req: Requirements) -> tuple[float, float]:
    """(torque at base speed / required torque, lowest power between base and maximum speed / required power)."""
    torque_at_base = float(np.interp(req.base_speed_rpm, env.speeds_rpm, env.torque))
    band = (env.speeds_rpm >= req.base_speed_rpm) & (env.speeds_rpm <= req.max_speed_rpm)
    return torque_at_base / req.peak_torque_nm, float(np.min(env.power[band])) / req.peak_power_w


@dataclass(frozen=True)
class Evaluation:
    id: str
    design: Design
    status: str                 # "ok", "cancelled", or the name of the exception that stopped the evaluation
    error: str
    mass_kg: float
    i_peak: float
    torque_ratio: float         # achieved / required, at base speed
    power_ratio: float          # achieved / required, worst over base..max speed
    peak_power_w: float
    power_density_kw_per_kg: float
    efficiency_base: float      # copper-only, at base speed
    feasible: bool
    envelope: Envelope | None
    key: KeyNumbers | None


def _failed(candidate: Candidate, stage: Stage1, status: str, error: str) -> Evaluation:
    return Evaluation(candidate.id, candidate.design, status, error, stage.mass.total, stage.i_peak,
                      _NAN, _NAN, _NAN, _NAN, _NAN, False, None, None)


def evaluate_stage2(candidate: Candidate, req: Requirements, stage: Stage1, *, grid: StageTwoGrid = StageTwoGrid(),
                    solver: str = "ngsolve", workers: int | None = None, cache_dir=None,
                    progress: Callable[[int, int], None] | None = None,
                    cancel: Callable[[], bool] | None = None) -> Evaluation:
    design = candidate.design
    machine = design.machine
    try:
        result = build_map(design, stage.i_peak, solver=solver, workers=workers, n_angles=grid.n_angles,
                           n_currents=grid.n_currents, cache_dir=cache_dir, progress=progress, cancel=cancel)
    except (MapFailed, MeshRejected, InputError, WorkerCrashed) as exc:
        return _failed(candidate, stage, type(exc).__name__, str(exc))
    if not result.complete:
        return _failed(candidate, stage, "cancelled", "map cancelled")
    env = envelope(result, machine, req.bus_voltage_v, phase_resistance(machine), speed_grid(req))
    torque_ratio, power_ratio = requirement_ratios(env, req)
    peak_power = float(np.max(env.power))
    at_base = int(np.argmin(np.abs(env.speeds_rpm - req.base_speed_rpm)))
    return Evaluation(candidate.id, design, "ok", "", stage.mass.total, stage.i_peak, torque_ratio, power_ratio,
                      peak_power, peak_power / 1000 / stage.mass.total, float(env.efficiency[at_base]),
                      torque_ratio >= 1.0 and power_ratio >= 1.0, env, key_numbers(result, machine))
