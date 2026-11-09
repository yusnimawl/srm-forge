"""Continuous and peak torque per speed from the hot-spot limit: root finding on a thermal solver, losses from a callable."""
from dataclasses import dataclass
from typing import Callable

import numpy as np

from srmcore.thermal.model import Temperatures, ThermalRunaway
from srmcore.thermal.solve import HotSpot, ThermalSolver

BRACKET_REL = 0.01       # stop when the bracket is under this share of the envelope torque
TOL_K = 0.5              # or when the hot spot is this close below the limit
MAX_EVALS = 12
STEPS0, STEPS_MAX, STEP_TOL_K = 50, 3200, 0.1
BIG_K = 1000.0           # excess assigned to an infeasible torque (no stroke, or runaway)


@dataclass(frozen=True)
class SpeedRating:
    rpm: float
    envelope_nm: float
    continuous_nm: float
    peak_nm: float
    continuous_hot_spot: HotSpot
    peak_hot_spot: HotSpot
    rotor_c: float
    rotor_peak_c: float
    bore_c: float
    bore_peak_c: float
    n_evaluations: int
    transient_steps: int
    note: str = ""
    start_nm: float | None = None


@dataclass(frozen=True)
class BudgetShare:
    row: str
    rpm: float
    hot_spot_rise_k: float


def _kind_mean(solver: ThermalSolver, t: Temperatures, kind: str) -> float:
    d = solver.problem.domain
    sel = np.flatnonzero(d.element_kind == kind)
    if len(sel) == 0:
        return float("nan")
    tri = d.triangles[sel]
    p = d.nodes[tri]
    area = 0.5 * np.abs((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1]) - (p[:, 1, 1] - p[:, 0, 1]) * (p[:, 2, 0] - p[:, 0, 0]))
    return float(np.average(t.field[tri].mean(axis=1), weights=area))


def _illinois(f, a, fa, pa, b, fb, span):
    """Root of f on [a, b], f(a) <= 0 < f(b); f(x) -> (value, payload). Returns the feasible end (x, value, payload)."""
    side, evals = 0, 0
    fa_w, fb_w = fa, fb
    while b - a >= BRACKET_REL * span and not (-TOL_K < fa <= 0) and evals < MAX_EVALS - 2:
        x = b - fb_w * (b - a) / (fb_w - fa_w)
        x = min(max(x, a + 1e-9 * span), b - 1e-9 * span)
        fx, px = f(x)
        evals += 1
        if fx <= 0:
            a, fa, fa_w, pa = x, fx, fx, px
            if side == -1:
                fb_w *= 0.5
            side = -1
        else:
            b, fb, fb_w = x, fx, fx
            if side == 1:
                fa_w *= 0.5
            side = 1
    return a, fa, pa


def rate_speed(rpm: float, envelope_nm: float, limit_c: float, peak_duration_s: float,
               solver_for: Callable[[], ThermalSolver], load_at: Callable[[float], Callable | None],
               start_nm: float | None = None) -> SpeedRating:
    """Rate one speed. `n_evaluations` counts torques for which `load_at` gave a load and a solve ran: one per steady
    torque and one per transient torque (the step-doubling re-solves of a transient are not counted).
    `transient_steps` is the step count of the final peak torque."""
    solver = solver_for()
    n_eval = 0
    none_spot = HotSpot(float("nan"), "none")

    def steady(torque):
        nonlocal n_eval
        load = load_at(torque)
        if load is None:
            return BIG_K, None
        n_eval += 1
        try:
            t = solver.steady(load)
        except ThermalRunaway:
            return BIG_K, None
        return solver.hot_spot(t).temperature_c - limit_c, t

    def result(cont, peak, t_c, t_p, steps, note="", peak_max=None):
        hs_c = solver.hot_spot(t_c) if t_c else none_spot
        hs_p = solver.hot_spot(t_p) if t_p else hs_c
        if peak_max is not None:
            hs_p = peak_max
        z = lambda t, k: _kind_mean(solver, t, k) if t else float("nan")
        return SpeedRating(rpm, envelope_nm, cont, peak, hs_c, hs_p, z(t_c, "rotor_iron"), z(t_p or t_c, "rotor_iron"),
                           z(t_c, "stator_iron"), z(t_p or t_c, "stator_iron"), n_eval, steps, note, start_nm)

    f0, t0 = steady(0.0)
    if f0 > 0:
        return result(0.0, 0.0, t0, None, 0, "no steady state within the hot-spot limit at zero torque")
    fe, te = steady(envelope_nm)
    if fe <= 0:
        cont, t_c = envelope_nm, te
    else:
        cont, _, t_c = _illinois(steady, 0.0, f0, t0, envelope_nm, fe, envelope_nm)
    if cont >= envelope_nm:
        return result(cont, cont, t_c, None, 0)

    note = ""
    t_start = t_c
    if start_nm is None:
        note = ("no continuous requirement: the peak starts from the rated continuous state, "
                "so it is about the continuous rating")
    elif start_nm < cont:
        _, t_start = steady(max(start_nm, 0.0))
        if t_start is None:
            t_start = t_c
    else:
        note = "required continuous torque at or above the rated continuous: the peak starts from the rated continuous state"

    def transient(torque):
        nonlocal n_eval
        load = load_at(torque)
        if load is None:
            return BIG_K, None
        n_eval += 1
        n, last = STEPS0, None
        while True:
            try:
                tr = solver.transient(t_start, load, peak_duration_s, n)
            except ThermalRunaway:
                return BIG_K, None
            end = tr.hot_spot_c[-1]
            if (last is not None and abs(end - last) < STEP_TOL_K) or n >= STEPS_MAX:
                break
            last, n = end, 2 * n
        # the trace holds no locations: the maximum is paired with the hot-spot location of the end state
        top = HotSpot(float(tr.hot_spot_c.max()), solver.hot_spot(tr.final).location)
        return top.temperature_c - limit_c, (tr.final, n, top)

    fp, pe = transient(envelope_nm)
    if fp <= 0:
        return result(cont, envelope_nm, t_c, pe[0], pe[1], note, pe[2])
    fc, pc = transient(cont)   # bracket start: the hot spot at the continuous torque from the start state
    if fc > 0:
        note = (note + "; " if note else "") + "the continuous torque exceeds the limit from the start state: peak = continuous"
        return result(cont, cont, t_c, pc[0] if pc else None, pc[1] if pc else 0, note, pc[2] if pc else None)
    peak, _, (t_p, steps, top) = _illinois(transient, cont, fc, pc, envelope_nm, fp, envelope_nm)
    return result(cont, peak, t_c, t_p, steps, note, top)
