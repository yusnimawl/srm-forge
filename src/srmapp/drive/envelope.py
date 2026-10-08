"""Minimal drive model: torque-speed envelope of a machine from the ψ/T map of phase A (v0 spec §4.5).

Single-pulse voltage control with a hysteresis current limit (the map's I_max unless given), ideal commutation, no
mutual coupling (the other phases are open in the map) and no iron loss. Peak-only and unvalidated."""
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
OFF_RANGE = (0.45, 0.995)      # turn-off search range
N_ON, N_OFF = 80, 80
_EPS = 1e-9


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
    over one rotor pole pitch of the chosen stroke (0 where no stroke is valid).

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
    waveforms: "Waveforms"
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


def _simulate(t: _Tables, omega: float, volts: float, r: float, on: np.ndarray, off: np.ndarray,
              trace: bool = False):
    """One stroke for every (on, off) index pair. Returns (work_torque, work_loop, ∫i² dθ, valid), and with `trace`
    also ψ and i at every grid point, shape (n_theta, n_pairs)."""
    n = on.size
    psi, i = np.zeros(n), np.zeros(n)
    w_t, w_l, i2, peak = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    dth = t.theta[1] - t.theta[0]
    psi_t, i_t = [psi], [i]
    for k in range(t.theta.size - 1):
        pulse = k < off
        started = k >= on
        v = np.where(pulse, volts, -volts)
        new = np.where(started, psi + (v - r * i) / omega * dth, 0.0)
        new = np.where(pulse, np.minimum(new, t.psi[k + 1, -1]), new)     # current limit while the pulse is on
        new = np.maximum(new, 0.0)
        # zero flux is zero current even when the map row has tied leading zeros
        i_new = np.where(new > 0, np.interp(new, t.psi[k + 1], t.current), 0.0)
        tq_old = np.interp(i, t.current, t.torque[k])
        tq_new = np.interp(i_new, t.current, t.torque[k + 1])
        w_t += 0.5 * (tq_old + tq_new) * dth * started
        w_l += 0.5 * (i + i_new) * (new - psi)
        i2 += 0.5 * (i**2 + i_new**2) * dth * started
        psi, i = new, i_new
        peak = np.maximum(peak, psi)
        psi_t.append(psi)
        i_t.append(i)
    # the residual tail after alignment (up to 1 % of the peak flux) is not counted
    valid = psi <= 0.01 * np.maximum(peak, 1e-12)       # flux must be gone by alignment
    if trace:
        return w_t, w_l, i2, valid, np.array(psi_t), np.array(i_t)
    return w_t, w_l, i2, valid


def envelope(result: MapResult, machine: RadialSRMParams, bus_voltage: float, resistance: float,
             speeds_rpm, *, current_limit: float | None = None, rms_limit: float | None = None,
             n_theta: int = N_THETA, n_on: int = N_ON, n_off: int = N_OFF) -> Envelope:
    """`current_limit` (A) is the hysteresis limit, at most the map's top current (the default). `rms_limit` (A)
    caps the phase RMS current over a rotor pole pitch: strokes above it are not used."""
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
    top = n_theta - 1
    on_axis = np.unique(np.round(np.linspace(*ON_RANGE, n_on) * top).astype(int))
    off_axis = np.unique(np.round(np.linspace(*OFF_RANGE, n_off) * top).astype(int))
    on, off = (a.ravel() for a in np.meshgrid(on_axis, off_axis, indexing="ij"))
    keep = off > on
    on, off = on[keep], off[keep]
    speeds = np.asarray(speeds_rpm, float)
    rows = []
    n = n_theta - 1
    q = machine.n_phases
    zero = np.zeros(n)
    traces = []
    for rpm in speeds:
        omega = rpm * 2 * math.pi / 60
        w_t, w_l, i2, valid = _simulate(t, omega, bus_voltage, resistance, on, off)
        if rms_limit is not None:
            valid &= i2 / period <= rms_limit**2 * (1 + _EPS)
        best = int(np.argmax(np.where(valid, w_t, -np.inf))) if valid.any() else -1
        if best < 0 or w_t[best] <= 0:
            rows.append((0.0, 0.0, t.theta[on[0]], t.theta[off[0]], 0.0, 0.0, 0.0))
            traces.append((zero,) * 5)
            continue
        *_, psi_g, i_g = _simulate(t, omega, bus_voltage, resistance, on[[best]], off[[best]], trace=True)
        psi_g, i_g = psi_g[:, 0], i_g[:, 0]
        i_bar = 0.5 * (i_g[:-1] + i_g[1:])
        v = omega * np.diff(psi_g) / (t.theta[1] - t.theta[0]) + resistance * i_bar
        tq = np.array([np.interp(i_g[k], t.current, t.torque[k]) for k in range(n)])
        traces.append((i_g[:-1], psi_g[:-1], v, tq, v * i_bar / bus_voltage))
        strokes_per_rev = machine.n_phases * machine.n_rotor_poles
        rows.append((strokes_per_rev * w_t[best] / (2 * math.pi),
                     machine.n_phases * resistance * i2[best] / period,
                     t.theta[on[best]], t.theta[off[best]], w_t[best], w_l[best],
                     math.sqrt(i2[best] / period)))
    torque, copper, th_on, th_off, work_t, work_l, i_rms = (np.array(c) for c in zip(*rows))
    cur, psi_w, volt, tq_w, bus = (np.array(c) for c in zip(*traces))
    wave = Waveforms(t.theta[:n], cur, psi_w, volt, tq_w, line_current(bus, q))
    power = torque * speeds * 2 * math.pi / 60
    return Envelope(speeds, torque, power, copper, th_on, th_off, work_t, work_l, i_rms, wave,
                    wave.line.mean(axis=1), np.sqrt((wave.line**2).mean(axis=1)),
                    power_factor(power, volt, cur, q))
