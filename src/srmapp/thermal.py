"""Continuous and peak torque per speed from the hot-spot limit: root finding on a thermal solver, losses from a callable."""
import dataclasses
import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from srmapp.thermal_fields import KINDS, ThermalFields
from srmcore.maps import build_map
from srmcore.maps.end_winding import end_winding_inductance, with_end_winding
from srmcore.maps.stroke import stroke_angles
from srmcore.model.design import Design
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
from .mechanical import mechanical_loss
from .requirements import Requirements
from .sizing.estimates import coil_side_area
from .sizing.generator import REFERENCE_TURNS
from .sizing.winding import Winding
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
    envelope_nm: float      # shaft torque: the EM envelope less the loss torque of the stroke at it (`ThermalContext.shaft_top`)
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


def peak_transient(solver: ThermalSolver, start: Temperatures, load: Callable, duration_s: float):
    """Transient from `start` under `load`, step count doubled until the end hot spot moves under STEP_TOL_K.
    Returns (final state, steps, hot spot at the maximum over the trace); raises ThermalRunaway."""
    n, last = STEPS0, None
    while True:
        tr = solver.transient(start, load, duration_s, n)
        end = tr.hot_spot_c[-1]
        if (last is not None and abs(end - last) < STEP_TOL_K) or n >= STEPS_MAX:
            break
        last, n = end, 2 * n
    # the trace holds no locations: the maximum is paired with the hot-spot location of the end state
    return tr.final, n, HotSpot(float(tr.hot_spot_c.max()), solver.hot_spot(tr.final).location)


def rate_speed(rpm: float, envelope_nm: float, limit_c: float, peak_duration_s: float,
               solver_for: Callable[[], ThermalSolver], load_at: Callable[[float], Callable | None],
               start_nm: float | None = None, keep: list | None = None) -> SpeedRating:
    """Rate one speed. `n_evaluations` counts torques for which `load_at` gave a load and a solve ran: one per steady
    torque and one per transient torque (the step-doubling re-solves of a transient are not counted).
    `transient_steps` is the step count of the final peak torque. `keep`, when given, receives `(t_c, t_p)` once: the
    steady and the end-of-peak temperatures behind the returned rating (None where there is no such state)."""
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
        if keep is not None:
            keep.append((t_c, t_p))
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
        try:
            final, n, top = peak_transient(solver, t_start, load, peak_duration_s)
        except ThermalRunaway:
            return BIG_K, None
        return top.temperature_c - limit_c, (final, n, top)

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
DRAG_TOL = 1e-3          # a stroke is enough when its torque is within this of the torque plus loss torque it must cover
DRAG_MAX_STROKES = 6     # secant steps converge in a few solves; hitting the cap means slow convergence or a shaft torque no stroke reaches


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


def required_torques(req: Requirements, rpm: float) -> tuple[float | None, float]:
    """(continuous torque or None, peak torque) in N·m the requirements ask for at `rpm`."""
    omega = max(rpm, req.base_speed_rpm) * 2 * math.pi / 60
    cont = None if req.continuous_power_w is None else req.continuous_power_w / omega
    return cont, req.peak_torque_nm if rpm <= req.base_speed_rpm else req.peak_power_w / omega


def rating_speeds(req: Requirements, n_speeds: int = 6) -> list[float]:
    """The base speed and linspace(max/n_speeds, max, n_speeds), ascending."""
    return sorted({req.base_speed_rpm} | {round(float(x), 6) for x in
                                          np.linspace(req.max_speed_rpm / n_speeds, req.max_speed_rpm, n_speeds)})


