"""Minimal drive model: torque-speed envelope of a machine from the ψ/T map of phase A (v0 spec §4.5).

Voltage control with a hysteresis current limit (the map's I_max unless given) and ideal commutation: a single pulse
per period, or continuous conduction (the flux left at turn-on, `_strokes`) where no single pulse completes. No
mutual coupling (the other phases are open in the map), which continuous conduction makes larger, and no iron loss.
Peak-only and unvalidated."""
import math
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator

from srmcore.maps import MapResult
from srmcore.maps.run import require_complete
from srmcore.maps.tables import angle_spline
from srmcore.model.design import RadialSRMParams

N_THETA = 181                 # angle points over one rotor pole pitch
N_CURRENT = 121               # current points over 0..current limit
ON_RANGE = (0.25, 0.80)       # turn-on search range, fraction of the pitch
OFF_RANGE = (0.45, 1.25)       # turn-off search range, fraction of the pitch from the table start (above 1 wraps)
OFF_ALIGNED_END = 0.995        # the turn-off grid has n_off points up to here, and continues at the same spacing
N_ON, N_OFF = 80, 80
_EPS = 1e-9
PERIODIC_TOL = 1e-6          # root tolerance, fraction of the largest limit flux: 1e-4 already moves the least-copper current by 0.2 %
PERIODIC_MAX_ITER = 60       # Illinois needs at most 22 on the probed designs; a stroke left unconverged is invalid


@dataclass(frozen=True)
class Waveforms:
    """Phase A over one rotor pole pitch at θ_k = k·τ/n (mechanical rad), shape (n_speeds, n) except `theta`.
    Units: A, Wb-turns, V, N·m. `voltage` is the converter's average over interval k, ω·Δψ/Δθ + R·ī. `line` is the
    dc-link current of all phases (each phase draws v·ī / V_bus)."""
    theta: np.ndarray
    current: np.ndarray
    psi: np.ndarray
    voltage: np.ndarray
    torque: np.ndarray
    line: np.ndarray


@dataclass(frozen=True)
class Envelope:
    """Per-speed best stroke. `torque` is the revolution average over all phases. `work_torque` is ∫T dθ and
    `work_loop` is ∮ i dψ for the chosen stroke; they agree up to discretisation. `i_rms` is the phase RMS current
    over one rotor pole pitch of the chosen stroke (0 where no stroke is valid). `theta_off` may exceed one pitch: the
    flux tail runs past alignment, and `theta_off` is then measured from the start of the table.

    A chosen stroke is a single pulse or, where no single pulse completes, a continuous-conduction stroke whose flux
    does not return to zero before the next turn-on.

    `waveforms` holds the chosen stroke of phase A and the dc-link current over one rotor pole pitch (zeros where no
    stroke is valid). `line_mean` and `line_rms` are the mean and RMS of the dc-link current. `power_factor` is the
    output power over q·V_rms·I_rms of one phase (copper loss only; NaN where there is no stroke)."""
    speeds_rpm: np.ndarray
    torque: np.ndarray
    power: np.ndarray
    copper_loss: np.ndarray
    theta_on: np.ndarray
    theta_off: np.ndarray
    work_torque: np.ndarray
    work_loop: np.ndarray
    i_rms: np.ndarray
    waveforms: "Waveforms | None"
    line_mean: np.ndarray
    line_rms: np.ndarray
    power_factor: np.ndarray

    @property
    def efficiency(self) -> np.ndarray:
        """Copper-only efficiency P / (P + P_cu)."""
        return self.power / np.maximum(self.power + self.copper_loss, 1e-12)


@dataclass(frozen=True)
class _Tables:
    theta: np.ndarray       # (n_theta,), 0..period inclusive
    current: np.ndarray     # (N_CURRENT,), 0..current limit
    psi: np.ndarray         # (n_theta, N_CURRENT), non-decreasing in current
    torque: np.ndarray      # (n_theta, N_CURRENT)


