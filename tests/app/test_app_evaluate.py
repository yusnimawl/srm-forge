import math
from unittest import mock

import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

from srmapp.drive.envelope import Envelope
from srmapp.evaluate import Evaluation, StageTwoGrid, evaluate_stage2, requirement_ratios, speed_grid
from srmapp.requirements import Requirements
from srmapp.sizing import estimates as est
from srmapp.sizing.generator import Candidate
from srmapp.sizing.stage1 import stage1
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import InputError, MapFailed, MeshRejected, WorkerCrashed

THICK = dict(kind="round", diameter=6.0e-3, outer_diameter=6.2e-3)


def _req(**kw):
    values = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    values.update(kw)
    return Requirements(**values)


def _cand():
    return Candidate("c0", Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))


def _map(stage):
    return synthetic_map(n_angles=24, currents=np.linspace(0.0, stage.i_map, 9))


def _evaluate(req, **kw):
    stage = stage1(req, make_8_6())
    with mock.patch("srmapp.evaluate.build_map", return_value=_map(stage)), \
            mock.patch("srmapp.evaluate.key_numbers", return_value=None):
        return evaluate_stage2(_cand(), req, stage, max_turns=30, **kw), stage


def test_speed_grid_contains_base_and_max_exactly():
    g = speed_grid(_req())
    assert 3000.0 in g and 6000.0 in g
    assert np.all(np.diff(g) > 0) and g[0] < 3000.0


def test_requirement_ratios():
    speeds = np.array([300.0, 3000.0, 4500.0, 6000.0])
    torque = np.array([10.0, 4.0, 2.0, 1.0])
    power = torque * speeds * 2 * math.pi / 60
    env = Envelope(speeds, torque, power, np.zeros(4), np.zeros(4), np.ones(4), np.zeros(4), np.zeros(4), np.zeros(4))
    t_ratio, p_ratio = requirement_ratios(env, _req())
    assert t_ratio == pytest.approx(4.0 / 3.2)
    assert p_ratio == pytest.approx(min(power[1:]) / 1000.0)


def test_stage_two_grid_defaults_to_the_preset():
    assert StageTwoGrid() == StageTwoGrid(None, None)


def test_failed_map_becomes_an_evaluation_and_does_not_raise():
    with mock.patch("srmapp.evaluate.build_map", side_effect=MapFailed(["3 of 50 points failed"], 3)):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()))
    assert isinstance(e, Evaluation)
    assert e.status == "MapFailed" and "3 of 50" in e.error
    assert not e.feasible and math.isnan(e.torque_ratio) and e.envelope is None and e.winding is None
    assert math.isnan(e.i_rms_a) and math.isnan(e.j_rms)


def test_cancelled_map_is_reported():
    partial = synthetic_map(complete=False)
    with mock.patch("srmapp.evaluate.build_map", return_value=partial):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()))
    assert e.status == "cancelled" and not e.feasible


def test_map_is_built_over_the_stage_one_range():
    stage = stage1(_req(), make_8_6())
    with mock.patch("srmapp.evaluate.build_map", return_value=_map(stage)) as bm, \
            mock.patch("srmapp.evaluate.key_numbers", return_value=None):
        evaluate_stage2(_cand(), _req(), stage, max_turns=5)
    assert bm.call_args.args[1] == stage.i_map


def test_stage_two_scans_within_the_stage_one_cap_by_default():
    req = _req(wires=[THICK], phase_current_a=100.0)
    stage = stage1(req, make_8_6())                    # cap 40 A/mm2
    assert stage.j_peak_max == 40e6
    with mock.patch("srmapp.evaluate.build_map", return_value=_map(stage)), \
            mock.patch("srmapp.evaluate.key_numbers", return_value=None):
        e = evaluate_stage2(_cand(), req, stage, j_limit=25e6)     # its own 2x would be 50 A/mm2
    assert e.scan and all(s.winding.current_density <= 40e6 * (1 + 1e-9) for s in e.scan)


def test_scan_limit_note_follows_the_equivalent_turns():
    e, _ = _evaluate(_req())
    assert e.winding.turns == 30 and e.winding.paths == 1 and "limit" in e.error
    e, _ = _evaluate(_req(), margin=3.47)        # feasible up to 21 turns in series; 30 turns on 2 paths is only 15
    assert next(s for s in e.scan if (s.winding.turns, s.winding.paths) == (30, 2)).feasible
    assert (e.winding.turns, e.winding.paths) == (21, 1) and "limit" not in e.error


def test_no_winding_reasons_name_the_cap_in_wire_mode():
    req = _req(wires=[dict(kind="round", diameter=1e-3, outer_diameter=1.08e-3)], phase_current_a=1e6)
    s = stage1(req, make_8_6())
    assert not s.passes and "no winding" in s.reason and "j_peak_max 40 A/mm2" in s.reason


