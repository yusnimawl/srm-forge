"""Turns, wire and current chosen after the map (v0a-2 spec §2-3), and the exact rescales of a map to other turns and
other stack lengths."""
import dataclasses
import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from srmcore.maps import MapResult
from srmcore.maps.pool import default_workers, map_ordered
from srmcore.model.design import RadialSRMParams

from .drive.envelope import Envelope, envelope
from .requirements import Requirements
from .sizing.estimates import J_LIMIT, J_PEAK, J_PEAK_SCREEN, J_SCREEN
from .sizing.winding import DENSITY_MAX_TURNS, Winding, density_windings, wire_windings


def rescale_turns(result: MapResult, k: float) -> MapResult:
    """The map of the same geometry with k times the turns per pole. The 2D field depends only on the ampere-turns,
    so the current axis divides by k and flux linkage multiplies by k; torque, energy, forces and flux density at
    a given ampere-turns are unchanged, and L_inc scales by k²."""
    if not k > 0:
        raise ValueError(f"turn ratio k must be positive, got {k}")
    return dataclasses.replace(result, currents=result.currents / k, psi=result.psi * k,
                               l_inc=result.l_inc * (k * k))


def rescale_stack(result: MapResult, k: float) -> MapResult:
    """The 2D map of the same cross-section with k times the stack length. The solver works per unit depth, so the
    field, the flux density and the axes are unchanged, and every quantity integrated over the depth (flux
    linkage, torque, energy, coenergy, L_inc, pole forces) scales by k. The end winding is not part of a 2D map:
    add it after the rescale, for the target machine. `design_hash` still names the design that was solved."""
    if not (k > 0 and math.isfinite(k)):
        raise ValueError(f"stack ratio k must be positive and finite, got {k}")
    return dataclasses.replace(result, psi=result.psi * k, torque_arkkio=result.torque_arkkio * k,
                               torque_virtual_work=result.torque_virtual_work * k, energy=result.energy * k,
                               coenergy=result.coenergy * k, l_inc=result.l_inc * k,
                               pole_force=result.pole_force * k)


def restack(result: MapResult, mapped: RadialSRMParams, target: RadialSRMParams) -> MapResult:
    """The map of `mapped` rescaled to `target`, a machine that differs from it only in `stack_length`."""
    if mapped.model_dump(exclude={"stack_length"}) != target.model_dump(exclude={"stack_length"}):
        raise ValueError("restack needs machines that differ only in stack_length")
    return rescale_stack(result, target.stack_length / mapped.stack_length)


def speed_grid(req: Requirements, n: int = 12) -> np.ndarray:
    """Speeds in rpm from 10 % of base to the maximum; base and maximum speed are members exactly."""
    base, top = req.base_speed_rpm, req.max_speed_rpm
    return np.unique(np.concatenate([base * np.array([0.1, 0.25, 0.5]), np.linspace(base, top, n)]))


def _ratios(speeds_rpm: np.ndarray, torque: np.ndarray, power: np.ndarray, req: Requirements) -> tuple[float, float]:
    torque_at_base = float(np.interp(req.base_speed_rpm, speeds_rpm, torque))
    band = (speeds_rpm >= req.base_speed_rpm) & (speeds_rpm <= req.max_speed_rpm)
    return torque_at_base / req.peak_torque_nm, float(np.min(power[band])) / req.peak_power_w


def requirement_ratios(env: Envelope, req: Requirements) -> tuple[float, float]:
    """(torque at base speed / required torque, lowest power between base and maximum speed / required power)."""
    return _ratios(env.speeds_rpm, env.torque, env.power, req)


@dataclass(frozen=True)
class ScanPoint:
    winding: Winding
    torque_ratio: float     # achieved / required, at base speed
    power_ratio: float      # achieved / required, worst over base..max speed
    i_rms: float            # A, phase RMS current, worst over base..max speed
    feasible: bool          # worst ratio at least the margin
    single_pulse: bool = True   # the single-pulse strokes alone meet the margin at base speed and over the band

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
    capped: bool                   # wire mode: the peak current-density cap (or screen) left out windings that fit the slot
    ranked: tuple[ScanPoint, ...] = ()   # the feasible windings, best first (`point` is the first)


def turns_scale(machine: RadialSRMParams, w: Winding) -> float:
    """Rescale factor from the map at `machine.turns_per_pole` to winding `w`: `paths` parallel paths of N turns
    act as N / paths turns in series."""
    return w.turns / (w.paths * machine.turns_per_pole)


class ScanCancelled(Exception):
    """`choose_turns` stopped because `cancel` returned True."""


MIN_PARALLEL_JOBS = 16     # fewer distinct drive evaluations than this run in the calling process


def _envelope(result: MapResult, machine: RadialSRMParams, req: Requirements, w: Winding, speeds,
              j_limit: float) -> Envelope:
    return envelope(rescale_turns(result, turns_scale(machine, w)), machine, req.bus_voltage_v, w.resistance,
                    speeds, current_limit=w.current, rms_limit=j_limit * w.paths * w.copper_area)