class ThermalContext:
    """Everything a rating needs before the speed loop: hot winding, meshes, the coefficient and network cache, the
    rescaled map, the stroke cache, `load_at` and `solver_for`. `result_ref` is the reference-turns map with the end
    winding added, or a callable returning it (called after the refusal probe, so a refusal costs no map)."""

    def __init__(self, req: Requirements, ref: Design, result_ref, w: Winding, *, em_budget: UncertaintyBudget | None = None,
                 n_angles: int = N_ANGLES, solver: str = "ngsolve", workers: int | None = None, cache_dir=None,
                 cancel: Callable[[], bool] | None = None, progress: Callable[[str, int, int], None] | None = None):
        self.req, self.ref, self.w = req, ref, w
        self.solver_name, self.workers, self.cache_dir, self.cancel, self.progress = solver, workers, cache_dir, cancel, progress
        # the machine with the chosen winding's turns and fill (what the evaluation's design holds)
        self.machine = machine = ref.machine.model_copy(update={
            "turns_per_pole": w.turns, "fill_factor": w.turns * w.copper_area / coil_side_area(ref.machine)})
        self.setup, self.limit = req.cooling, req.hot_spot_limit_c
        self.fill = machine.fill_factor
        self.q, self.tau = machine.n_phases, 2 * math.pi / machine.n_rotor_poles
        rho = load_material(machine.materials.coil).resistivity_at
        self.hot = dataclasses.replace(w, resistance=w.resistance * rho(self.limit) / rho(req.winding_temperature_c))
        self.static = build_machine_mesh(ref)
        self.domain = thermal_domain(self.static, ref.machine)
        g = MEASURED_GAP["peak_torque"]
        self.em_total = None if em_budget is None else em_budget.total["peak_torque"] - g / (1 - g)
        self.iron = (machine.materials.stator, machine.materials.rotor)
        self.cache: dict = {}
        self.strokes: dict = {}
        self.band: dict = {}
        self.at(rating_speeds(req)[0], frozenset())     # refusals before any map or stroke solve
        if callable(result_ref):
            result_ref = result_ref()
        self.result = rescale_turns(result_ref, turns_scale(ref.machine, w))
        self.angles = stroke_angles(self.static, self.tau, n_angles)
        self.capped = _capped(self.result, w.current)
        self.scale = w.turns / (w.paths * REFERENCE_TURNS)
        self.wire = req.wires[w.wire] if w.wire is not None and req.wire_mode else None
        self._env: dict = {}

    def check(self) -> None:
        if self.cancel is not None and self.cancel():
            raise InterruptedError("rating cancelled")

    def envelope_at(self, speeds: list[float]) -> dict[float, float]:
        """Peak torque of the envelope (winding current limit, no j_limit) per speed."""
        key = tuple(speeds)
        if key not in self._env:
            env = envelope(self.result, self.ref.machine, self.req.bus_voltage_v, self.hot.resistance, speeds,
                           current_limit=self.w.current)
            self._env[key] = {rpm: float(env.torque[k]) for k, rpm in enumerate(speeds)}
        return self._env[key]

    def at(self, rpm: float, rows: frozenset):
        if (rpm, rows) not in self.cache:
            c = coefficients(self.setup, self.machine, rpm, rows, self.em_total, fill=self.fill)
            self.cache[rpm, rows] = (c, build_network(self.domain, self.machine, self.hot, self.fill, c, self.setup,
                                                      iron_materials=self.iron))
        return self.cache[rpm, rows]

    def stroke(self, rpm: float, torque: float):
        key = (rpm, torque)
        if key not in self.strokes:
            self.check()
            req = self.req
            trace = min_copper_stroke(self.capped, self.ref.machine, req.bus_voltage_v, self.hot.resistance, rpm,
                                      torque * (1.0 - _TORQUE_TOL))
            sl = None
            if trace is not None:
                coil = phase_current_samples(trace.current, self.angles, self.tau, self.q) * self.scale
                sl = stroke_losses(self.static, self.ref, self.angles, coil, rpm, solver=self.solver_name,
                                   workers=self.workers, cache_dir=self.cache_dir, cancel=self.cancel,
                                   cut_process=req.cut_process, fractions=self.band)
            self.strokes[key] = None if sl is None else (trace, sl)
            if self.progress is not None:
                self.progress("strokes", len(self.strokes), len(self.strokes))
        return self.strokes[key]

    def solver_for(self, rpm, rows):
        return lambda: ThermalSolver(self.at(rpm, rows)[1].problem)

    def _drag_terms(self, rpm, rows):
        """Torque factor, iron factor, speed (rad/s) and the set's mechanical loss (W; the same for every torque)."""
        coeffs = self.at(rpm, rows)[0]
        mech = mechanical_loss(self.machine, self.req.bearing, rpm, unfavourable="mechanical_loss" in rows)
        return coeffs, rpm * 2 * math.pi / 60, mech

    def shaft_top(self, rpm, rows, em_top):
        """The shaft torque whose stroke ask stays within the EM envelope `em_top`: the loss torque of the stroke at
        `em_top` comes off em_top / factor. The stroke at the shaft top can carry more iron loss than the stroke at
        `em_top`; it then needs more EM torque than the envelope gives, `load_at` finds no stroke there and returns
        None, and `rate_speed` brackets down and stays on the feasible side, within its 1 % stop rule.
        Returns (torque, fell_back); fell_back is true when no stroke reaches `em_top`, and the top is
        then em_top / factor."""
        coeffs, omega, mech = self._drag_terms(rpm, rows)
        s = self.stroke(rpm, em_top)
        if s is None:
            return em_top / coeffs.torque_factor, True
        loss = (s[1].iron_w * coeffs.iron_factor + mech.total_w) / omega
        return max(em_top / coeffs.torque_factor - loss, 0.0) * (1.0 - DRAG_TOL), False

    def load_at(self, rpm, rows):
        coeffs, net = self.at(rpm, rows)
        domain = self.domain
        _, omega, mech = self._drag_terms(rpm, rows)

        def load(torque: float):
            if torque <= 0:
                zero = ThermalLoad(np.zeros(len(domain.triangles)), {})
                return lambda t: zero
            # `torque` is at the shaft: the stroke must also cover the iron, windage and friction torque. All the iron
            # loss counts as drag torque (safe side: part of the core loss is supplied electrically, so this
            # understates the shaft torque).
            ask, need, hist = torque * coeffs.torque_factor, float("nan"), []
            n, secant = 0, False
            while n < DRAG_MAX_STROKES:
                s = self.stroke(rpm, ask)
                if s is None:
                    if not secant:
                        return None
                    ask, secant = need, False   # a secant ask can pass the EM envelope; the plain step does not
                    continue
                n += 1
                trace, sl = s
                need = (torque + (sl.iron_w * coeffs.iron_factor + mech.total_w) / omega) * coeffs.torque_factor
                if trace.torque_avg >= need * (1.0 - DRAG_TOL):
                    break
                hist.append((ask, need))
                nxt = need
                secant = False
                if len(hist) >= 2:   # secant step on the fixed point a = need(a)
                    (a0, n0), (a1, n1) = hist[-2:]
                    den = 1.0 - (n1 - n0) / (a1 - a0) if a1 != a0 else 0.0
                    if den > 0:
                        nxt = a1 + (n1 - a1) / den
                        secant = math.isfinite(nxt) and nxt > 0 and nxt != need
                ask = nxt if math.isfinite(nxt) and nxt > 0 else need
            else:
                raise RuntimeError(f"no stroke covers the shaft torque {torque:g} N.m plus the loss torque within "
                                   f"{DRAG_MAX_STROKES} strokes at {rpm:g} rpm (last need {need:g} N.m)")
            heat = point_heat(sl, trace, domain, self.static, self.hot, self.wire, self.machine, self.limit,
                              coeffs.iron_factor, rpm, mech)
            return load_fn(heat, net, self.machine, self.hot)
        return load