def _tables(result: MapResult, period: float, i_top: float, n_theta: int) -> _Tables:
    e = result.circuits.index(result.excited)
    current = np.linspace(0.0, i_top, N_CURRENT)
    psi = PchipInterpolator(result.currents, result.psi[..., e], axis=1)(current)
    torque = PchipInterpolator(result.currents, result.torque_arkkio, axis=1)(current)
    theta = np.linspace(0.0, period, n_theta)
    psi_f = angle_spline(result.angles, psi, period)(theta)
    torque_f = angle_spline(result.angles, torque, period)(theta)
    return _Tables(theta, current, np.maximum.accumulate(np.maximum(psi_f, 0.0), axis=1), torque_f)


def line_current(per_phase: np.ndarray, n_phases: int) -> np.ndarray:
    """Sum of `per_phase` (shape (..., n), one period) over the phases, phase j shifted by j·n/q samples (periodic
    linear interpolation when n/q is not an integer)."""
    n = per_phase.shape[-1]
    out = np.zeros_like(per_phase, dtype=float)
    for j in range(n_phases):
        a, f = divmod(j * n / n_phases, 1.0)
        a = int(a)
        out += (1 - f) * np.roll(per_phase, a, axis=-1) + f * np.roll(per_phase, a + 1, axis=-1)
    return out


def power_factor(power: np.ndarray, voltage: np.ndarray, current: np.ndarray, n_phases: int) -> np.ndarray:
    """power / (q · rms(v) · rms(i)) along the last axis; NaN where the denominator is 0."""
    den = n_phases * np.sqrt((voltage**2).mean(axis=-1)) * np.sqrt((current**2).mean(axis=-1))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > 0, power / den, np.nan)


def _run(t: _Tables, omega: float, volts: float, r: float, on: np.ndarray, off: np.ndarray, psi0: np.ndarray,
         trace: bool = False):
    """One period for every (on, off) index pair, each simulated from its turn-on with the flux `psi0` (Wb-turns;
    0 is the stroke from rest), on the periodic table (the flux tail runs past alignment into the start of the next
    period). `off` may exceed the table end. Returns (work_torque, work_loop, ∫i² dθ, end flux, peak flux, beyond),
    and with `trace` also ψ and i at every step from turn-on, shape (n_theta, n_pairs), row 0 the start. `beyond` is
    true for a stroke that at some step would hold the current above the limit even with full negative voltage.

    The pairs are kept sorted by turn-on (`psi0` with them), so the strokes running at step `a` (turn-on in
    (a - n, a]) are one contiguous slice and only that slice is advanced. A stroke that was running at the previous
    step starts its step at the end torque of that step, which is reused except where the table row wraps."""
    n = t.theta.size - 1
    order = None if on.size < 2 or np.all(on[1:] >= on[:-1]) else np.argsort(on, kind="stable")
    if order is not None:
        on, off, psi0 = on[order], off[order], psi0[order]
    psi = np.array(psi0, dtype=float)
    i = np.zeros(on.size)
    for k in np.unique(on[psi > 0] % n):
        m = (on % n == k) & (psi > 0)
        i[m] = np.interp(psi[m], t.psi[k], t.current)
    lim = t.psi[:, -1]
    beyond = np.zeros(on.size, bool)
    w_t, w_l, i2, peak = np.zeros(on.size), np.zeros(on.size), np.zeros(on.size), np.zeros(on.size)
    tq_end = np.zeros(on.size)       # torque at the end of the previous step, per stroke
    dth = t.theta[1] - t.theta[0]
    psi_t, i_t = (np.zeros((n + 1, on.size)), np.zeros((n + 1, on.size))) if trace else (None, None)
    if trace:
        psi_t[0], i_t[0] = psi, i
    steps = np.arange(int(on.max()) + n)
    first = np.searchsorted(on, steps - n, side="right")     # strokes with on <= a - n have finished
    started = np.searchsorted(on, steps, side="right")       # strokes with on <= a
    starting = np.searchsorted(on, steps, side="left")       # strokes with on == a begin here
    for a in range(steps.size):
        lo, hi, new_from = int(first[a]), int(started[a]), int(starting[a])
        k = a % n
        s = slice(lo, hi)
        psi_s, i_s = psi[s], i[s]
        pulse = a < off[s]
        beyond[s] |= psi_s - (volts + r * i_s) / omega * dth > lim[k + 1] * (1 + _EPS)
        v = np.where(pulse, volts, -volts)
        new = psi_s + (v - r * i_s) / omega * dth
        new = np.where(pulse, np.minimum(new, t.psi[k + 1, -1]), new)     # current limit while the pulse is on
        new = np.maximum(new, 0.0)
        # zero flux is zero current even when the map row has tied leading zeros
        i_new = np.where(new > 0, np.interp(new, t.psi[k + 1], t.current), 0.0)
        tq_old = tq_end[s].copy() if k > 0 else np.interp(i_s, t.current, t.torque[k])
        if k > 0:
            tq_old[new_from - lo:] = np.interp(i_s[new_from - lo:], t.current, t.torque[k])
        tq_new = np.interp(i_new, t.current, t.torque[k + 1])
        w_t[s] += 0.5 * (tq_old + tq_new) * dth
        w_l[s] += 0.5 * (i_s + i_new) * (new - psi_s)
        i2[s] += 0.5 * (i_s**2 + i_new**2) * dth
        psi[s], i[s], tq_end[s] = new, i_new, tq_new
        peak[s] = np.maximum(peak[s], new)
        if trace:
            idx = np.arange(lo, hi)
            psi_t[a + 1 - on[idx], idx] = new
            i_t[a + 1 - on[idx], idx] = i_new
    out = (w_t, w_l, i2, psi, peak, beyond, psi_t, i_t) if trace else (w_t, w_l, i2, psi, peak, beyond)
    if order is not None:
        back = np.empty_like(order)
        back[order] = np.arange(order.size)
        out = tuple(x[back] if x.ndim == 1 else x[:, back] for x in out)
    return out


