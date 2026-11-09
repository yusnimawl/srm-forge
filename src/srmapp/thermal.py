"""Continuous and peak torque per speed from the hot-spot limit: root finding on a thermal solver, losses from a callable."""
import dataclasses
import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from srmcore.maps import build_map
from srmcore.maps.end_winding import end_winding_inductance, with_end_winding
from srmcore.maps.stroke import stroke_angles
from srmcore.maps.validation import MEASURED_GAP, UncertaintyBudget
from srmcore.materials.library import load_material
from srmcore.mesh import build_machine_mesh
from srmcore.post.rotor_stress import GapClosure, RotorStress, gap_closure, rotor_stress
from srmcore.thermal.domain import thermal_domain
from srmcore.thermal.model import Temperatures, ThermalLoad, ThermalRunaway
from srmcore.thermal.solve import HotSpot, ThermalSolver

from . import __version__
from .case import CaseInputs, map_request
from .cooling import ROWS, CoolingSetup, K_IRON_HI, coefficients
from .drive.envelope import envelope, min_copper_stroke
from .evaluate import END_IMAGE_FACTOR, Evaluation
from .losses import N_ANGLES, _capped, check_loss_data, phase_current_samples, stroke_losses
from .sizing.generator import REFERENCE_TURNS
from .thermal_load import load_fn, point_heat
from .thermal_network import build_network
from .turns import rescale_turns, turns_scale

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


# The FE showed the centrifugal growth up to 9.4 % low (docs/r5-thermal-results.md); the gap uses the unsafe-side correction.
GROWTH_LOW = 0.094
_TORQUE_TOL = 1e-9


@dataclass(frozen=True)
class Rating:
    nominal: tuple[SpeedRating, ...]
    rated: tuple[SpeedRating, ...]
    shares: tuple[BudgetShare, ...]
    limit_c: float
    insulation_class: str
    cooling: CoolingSetup
    stress: RotorStress
    gap: dict[str, GapClosure]
    torque_factor: float
    n_strokes: int
    notes: tuple[str, ...]
    srmapp_version: str


