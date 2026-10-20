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
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

from srmcore.maps import build_map
from srmcore.maps.end_winding import end_winding_inductance, with_end_winding
from srmcore.maps.run import MapResult
from srmcore.maps.stroke import DEFAULT_STROKE_ANGLES, IronWaveforms, StrokeFields, iron_waveforms, stroke_angles, stroke_fields, stroke_key
from srmcore.materials import LossModel, loss_model
from srmcore.materials.library import load_material
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design
from srmcore.post.cut_edge import B0, CUT_PROCESSES, band_fraction, edge_multiplier
from srmcore.post.iron_loss import SHARE_LIMIT, waveform_loss

from . import __version__, field
from .case import CaseInputs, map_request
from .copper import ac_copper_loss
from .drive.envelope import N_CURRENT, envelope, min_copper_stroke
from .evaluate import END_IMAGE_FACTOR, Evaluation
from .sizing.generator import REFERENCE_TURNS
from .turns import rescale_turns, turns_scale

NAN = float("nan")
N_ANGLES = DEFAULT_STROKE_ANGLES
# Largest relative change of the iron loss between the default angle count and twice that. The limit stands in
# until the slow convergence test has measured it.
ANGLE_CONVERGENCE_REL = 0.02
LOSS_GRADE_ALLOWANCE = {"A": 0.0, "B": 0.10, "C": 0.25}   # provisional, as for the B-H grades
# The envelope and the stroke search compute the same torque with different operation orders.
_TORQUE_TOL = 1e-9
_EXTRAPOLATION_NOTE = ("some iron has a peak flux density above the range of the loss data: its loss is extrapolated, "
                       "and the iron uncertainty only adds the share of the loss from that iron times the fit error; "
                       "it does not bound the error of the loss above the range (1.3 T for the library data)")
_LOW_B_NOTE = ("more than 5 % of the iron loss of a side comes from iron below the flux density range of the loss "
               "data: the model over-predicts there")
CUT_EDGE_NOTE = ("cut-edge parameters are grade C for 10JNEX900 (no thin-gauge data); stacking and joining are not "
                 "modelled; with the cut process unspecified the range is one-sided (wedm low to laser high)")
_FREQUENCY_NOTE = ("the flux waveform has a fundamental or harmonic above the frequency range of the loss data: "
                   "the loss model is extrapolated in frequency")


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
    cut_edge_rel: tuple[float, float] = (NAN, NAN)    # iron loss at the low and high end of the cut range, relative to iron_w, minus 1
    cut_edge_factor: dict[str, float] = dataclasses.field(default_factory=dict)   # per region: hysteresis + excess with over without


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
    cut_process: str = "unspecified"


def range_notes(sides: list[_Side]) -> list[str]:
    """One note per cause of leaving the fit range that is present on any side."""
    notes = []
    if any(s.high_b_share > 0 for s in sides):
        notes.append(_EXTRAPOLATION_NOTE)
    if any(s.low_b_share > SHARE_LIMIT for s in sides):
        notes.append(_LOW_B_NOTE)
    if any(s.beyond and s.high_b_share <= SHARE_LIMIT and s.low_b_share <= SHARE_LIMIT for s in sides):
        notes.append(_FREQUENCY_NOTE)
    return notes


def thickness_notes_for(design: Design) -> list[str]:
    """Notes on a lamination thickness that differs from the loss data's (or is missing)."""
    d = design.machine.lamination_thickness
    notes = []
    for name in sorted({design.machine.materials.stator, design.machine.materials.rotor}):
        t = loss_model(name).thickness
        if d is None:
            notes.append(f"{name}: design has no lamination thickness; using the loss data's {t * 1e3:.3g} mm")
        elif not math.isclose(t, d, rel_tol=1e-9):
            notes.append(f"{name}: loss data measured at {t * 1e3:.3g} mm; classical eddy scaled to the design's "
                         f"{d * 1e3:.3g} mm")
    return notes


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
    low_b_share: float
    beyond: bool
    classical_w: float = 0.0               # W, classical eddy loss of the whole side
    he_mass: np.ndarray | None = None      # W per element, hysteresis + excess before any cut-edge multiplier
    base_he: dict[str, float] | None = None   # W per region, the same summed