def _simulate(t: _Tables, omega: float, volts: float, r: float, on: np.ndarray, off: np.ndarray,
              trace: bool = False):
    """One stroke for every (on, off) index pair, each simulated from its turn-on at zero flux over exactly one
    period (see `_run`). Returns (work_torque, work_loop, ∫i² dθ, valid), and with `trace` also ψ and i at every step
    from turn-on, shape (n_theta, n_pairs). A stroke is valid when its flux is back to 1 % of its peak before the
    same phase turns on again."""
    w_t, w_l, i2, psi, peak, _, *tr = _run(t, omega, volts, r, on, off, np.zeros(on.size), trace)
    valid = psi <= 0.01 * np.maximum(peak, 1e-12)       # the flux must be gone before the next turn-on
    return (w_t, w_l, i2, valid, *tr)


def _strokes(t: _Tables, omega: float, volts: float, r: float, on: np.ndarray, off: np.ndarray):
    """Single-pulse strokes (`_simulate`), plus the periodic steady state of every stroke `_simulate` rejects.
    With F(p) the end flux of one period that starts at turn-on with flux p, a rejected stroke has F(0) > 0 and
    G = F - p falls with p, so a root in [0, ψ(θ_on, I_lim)] is found by Illinois regula falsi. A root is accepted
    when it converged and no step needs more than the current limit (`_run` `beyond`). Returns (work_torque,
    work_loop, ∫i² dθ, valid, start flux); accepted periodic strokes carry their integrals and root, every other
    stroke keeps `_simulate`'s numbers and a start flux of 0."""
    n = t.theta.size - 1
    w_t, w_l, i2, valid = _simulate(t, omega, volts, r, on, off)
    psi0 = np.zeros(on.size)
    sel = np.flatnonzero(~valid)
    if sel.size == 0:
        return w_t, w_l, i2, valid, psi0
    o, f = on[sel], off[sel]
    tol = PERIODIC_TOL * t.psi[:, -1].max()
    lo, hi = np.zeros(sel.size), t.psi[o % n, -1].copy()
    g_lo = _run(t, omega, volts, r, o, f, lo)[3] - lo
    g_hi = _run(t, omega, volts, r, o, f, hi)[3] - hi
    act = g_hi <= 0                                      # G(cap) > 0: no admissible periodic state
    ok = act.copy()
    x = hi.copy()
    side = np.zeros(sel.size, int)
    for _ in range(PERIODIC_MAX_ITER):
        idx = np.flatnonzero(act)
        if idx.size == 0:
            break
        xn = (lo[idx] * g_hi[idx] - hi[idx] * g_lo[idx]) / (g_hi[idx] - g_lo[idx])
        g = _run(t, omega, volts, r, o[idx], f[idx], xn)[3] - xn
        x[idx] = xn
        done = (np.abs(g) <= tol) | (hi[idx] - lo[idx] <= tol)
        pos = g > 0
        up, down = idx[pos], idx[~pos]
        g_hi[up[side[up] == 1]] *= 0.5                   # Illinois: halve the retained end after two moves on one side
        lo[up], g_lo[up], side[up] = xn[pos], g[pos], 1
        g_lo[down[side[down] == -1]] *= 0.5
        hi[down], g_hi[down], side[down] = xn[~pos], g[~pos], -1
        act[idx[done]] = False
    idx = np.flatnonzero(ok & ~act)
    if idx.size:
        a_t, a_l, a_i2, _, _, beyond = _run(t, omega, volts, r, o[idx], f[idx], x[idx])
        good = ~beyond
        gi = sel[idx[good]]
        w_t[gi], w_l[gi], i2[gi], psi0[gi] = a_t[good], a_l[good], a_i2[good], x[idx[good]]
        valid[gi] = True
    return w_t, w_l, i2, valid, psi0


