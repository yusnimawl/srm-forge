import dataclasses
import math
from unittest import mock

import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

import srmapp.losses as losses
from srmapp.case import CaseInputs, FixedWinding, evaluate_design
from srmapp.losses import check_loss_data, efficiency_map, phase_current_samples
from srmapp.requirements import Requirements
from srmcore.maps.point import solve_point
from srmcore.materials import MissingLossData
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design, MeshSettings, RegionMaterials
from srmcore.solvers.factory import make_solver

WIRE = dict(kind="round", diameter=1.0e-3, outer_diameter=1.08e-3)
IRON = RegionMaterials(stator="10JNEX900", rotor="10JNEX900")
DESIGN = Design(machine=make_8_6(materials=IRON, lamination_thickness=1.0e-4), mesh=MeshSettings(preset="screening"))
N_SPEEDS, N_TORQUES, N_ANGLES = 2, 2, 8


def _fake_map(design, i_max, **kw):
    return synthetic_map(n_angles=24, currents=np.linspace(0.0, i_max, 9))


@pytest.fixture(scope="module")
def case():
    req = Requirements(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0,
                       wires=[WIRE], phase_current_a=15.0)
    inputs = CaseInputs(requirements=req, design=DESIGN, winding=FixedWinding(turns=8, strands=1, paths=1, wire=0))
    with mock.patch("srmapp.evaluate.build_map", side_effect=_fake_map):
        evaluation = evaluate_design(inputs)
    assert evaluation.status == "ok"
    return inputs, evaluation


@pytest.fixture(scope="module")
def result(case, tmp_path_factory):
    inputs, evaluation = case
    seen = []
    with mock.patch("srmapp.losses.build_map", side_effect=_fake_map):
        out = efficiency_map(inputs, evaluation, n_speeds=N_SPEEDS, n_torques=N_TORQUES, n_angles=N_ANGLES,
                             cache_dir=tmp_path_factory.mktemp("eff"), progress=lambda *a: seen.append(a))
    return out, seen


def test_energy_balance(result):
    out, _ = result
    assert all(p.reached for p in out.points)
    for p in out.points:
        assert p.power_w > 0 and p.iron_w > 0 and p.copper_ac_w is not None
        assert p.efficiency == pytest.approx(p.power_w / (p.power_w + p.copper_dc_w + p.copper_ac_w + p.iron_w))
        assert p.iron_w == pytest.approx(sum(r.hysteresis + r.classical + r.excess for r in p.iron.values()))
        assert p.iron_uncertainty_rel > losses.ANGLE_CONVERGENCE_REL
        assert p.stroke_key


def test_iron_grows_with_speed(result):
    out, _ = result
    by = {(p.speed_rpm, p.torque_nm): p for p in out.points}
    for k in range(N_TORQUES):
        low, high = (sorted((p for p in out.points if p.speed_rpm == s), key=lambda p: p.torque_nm)[k]
                     for s in out.speeds_rpm)
        assert high.iron_w > low.iron_w
    assert len(by) == N_SPEEDS * N_TORQUES
    assert out.winding_temperature_c == 120.0 and out.n_angles == N_ANGLES


def test_progress_steps(result):
    _, seen = result
    steps = [s for s, *_ in seen]
    assert set(steps) == {"strokes", "fields", "losses"}
    assert steps.index("fields") > max(i for i, s in enumerate(steps) if s == "strokes")
    for step in ("strokes", "fields", "losses"):
        last = [a for a in seen if a[0] == step][-1]
        assert last[1] == last[2]


def test_unreachable_point_is_skipped(case, tmp_path):
    inputs, evaluation = case
    real = losses.min_copper_stroke
    top = {}

    def fake(result, machine, volts, r, rpm, torque, **kw):
        top["rpm"] = max(top.get("rpm", 0.0), rpm)
        return None if rpm >= 6000.0 * 0.99 else real(result, machine, volts, r, rpm, torque, **kw)

    with mock.patch("srmapp.losses.build_map", side_effect=_fake_map), \
            mock.patch("srmapp.losses.min_copper_stroke", side_effect=fake):
        out = efficiency_map(inputs, evaluation, n_speeds=N_SPEEDS, n_torques=1, n_angles=N_ANGLES,
                             cache_dir=tmp_path)
    off = [p for p in out.points if not p.reached]
    ok = [p for p in out.points if p.reached]
    assert len(off) == 1 and len(ok) == 1
    assert math.isnan(off[0].iron_w) and math.isnan(off[0].efficiency) and math.isnan(off[0].copper_dc_w)
    assert off[0].iron == {} and off[0].stroke_key == ""
    assert ok[0].iron_w > 0