def design_model(model: LossModel, thickness: float | None) -> LossModel:
    """`model` with the classical eddy term of a lamination of `thickness` (k_c and the eddy term scale as d²);
    unchanged when the design gives no thickness."""
    if thickness is None:
        return model
    return dataclasses.replace(model, thickness=thickness, k_c=model.k_c * (thickness / model.thickness) ** 2)


def _side_loss(side: IronWaveforms, omega: float, stack_length: float, model: LossModel | None = None,
               thickness: float | None = None, multiplier: np.ndarray | None = None) -> _Side:
    name = str(side.material[0])
    material = load_material(name)
    model = design_model(loss_model(name) if model is None else model, thickness)
    el = waveform_loss(side.b / material.stacking_factor, side.centroids, side.period_s(omega), model, side.areas)
    mass = side.areas * stack_length * material.stacking_factor * material.density
    he_mass = (el.hysteresis + el.excess) * mass
    hyst, excess = (el.hysteresis, el.excess) if multiplier is None else (el.hysteresis * multiplier,
                                                                         el.excess * multiplier)
    regions, base_he = {}, {}
    for region in np.unique(side.region):
        m = side.region == region
        regions[str(region)] = RegionLoss(*(float(np.sum(w[m] * mass[m])) for w in (hyst, el.classical, excess)))
        base_he[str(region)] = float(np.sum(he_mass[m]))
    return _Side(regions, model.fit_error, model.confidence, el.high_b_share, el.low_b_share, el.beyond_fit_range,
                 float(np.sum(el.classical * mass)), he_mass, base_he)


@dataclass(frozen=True)
class StrokeLoss:
    fields: StrokeFields
    sides: tuple[_Side, _Side]             # stator, rotor
    iron: dict[str, RegionLoss]            # W per region
    iron_w: float
    cut_edge_rel: tuple[float, float] = (NAN, NAN)    # iron loss at the low and high end of the range over iron_w, minus 1
    cut_edge_factor: dict[str, float] = dataclasses.field(default_factory=dict)   # per region, hysteresis + excess


def iron_fractions(static, delta: float) -> tuple[np.ndarray, np.ndarray]:
    """Share of each iron element within `delta` of a cut edge, for the stator and the rotor, in the element order of
    the `IronWaveforms` of `iron_waveforms`."""
    kinds = np.array([static.region_kind[n] for n in static.region_names])
    out = []
    for part, iron in ((static.stator, "stator_iron"), (static.rotor, "rotor_iron")):
        out.append(band_fraction(part.nodes, part.triangles[kinds[part.region_ids] == iron], delta))
    return out[0], out[1]


