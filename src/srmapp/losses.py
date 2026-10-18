"""Efficiency map of an evaluated case: for each (speed, torque) the stroke with the least copper loss, the field of
that stroke on the reference-turns design, and from it the iron loss and the AC copper loss.

The map, the end-winding inductance and the turns rescaling are those of the evaluation, so the torque levels (k/n
of the envelope torque at each speed) are torques the evaluated winding delivers. Stroke solves run on the
reference-turns design with coil current = phase current x turns / (paths x REFERENCE_TURNS), so the ampere-turns
are the physical ones and the field needs no rescaling. Friction and windage are not included."""
import dataclasses
import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator

from srmcore.maps import build_map
from srmcore.maps.end_winding import end_winding_inductance, with_end_winding
from srmcore.maps.run import MapResult
from srmcore.maps.stroke import IronWaveforms, stroke_angles, stroke_fields, stroke_key
from srmcore.materials import loss_model
from srmcore.materials.library import load_material
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design
from srmcore.post.iron_loss import waveform_loss

from . import __version__
from .case import CaseInputs, map_request
from .copper import ac_copper_loss
from .drive.envelope import N_CURRENT, envelope, min_copper_stroke
from .evaluate import END_IMAGE_FACTOR, Evaluation
from .sizing.generator import REFERENCE_TURNS
from .turns import rescale_turns, turns_scale

NAN = float("nan")
# Largest relative change of the iron loss between the default angle count and twice that. The limit stands in
# until the slow convergence test has measured it.
ANGLE_CONVERGENCE_REL = 0.02
LOSS_GRADE_ALLOWANCE = {"A": 0.0, "B": 0.10, "C": 0.25}   # provisional, as for the B-H grades
# The envelope and the stroke search compute the same torque with different operation orders.
_TORQUE_TOL = 1e-9
_EXTRAPOLATION_NOTE = ("some iron has a peak flux density above the range of the loss data: its loss is extrapolated, "
                       "and the iron uncertainty adds the share of the loss from that iron times the fit error")


@dataclass(frozen=True)
class RegionLoss:
    hysteresis: float   # W
    classical: float
    excess: float


@dataclass(frozen=True)
class OperatingLoss:
    speed_rpm: float
    torque_nm: float                       # the requested torque level; the stroke delivers at least this
    reached: bool
    power_w: float                         # output power of the stroke's average torque
    copper_dc_w: float
    copper_ac_w: float | None              # None in density mode
    iron: dict[str, RegionLoss]            # stator_pole, stator_yoke, rotor_pole, rotor_yoke
    iron_w: float
    efficiency: float
    iron_uncertainty_rel: float
    beyond_fit_range: bool
    theta_on: float
    theta_off: float
    current_limit: float
    stroke_key: str                        # file stem of the cached fields under <cache_dir>/strokes/


@dataclass(frozen=True)
class LossResult:
    points: tuple[OperatingLoss, ...]      # speed-major, torque levels ascending
    speeds_rpm: tuple[float, ...]
    torque_fractions: tuple[float, ...]
    winding_temperature_c: float
    n_angles: int
    angle_convergence_rel: float
    srmapp_version: str
    notes: tuple[str, ...]


def check_loss_data(design: Design) -> None:
    """Raises MissingLossData when the stator or the rotor material has no loss model."""
    for name in {design.machine.materials.stator, design.machine.materials.rotor}:
        loss_model(name)


def phase_current_samples(table_current: np.ndarray, angles: np.ndarray, tau: float, n_phases: int) -> np.ndarray:
    """(len(angles), n_phases) phase currents at the rotor `angles`. `table_current` is phase A over one rotor pole
    pitch tau on the envelope's table angles k·tau/n (angle 0 is phase A aligned, as for the stroke angles); phase j
    is phase A delayed by j·tau/n_phases."""
    n = len(table_current)
    grid = np.arange(n) * tau / n
    return np.stack([np.interp(angles - j * tau / n_phases, grid, table_current, period=tau)
                     for j in range(n_phases)], axis=1)


def _capped(result: MapResult, i_top: float) -> MapResult:
    """The map on the current axis 0..i_top, sampled as the envelope tables sample it, so the stroke search sees the
    same flux and torque tables as an envelope with `current_limit=i_top`."""
    axis = np.linspace(0.0, i_top, N_CURRENT)
    return dataclasses.replace(result, currents=axis,
                               psi=PchipInterpolator(result.currents, result.psi, axis=1)(axis),
                               torque_arkkio=PchipInterpolator(result.currents, result.torque_arkkio, axis=1)(axis))


@dataclass(frozen=True)
class _Side:
    regions: dict[str, RegionLoss]
    fit_error: float
    grade: str
    high_b_share: float
    beyond: bool


def _side_loss(side: IronWaveforms, omega: float, stack_length: float) -> _Side:
    name = str(side.material[0])
    material = load_material(name)
    model = loss_model(name)
    el = waveform_loss(side.b / material.stacking_factor, side.centroids, side.period_s(omega), model, side.areas)
    mass = side.areas * stack_length * material.stacking_factor * material.density
    regions = {}
    for region in np.unique(side.region):
        m = side.region == region
        regions[str(region)] = RegionLoss(*(float(np.sum(w[m] * mass[m]))
                                            for w in (el.hysteresis, el.classical, el.excess)))
    return _Side(regions, model.fit_error, model.confidence, el.high_b_share, el.beyond_fit_range)


def _uncertainty(sides: list[_Side]) -> float:
    return max(s.fit_error * (1.0 + s.high_b_share) + LOSS_GRADE_ALLOWANCE[s.grade] + ANGLE_CONVERGENCE_REL
               for s in sides)