def _stroke_waveforms(t: _Tables, omega: float, volts: float, r: float, on: int, off: int, psi0: float = 0.0):
    """Current, flux, average phase voltage, torque and dc-link current of one stroke from its root flux `psi0`, each
    shape (n,) on the table angles (the tail wraps into the start of the period)."""
    n = t.theta.size - 1
    *_, psi_r, i_r = _run(t, omega, volts, r, np.array([on]), np.array([off]), np.array([float(psi0)]), trace=True)
    psi_r, i_r = psi_r[:, 0], i_r[:, 0]
    i_bar = 0.5 * (i_r[:-1] + i_r[1:])
    v = omega * np.diff(psi_r) / (t.theta[1] - t.theta[0]) + r * i_bar
    rows = (on + np.arange(n)) % n
    tq = np.array([np.interp(i_r[j], t.current, t.torque[rows[j]]) for j in range(n)])
    out = []
    for w in (i_r[:-1], psi_r[:-1], v, tq, v * i_bar / volts):
        a = np.empty(n)
        a[rows] = w
        out.append(a)
    return tuple(out)


def _theta(t: _Tables, index: int) -> float:
    """Angle of a (possibly wrapped) stroke index, unwrapped past the table end."""
    n = t.theta.size - 1
    return float(t.theta[index % n] + (index // n) * t.theta[-1])


def _stroke_pairs(n_theta: int, n_on: int, n_off: int) -> tuple[np.ndarray, np.ndarray]:
    """Table indices (on, off) of every candidate stroke with off after on. The turn-off axis has `n_off` points up to
    OFF_ALIGNED_END and goes on at that spacing to OFF_RANGE[1], so it holds every point of an axis that stops at
    alignment."""
    top = n_theta - 1
    on_axis = np.unique(np.round(np.linspace(*ON_RANGE, n_on) * top).astype(int))
    step = (OFF_ALIGNED_END - OFF_RANGE[0]) / (n_off - 1)
    n_pts = int(math.floor((OFF_RANGE[1] - OFF_RANGE[0]) / step + 1e-9)) + 1
    off_axis = np.unique(np.round((OFF_RANGE[0] + step * np.arange(n_pts)) * top).astype(int))
    on, off = (a.ravel() for a in np.meshgrid(on_axis, off_axis, indexing="ij"))
    keep = off > on
    return on[keep], off[keep]


def envelope(result: MapResult, machine: RadialSRMParams, bus_voltage: float, resistance: float,
             speeds_rpm, *, current_limit: float | None = None, rms_limit: float | None = None,
             n_theta: int = N_THETA, n_on: int = N_ON, n_off: int = N_OFF, waveforms: bool = True) -> Envelope:
    """`current_limit` (A) is the hysteresis limit, at most the map's top current (the default). `rms_limit` (A)
    caps the phase RMS current over a rotor pole pitch: strokes above it are not used. With `waveforms` False the
    chosen strokes are not re-simulated: `waveforms` is None and `line_mean`, `line_rms` and `power_factor` are
    NaN; every other field is the same."""
    require_complete(result)
    if result.excited != "A":
        raise ValueError("the envelope needs the phase A map (excited='A')")
    if rms_limit is not None and not rms_limit > 0:
        raise ValueError(f"rms limit {rms_limit} A must be positive")
    top_current = float(result.currents[-1])
    i_top = top_current if current_limit is None else float(current_limit)
    if not 0 < i_top <= top_current * (1 + 1e-6):
        raise ValueError(f"current limit {i_top} A is outside the map's range (0, {top_current}] A")
    period = 2 * math.pi / machine.n_rotor_poles
    t = _tables(result, period, i_top, n_theta)
    on, off = _stroke_pairs(n_theta, n_on, n_off)
    speeds = np.asarray(speeds_rpm, float)
    rows = []
    n = n_theta - 1
    q = machine.n_phases
    zero = np.zeros(n)
    traces = []
    for rpm in speeds:
        omega = rpm * 2 * math.pi / 60
        w_t, w_l, i2, valid, psi0 = _strokes(t, omega, bus_voltage, resistance, on, off)
        if rms_limit is not None:
            valid &= i2 / period <= rms_limit**2 * (1 + _EPS)
        best = int(np.argmax(np.where(valid, w_t, -np.inf))) if valid.any() else -1
        if best < 0 or w_t[best] <= 0:
            rows.append((0.0, 0.0, _theta(t, on[0]), _theta(t, off[0]), 0.0, 0.0, 0.0))
            traces.append((zero,) * 5)
            continue
        if waveforms:
            traces.append(_stroke_waveforms(t, omega, bus_voltage, resistance, int(on[best]), int(off[best]),
                                                 float(psi0[best])))
        strokes_per_rev = machine.n_phases * machine.n_rotor_poles
        rows.append((strokes_per_rev * w_t[best] / (2 * math.pi),
                     machine.n_phases * resistance * i2[best] / period,
                     _theta(t, on[best]), _theta(t, off[best]), w_t[best], w_l[best],
                     math.sqrt(i2[best] / period)))
    torque, copper, th_on, th_off, work_t, work_l, i_rms = (np.array(c) for c in zip(*rows))
    power = torque * speeds * 2 * math.pi / 60
    if not waveforms:
        nan = np.full(speeds.size, np.nan)
        return Envelope(speeds, torque, power, copper, th_on, th_off, work_t, work_l, i_rms, None, nan, nan, nan)
    cur, psi_w, volt, tq_w, bus = (np.array(c) for c in zip(*traces))
    wave = Waveforms(t.theta[:n], cur, psi_w, volt, tq_w, line_current(bus, q))
    return Envelope(speeds, torque, power, copper, th_on, th_off, work_t, work_l, i_rms, wave,
                    wave.line.mean(axis=1), np.sqrt((wave.line**2).mean(axis=1)),
                    power_factor(power, volt, cur, q))


@dataclass(frozen=True)
class StrokeTrace:
    """One stroke of phase A on the table angles (n,), tail wrapped into the start of the period. `current_limit`
    is the hysteresis limit (A), `torque_avg` the revolution average over all phases, `copper_dc_w` = q·R·i_rms².
    `psi_on` is the flux at turn-on (Wb-turns): 0 for a single pulse, above 0 for a continuous-conduction stroke."""
    theta_on: float
    theta_off: float
    current_limit: float
    current: np.ndarray
    psi: np.ndarray
    torque_avg: float
    i_rms: float
    copper_dc_w: float
    valid: bool = True
    psi_on: float = 0.0


def min_copper_stroke(result: MapResult, machine: RadialSRMParams, bus_voltage: float, resistance: float,
                      rpm: float, torque_nm: float, *, n_limits: int = 8, n_theta: int = N_THETA,
                      n_on: int = N_ON, n_off: int = N_OFF) -> StrokeTrace | None:
    """The valid stroke with average torque of at least `torque_nm` and the least copper loss, over turn-on, turn-off
    and current limits k/n_limits of the map's top current; None when no stroke reaches the torque."""
    require_complete(result)
    if result.excited != "A":
        raise ValueError("the envelope needs the phase A map (excited='A')")
    if not torque_nm > 0:
        raise ValueError(f"torque {torque_nm} N·m must be positive")
    top_current = float(result.currents[-1])
    period = 2 * math.pi / machine.n_rotor_poles
    on, off = _stroke_pairs(n_theta, n_on, n_off)
    omega = rpm * 2 * math.pi / 60
    per_rev = machine.n_phases * machine.n_rotor_poles / (2 * math.pi)
    best = None
    for k in range(1, n_limits + 1):
        limit = k / n_limits * top_current
        t = _tables(result, period, limit, n_theta)
        w_t, _, i2, valid, psi0 = _strokes(t, omega, bus_voltage, resistance, on, off)
        ok = valid & (per_rev * w_t >= torque_nm)
        if not ok.any():
            continue
        j = int(np.argmin(np.where(ok, i2, np.inf)))
        if best is None or i2[j] < best[0]:
            best = (i2[j], t, limit, int(on[j]), int(off[j]), per_rev * w_t[j], float(psi0[j]))
    if best is None:
        return None
    i2, t, limit, o, f, tq, p0 = best
    return _trace(t, machine, omega, bus_voltage, resistance, limit, o, f, tq, i2, True, p0)


def _trace(t: _Tables, machine: RadialSRMParams, omega: float, volts: float, resistance: float, limit: float,
           on: int, off: int, torque: float, i2: float, valid: bool, psi0: float = 0.0) -> StrokeTrace:
    period = t.theta[-1]
    cur, psi, *_ = _stroke_waveforms(t, omega, volts, resistance, on, off, psi0)
    return StrokeTrace(_theta(t, on), _theta(t, off), limit, cur, psi, torque, math.sqrt(i2 / period),
                       machine.n_phases * resistance * i2 / period, valid, psi0)


def fixed_stroke(result: MapResult, machine: RadialSRMParams, bus_voltage: float, resistance: float, rpm: float,
                 theta_on: float, theta_off: float, current_limit: float, *, n_theta: int = N_THETA) -> StrokeTrace:
    """The stroke from `theta_on` to `theta_off` (rad on the table, 0 = aligned; `theta_off` may exceed one rotor
    pole pitch) with the hysteresis limit `current_limit` (A, at most the map's top current), snapped to the table
    angles: a single pulse, or the periodic steady state where the flux does not die away before the next turn-on.
    `valid` is False when no periodic state keeps the current within the limit."""
    require_complete(result)
    if result.excited != "A":
        raise ValueError("the envelope needs the phase A map (excited='A')")
    if not 0 < current_limit <= float(result.currents[-1]) * (1 + 1e-6):
        raise ValueError(f"current limit {current_limit} A is outside the map's range (0, {result.currents[-1]}] A")
    period = 2 * math.pi / machine.n_rotor_poles
    n = n_theta - 1
    on, off = round(theta_on / period * n), round(theta_off / period * n)
    if not 0 <= on < off:
        raise ValueError(f"the pulse needs 0 <= theta_on < theta_off, got {theta_on} and {theta_off} rad")
    t = _tables(result, period, current_limit, n_theta)
    omega = rpm * 2 * math.pi / 60
    w_t, _, i2, valid, psi0 = _strokes(t, omega, bus_voltage, resistance, np.array([on]), np.array([off]))
    per_rev = machine.n_phases * machine.n_rotor_poles / (2 * math.pi)
    return _trace(t, machine, omega, bus_voltage, resistance, current_limit, on, off, per_rev * w_t[0], i2[0],
                  bool(valid[0]), float(psi0[0]))
