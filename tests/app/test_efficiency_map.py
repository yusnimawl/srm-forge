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