def thermal_context(req: Requirements, ref: Design, result_ref, w: Winding, *, em_budget: UncertaintyBudget | None = None,
                    n_angles: int = N_ANGLES, solver: str = "ngsolve", workers: int | None = None, cache_dir=None,
                    cancel: Callable[[], bool] | None = None,
                    progress: Callable[[str, int, int], None] | None = None) -> ThermalContext:
    """Raises MissingLossData, MissingCoolingData and ValueError (no thermal data) before any solve."""
    check_loss_data(ref)
    return ThermalContext(req, ref, result_ref, w, em_budget=em_budget, n_angles=n_angles, solver=solver, workers=workers,
                          cache_dir=cache_dir, cancel=cancel, progress=progress)


NO_STROKE = "no stroke reaches the required torque"   # an EM limit at the rated torque factor
HOT_SPOT_ABOVE = "hot spot above the limit"             # continuous or peak, or a thermal runaway


@dataclass(frozen=True)
class RequirementCheck:
    holds: bool
    rpm: float | None                      # first failing speed
    continuous_hot_c: tuple[float, ...]    # per checked speed; nan where no continuous torque is required
    peak_hot_c: tuple[float, ...]
    notes: tuple[str, ...]
    reason: str = ""                       # NO_STROKE or HOT_SPOT_ABOVE at the failing speed; empty when it holds
    which: str = ""                        # "continuous" or "peak": the torque that failed; empty when it holds
    hot_c: float = float("nan")            # hot spot at the failing torque; nan for a runaway or no stroke


