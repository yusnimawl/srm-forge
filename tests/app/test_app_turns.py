import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

from srmapp.drive.envelope import envelope
from srmapp.turns import rescale_turns

MACHINE = make_8_6()
SPEEDS = np.array([100.0, 1500.0, 6000.0, 12000.0])


def test_rescale_moves_current_and_flux_and_keeps_torque_and_energy():
    r = synthetic_map(n_angles=16)
    s = rescale_turns(r, 2.0)
    np.testing.assert_allclose(s.currents, r.currents / 2)
    np.testing.assert_allclose(s.psi, 2 * r.psi)
    np.testing.assert_allclose(s.l_inc, 4 * r.l_inc)
    for name in ("torque_arkkio", "torque_virtual_work", "energy", "coenergy", "pole_force", "b_peak"):
        np.testing.assert_array_equal(getattr(s, name), getattr(r, name))
    assert s.angles is r.angles and s.complete == r.complete


def test_rescaled_drive_equals_the_original_at_scaled_voltage():
    # k times the turns: ψ' = kψ, i' = i/k, R' = k²R, so dψ/dt = V/k − R·i on the original map
    r, k, res = synthetic_map(n_angles=24), 3.0, 0.2
    scaled = envelope(rescale_turns(r, k), MACHINE, 300.0, k * k * res, SPEEDS, current_limit=20.0 / k)
    original = envelope(r, MACHINE, 300.0 / k, res, SPEEDS, current_limit=20.0)
    np.testing.assert_allclose(scaled.torque, original.torque, rtol=1e-9, atol=1e-12)
    np.testing.assert_allclose(scaled.copper_loss, original.copper_loss, rtol=1e-9, atol=1e-12)


@pytest.mark.slow
def test_fem_map_at_double_turns_matches_the_rescale():
    pytest.importorskip("ngsolve")
    from srmcore.maps import build_map
    from srmcore.model.design import Design, MeshSettings

    def run(turns, i_max):
        design = Design(machine=make_8_6(turns_per_pole=turns), mesh=MeshSettings(preset="screening"))
        return build_map(design, i_max, n_angles=6, n_currents=4, workers=2)
    base, double = run(40, 20.0), run(80, 10.0)
    predicted = rescale_turns(base, 2.0)
    np.testing.assert_allclose(double.currents, predicted.currents, rtol=1e-12)
    psi_scale = np.max(np.abs(double.psi))
    np.testing.assert_allclose(double.psi, predicted.psi, rtol=1e-6, atol=1e-7 * psi_scale)
    t_scale = np.max(np.abs(double.torque_arkkio))
    np.testing.assert_allclose(double.torque_arkkio, predicted.torque_arkkio, rtol=1e-6, atol=1e-7 * t_scale)
