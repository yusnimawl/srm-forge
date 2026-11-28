import dataclasses

import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import inductance, synthetic_map

from srmapp.requirements import Requirements
from srmapp.sizing.winding import Winding
from srmapp.turns import ripple_half, ripple_limited

MACHINE = make_8_6()
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
    return dataclasses.replace(r, l_inc=l_inc)


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