def stroke_losses(static, design: Design, angles: np.ndarray, coil_currents: np.ndarray, rpm: float, *,
                  solver: str = "ngsolve", workers: int | None = None, cache_dir=None, progress=None, cancel=None,
                  model: LossModel | None = None, cut_process: str = "unspecified",
                  fractions: dict[float, tuple[np.ndarray, np.ndarray]] | None = None) -> StrokeLoss:
    """Iron loss of a given stroke: the fields at the rotor `angles` (one pole pitch) with the coil currents
    `coil_currents` (n_angles, n_phases), at `rpm`. `model` replaces the loss model of the iron materials.
    `cut_process` ("unspecified" or a key of CUT_PROCESSES) raises the hysteresis and excess loss near cut edges; `cut_edge_rel` is the iron loss range over the process's
    width coefficient (for "unspecified": wedm low to laser high) relative to `iron_w`. `fractions` caches
    `iron_fractions(static, delta)` by delta; pass the same dict for every stroke on one static mesh."""
    fields = stroke_fields(static, design, angles, coil_currents, solver=solver, workers=workers,
                           cache_dir=cache_dir, progress=progress, cancel=cancel)
    omega = rpm * 2 * math.pi / 60
    d = design.machine.lamination_thickness
    unspecified = cut_process == "unspecified"
    fractions = {} if fractions is None else fractions

    def frac(delta: float) -> tuple[np.ndarray, np.ndarray]:
        if delta not in fractions:
            fractions[delta] = iron_fractions(static, delta)
        return fractions[delta]

    if unspecified:
        proc, mult = None, (None, None)
    else:
        proc = CUT_PROCESSES[cut_process]
        mult = tuple(edge_multiplier(f, proc.a, proc.delta) for f in frac(proc.delta))
    sides = (_side_loss(fields.stator, omega, design.machine.stack_length, model, d, mult[0]),
             _side_loss(fields.rotor, omega, design.machine.stack_length, model, d, mult[1]))
    iron = {k: v for s in sides for k, v in s.regions.items()}
    iron_w = sum(r.hysteresis + r.classical + r.excess for r in iron.values())
    base_he = {k: v for s in sides for k, v in s.base_he.items()}
    factor = {k: 1.0 if unspecified or base_he[k] <= 0 else (r.hysteresis + r.excess) / base_he[k]
              for k, r in iron.items()}

    def total(a: float, delta: float) -> float:
        if a == 0:
            return sum(s.classical_w + float(np.sum(s.he_mass)) / B0 for s in sides)
        return sum(s.classical_w + float(np.sum(s.he_mass * (1 + a / (2 * delta) * f))) / B0
                   for s, f in zip(sides, frac(delta)))

    if unspecified:
        wedm, laser = CUT_PROCESSES["wedm"], CUT_PROCESSES["laser"]
        low, high = total(wedm.a_low, wedm.delta), total(laser.a_high, laser.delta)
    else:
        low, high = total(proc.a_low, proc.delta), total(proc.a_high, proc.delta)
    return StrokeLoss(fields, sides, iron, iron_w, (low / iron_w - 1.0, high / iron_w - 1.0), factor)


def iron_uncertainty(sides: list[_Side]) -> float:
    return max(s.fit_error * (1.0 + s.high_b_share) + LOSS_GRADE_ALLOWANCE[s.grade] + ANGLE_CONVERGENCE_REL
               for s in sides)


def _progress(progress, step: str, done: int, total: int) -> None:
    if progress is not None:
        progress(step, done, total)


def efficiency_map(inputs: CaseInputs, evaluation: Evaluation, *, n_speeds: int = 6, n_torques: int = 5,
                   n_angles: int = N_ANGLES, solver: str = "ngsolve", workers: int | None = None, cache_dir=None,
                   progress: Callable[[str, int, int], None] | None = None,
                   cancel: Callable[[], bool] | None = None) -> LossResult:
    """Losses and efficiency at `n_speeds` speeds (linspace(max/n, max, n) of the requirements) and torque levels
    k/n_torques of the envelope torque at each speed. `progress(step, done, total)` reports "strokes" (stroke
    choices), "fields" (solved angles) and "losses". Raises MissingLossData before any work when a material has no
    loss data, ValueError for an evaluation without a winding, and InterruptedError when `cancel` fires."""
    design = inputs.design
    check_loss_data(design)
    thickness_notes = thickness_notes_for(design)
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
    points, side_flags, band = [], [], {}
    for done, ((i, f), trace) in enumerate(zip(grid, strokes), 1):
        rpm, torque = float(speeds[i]), f * float(env.torque[i])
        if trace is None:
            points.append(OperatingLoss(rpm, torque, False, NAN, NAN, NAN if wire else None, {}, NAN, NAN, NAN,
                                        False, NAN, NAN, NAN, "", (NAN, NAN), {}))
            continue
        phase = phase_current_samples(trace.current, angles, tau, q)
        coil = phase * scale
        omega = rpm * 2 * math.pi / 60
        sl = stroke_losses(static, ref, angles, coil, rpm, solver=solver, workers=workers, cache_dir=cache_dir,
                           progress=field_progress, cancel=cancel,
                           cut_process=req.cut_process, fractions=band)
        fields, sides, iron, iron_w = sl.fields, list(sl.sides), sl.iron, sl.iron_w
        solved[0] += len(angles)
        ac = None if wire is None else ac_copper_loss(w, wire, phase[:, 0], tau / omega, fields.b_coil,
                                                      fields.coil_side, fields.coil_areas, machine,
                                                      req.winding_temperature_c)
        power = trace.torque_avg * omega
        points.append(OperatingLoss(
            rpm, torque, True, power, trace.copper_dc_w, ac, iron, iron_w,
            power / (power + trace.copper_dc_w + (ac or 0.0) + iron_w), iron_uncertainty(sides),
            any(s.beyond for s in sides), trace.theta_on, trace.theta_off, trace.current_limit,
            stroke_key(ref, angles, coil, solver), sl.cut_edge_rel, sl.cut_edge_factor))
        side_flags.extend(sides)
        _progress(progress, "losses", done, len(grid))
    _progress(progress, "losses", len(grid), len(grid))

    notes = []
    notes.extend(range_notes(side_flags))
    notes.extend(thickness_notes)
    notes.append(CUT_EDGE_NOTE)
    if wire is None:
        notes.append("density mode: no wire, so the AC copper loss is not computed")
    return LossResult(tuple(points), tuple(float(s) for s in speeds), fractions, req.winding_temperature_c,
                      len(angles), ANGLE_CONVERGENCE_REL, __version__, tuple(notes), req.cut_process)


