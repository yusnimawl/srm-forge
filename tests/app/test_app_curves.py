import dataclasses
from unittest import mock

import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

from srmapp.curves import MapCurves, map_curves
from srmapp.evaluate import MapArrays, evaluate_stage2, turns_scale
from srmapp.requirements import Requirements
from srmapp.sizing.generator import Candidate
from srmapp.sizing.stage1 import stage1
from srmapp.sizing.winding import Winding
from srmcore.maps.end_winding import end_winding_inductance
from srmcore.maps.results import key_numbers
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import MapFailed

MACHINE = make_8_6()
WINDING = Winding(60, 1, 1e-6, 10.0, 0.1, 1.0, None, 1)


def _arrays_and_key():
    r = synthetic_map(n_angles=24, currents=np.linspace(0.0, 20.0, 9), l0=30e-3, l1=20e-3)   # 10 mH to 50 mH
    arrays = MapArrays(r.angles, r.currents, r.psi[..., 0], r.torque_arkkio)
    return arrays, key_numbers(r, MACHINE)


def test_linear_map_has_constant_saliency():
    arrays, key = _arrays_and_key()
    c = map_curves(arrays, MACHINE, WINDING, key)
    assert isinstance(c, MapCurves)
    assert len(c.currents) == len(arrays.currents) - 1 and c.currents[0] > 0
    assert c.inductance.shape == (len(arrays.angles), len(c.currents))
    np.testing.assert_allclose(c.la_sat, 50e-3, rtol=1e-4)    # periodic spline of a cosine on 24 angles
    np.testing.assert_allclose(c.lu, 10e-3, rtol=1e-4)
    np.testing.assert_allclose(c.k2, 1 - 10 / 50, rtol=1e-4)
    np.testing.assert_allclose(c.la_lu, 5.0, rtol=1e-4)
    assert c.la_unsat == pytest.approx(key.la)


def test_stator_pole_flux_density_follows_the_hand_formula():
    arrays, key = _arrays_and_key()
    c = map_curves(arrays, MACHINE, WINDING, key)
    n_series = 60 * (MACHINE.n_stator_poles // MACHINE.n_phases)
    a_face = (MACHINE.rotor_outer_diameter / 2 + MACHINE.air_gap) * MACHINE.stator_pole_arc * MACHINE.stack_length
    np.testing.assert_allclose(c.b_sp, 50e-3 * c.currents / (n_series * a_face))
    np.testing.assert_allclose(c.b_sp_k2, c.b_sp * c.k2)
    with_end = map_curves(arrays, MACHINE, WINDING, key, l_end=2e-3)
    np.testing.assert_allclose(c.b_sp - with_end.b_sp, 2e-3 * c.currents / (n_series * a_face))
    np.testing.assert_allclose(with_end.k2, c.k2)
    two_paths = map_curves(arrays, MACHINE, dataclasses.replace(WINDING, paths=2), key)
    np.testing.assert_allclose(two_paths.b_sp, 2 * c.b_sp)


def test_evaluation_carries_curves_only_when_ok():
    req = Requirements(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    stage = stage1(req, MACHINE)
    cand = Candidate("c0", Design(machine=MACHINE, mesh=MeshSettings(preset="screening")))
    raw = synthetic_map(n_angles=24, currents=np.linspace(0.0, stage.i_map, 9))
    with mock.patch("srmapp.evaluate.build_map", return_value=raw):
        e = evaluate_stage2(cand, req, stage, max_turns=30)
    assert e.status == "ok" and len(e.curves.currents) == len(raw.currents) - 1
    with mock.patch("srmapp.evaluate.build_map", side_effect=MapFailed(["1 of 50 points failed"], 1)):
        assert evaluate_stage2(cand, req, stage).curves is None


def test_evaluation_leaves_the_end_winding_out_of_b_sp():
    req = Requirements(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    stage = stage1(req, MACHINE)
    cand = Candidate("c0", Design(machine=MACHINE, mesh=MeshSettings(preset="screening")))
    raw = synthetic_map(n_angles=24, currents=np.linspace(0.0, stage.i_map, 9))
    with mock.patch("srmapp.evaluate.build_map", return_value=raw):
        e = evaluate_stage2(cand, req, stage, max_turns=30)
    w, m = e.winding, e.design.machine
    l_end = end_winding_inductance(MACHINE, image_factor=1.5) * turns_scale(MACHINE, w) ** 2
    n_series = w.turns * (m.n_stator_poles // m.n_phases) / w.paths
    a_face = (m.rotor_outer_diameter / 2 + m.air_gap) * m.stator_pole_arc * m.stack_length
    c = e.curves
    np.testing.assert_allclose(c.b_sp, (c.la_sat - l_end) * c.currents / (n_series * a_face))