def _drive_key(machine: RadialSRMParams, w: Winding, j_limit: float) -> tuple[float, float, float, float]:
    """Everything of a winding the drive envelope reads: the turn ratio, resistance, current limit and RMS limit.
    Windings with equal keys (for example N turns on one path and 2N turns on two) have the same envelope."""
    return turns_scale(machine, w), w.resistance, w.current, j_limit * w.paths * w.copper_area


_SCAN: dict = {}


def _scan_init(result: MapResult, machine: RadialSRMParams, bus_voltage: float, band: np.ndarray) -> None:
    _SCAN.update(result=result, machine=machine, bus_voltage=bus_voltage, band=band)


def _drive_summary(result: MapResult, machine: RadialSRMParams, bus_voltage: float, band: np.ndarray,
                   key: tuple[float, float, float, float]):
    """(speeds, torque, power, i_rms, single-pulse torque) of the drive envelope of one `_drive_key` over `band`; no
    waveforms."""
    k, resistance, current, rms_limit = key
    env = envelope(rescale_turns(result, k), machine, bus_voltage, resistance, band, current_limit=current,
                   rms_limit=rms_limit, waveforms=False)
    return env.speeds_rpm, env.torque, env.power, env.i_rms, env.torque_single_pulse


def _scan_job(key: tuple[float, float, float, float]):
    return _drive_summary(_SCAN["result"], _SCAN["machine"], _SCAN["bus_voltage"], _SCAN["band"], key)


RIPPLE_HALF_SHARE = 0.25   # dI/2 = V / (4 L f): hard chopping at zero back-EMF, twice the soft-chopping ripple
_RIPPLE_GRID = 1000        # current steps over [0, w.current]: 0.1 %


def _ripple_inductance(result: MapResult, machine: RadialSRMParams, w: Winding):
    """(currents, lowest L_inc over the angles) of the excited column on the map rescaled to `w`, valid nodes only."""
    scaled = rescale_turns(result, turns_scale(machine, w))
    column = scaled.circuits.index(scaled.excited)
    with np.errstate(all="ignore"):
        low = np.fmin.reduce(scaled.l_inc[..., column], axis=0)
    ok = np.isfinite(low)
    if not ok.any() or np.any(low[ok] <= 0):
        raise ValueError("no positive incremental inductance on the map: the current ripple cannot be computed")
    return scaled.currents[ok], low[ok]


def _lower_inductance(cur: np.ndarray, low: np.ndarray, x: np.ndarray) -> np.ndarray:
    """L at the currents `x`: the lower of the two neighbouring nodes (a straight line reads high where L_inc levels
    off); the first node below the map, the lowest L of the map above its top node."""
    i = np.searchsorted(cur, x)
    lower = np.minimum(low[np.clip(i - 1, 0, len(low) - 1)], low[np.clip(i, 0, len(low) - 1)])
    return np.where(i >= len(cur), low.min(), lower)


def ripple_half(result: MapResult, machine: RadialSRMParams, w: Winding, req: Requirements,
                current: float) -> tuple[float, float]:
    """(half the peak-to-peak ripple in A, lowest L_inc in H) at winding current `current`."""
    cur, low = _ripple_inductance(result, machine, w)
    inductance = float(_lower_inductance(cur, low, np.asarray(current)))
    volts = req.max_bus_voltage_v or req.bus_voltage_v
    return RIPPLE_HALF_SHARE * volts / (inductance * req.switching_frequency_hz), inductance


def ripple_note(result: MapResult, machine: RadialSRMParams, w: Winding, req: Requirements,
                j_peak: float) -> str | None:
    """The evaluation note for the ripple-limited winding `w`; None when no limit is set or it does not bind. It
    binds when `ripple_limited` lowered the winding's own current (the device peak in wire mode, `j_peak` over the
    copper in density mode, as the winding builders set it) or left it within one grid step of the device peak."""
    if req.switching_frequency_hz is None or req.phase_current_a is None:
        return None
    own = req.phase_current_a if w.wire is not None else j_peak * w.copper_area * w.paths
    half, low = ripple_half(result, machine, w, req, w.current)
    if w.current > own * (1 - 0.5 / _RIPPLE_GRID) and w.current + half <= req.phase_current_a - own / _RIPPLE_GRID:
        return None
    return (f"current limit {w.current:.1f} A: the {req.phase_current_a:.0f} A device peak less half the "
            f"{2 * half:.1f} A ripple ({req.switching_frequency_hz / 1e3:g} kHz, "
            f"{req.max_bus_voltage_v or req.bus_voltage_v:g} V, hard chopping, lowest L_inc {low * 1e3:.3g} mH)")