def _progress(progress, step: str, done: int, total: int) -> None:
    if progress is not None:
        progress(step, done, total)


def efficiency_map(inputs: CaseInputs, evaluation: Evaluation, *, n_speeds: int = 6, n_torques: int = 5,
                   n_angles: int = 60, solver: str = "ngsolve", workers: int | None = None, cache_dir=None,
                   progress: Callable[[str, int, int], None] | None = None,
                   cancel: Callable[[], bool] | None = None) -> LossResult:
    """Losses and efficiency at `n_speeds` speeds (linspace(max/n, max, n) of the requirements) and torque levels
    k/n_torques of the envelope torque at each speed. `progress(step, done, total)` reports "strokes" (stroke
    choices), "fields" (solved angles) and "losses". Raises MissingLossData before any work when a material has no
    loss data, ValueError for an evaluation without a winding, and InterruptedError when `cancel` fires."""
    design = inputs.design
    check_loss_data(design)
    w = evaluation.winding
    if evaluation.status != "ok" or w is None:
        raise ValueError(f"the evaluation has no winding (status {evaluation.status!r})")
    req = inputs.requirements
    ref, i_map, _ = map_request(inputs)
    machine = ref.machine
    q = machine.n_phases
    tau = 2 * math.pi / machine.n_rotor_poles

    result = build_map(ref, i_map, solver=solver, workers=workers, cache_dir=cache_dir, cancel=cancel)
    if not result.complete:
        raise InterruptedError("map cancelled")
    result = rescale_turns(with_end_winding(result, end_winding_inductance(machine, image_factor=END_IMAGE_FACTOR)),
                           turns_scale(machine, w))
    speeds = np.linspace(req.max_speed_rpm / n_speeds, req.max_speed_rpm, n_speeds)
    env = envelope(result, machine, req.bus_voltage_v, w.resistance, speeds, current_limit=w.current,
                   rms_limit=evaluation.j_limit * w.paths * w.copper_area)
    capped = _capped(result, w.current)

    fractions = tuple(k / n_torques for k in range(1, n_torques + 1))
    grid = [(i, f) for i in range(n_speeds) for f in fractions]
    strokes = []
    for done, (i, f) in enumerate(grid, 1):
        if cancel is not None and cancel():
            raise InterruptedError("efficiency map cancelled")
        torque = f * float(env.torque[i])
        strokes.append(min_copper_stroke(capped, machine, req.bus_voltage_v, w.resistance, float(speeds[i]),
                                         torque * (1.0 - _TORQUE_TOL)) if torque > 0 else None)
        _progress(progress, "strokes", done, len(grid))

    static = build_machine_mesh(ref)
    angles = stroke_angles(static, tau, n_angles)
    scale = w.turns / (w.paths * REFERENCE_TURNS)
    reached = sum(s is not None for s in strokes)
    solved = [0]

    def field_progress(done: int, total: int) -> None:
        _progress(progress, "fields", solved[0] + done, reached * len(angles))

    wire = req.wires[w.wire] if w.wire is not None and req.wire_mode else None
    stack = machine.stack_length
    points, side_flags = [], []
    for done, ((i, f), trace) in enumerate(zip(grid, strokes), 1):
        rpm, torque = float(speeds[i]), f * float(env.torque[i])
        if trace is None:
            points.append(OperatingLoss(rpm, torque, False, NAN, NAN, NAN if wire else None, {}, NAN, NAN, NAN,
                                        False, NAN, NAN, NAN, ""))
            continue
        phase = phase_current_samples(trace.current, angles, tau, q)
        coil = phase * scale
        omega = rpm * 2 * math.pi / 60
        fields = stroke_fields(static, ref, angles, coil, solver=solver, workers=workers, cache_dir=cache_dir,
                               progress=field_progress, cancel=cancel)
        solved[0] += len(angles)
        sides = [_side_loss(fields.stator, omega, stack), _side_loss(fields.rotor, omega, stack)]
        iron = {k: v for s in sides for k, v in s.regions.items()}
        iron_w = sum(r.hysteresis + r.classical + r.excess for r in iron.values())
        ac = None if wire is None else ac_copper_loss(w, wire, phase[:, 0], tau / omega, fields.b_coil,
                                                      fields.coil_side, fields.coil_areas, machine,
                                                      req.winding_temperature_c)
        power = trace.torque_avg * omega
        points.append(OperatingLoss(
            rpm, torque, True, power, trace.copper_dc_w, ac, iron, iron_w,
            power / (power + trace.copper_dc_w + (ac or 0.0) + iron_w), _uncertainty(sides),
            any(s.beyond for s in sides), trace.theta_on, trace.theta_off, trace.current_limit,
            stroke_key(ref, angles, coil, solver)))
        side_flags.extend(sides)
        _progress(progress, "losses", done, len(grid))
    _progress(progress, "losses", len(grid), len(grid))

    notes = []
    if any(s.high_b_share > 0 for s in side_flags):
        notes.append(_EXTRAPOLATION_NOTE)
    for name in sorted({design.machine.materials.stator, design.machine.materials.rotor}):
        model = loss_model(name)
        if not math.isclose(model.thickness, design.machine.lamination_thickness, rel_tol=1e-9):
            notes.append(f"{name}: the loss model uses the material's lamination thickness "
                         f"{model.thickness * 1e3:.3g} mm, the design has {design.machine.lamination_thickness * 1e3:.3g} mm")
    if wire is None:
        notes.append("density mode: no wire, so the AC copper loss is not computed")
    return LossResult(tuple(points), tuple(float(s) for s in speeds), fractions, req.winding_temperature_c,
                      len(angles), ANGLE_CONVERGENCE_REL, __version__, tuple(notes))
