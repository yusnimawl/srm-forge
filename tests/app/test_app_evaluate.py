import math
from unittest import mock

import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

from srmapp.drive.envelope import Envelope
from srmapp.evaluate import Evaluation, StageTwoGrid, evaluate_stage2, requirement_ratios, speed_grid
from srmapp.requirements import Requirements
from srmapp.sizing.generator import Candidate
from srmapp.sizing.stage1 import stage1
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import MapFailed


def _req(**kw):
    values = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    values.update(kw)
    return Requirements(**values)


def _cand():
    return Candidate("c0", Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))


def test_speed_grid_contains_base_and_max_exactly():
    g = speed_grid(_req())
    assert 3000.0 in g and 6000.0 in g
    assert np.all(np.diff(g) > 0) and g[0] < 3000.0


def test_requirement_ratios():
    speeds = np.array([300.0, 3000.0, 4500.0, 6000.0])
    torque = np.array([10.0, 4.0, 2.0, 1.0])
    power = torque * speeds * 2 * math.pi / 60
    env = Envelope(speeds, torque, power, np.zeros(4), np.zeros(4), np.ones(4), np.zeros(4), np.zeros(4))
    t_ratio, p_ratio = requirement_ratios(env, _req())
    assert t_ratio == pytest.approx(4.0 / 3.2)
    assert p_ratio == pytest.approx(min(power[1:]) / 1000.0)


def test_failed_map_becomes_an_evaluation_and_does_not_raise():
    with mock.patch("srmapp.evaluate.build_map", side_effect=MapFailed(["3 of 50 points failed"], 3)):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()))
    assert isinstance(e, Evaluation)
    assert e.status == "MapFailed" and "3 of 50" in e.error
    assert not e.feasible and math.isnan(e.torque_ratio) and e.envelope is None


def test_cancelled_map_is_reported():
    partial = synthetic_map(complete=False)
    with mock.patch("srmapp.evaluate.build_map", return_value=partial):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()))
    assert e.status == "cancelled" and not e.feasible


def test_evaluation_of_a_synthetic_map_fills_the_metrics():
    m = make_8_6()
    with mock.patch("srmapp.evaluate.build_map", return_value=synthetic_map(n_angles=24)), \
            mock.patch("srmapp.evaluate.key_numbers", return_value=None):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), m))
    assert e.status == "ok" and e.error == ""
    assert e.mass_kg > 0 and e.peak_power_w > 0
    assert e.power_density_kw_per_kg == pytest.approx(e.peak_power_w / 1000 / e.mass_kg)
    assert 0 < e.efficiency_base <= 1
    assert e.feasible == (e.torque_ratio >= 1 and e.power_ratio >= 1)


@pytest.mark.slow
def test_real_8_6_evaluation():
    pytest.importorskip("ngsolve")
    req = _req(peak_power_w=2000.0, peak_torque_nm=6.4, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    e = evaluate_stage2(_cand(), req, stage1(req, make_8_6()), grid=StageTwoGrid(8, 4), workers=4)
    assert e.status == "ok", e.error
    assert 1.0 < e.envelope.torque[0] < stage1(req, make_8_6()).torque_upper
    assert e.key is not None and e.key.peak_torque > 0
