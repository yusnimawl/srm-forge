"""Turns, wire and current chosen after the map (v0a-2 spec §2-3)."""
import dataclasses
import math
from dataclasses import dataclass

import numpy as np

from srmcore.maps import MapResult
from srmcore.model.design import RadialSRMParams

from .drive.envelope import Envelope, envelope
from .requirements import Requirements
from .sizing.estimates import J_LIMIT, J_PEAK
from .sizing.winding import DENSITY_MAX_TURNS, Winding, density_windings, wire_windings


def rescale_turns(result: MapResult, k: float) -> MapResult:
    """The map of the same geometry with k times the turns per pole. The 2D field depends only on the ampere-turns,
    so the current axis divides by k and flux linkage multiplies by k; torque, energy, forces and flux density at
    a given ampere-turns are unchanged, and L_inc scales by k²."""
    if not k > 0:
        raise ValueError(f"turn ratio k must be positive, got {k}")
    return dataclasses.replace(result, currents=result.currents / k, psi=result.psi * k,
                               l_inc=result.l_inc * (k * k))


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
class ScanPoint:
    winding: Winding
    torque_ratio: float     # achieved / required, at base speed
    power_ratio: float      # achieved / required, worst over base..max speed
    i_rms: float            # A, phase RMS current, worst over base..max speed
    feasible: bool          # worst ratio at least the margin

    @property
    def worst(self) -> float:
        return min(self.torque_ratio, self.power_ratio)

    @property
    def j_rms(self) -> float:
        """A/m², conductor RMS current density."""
        return self.i_rms / (self.winding.paths * self.winding.copper_area)


@dataclass(frozen=True)
class TurnsChoice:
    point: ScanPoint | None        # None when no winding meets the wire, current and current-density limits
    feasible: bool
    envelope: Envelope | None      # chosen winding over the full speed grid
    scan: tuple[ScanPoint, ...]    # every winding tried, in scan order
    capped: bool                   # wire mode: the peak current-density cap left out windings that fit the slot


def turns_scale(machine: RadialSRMParams, w: Winding) -> float:
    """Rescale factor from the map at `machine.turns_per_pole` to winding `w`: `paths` parallel paths of N turns
    act as N / paths turns in series."""
    return w.turns / (w.paths * machine.turns_per_pole)


def _envelope(result: MapResult, machine: RadialSRMParams, req: Requirements, w: Winding, speeds,
              j_limit: float) -> Envelope:
    return envelope(rescale_turns(result, turns_scale(machine, w)), machine, req.bus_voltage_v, w.resistance,
                    speeds, current_limit=w.current, rms_limit=j_limit * w.paths * w.copper_area)


def choose_turns(result: MapResult, machine: RadialSRMParams, req: Requirements, *, j_peak: float = J_PEAK,
                 j_limit: float = J_LIMIT, j_peak_max: float | None = None, margin: float = 1.0,
                 max_turns: int = DENSITY_MAX_TURNS, only: Winding | None = None) -> TurnsChoice:
    """Scan every allowed winding on the map of `machine` (built at `machine.turns_per_pole`). `j_limit` caps the
    conductor RMS current density, `j_peak_max` (default 2 · `j_limit`) the peak density in wire mode. A winding is
    feasible when its worst ratio is at least `margin`. Wire mode keeps the feasible winding with the lowest
    resistance; density mode keeps the feasible winding with the most equivalent turns (turns / paths), then the fewest paths. With no
    feasible winding, the one with the largest worst ratio is reported. `only` replaces the scan with that one winding."""
    cap = 2 * j_limit if j_peak_max is None else j_peak_max
    capped = False
    if only is not None:
        windings = [only]
    elif req.wire_mode:
        windings = [w for i in range(len(req.wires)) for w in wire_windings(machine, req, i, cap)]
        capped = len(windings) < sum(len(wire_windings(machine, req, i, math.inf)) for i in range(len(req.wires)))
    else:
        windings = density_windings(machine, req, j_peak, max_turns)
    grid = speed_grid(req)
    band = grid[grid >= req.base_speed_rpm]

    def scan_point(w: Winding) -> ScanPoint:
        env = _envelope(result, machine, req, w, band, j_limit)
        torque_ratio, power_ratio = requirement_ratios(env, req)
        return ScanPoint(w, torque_ratio, power_ratio, float(np.max(env.i_rms)),
                         min(torque_ratio, power_ratio) >= margin)

    scan = tuple(scan_point(w) for w in windings)
    if not scan:
        return TurnsChoice(None, False, None, (), capped)
    feasible = [s for s in scan if s.feasible]
    if not feasible:
        point = max(scan, key=lambda s: (s.worst, -s.winding.resistance))
    elif req.wire_mode:
        point = min(feasible, key=lambda s: (s.winding.resistance, s.winding.turns, s.winding.paths))
    else:
        point = max(feasible, key=lambda s: (s.winding.turns / s.winding.paths, -s.winding.paths))
    return TurnsChoice(point, bool(feasible), _envelope(result, machine, req, point.winding, grid, j_limit), scan,
                       capped)
