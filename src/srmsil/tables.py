"""Motor tables for the simulator (i(θ,ψ), T(θ,ψ), field energy) and for the controller (i*(θ,T) in a C header)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

from srmapp.evaluate import Evaluation
from srmcore.maps.tables import angle_spline

N_CURRENT_FINE = 512


@dataclass(frozen=True)
class MotorData:
    """Phase A map at the chosen turns (end winding included). Angles span one rotor pole pitch, phase A aligned at 0."""
    angles: np.ndarray
    currents: np.ndarray
    psi: np.ndarray             # Wb-turns, (n_angles, n_currents)
    torque: np.ndarray          # N·m, same shape
    resistance: float           # Ω, phase
    n_phases: int
    n_rotor_poles: int
    bus_voltage: float          # V

    @property
    def pole_pitch(self) -> float:
        return 2 * math.pi / self.n_rotor_poles

    @property
    def stroke(self) -> float:
        return self.pole_pitch / self.n_phases


def motor_data(evaluation: Evaluation, bus_voltage: float) -> MotorData:
    m, w = evaluation.map, evaluation.winding
    if m is None or w is None:
        raise ValueError("evaluation has no map or winding")
    mach = evaluation.design.machine
    return MotorData(np.asarray(m.angles, float), np.asarray(m.currents, float), np.asarray(m.psi, float),
                     np.asarray(m.torque, float), float(w.resistance), mach.n_phases, mach.n_rotor_poles,
                     float(bus_voltage))


def motor_data_from_json(evaluation: dict, bus_voltage: float) -> MotorData:
    m, w = evaluation.get("map"), evaluation.get("winding")
    if not m or not w:
        raise ValueError("evaluation has no map or winding")
    mach = evaluation["design"]["machine"]
    return MotorData(np.asarray(m["angles"], float), np.asarray(m["currents"], float), np.asarray(m["psi"], float),
                     np.asarray(m["torque"], float), float(w["resistance"]), int(mach["n_phases"]),
                     int(mach["n_rotor_poles"]), float(bus_voltage))


def _on_grid(m: MotorData, theta: np.ndarray, current: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """ψ and torque on (theta, current): PCHIP in current, periodic cubic spline in angle."""
    psi = PchipInterpolator(m.currents, m.psi, axis=1)(current)
    torque = PchipInterpolator(m.currents, m.torque, axis=1)(current)
    return (angle_spline(m.angles, psi, m.pole_pitch)(theta),
            angle_spline(m.angles, torque, m.pole_pitch)(theta))


@dataclass(frozen=True)
class SimTables:
    current: np.ndarray         # A, (n_theta, n_psi)
    torque: np.ndarray          # N·m
    w_field: np.ndarray         # J, ∫₀^ψ i dψ′
    psi_max: float
    i_max: float
    roundtrip_error: float
    theta_step: float
    psi_step: float


def sim_tables(m: MotorData, n_theta: int = 720, n_psi: int = 512) -> SimTables:
    theta = np.arange(n_theta) * (m.pole_pitch / n_theta)
    i_top = float(m.currents[-1])
    cur = np.linspace(0.0, i_top, N_CURRENT_FINE)
    psi_f, torque_f = _on_grid(m, theta, cur)
    psi_f = np.maximum.accumulate(np.maximum(psi_f, 0.0), axis=1)
    psi_max = float(psi_f[:, -1].max())
    psi_grid = np.linspace(0.0, psi_max, n_psi)
    current = np.empty((n_theta, n_psi))
    torque = np.empty((n_theta, n_psi))
    err = 0.0
    for r in range(n_theta):
        row = psi_f[r]
        i_row = np.interp(psi_grid, row, cur)
        # beyond the row's top flux np.interp holds i_top; continue the last distinct segment's slope instead
        distinct = np.nonzero(np.diff(row) > 1e-12 * psi_max)[0]
        if distinct.size:
            q = distinct[-1]
            dpsi_seg = row[q + 1] - row[q]
            slope = (cur[q + 1] - cur[q]) / dpsi_seg
            t_slope = (torque_f[r, q + 1] - torque_f[r, q]) / dpsi_seg
            over = psi_grid > row[-1]
            i_row[over] = i_top + slope * (psi_grid[over] - row[-1])
        else:
            over, t_slope = np.zeros(n_psi, bool), 0.0
        current[r] = i_row
        torque[r] = np.interp(i_row, cur, torque_f[r])
        torque[r, over] = torque_f[r, -1] + t_slope * (psi_grid[over] - row[-1])
        inside = psi_grid <= row[-1]
        err = max(err, float(np.abs(np.interp(i_row[inside], cur, row) - psi_grid[inside]).max()) / psi_max)
    dw = 0.5 * (current[:, 1:] + current[:, :-1]) * np.diff(psi_grid)
    w = np.concatenate([np.zeros((n_theta, 1)), np.cumsum(dw, axis=1)], axis=1)
    return SimTables(np.ascontiguousarray(current), np.ascontiguousarray(torque), np.ascontiguousarray(w),
                     psi_max, i_top, err, m.pole_pitch / n_theta, psi_max / (n_psi - 1))


@dataclass(frozen=True)
class CtrlTables:
    i_of_t: np.ndarray          # A, float32, (n_theta_c, n_t)
    t_max: float
    i_max: float
    l_min: float
    l_max: float


def ctrl_tables(m: MotorData, n_theta: int = 180, n_t: int = 64) -> CtrlTables:
    theta = np.arange(n_theta) * (m.pole_pitch / n_theta)
    i_top = float(m.currents[-1])
    cur = np.linspace(0.0, i_top, N_CURRENT_FINE)
    _, torque = _on_grid(m, theta, cur)
    t_max = float(m.torque.max())
    targets = np.arange(n_t) * (t_max / (n_t - 1))
    out = np.zeros((n_theta, n_t), np.float32)
    for r in range(n_theta):
        row = torque[r]
        if row.max() <= 0:
            continue
        for j, tj in enumerate(targets):
            if tj >= row.max():
                out[r, j] = cur[int(np.argmax(row))]
                continue
            k = int(np.argmax(row >= tj))
            if k == 0:
                out[r, j] = cur[0]
            else:
                f = (tj - row[k - 1]) / (row[k] - row[k - 1])
                out[r, j] = cur[k - 1] + f * (cur[k] - cur[k - 1])
    k1 = int(np.argmax(m.currents > 0))
    dpsi = PchipInterpolator(m.currents, m.psi, axis=1)(m.currents[k1], 1)
    return CtrlTables(out, t_max, i_top, float(dpsi.min()), float(dpsi.max()))


def _f(x: float) -> str:
    t = f"{float(x):.9g}"
    return t + ("f" if any(c in t for c in ".eE") else ".0f")


def write_header(m: MotorData, ct: CtrlTables, path: Path) -> None:
    if not ct.t_max > 0:
        raise ValueError("motor map has no positive torque; no torque table can be written")
    n_theta, n_t = ct.i_of_t.shape
    rows = ",\n".join("  {" + ", ".join(_f(v) for v in r) + "}" for r in ct.i_of_t)
    Path(path).write_text(f"""#ifndef SRM_MOTOR_TABLES_H
