"""Cheap consistency checks of a map (spec §7.3) and `analyse_map`, which bundles the map with its products."""
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.interpolate import PchipInterpolator

from ..materials.library import load_material
from ..model.design import Design
from .grids import aligned_angle
from .results import KeyNumbers, key_numbers
from .run import MapResult, require_complete
from .tables import DriveTables, angle_spline, dpsi_dtheta, drive_tables

MU0 = 4e-7 * math.pi
Status = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    value: float
    limit: float
    detail: str


@dataclass(frozen=True, eq=False)
class MapReport:
    result: MapResult
    key_numbers: KeyNumbers
    tables: DriveTables
    dpsi_dtheta: np.ndarray
    checks: tuple[Check, ...]

    @property
    def ok(self) -> bool:
        return all(c.status != "fail" for c in self.checks)


def _upper(name, value, limit, detail, bad: Status = "fail") -> Check:
    return Check(name, bad if value > limit else "pass", float(value), limit, detail)


def map_checks(result: MapResult, design: Design) -> tuple[Check, ...]:
    require_complete(result)
    m = design.machine
    e = result.circuits.index(result.excited)
    tau = 2 * math.pi / m.n_rotor_poles
    th_a = aligned_angle(m, result.excited)
    th_u = th_a + tau / 2
    cur, ang = result.currents, result.angles
    nz = cur > 0
    psi = result.psi[..., e]
    key = key_numbers(result, m)
    peak = key.peak_torque
    t_ark, t_vw = result.torque_arkkio, result.torque_virtual_work
    t_spl = angle_spline(ang, t_ark, tau)
    stroke = (th_a - tau / 2, th_a)
    stroke_work = t_spl.integrate(*stroke)                       # per current
    psi_spl = angle_spline(ang, psi, tau)
    checks = []

    w_spl = angle_spline(ang, result.coenergy, tau)
    dw = w_spl(th_a) - w_spl(th_u)
    checks.append(_upper("coenergy_torque", np.max(np.abs(stroke_work[nz] - dw[nz]) / np.abs(dw[nz])), 0.02,
                         "∫ T dθ over the motoring stroke against ΔW′ (aligned − unaligned), per current"))
    checks.append(_upper("arkkio_vs_nodal", np.max(np.abs(t_ark - t_vw)) / peak, 0.01,
                         "Arkkio against nodal-force torque, relative to peak torque"))
    ei = psi * cur[None, :]
    checks.append(_upper("energy_identity", np.max(np.abs(result.energy + result.coenergy - ei)) / ei.max(), 1e-3,
                         "W + W′ = ψ·i"))

    d_psi = psi_spl(th_a) - psi_spl(th_u)                        # per current
    loop = PchipInterpolator(cur, d_psi).integrate(0.0, cur[-1])
    checks.append(_upper("loop_energy", abs(loop - stroke_work[-1]) / loop, 0.02,
                         "∫(ψ_a − ψ_u) di against ∫ T dθ over the stroke at I_max"))

    checks.append(_upper("zero_mean_torque", np.max(np.abs(t_spl.integrate(0.0, tau))) / (peak * tau), 0.01,
                         "mean torque over one rotor pole pitch, relative to peak torque"))
    checks.append(_upper("zero_torque_aligned_unaligned", np.max(np.abs(t_spl([th_a, th_u]))) / peak, 0.01,
                         "torque at the aligned and unaligned angles, relative to peak torque"))

    x = (ang - th_a) % tau                                       # angle past alignment, [0, τ)
    eps = 1e-9 * tau
    leaving = (x > eps) & (x < tau / 2 - eps)
    approaching = x > tau / 2 + eps
    worst = max(np.max(t_ark[leaving] - 0.01 * peak, initial=0.0),
                np.max(-t_ark[approaching] - 0.01 * peak, initial=0.0))
    checks.append(_upper("sign_pattern", worst / peak, 0.0,
                         "torque negative while leaving alignment, positive while approaching it (1 % of peak tolerated)"))

    checks.append(Check("la_lu", "fail" if key.la_lu < 2 else "warn" if key.la_lu < 3 or key.la_lu > 15 else "pass",
                        key.la_lu, 2.0 if key.la_lu < 3 else 15.0, "La/Lu; pass in 3–15, warn in 2–3 and above 15"))

    d_min = np.min(np.diff(psi, axis=1)) / key.psi_max
    checks.append(Check("dpsi_di_positive", "pass" if d_min > 0 else "fail", float(d_min), 0.0,
                        "smallest ψ step along current, relative to ψ_max"))

    js = load_material(m.materials.stator).saturation_polarisation
    n_series = m.turns_per_pole * m.n_stator_poles / m.n_phases
    w_pole = 2 * m.bore_radius * math.sin(m.stator_pole_arc / 2)
    checks.append(_upper("psi_bound", key.psi_max / (n_series * js * w_pole * m.stack_length * 1.1), 1.0,
                         "ψ_max against N_series·Js·pole width·L with 10 % margin"))

    order = np.argsort(x)
    xs, top = x[order], psi[order, -1]
    down = xs <= tau / 2
    rise = np.max(np.diff(top[down]), initial=0.0)
    up_v = np.append(top[~down], top[0])
    fall = np.max(-np.diff(up_v), initial=0.0)
    checks.append(_upper("psi_decreasing", max(rise, fall) / key.psi_max, 0.005,
                         "ψ(θ, I_max) falls from aligned to unaligned and rises back (worst reversal / ψ_max)"))

    p_ph, n = m.n_stator_poles / m.n_phases, m.turns_per_pole
    la_est = p_ph * n**2 * MU0 * m.bore_radius * min(m.stator_pole_arc, m.rotor_pole_arc) * m.stack_length / m.air_gap
    ratio = key.la / la_est
    checks.append(Check("la_analytic", "warn" if not 0.5 <= ratio <= 1.5 else "pass", ratio,
                        0.5 if ratio < 0.5 else 1.5, "La / La_est, La_est = p·N²·µ0·r·min(βs, βr)·L/g"))
    h_r = m.rotor_outer_radius - m.rotor_yoke_outer_radius
    lu_est = p_ph * n**2 * MU0 * m.bore_radius * m.stator_pole_arc * m.stack_length / (m.air_gap + h_r)
    ratio = key.lu / lu_est
    checks.append(Check("lu_air_slot", "fail" if ratio < 1 else "pass", ratio, 1.0,
                        "Lu / Lu_est, Lu_est = p·N²·µ0·r·βs·L/(g + h_r); the air path is a lower bound"))
    b = float(np.max(result.b_peak)) / js
    checks.append(_upper("iron_b_peak", b, 1.15, "peak iron |B| / Js", bad="warn"))
    return tuple(checks)


def analyse_map(result: MapResult, design: Design) -> MapReport:
    require_complete(result)
    tau = 2 * math.pi / design.machine.n_rotor_poles
    return MapReport(result, key_numbers(result, design.machine), drive_tables(result),
                     dpsi_dtheta(result, tau), map_checks(result, design))