def test_density_mode_evaluation_fills_the_metrics():
    e, stage = _evaluate(_req())
    assert e.status == "ok" and e.winding is not None and e.winding.wire is None
    m = e.design.machine
    assert m.turns_per_pole == e.winding.turns
    assert est.phase_resistance(m) == pytest.approx(e.winding.resistance * e.winding.paths**2)
    assert e.mass_kg == pytest.approx(stage.mass.iron + e.winding.copper_mass)
    assert len(e.scan) == 60          # 30 turn counts x paths 1 and 2
    assert e.peak_power_w > 0
    assert e.power_density_kw_per_kg == pytest.approx(e.peak_power_w / 1000 / e.mass_kg)
    assert 0 < e.efficiency_base <= 1
    assert e.feasible == (e.torque_ratio >= 1 and e.power_ratio >= 1)


def test_wire_mode_evaluation_uses_the_inverter_current():
    req = _req(wires=[THICK], phase_current_a=100.0)
    e, _ = _evaluate(req)
    assert e.status == "ok" and e.winding.wire == 0
    assert e.winding.current == 100.0 and e.winding.strands >= 1
    assert e.winding.current_density <= 40e6 * (1 + 1e-9)
    assert 0 < e.i_rms_a and e.j_rms <= 20e6 * (1 + 1e-9)
    assert e.j_rms == pytest.approx(e.i_rms_a / (e.winding.paths * e.winding.copper_area))
    assert est.phase_resistance(e.design.machine) == pytest.approx(e.winding.resistance * e.winding.paths**2)


def test_margin_reaches_the_turns_choice():
    e, _ = _evaluate(_req(), margin=1e6)
    assert e.status == "ok" and not e.feasible


def test_capped_infeasible_result_carries_a_note():
    req = _req(wires=[THICK], phase_current_a=800.0, peak_torque_nm=1e3, peak_power_w=314_159.0)
    e, _ = _evaluate(req, j_limit=10e6, j_peak_max=20e6)          # cap 20 A/mm² leaves out the one-strand windings
    assert e.status == "ok" and not e.feasible
    assert "j_peak_max" in e.error


def test_no_winding_is_reported_not_raised():
    e, _ = _evaluate(_req(wires=[THICK], phase_current_a=100.0), j_peak_max=1.0)    # stricter than the stage-1 range
    assert e.status == "no_winding" and not e.feasible and e.winding is None and e.envelope is None


def test_mass_over_the_limit_after_the_winding_is_chosen_is_infeasible():
    req = _req(wires=[THICK], phase_current_a=100.0)
    free, _ = _evaluate(req)
    iron = stage1(req, make_8_6()).mass.iron
    limit = iron + 0.5 * free.winding.copper_mass
    e, stage = _evaluate(_req(wires=[THICK], phase_current_a=100.0, max_mass_kg=limit))
    assert stage.passes and e.status == "ok" and not e.feasible
    assert "mass" in e.error and f"{limit:.2f} kg limit" in e.error
    assert free.error == ""


@pytest.mark.slow
def test_real_8_6_evaluation():
    pytest.importorskip("ngsolve")
    req = _req(peak_power_w=2000.0, peak_torque_nm=6.4, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    stage = stage1(req, make_8_6())
    e = evaluate_stage2(_cand(), req, stage, grid=StageTwoGrid(8, 4), workers=4, max_turns=120)
    assert e.status == "ok", e.error
    assert 1.0 < e.envelope.torque[0] < stage.torque_upper
    assert e.key is not None and e.key.peak_torque > 0


@pytest.mark.parametrize("exc", [MeshRejected(["min angle"], None), InputError([]), WorkerCrashed([3]),
                                 RuntimeError("boom"), ValueError("bad current")])
def test_any_exception_from_build_map_becomes_a_failed_evaluation(exc):
    with mock.patch("srmapp.evaluate.build_map", side_effect=exc):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()))
    assert e.status == type(exc).__name__ and not e.feasible
    assert math.isnan(e.torque_ratio) and e.envelope is None


def test_keyboard_interrupt_is_not_swallowed():
    with mock.patch("srmapp.evaluate.build_map", side_effect=KeyboardInterrupt), pytest.raises(KeyboardInterrupt):
        evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()))


def test_turns_are_chosen_on_the_end_winding_corrected_map():
    from srmapp import evaluate as ev
    from srmcore.maps.end_winding import end_winding_inductance
    req = _req()
    stage = stage1(req, make_8_6())
    raw = _map(stage)
    seen = []
    real = ev.choose_turns

    def spy(result, *a, **kw):
        seen.append(result)
        return real(result, *a, **kw)
    with mock.patch("srmapp.evaluate.build_map", return_value=raw), \
            mock.patch("srmapp.evaluate.key_numbers", return_value=None), \
            mock.patch("srmapp.evaluate.choose_turns", side_effect=spy):
        evaluate_stage2(_cand(), req, stage, max_turns=30)
    l_end = end_winding_inductance(make_8_6(), image_factor=1.5)
    k = raw.circuits.index(raw.excited)
    assert l_end > 0
    np.testing.assert_allclose(seen[0].psi[..., k], raw.psi[..., k] + l_end * raw.currents[None, :])