#define SRM_MOTOR_TABLES_H

#include <math.h>

#define SRM_N_PHASES {m.n_phases}
#define SRM_N_ROTOR_POLES {m.n_rotor_poles}
#define SRM_POLE_PITCH_RAD {_f(m.pole_pitch)}
#define SRM_STROKE_RAD {_f(m.stroke)}
#define SRM_I_MAX_A {_f(ct.i_max)}
#define SRM_T_MAX_NM {_f(ct.t_max)}
#define SRM_R_OHM {_f(m.resistance)}
#define SRM_L_MIN_H {_f(ct.l_min)}
#define SRM_L_MAX_H {_f(ct.l_max)}
#define SRM_I_OF_T_N_THETA {n_theta}
#define SRM_I_OF_T_N_T {n_t}

/* i*(theta, T): rows are theta = j * pole pitch / N_THETA in the phase's own frame, columns T = k * T_MAX / (N_T - 1). */
static const float srm_i_of_t_table[SRM_I_OF_T_N_THETA][SRM_I_OF_T_N_T] = {{
{rows}
}};

/* Bilinear lookup; theta_phase is wrapped periodically, t_nm is clamped to [0, SRM_T_MAX_NM]. */
static inline float srm_i_of_t(float theta_phase, float t_nm)
{{
    if (!(fabsf(theta_phase) < 1.0e30f)) theta_phase = 0.0f;
    float u = theta_phase / SRM_POLE_PITCH_RAD;
    u -= floorf(u);
    float x = u * (float)SRM_I_OF_T_N_THETA;
    int j = (int)x;
    float fj = x - (float)j;
    if (j >= SRM_I_OF_T_N_THETA) j -= SRM_I_OF_T_N_THETA;
    int j1 = (j + 1 >= SRM_I_OF_T_N_THETA) ? 0 : j + 1;
    if (!(t_nm > 0.0f)) t_nm = 0.0f;
    if (t_nm > SRM_T_MAX_NM) t_nm = SRM_T_MAX_NM;
    float y = t_nm / SRM_T_MAX_NM * (float)(SRM_I_OF_T_N_T - 1);
    int k = (int)y;
    if (k > SRM_I_OF_T_N_T - 2) k = SRM_I_OF_T_N_T - 2;
    float fk = y - (float)k;
    float a = srm_i_of_t_table[j][k] * (1.0f - fk) + srm_i_of_t_table[j][k + 1] * fk;
    float b = srm_i_of_t_table[j1][k] * (1.0f - fk) + srm_i_of_t_table[j1][k + 1] * fk;
    return a * (1.0f - fj) + b * fj;
}}

#endif
""", encoding="utf-8")