def rate(inputs: CaseInputs, evaluation: Evaluation, *, em_budget: UncertaintyBudget | None = None,
         n_speeds: int = 6, n_angles: int = N_ANGLES, solver: str = "ngsolve", workers: int | None = None,
         cache_dir=None, progress: Callable[[str, int, int], None] | None = None,
         cancel: Callable[[], bool] | None = None) -> Rating:
    """Continuous and peak torque per speed from the hot-spot limit, nominal and with every budget row at its
    unfavourable end. Speeds: the base speed and linspace(max/n_speeds, max, n_speeds). The envelope that tops the
    bracket has no current-density limit. Raises MissingLossData, MissingCoolingData and ValueError (no winding, no
    thermal data) before any stroke solve, and InterruptedError when `cancel` fires."""
    req, design = inputs.requirements, inputs.design
    check_loss_data(design)
    w = evaluation.winding
    if evaluation.status != "ok" or w is None:
        raise ValueError(f"the evaluation has no winding (status {evaluation.status!r})")
    setup, limit = req.cooling, req.hot_spot_limit_c
    ref, i_map, _ = map_request(inputs)
    machine = evaluation.design.machine
    fill = machine.fill_factor
    q, tau = machine.n_phases, 2 * math.pi / machine.n_rotor_poles
    rho = load_material(machine.materials.coil).resistivity_at
    hot = dataclasses.replace(w, resistance=w.resistance * rho(limit) / rho(req.winding_temperature_c))
    speeds = sorted({req.base_speed_rpm} | set(np.linspace(req.max_speed_rpm / n_speeds, req.max_speed_rpm, n_speeds).tolist()))

    def check() -> None:
        if cancel is not None and cancel():
            raise InterruptedError("rating cancelled")

    static = build_machine_mesh(ref)
    domain = thermal_domain(static, ref.machine)
    g = MEASURED_GAP["peak_torque"]
    em_total = None if em_budget is None else em_budget.total["peak_torque"] - g / (1 - g)
    iron = (machine.materials.stator, machine.materials.rotor)

    def parts(rpm: float, rows: frozenset):
        c = coefficients(setup, machine, rpm, rows, em_total, fill=fill)
        return c, build_network(domain, machine, hot, fill, c, setup, iron_materials=iron)

    parts(speeds[0], frozenset())     # refusals before any map or stroke solve

    result = build_map(ref, i_map, solver=solver, workers=workers, cache_dir=cache_dir, cancel=cancel)
    if not result.complete:
        raise InterruptedError("map cancelled")
    result = rescale_turns(with_end_winding(result, end_winding_inductance(ref.machine, image_factor=END_IMAGE_FACTOR)),
                           turns_scale(ref.machine, w))
    env = envelope(result, ref.machine, req.bus_voltage_v, hot.resistance, speeds, current_limit=w.current)
    capped = _capped(result, w.current)
    angles = stroke_angles(static, tau, n_angles)
    scale = w.turns / (w.paths * REFERENCE_TURNS)
    wire = req.wires[w.wire] if w.wire is not None and req.wire_mode else None
    strokes: dict = {}
    band: dict = {}

    def stroke(rpm: float, torque: float):
        key = (rpm, torque)
        if key not in strokes:
            check()
            trace = min_copper_stroke(capped, ref.machine, req.bus_voltage_v, hot.resistance, rpm,
                                      torque * (1.0 - _TORQUE_TOL))
            sl = None
            if trace is not None:
                coil = phase_current_samples(trace.current, angles, tau, q) * scale
                sl = stroke_losses(static, ref, angles, coil, rpm, solver=solver, workers=workers, cache_dir=cache_dir,
                                   cancel=cancel, cut_process=req.cut_process, fractions=band)
            strokes[key] = None if sl is None else (trace, sl)
            if progress is not None:
                progress("strokes", len(strokes), len(strokes))
        return strokes[key]

    cache: dict = {}

    def at(rpm: float, rows: frozenset):
        if (rpm, rows) not in cache:
            cache[rpm, rows] = parts(rpm, rows)
        return cache[rpm, rows]

    def solver_for(rpm, rows):
        return lambda: ThermalSolver(at(rpm, rows)[1].problem)

    def load_at(rpm, rows):
        coeffs, net = at(rpm, rows)

        def load(torque: float):
            if torque <= 0:
                zero = ThermalLoad(np.zeros(len(domain.triangles)), {})
                return lambda t: zero
            s = stroke(rpm, torque * coeffs.torque_factor)
            if s is None:
                return None
            trace, sl = s
            heat = point_heat(sl, trace, domain, static, hot, wire, machine, limit, coeffs.iron_factor, rpm)
            return load_fn(heat, net, machine, hot)
        return load

    notes: list[str] = []
    if setup.placeholder:
        notes.append("cooling uses owner placeholders (ambient, housing or jacket dimensions and flow): ratings are not final")
    notes.append(f"iron loss rated at x{K_IRON_HI:g} (K_IRON_HI band)")
    notes.append("no measured continuous thermal case: the continuous rating has no measured check (spec §1 item 4)")
    if em_budget is None:
        notes.append("the EM budget was not computed: the EM torque row uses the 10 % floor")

    nominal, rated, shares = [], [], []
    for k, rpm in enumerate(speeds):
        omega = max(rpm, req.base_speed_rpm) * 2 * math.pi / 60
        start = None if req.continuous_power_w is None else req.continuous_power_w / omega
        top = float(env.torque[k])
        ratings = [rate_speed(rpm, top, limit, req.peak_duration_s, solver_for(rpm, rows), load_at(rpm, rows), start)
                   for rows in (frozenset(), frozenset(ROWS))]
        nominal.append(ratings[0])
        rated.append(ratings[1])
        t_rated = ratings[1].continuous_nm
        if t_rated > 0:
            def hot_spot(rows):
                load = load_at(rpm, rows)(t_rated)
                if load is None:
                    return None
                sv = ThermalSolver(at(rpm, rows)[1].problem)
                try:
                    return sv.hot_spot(sv.steady(load)).temperature_c
                except ThermalRunaway:
                    return None
            base = hot_spot(frozenset())
            for row in ROWS:
                if row in ("thermal_mesh", "end_winding_model"):
                    rise = 0.0
                else:
                    h = hot_spot(frozenset({row}))
                    rise = BIG_K if h is None or base is None else max(0.0, h - base)
                shares.append(BudgetShare(row, rpm, rise))
        else:
            notes.append(f"{rpm:.0f} rpm: rated continuous torque is 0, so no budget shares there")
        if progress is not None:
            progress("thermal", k + 1, len(speeds))
        check()

    for r in ratings_notes(nominal, rated):
        notes.append(r)
    c_all, n_all = at(speeds[0], frozenset(ROWS))
    for n in (*c_all.notes, *n_all.notes):
        if n not in notes:
            notes.append(n)

    rotor = load_material(machine.materials.rotor)
    last = rated[-1]
    stress = rotor_stress(machine, rotor.density, rotor.mechanical, req.max_speed_rpm, last.rotor_c)
    gaps: dict[str, GapClosure] = {}
    if rotor.mechanical is None:
        notes.append("the rotor material has no mechanical data: no gap closure")
    else:
        stator = load_material(machine.materials.stator)
        exp = lambda m: getattr(m.thermal, "expansion", None) if m.thermal is not None else None  # noqa: E731
        for key, factor, (t_r, t_s) in (("continuous_max", 1.0, (last.rotor_c, last.bore_c)),
                                        ("continuous_overspeed", 1.2, (last.rotor_c, last.bore_c)),
                                        ("peak_max", 1.0, (last.rotor_peak_c, last.bore_peak_c)),
                                        ("peak_overspeed", 1.2, (last.rotor_peak_c, last.bore_peak_c))):
            gc = gap_closure(machine, rotor.density, rotor.mechanical, exp(rotor), exp(stator),
                             factor * req.max_speed_rpm, t_r, t_s)
            grown = gc.centrifugal / (1.0 - GROWTH_LOW)
            gaps[key] = dataclasses.replace(gc, centrifugal=grown,
                                            closure=None if gc.closure is None else gc.closure + grown - gc.centrifugal)
        notes.append(f"gap closure: centrifugal growth raised by 1/(1 - {GROWTH_LOW}) for the FE comparison")
    coeffs_top = at(speeds[-1], frozenset(ROWS))[0]
    return Rating(tuple(nominal), tuple(rated), tuple(shares), limit, req.insulation_class, setup, stress, gaps,
                  coeffs_top.torque_factor, len(strokes), tuple(dict.fromkeys(notes)), __version__)


def ratings_notes(*sets) -> list[str]:
    return [f"{s.rpm:.0f} rpm: {s.note}" for group in sets for s in group if s.note]
