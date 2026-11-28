import dataclasses

import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import inductance, synthetic_map

from srmapp.requirements import Requirements
from srmapp.sizing.winding import Winding
from srmcore.maps.end_winding import end_winding_inductance, with_end_winding
from srmcore.maps.validation import MEASURED_LU_GAP
from srmapp.turns import END_IMAGE_FACTOR, _lower_inductance, ripple_half, ripple_limited, ripple_note

MACHINE = make_8_6()
# The maps carry the end winding at END_IMAGE_FACTOR, as evaluate_stage2 builds them.
L_END = end_winding_inductance(MACHINE, END_IMAGE_FACTOR)
F = 20e3


def _req(**kw):
    values = dict(peak_power_w=10.47, peak_torque_nm=0.1, base_speed_rpm=1000.0, max_speed_rpm=2000.0,
                  switching_frequency_hz=F, phase_current_a=100.0)
    values.update(kw)
    return Requirements(**values)


def _winding(turns, current=105.0):
    return Winding(turns, 1, 1e-6, current, 0.1, 1.0, None)


def _map(psi_sat=None):
    r = synthetic_map(n_angles=24, currents=np.linspace(0.0, 400.0, 81), psi_sat=psi_sat)
    cur = r.currents
    lam = inductance(r.angles)[:, None] * cur[None, :]
    col = r.circuits.index(r.excited)
    l_inc = np.full(r.l_inc.shape, np.nan)
    if psi_sat is None:
        l_inc[..., col] = inductance(r.angles)[:, None] + 0 * cur[None, :]
    else:
        l_inc[..., col] = inductance(r.angles)[:, None] / np.cosh(lam / psi_sat) ** 2
    return with_end_winding(dataclasses.replace(r, l_inc=l_inc), L_END)


@pytest.mark.parametrize("psi_sat", [None, 0.5])
def test_regulated_current_plus_half_ripple_is_the_device_peak(psi_sat):
    r, req = _map(psi_sat), _req()
    w = _winding(MACHINE.turns_per_pole)
    (out,) = ripple_limited([w], r, MACHINE, req)
    half, _ = ripple_half(r, MACHINE, out, req, out.current)
    assert out.current + half <= 100.0 * (1 + 1e-9)
    assert out.current + half >= 100.0 * 0.998


def test_more_turns_give_a_higher_regulated_current():
    r, req = _map(), _req()
    a, b = ripple_limited([_winding(MACHINE.turns_per_pole), _winding(2 * MACHINE.turns_per_pole)], r, MACHINE, req)
    assert b.current > a.current


def test_max_bus_voltage_raises_the_ripple_in_proportion():
    r, w = _map(), _winding(MACHINE.turns_per_pole)
    lo, hi = _req(), _req(max_bus_voltage_v=800.0)
    assert ripple_half(r, MACHINE, w, hi, 20.0)[0] == pytest.approx(2 * ripple_half(r, MACHINE, w, lo, 20.0)[0])
    assert ripple_limited([w], r, MACHINE, hi)[0].current < ripple_limited([w], r, MACHINE, lo)[0].current


def test_unset_frequency_or_device_peak_changes_nothing():
    r, w = _map(), _winding(MACHINE.turns_per_pole)
    assert ripple_limited([w], r, MACHINE, _req(switching_frequency_hz=None)) == [w]
    assert ripple_limited([w], r, MACHINE, _req(phase_current_a=None)) == [w]


def test_zero_inductance_map_raises():
    r = _map()
    r = dataclasses.replace(r, l_inc=np.zeros_like(r.l_inc))
    with pytest.raises(ValueError, match="incremental inductance"):
        ripple_limited([_winding(MACHINE.turns_per_pole)], r, MACHINE, _req())


def test_max_bus_voltage_below_bus_is_refused():
    with pytest.raises(ValueError, match="max_bus_voltage_v"):
        _req(max_bus_voltage_v=300.0)


@pytest.mark.parametrize("device_peak", [120.0, 250.0, 350.0])
def test_saturated_tanh_map_true_peak_stays_under_the_device_peak(device_peak):
    psi_sat = 0.2
    cur = np.unique(400.0 * np.linspace(0, 1, 20) ** 2)
    r = synthetic_map(n_angles=24, currents=cur, psi_sat=psi_sat)
    col = r.circuits.index("A")
    lam = inductance(r.angles)[:, None] * r.currents[None, :]
    l_inc = np.full(r.l_inc.shape, np.nan)
    l_inc[..., col] = inductance(r.angles)[:, None] / np.cosh(lam / psi_sat) ** 2
    r, req = with_end_winding(dataclasses.replace(r, l_inc=l_inc), L_END), _req(phase_current_a=device_peak)
    (out,) = ripple_limited([_winding(MACHINE.turns_per_pole, 399.0)], r, MACHINE, req)
    th = np.linspace(0, 2 * np.pi / 6, 2001)
    true_l = (inductance(th) / np.cosh(inductance(th) * out.current / psi_sat) ** 2).min() + end_winding_inductance(MACHINE, 1.0)
    assert out.current + 0.25 * 400.0 / (true_l * F) <= device_peak * (1 + 1e-9)


def test_inductance_step_never_reads_above_a_neighbour():
    cur, low = np.array([0.0, 1.0, 2.0]), np.array([3.0, 1.0, 2.0])
    assert list(_lower_inductance(cur, low, np.array([0.5, 1.0, 1.5, 2.0, 5.0]))) == [1.0, 1.0, 1.0, 1.0, 1.0]


def test_note_present_when_the_ripple_binds_and_absent_when_it_does_not():
    r, req = _map(), _req()
    w = _winding(MACHINE.turns_per_pole, 100.0)
    (bound,) = ripple_limited([w], r, MACHINE, req)
    half, _ = ripple_half(r, MACHINE, bound, req, bound.current)
    assert ripple_note(r, MACHINE, bound, req, j_peak=100.0 / w.copper_area) == (
        f"current limit {bound.current:.1f} A: the 100 A device peak less half the {2 * half:.1f} A ripple "
        "(20 kHz, 400 V, hard chopping, lowest L_inc 0.748 mH)")
    low = _winding(MACHINE.turns_per_pole, 50.0)
    assert ripple_limited([low], r, MACHINE, req) == [low]
    assert ripple_note(r, MACHINE, low, req, j_peak=50.0 / low.copper_area) is None


def test_ripple_inductance_is_free_air_end_winding_over_one_plus_the_measured_lu_gap():
    r, w = _map(), _winding(MACHINE.turns_per_pole)
    _, low = ripple_half(r, MACHINE, w, _req(), 20.0)
    assert low == pytest.approx((inductance(r.angles).min() + end_winding_inductance(MACHINE, 1.0)) / (1 + MEASURED_LU_GAP))