def test_missing_loss_data_raises_before_any_solve(case):
    inputs, evaluation = case
    machine = make_8_6(materials=RegionMaterials(stator="Hiperco50A", rotor="Hiperco50A"))
    design = Design(machine=machine, mesh=MeshSettings(preset="screening"))
    with pytest.raises(MissingLossData):
        check_loss_data(design)
    bad = inputs.model_copy(update={"design": design})
    with mock.patch("srmapp.losses.build_map", side_effect=AssertionError("no map")):
        with pytest.raises(MissingLossData):
            efficiency_map(bad, evaluation, n_speeds=1, n_torques=1, n_angles=N_ANGLES)


def test_stroke_angle_origin_is_phase_a_aligned():
    # The envelope table starts at the angle where phase A is aligned; the stroke angles use the same origin.
    static = build_machine_mesh(DESIGN)
    solver = make_solver("ngsolve")
    tau = 2 * math.pi / DESIGN.machine.n_rotor_poles
    psi = [solve_point(static, DESIGN, a, {"A": 5.0}, solver).psi[0] for a in (0.0, tau / 2)]
    assert psi[0] > 1.5 * psi[1]


def test_phase_currents_are_delayed_by_a_stroke_angle_per_phase():
    tau, q = 2 * math.pi / 6, 4
    table = np.zeros(180)
    table[20:60] = 3.0
    angles = np.arange(0, 48) * tau / 48
    cur = phase_current_samples(table, angles, tau, q)
    assert cur.shape == (48, q)
    np.testing.assert_allclose(cur[:, 0], np.interp(angles, np.arange(180) * tau / 180, table, period=tau))
    np.testing.assert_allclose(cur[12:, 1], cur[:-12, 0], atol=1e-12)         # delayed by tau / q = 12 samples



def test_stroke_losses_given_stroke_and_model_override(tmp_path):
    static = build_machine_mesh(DESIGN)
    tau = 2 * math.pi / DESIGN.machine.n_rotor_poles
    angles = losses.stroke_angles(static, tau, N_ANGLES)
    currents = np.zeros((len(angles), DESIGN.machine.n_phases))
    currents[:, 0] = 40.0 * np.sin(np.linspace(0.0, math.pi, len(angles)))
    base = losses.stroke_losses(static, DESIGN, angles, currents, 3000.0, workers=1, cache_dir=tmp_path)
    assert base.iron_w > 0
    assert base.iron_w == pytest.approx(sum(r.hysteresis + r.classical + r.excess for r in base.iron.values()))
    same = losses.stroke_losses(static, DESIGN, angles, currents, 3000.0, workers=1, cache_dir=tmp_path,
                                model=losses.loss_model("10JNEX900"))
    assert same.iron_w == pytest.approx(base.iron_w)
    none = losses.stroke_losses(static, DESIGN, angles, currents, 3000.0, workers=1, cache_dir=tmp_path,
                                model=dataclasses.replace(losses.loss_model("10JNEX900"), k_h=0.0, k_e=0.0))
    assert all(r.hysteresis == 0.0 and r.excess == 0.0 for r in none.iron.values())
    assert 0 < none.iron_w < base.iron_w


def test_no_lamination_thickness_keeps_the_data_thickness(case, tmp_path):
    inputs, evaluation = case
    design = Design(machine=make_8_6(materials=IRON, lamination_thickness=None), mesh=MeshSettings(preset="screening"))
    t = losses.loss_model("10JNEX900").thickness
    assert losses.design_model(losses.loss_model("10JNEX900"), None).thickness == t
    with mock.patch("srmapp.losses.build_map", side_effect=_fake_map):
        out = efficiency_map(inputs.model_copy(update={"design": design}), evaluation, n_speeds=1, n_torques=1,
                             n_angles=N_ANGLES, cache_dir=tmp_path)
    assert any("design has no lamination thickness" in n and "using the loss data's" in n for n in out.notes)