def ripple_limited(windings: list[Winding], result: MapResult, machine: RadialSRMParams,
                   req: Requirements) -> list[Winding]:
    """Each winding with its current lowered to the largest I <= w.current whose peak I + dI(I)/2 stays within
    `req.phase_current_a`; a winding with no such I is dropped. Unchanged without a switching frequency and a device
    peak. A map with no incremental inductance raises ValueError."""
    if req.switching_frequency_hz is None or req.phase_current_a is None:
        return list(windings)
    volts = req.max_bus_voltage_v or req.bus_voltage_v
    out = []
    for w in windings:
        cur, low = _ripple_inductance(result, machine, w)
        grid = w.current * (np.arange(1, _RIPPLE_GRID + 1) / _RIPPLE_GRID)   # the top point is w.current exactly
        peak = grid + RIPPLE_HALF_SHARE * volts / (_lower_inductance(cur, low, grid) * req.switching_frequency_hz)
        fits = np.flatnonzero(peak <= req.phase_current_a)
        if fits.size:
            out.append(dataclasses.replace(w, current=float(grid[fits[-1]])))
    return out


def choose_turns(result: MapResult, machine: RadialSRMParams, req: Requirements, *, j_peak: float = J_PEAK,
                 j_limit: float = J_SCREEN, j_peak_max: float | None = None, margin: float = 1.0,
                 max_turns: int = DENSITY_MAX_TURNS, only: Winding | None = None, workers: int | None = 1,
                 progress: Callable[[int, int], None] | None = None,
                 cancel: Callable[[], bool] | None = None) -> TurnsChoice:
    """Scan every allowed winding on the map of `machine` (built at `machine.turns_per_pole`). `j_limit` caps the
    conductor RMS current density, `j_peak_max` (default None: `J_PEAK_SCREEN`) the peak density in wire mode. A winding is
    feasible when its worst ratio is at least `margin`. Wire mode keeps the feasible winding with the lowest
    resistance; density mode keeps the feasible winding with the most equivalent turns (turns / paths), then the fewest paths, among
    the windings whose single-pulse strokes alone meet the margin (`ScanPoint.single_pulse`) while any exists: mutual
    coupling under continuous conduction is not measured yet (owner, 2026-11-27). With no
    feasible winding, the one with the largest worst ratio is reported. `only` replaces the scan with that one winding.

    The scan runs one drive envelope per distinct (turn ratio, resistance, current limit, RMS limit), so windings
    that give the same drive share one. `workers` runs them in a process pool (None: half the logical CPUs; one
    worker, or fewer than `MIN_PARALLEL_JOBS` distinct evaluations, stays in this process); the result does not
    depend on it. `progress(done, total)` follows the distinct evaluations; `cancel` is polled between them and
    raises `ScanCancelled`."""
    cap = J_PEAK_SCREEN if j_peak_max is None else j_peak_max
    capped = False
    if only is not None:
        windings = [only]
    elif req.wire_mode:
        windings = [w for i in range(len(req.wires)) for w in wire_windings(machine, req, i, cap)]
        capped = len(windings) < sum(len(wire_windings(machine, req, i, math.inf)) for i in range(len(req.wires)))
    else:
        windings = density_windings(machine, req, j_peak, max_turns)
    windings = ripple_limited(windings, result, machine, req)
    grid = speed_grid(req)
    band = grid[grid >= req.base_speed_rpm]

    keys = [_drive_key(machine, w, j_limit) for w in windings]
    distinct = list(dict.fromkeys(keys))
    args = (result, machine, req.bus_voltage_v, band)
    n_workers = default_workers(workers, len(distinct)) if len(distinct) >= MIN_PARALLEL_JOBS else 1
    if n_workers > 1:
        summaries = map_ordered(_scan_job, distinct, workers=n_workers, initializer=_scan_init, initargs=args,
                                cancel=cancel, progress=progress)
    else:
        summaries = []
        for done, key in enumerate(distinct, start=1):
            if cancel is not None and cancel():
                break
            summaries.append(_drive_summary(*args, key))
            if progress is not None:
                progress(done, len(distinct))
    if len(summaries) < len(distinct) or any(x is None for x in summaries):
        raise ScanCancelled()
    by_key = dict(zip(distinct, summaries))

    def scan_point(w: Winding, key) -> ScanPoint:
        speeds, torque, power, i_rms, pulse = by_key[key]
        torque_ratio, power_ratio = _ratios(speeds, torque, power, req)
        pulse_t, pulse_p = _ratios(speeds, pulse, pulse * speeds * 2 * math.pi / 60, req)
        return ScanPoint(w, torque_ratio, power_ratio, float(np.max(i_rms)),
                         min(torque_ratio, power_ratio) >= margin, min(pulse_t, pulse_p) >= margin)

    scan = tuple(scan_point(w, key) for w, key in zip(windings, keys))
    if not scan:
        return TurnsChoice(None, False, None, (), capped)
    feasible = [s for s in scan if s.feasible]
    ranked = []
    if not feasible:
        point = max(scan, key=lambda s: (s.worst, -s.winding.resistance))
    elif req.wire_mode:
        ranked = sorted(feasible, key=lambda s: (s.winding.resistance, s.winding.turns, s.winding.paths))
    else:
        ranked = sorted(feasible, key=lambda s: (not s.single_pulse, -s.winding.turns / s.winding.paths, s.winding.paths))
    if feasible:
        point = ranked[0]
    return TurnsChoice(point, bool(feasible), _envelope(result, machine, req, point.winding, grid, j_limit), scan,
                       capped, tuple(ranked))
