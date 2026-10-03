"""TEAM Problem 24 (spec §2.3, §8.2 suite 5): the 2D magnetostatic model against the published
measurements. The model omits 3D end flux and eddy currents, so the checks are regression pins, signs
and a sanity band, not a pass/fail tolerance against the measurement (docs/m5b-team24-results.md)."""
import numpy as np
import pytest
from scipy.interpolate import PchipInterpolator

import team24_fixture as t24
from srmcore.materials.laws import MU0
from srmcore.post.quantities import arkkio_torque, flux_linkage, virtual_work_torque
from srmcore.solvers.skfem_reference import SkfemReference


def test_bh_table_reading():
    h, b = np.array(t24.H_TABLE), np.array(t24.B_TABLE)
    assert len(h) == 17
    assert h[1] == pytest.approx(4000.0) and h[-1] == pytest.approx(240200.0)
    j = b - MU0 * h
    assert np.all(np.diff(j) > 0)
    assert t24.ASSUMED_JS > j[-1]
    t24.steel_law()          # process_bh accepts the table


def test_table_ii_voltage():
    assert t24.table_ii_voltage(0.0) == 0.0
    assert t24.table_ii_voltage(0.0002) == pytest.approx(23.60)
    assert t24.table_ii_voltage(0.5) == pytest.approx(23.10)


def test_current_rise_linear_inductor():
    # psi = L i with constant V: i(t) = V/R (1 - exp(-R t / L))
    inductance, r, v = 0.05, 3.0, 23.1
    grid = np.linspace(0.0, 10.0, 11)
    times = np.array([0.002, 0.01, 0.05, 0.2])
    got = t24.current_rise(PchipInterpolator(grid, inductance * grid), times, resistance=r, voltage=v)
    want = v / r * (1 - np.exp(-r * times / inductance))
    assert got == pytest.approx(want, rel=1e-5)


def test_current_rise_callable_voltage():
    grid = np.linspace(0.0, 10.0, 11)
    psi = PchipInterpolator(grid, 0.05 * grid)
    times = np.array([0.01, 0.1])
    const = t24.current_rise(psi, times, voltage=23.1)
    measured = t24.current_rise(psi, times, voltage=t24.table_ii_voltage)
    assert np.all(measured > const)          # Table II overshoots 23.1 V early on
    assert np.all(np.diff(measured) > 0)


I_FINAL = 7.41
MEASURED_TORQUE = 3.22
# 2D results at 7.41 A on the default mesh (docs/m5b-team24-results.md); regression pins.
TORQUE_2D = 2.7996
PSI_2D = 0.3676
ROTOR_FLUX_2D = 3.9069e-4
CURRENT_20MS_2D = 5.308


def _rel(x, y):
    return abs(x - y) / max(abs(y), 1e-30)


@pytest.fixture(scope="module")
def final_point():
    p = t24.team24_problem(I_FINAL)
    s = SkfemReference().solve(p)
    assert s.status.value == "OK"
    return p, s


@pytest.fixture(scope="module")
def lr_map():
    return t24.locked_rotor_map(SkfemReference())


@pytest.mark.slow
def test_cross_solver_agreement(final_point):
    pytest.importorskip("ngsolve")
    from srmcore.solvers.ngsolve_adapter import NgsolveAdapter
    p, ref = final_point
    ngs = NgsolveAdapter().solve(p)
    assert ngs.status.value == "OK"
    assert np.abs(ngs.a - ref.a).max() / np.abs(ref.a).max() < 1e-4
    assert _rel(flux_linkage(p, ngs)[0], flux_linkage(p, ref)[0]) < 1e-4
    assert _rel(ngs.energy, ref.energy) < 1e-4
    assert _rel(arkkio_torque(p, ngs), arkkio_torque(p, ref)) < 1e-4


@pytest.mark.slow
def test_static_torque(final_point):
    p, s = final_point
    t_ark, t_vw = arkkio_torque(p, s), virtual_work_torque(p, s)
    assert t_ark > 0                                  # counter-clockwise, towards alignment
    assert _rel(t_vw, t_ark) < 1e-3
    assert t_ark == pytest.approx(TORQUE_2D, rel=1e-3)
    assert flux_linkage(p, s)[0] == pytest.approx(PSI_2D, rel=1e-3)
    error = (t_ark - MEASURED_TORQUE) / MEASURED_TORQUE
    assert -0.25 < error < 0                          # 2D omits end flux: below the measurement


@pytest.mark.slow
def test_rotor_pole_flux_symmetric(final_point):
    p, s = final_point
    top, bottom = t24.rotor_pole_flux(p, s, 1), t24.rotor_pole_flux(p, s, -1)
    assert _rel(bottom, top) < 1e-3
    assert top == pytest.approx(ROTOR_FLUX_2D, rel=1e-3)
    per_turn = flux_linkage(p, s)[0] / (2 * t24.TURNS)
    assert 0.5 * per_turn < top < per_turn            # pole flux is the coil flux less leakage
    assert -0.25 < (top - t24.TABLE_ROTOR_FLUX[-1]) / t24.TABLE_ROTOR_FLUX[-1] < 0


@pytest.mark.slow
def test_current_rise(lr_map):
    psi = PchipInterpolator(lr_map["current"], lr_map["psi"])
    model = t24.current_rise(psi, t24.TABLE_TIME)
    error = (model - t24.TABLE_CURRENT) / t24.TABLE_CURRENT
    mid = (t24.TABLE_TIME >= 0.005) & (t24.TABLE_TIME <= 0.100)
    assert np.all(model[mid] >= t24.TABLE_CURRENT[mid])   # model runs ahead mid-rise: lower 2D inductance and no eddy currents
    assert np.all(np.abs(error) < 0.25)
    assert model[t24.TABLE_TIME == 0.020][0] == pytest.approx(CURRENT_20MS_2D, rel=2e-3)
    assert model[-1] == pytest.approx(t24.VOLTAGE / t24.RESISTANCE, rel=2e-3)