def test_design_thickness_scales_the_classical_term_by_the_square(tmp_path):
    t = losses.loss_model("10JNEX900").thickness
    notes = losses.thickness_notes_for(Design(machine=make_8_6(materials=IRON, lamination_thickness=2 * t),
                                              mesh=MeshSettings(preset="screening")))
    assert len(notes) == 1 and "loss data measured at" in notes[0] and "classical eddy scaled to the design's" in notes[0]
    static = build_machine_mesh(DESIGN)
    angles = losses.stroke_angles(static, 2 * math.pi / DESIGN.machine.n_rotor_poles, N_ANGLES)
    currents = np.zeros((len(angles), DESIGN.machine.n_phases))
    currents[:, 0] = 40.0 * np.sin(np.linspace(0.0, math.pi, len(angles)))
    classical = []
    for d in (t, 2 * t):
        design = Design(machine=make_8_6(materials=IRON, lamination_thickness=d), mesh=MeshSettings(preset="screening"))
        sl = losses.stroke_losses(static, design, angles, currents, 3000.0, workers=1, cache_dir=tmp_path)
        classical.append(sum(r.classical for r in sl.iron.values()))
    assert classical[1] == pytest.approx(4 * classical[0], rel=1e-9)


def test_range_notes_one_per_cause():
    side = lambda high=0.0, low=0.0, beyond=False: losses._Side({}, 0.1, "A", high, low, beyond)
    assert losses.range_notes([side()]) == []
    assert losses.range_notes([side(high=0.1, beyond=True)]) == [losses._EXTRAPOLATION_NOTE]
    assert losses.range_notes([side(low=0.1, beyond=True), side(low=0.2, beyond=True)]) == [losses._LOW_B_NOTE]
    assert losses.range_notes([side(beyond=True)]) == [losses._FREQUENCY_NOTE]


def _stroke(tmp_path, **kw):
    static = build_machine_mesh(DESIGN)
    tau = 2 * math.pi / DESIGN.machine.n_rotor_poles
    angles = losses.stroke_angles(static, tau, N_ANGLES)
    currents = np.zeros((len(angles), DESIGN.machine.n_phases))
    currents[:, 0] = 40.0 * np.sin(np.linspace(0.0, math.pi, len(angles)))
    return losses.stroke_losses(static, DESIGN, angles, currents, 3000.0, workers=1, cache_dir=tmp_path, **kw)


def test_unspecified_is_r3_bit_for_bit(tmp_path):
    base, cut = _stroke(tmp_path), _stroke(tmp_path, cut_process="unspecified")
    assert cut.iron == base.iron and cut.iron_w == base.iron_w
    assert all(v == 1.0 for v in cut.cut_edge_factor.values())
    lo, hi = cut.cut_edge_rel
    assert lo < 0 < hi


def test_process_raises_hysteresis_and_excess_only(tmp_path):
    base, laser = _stroke(tmp_path), _stroke(tmp_path, cut_process="laser")
    for k in base.iron:
        assert laser.iron[k].classical == base.iron[k].classical
        assert laser.iron[k].hysteresis > base.iron[k].hysteresis / losses.B0
    assert laser.cut_edge_factor["stator_pole"] > 1.0


def test_range_is_linear_in_a(tmp_path, monkeypatch):
    p = losses.CUT_PROCESSES["punching"]
    sl = _stroke(tmp_path, cut_process="punching")
    for a, rel in ((p.a_low, sl.cut_edge_rel[0]), (p.a_high, sl.cut_edge_rel[1])):
        monkeypatch.setitem(losses.CUT_PROCESSES, "punching", dataclasses.replace(p, a=a))
        direct = _stroke(tmp_path, cut_process="punching").iron_w
        assert direct == pytest.approx(sl.iron_w * (1 + rel), rel=1e-12)


def test_efficiency_map_records_process_and_note(case, tmp_path):
    inputs, evaluation = case
    laser = inputs.model_copy(update={"requirements": inputs.requirements.model_copy(update={"cut_process": "laser"})})
    with mock.patch("srmapp.losses.build_map", side_effect=_fake_map):
        out = efficiency_map(laser, evaluation, n_speeds=N_SPEEDS, n_torques=N_TORQUES, n_angles=N_ANGLES,
                             cache_dir=tmp_path, workers=1)
    assert out.cut_process == "laser" and losses.CUT_EDGE_NOTE in out.notes
    for pt in out.points:
        if pt.reached:
            assert all(math.isfinite(v) for v in pt.cut_edge_rel) and pt.cut_edge_factor
        else:
            assert all(math.isnan(v) for v in pt.cut_edge_rel) and pt.cut_edge_factor == {}


def test_band_fractions_computed_once_per_delta(tmp_path):
    band = {}
    with mock.patch.object(losses, "iron_fractions", wraps=losses.iron_fractions) as spy:
        first = _stroke(tmp_path, cut_process="punching", fractions=band)
        again = _stroke(tmp_path, cut_process="punching", fractions=band)
    assert spy.call_count == 1 and set(band) == {losses.CUT_PROCESSES["punching"].delta}
    assert again.iron_w == first.iron_w == _stroke(tmp_path, cut_process="punching").iron_w