def check_requirement(ctx: ThermalContext, n_speeds: int = 6, rows: frozenset = frozenset(ROWS)) -> RequirementCheck:
    """Whether the set with `rows` at their unfavourable end (default: the rated set, every row of
    ROWS) holds the required continuous torque in steady state and the required peak torque for `peak_duration_s`
    (from that steady state) under the hot-spot limit at every rating
    speed. Stops at the first failing speed; a torque no stroke reaches fails."""
    req = ctx.req
    cont_hot, peak_hot, notes = [], [], []
    if req.continuous_power_w is None:
        notes.append("no continuous power required: continuous not checked")
    for rpm in rating_speeds(req, n_speeds):
        cont, peak = required_torques(req, rpm)
        solver = ctx.solver_for(rpm, rows)()
        load_at = ctx.load_at(rpm, rows)
        reason, which, hot = "", "", float("nan")
        try:
            start = load_at(0.0)
            if cont is not None:
                which = "continuous"
                load = load_at(cont)
                if load is None:
                    reason = NO_STROKE
                else:
                    start = solver.steady(load)
                    cont_hot.append(solver.hot_spot(start).temperature_c)
                    if cont_hot[-1] > ctx.limit:
                        reason, hot = HOT_SPOT_ABOVE, cont_hot[-1]
            else:
                cont_hot.append(float("nan"))
                start = solver.steady(start)
            if not reason:
                which = "peak"
                load = load_at(peak)
                if load is None:
                    reason = NO_STROKE
                else:
                    top = peak_transient(solver, start, load, req.peak_duration_s)[2]
                    peak_hot.append(top.temperature_c)
                    if top.temperature_c > ctx.limit:
                        reason, hot = HOT_SPOT_ABOVE, top.temperature_c
        except ThermalRunaway:
            reason = HOT_SPOT_ABOVE
        if reason:
            notes.append(f"{rpm:.0f} rpm: {reason}")
            return RequirementCheck(False, rpm, tuple(cont_hot), tuple(peak_hot), tuple(notes), reason, which, hot)
    return RequirementCheck(True, None, tuple(cont_hot), tuple(peak_hot), tuple(notes))


def rate(inputs: CaseInputs, evaluation: Evaluation, *, em_budget: UncertaintyBudget | None = None,
         n_speeds: int = 6, n_angles: int = N_ANGLES, solver: str = "ngsolve", workers: int | None = None,
         cache_dir=None, progress: Callable[[str, int, int], None] | None = None,
         cancel: Callable[[], bool] | None = None) -> Rating:
    """Continuous and peak torque per speed from the hot-spot limit, nominal and with every budget row at its
    unfavourable end. Speeds: the base speed and linspace(max/n_speeds, max, n_speeds). The envelope that tops the
    bracket has no current-density limit. Raises MissingLossData, MissingCoolingData and ValueError (no winding, no
    thermal data) before any stroke solve, and InterruptedError when `cancel` fires. `progress(step, done, total)`:
    "strokes" (each distinct stroke solved; the count is not known up front, so total = done) and "thermal" (speeds
    done of all)."""
    w = evaluation.winding
    if evaluation.status != "ok" or w is None:
        raise ValueError(f"the evaluation has no winding (status {evaluation.status!r})")
    req = inputs.requirements
    ref, i_map, _ = map_request(inputs)

    def reference_map():
        result = build_map(ref, i_map, solver=solver, workers=workers, cache_dir=cache_dir, cancel=cancel)
        if not result.complete:
            raise InterruptedError("map cancelled")
        return with_end_winding(result, end_winding_inductance(ref.machine, image_factor=END_IMAGE_FACTOR))

    ctx = thermal_context(req, ref, reference_map, w, em_budget=em_budget, n_angles=n_angles, solver=solver,
                          workers=workers, cache_dir=cache_dir, cancel=cancel, progress=progress)
    return rate_context(ctx, em_budget=em_budget, n_speeds=n_speeds, progress=progress)


