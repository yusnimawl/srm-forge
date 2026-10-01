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
N_ON, N_OFF = 40, 40


@dataclass(frozen=True)
class Envelope:
    """Per-speed best stroke. `torque` is the revolution average over all phases. `work_torque` is ∫T dθ and
    `work_loop` is ∮ i dψ for the chosen stroke; they agree up to discretisation."""
    speeds_rpm: np.ndarray
    torque: np.ndarray
    power: np.ndarray
    copper_loss: np.ndarray
    theta_on: np.ndarray
    theta_off: np.ndarray
    work_torque: np.ndarray
    work_loop: np.ndarray

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


def _simulate(t: _Tables, omega: float, volts: float, r: float, on: np.ndarray, off: np.ndarray):
    """One stroke for every (on, off) index pair. Returns (work_torque, work_loop, ∫i² dθ, valid)."""
    n = on.size
    psi, i = np.zeros(n), np.zeros(n)
    w_t, w_l, i2, peak = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    dth = t.theta[1] - t.theta[0]
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
    # the residual tail after alignment (up to 1 % of the peak flux) is not counted
    valid = psi <= 0.01 * np.maximum(peak, 1e-12)       # flux must be gone by alignment
    return w_t, w_l, i2, valid


def envelope(result: MapResult, machine: RadialSRMParams, bus_voltage: float, resistance: float,
             speeds_rpm, *, current_limit: float | None = None, n_theta: int = N_THETA, n_on: int = N_ON,
             n_off: int = N_OFF) -> Envelope:
    """`current_limit` (A) is the hysteresis limit, at most the map's top current (the default)."""
    require_complete(result)
    if result.excited != "A":
        raise ValueError("the envelope needs the phase A map (excited='A')")
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
    for rpm in speeds:
        omega = rpm * 2 * math.pi / 60
        w_t, w_l, i2, valid = _simulate(t, omega, bus_voltage, resistance, on, off)
        best = int(np.argmax(np.where(valid, w_t, -np.inf))) if valid.any() else -1
        if best < 0 or w_t[best] <= 0:
            rows.append((0.0, 0.0, t.theta[on[0]], t.theta[off[0]], 0.0, 0.0))
            continue
        strokes_per_rev = machine.n_phases * machine.n_rotor_poles
        rows.append((strokes_per_rev * w_t[best] / (2 * math.pi),
                     machine.n_phases * resistance * i2[best] / period,
                     t.theta[on[best]], t.theta[off[best]], w_t[best], w_l[best]))
    torque, copper, th_on, th_off, work_t, work_l = (np.array(c) for c in zip(*rows))
    return Envelope(speeds, torque, torque * speeds * 2 * math.pi / 60, copper, th_on, th_off, work_t, work_l)