def locate(tri_nodes: np.ndarray, point: np.ndarray) -> tuple[int, bool]:
    """Index of the triangle (rows of `tri_nodes`, (m, 3, 2)) that contains `point` and True; when none does, the
    triangle with the nearest centroid and False."""
    a, b, c = tri_nodes[:, 0], tri_nodes[:, 1], tri_nodes[:, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    x, y = point[0] - c[:, 0], point[1] - c[:, 1]
    l1 = ((b[:, 1] - c[:, 1]) * x + (c[:, 0] - b[:, 0]) * y) / d
    l2 = ((c[:, 1] - a[:, 1]) * x + (a[:, 0] - c[:, 0]) * y) / d
    inside = np.flatnonzero(np.minimum(np.minimum(l1, l2), 1.0 - l1 - l2) >= 0.0)
    if inside.size:
        return int(inside[0]), True
    return int(np.argmin(np.hypot(*(tri_nodes.mean(axis=1) - point).T))), False


def b_waveform(design: Design, key: str, n_angles: int, rpm: float, x: float, y: float, *,
               cache_dir) -> dict:
    """Lamination flux density over one period at the iron element containing (x, y) (metres, the stator frame with
    the rotor at angle 0; the nearest element when the point is outside the iron). The fields are the cached stroke
    `key` of `efficiency_map` run with `n_angles` and `design` (the reference-turns design). Returns t (s), b_r and
    b_t (T, radial and tangential about the axis, as the loss model sees them: finite-element B divided by the
    stacking factor), the region and the side. Raises FileNotFoundError when the cache file is gone."""
    with np.load(Path(cache_dir) / "strokes" / f"{key}.npz") as f:
        b_stator, b_rotor = f["stator"], f["rotor"]
    static = field.static_mesh(design.to_json())
    angles = stroke_angles(static, 2 * math.pi / design.machine.n_rotor_poles, n_angles)
    if len(angles) != b_stator.shape[0]:
        raise ValueError(f"the cached stroke has {b_stator.shape[0]} angles, {n_angles} requested give {len(angles)}")
    sides = dict(zip(("stator", "rotor"), iron_waveforms(static, design, angles, b_stator, b_rotor)))
    point = np.array([x, y], dtype=float)
    found = {}
    for name, part, iron in (("stator", static.stator, "stator_iron"), ("rotor", static.rotor, "rotor_iron")):
        kind = np.array([static.region_kind[n] for n in static.region_names])[part.region_ids]
        nodes = part.nodes[part.triangles[kind == iron]]
        e, inside = locate(nodes, point)
        found[name] = (e, inside, np.hypot(*(nodes[e].mean(axis=0) - point)))
    side = min(found, key=lambda n: (not found[n][1], found[n][2]))
    e = found[side][0]
    w = sides[side]
    b = w.b[:, e] / load_material(str(w.material[e])).stacking_factor
    centre = w.centroids[e]
    radial = centre / np.hypot(*centre)
    n = b.shape[0]
    return dict(t=np.arange(n) * w.period_s(rpm * 2 * math.pi / 60) / n, b_r=b @ radial,
                b_t=b @ np.array([-radial[1], radial[0]]), region=str(w.region[e]), side=side)