def _fields(ctx, speeds, kept) -> ThermalFields:
    d = ctx.domain
    n = len(d.nodes)
    ends = tuple(ctx.at(speeds[0], frozenset(ROWS))[1].end_lumps.values())
    nan_row = np.full(n, np.nan, np.float32)
    end = lambda t: max(t.lumps[x] for x in ends) if t is not None else float("nan")  # noqa: E731
    rows = lambda i: np.array([t[i].field if t[i] is not None else nan_row for t in kept], np.float32).reshape(len(kept), n)  # noqa: E731
    return ThermalFields(
        d.nodes.astype(np.float32), d.triangles.astype(np.int32),
        np.array([KINDS.index(k) for k in d.element_kind], np.uint8), np.array(speeds, float),
        rows(0), rows(1), np.array([end(t[0]) for t in kept]), np.array([end(t[1]) for t in kept]))


def rate_context(ctx: ThermalContext, *, em_budget: UncertaintyBudget | None = None, n_speeds: int = 6,
                 progress: Callable[[str, int, int], None] | None = None,
                 fields_out: Callable[[ThermalFields], None] | None = None) -> Rating:
    """The rating of `rate` from the speed loop on, for a prepared context. `fields_out`, when given, is called once
    with the rated set's temperature fields."""
    req, machine, limit, setup = ctx.req, ctx.machine, ctx.limit, ctx.setup
    speeds = rating_speeds(req, n_speeds)
    env = ctx.envelope_at(speeds)
    at, strokes, check = ctx.at, ctx.strokes, ctx.check
    solver_for, load_at, domain = ctx.solver_for, ctx.load_at, ctx.domain

    notes: list[str] = []
    if setup.placeholder:
        notes.append("cooling uses owner placeholders (ambient, housing or jacket dimensions and flow): ratings are not final")
    notes.append(f"iron loss rated at x{K_IRON_HI[0][1]:g} up to {K_IRON_HI[0][0]:g} Hz, rising to "
                 f"x{K_IRON_HI[-1][1]:g} at {K_IRON_HI[-1][0]:g} Hz (K_IRON_HI band)")
    probe = mechanical_loss(machine, req.bearing, req.max_speed_rpm)
    notes.extend(probe.notes)
    notes.append("windage heats the rotor iron and bearing friction heats the end caps; the rated set takes the high end of both bands")
    notes.append("no measured continuous thermal case: the continuous rating has no measured check (spec §1 item 4)")
    if em_budget is None:
        notes.append("the EM budget was not computed: the EM torque row uses the 10 % floor")

    nominal, rated, shares = [], [], []
    kept: list = []
    for k, rpm in enumerate(speeds):
        omega = max(rpm, req.base_speed_rpm) * 2 * math.pi / 60
        start = None if req.continuous_power_w is None else req.continuous_power_w / omega
        top = env[rpm]
        ratings = []
        for rows in (frozenset(), frozenset(ROWS)):
            # SpeedRating.envelope_nm is the shaft envelope: the EM top less the loss torque of the stroke at it
            shaft, fell_back = ctx.shaft_top(rpm, rows, top)
            if fell_back and "no stroke reaches the EM top" not in " ".join(notes):
                notes.append("no stroke reaches the EM top at some speed: the shaft envelope there ignores the loss torque")
            ratings.append(rate_speed(rpm, shaft, limit, req.peak_duration_s, solver_for(rpm, rows), load_at(rpm, rows),
                                      start, keep=kept if rows else None))
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

    if fields_out is not None:
        fields_out(_fields(ctx, speeds, kept))
    for r in ratings_notes(nominal, rated):
        notes.append(r)
    c_all, n_all = at(speeds[0], frozenset(ROWS))
    for n in (*c_all.notes, *n_all.notes):
        if n not in notes:
            notes.append(n)

    rotor = load_material(machine.materials.rotor)
    last = rated[-1]
    known = math.isfinite(last.rotor_c)
    if not known:
        notes.append("rotor temperature unknown (no steady state): stress taken at the hot-spot limit temperature")
    stress = rotor_stress(machine, rotor.density, rotor.mechanical, req.max_speed_rpm,
                          last.rotor_c if known else limit)
    gaps: dict[str, GapClosure] = {}
    if rotor.mechanical is None:
        notes.append("the rotor material has no mechanical data: no gap closure")
    elif not known:
        notes.append("rotor temperature unknown (no steady state): no gap closure")
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
                  coeffs_top.torque_factor, sum(v is not None for v in strokes.values()), tuple(dict.fromkeys(notes)), __version__)


def ratings_notes(*sets) -> list[str]:
    return [f"{s.rpm:.0f} rpm: {s.note}" for group in sets for s in group if s.note]
