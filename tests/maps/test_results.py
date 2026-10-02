import dataclasses
import math
from types import SimpleNamespace

import numpy as np
import pytest
from conftest import make_8_6, make_12_8
from map_fixtures import L0, L1, PERIOD, synthetic_map

from srmcore.maps.grids import aligned_angle, current_grid
from srmcore.maps.results import inductance_curves, key_numbers

D = math.radians


@pytest.mark.parametrize("machine, expected", [
    (make_8_6(), [0, 15, 30, 45]),
    (make_12_8(), [0, 15, 30]),
    (SimpleNamespace(n_rotor_poles=4, n_phases=3), [0, 30, 60]),
])
def test_aligned_angle(machine, expected):
    got = [aligned_angle(machine, p) for p in "ABCD"[:machine.n_phases]]
    assert got == pytest.approx([D(x) for x in expected])


def test_aligned_angle_rejects_unknown_phase():
    for bad in ("E", "AB", "", "a"):
        with pytest.raises(ValueError, match="not a phase"):
            aligned_angle(make_8_6(), bad)


def test_key_numbers_linear_map():
    r = synthetic_map()
    k = key_numbers(r, make_8_6())
    assert k.i_max == 20
    assert k.aligned_angle == 0
    assert k.unaligned_angle == pytest.approx(PERIOD / 2)
    assert k.la == pytest.approx(L0 + L1, rel=1e-12)  # linear map: any current gives the same secant
    assert k.lu == pytest.approx(L0 - L1, rel=1e-2)
    assert k.la_lu == pytest.approx(k.la / k.lu)
    assert k.psi_max == pytest.approx((L0 + L1) * 20)
    assert k.peak_torque == pytest.approx(np.abs(r.torque_arkkio).max())
    assert k.peak_torque == pytest.approx(0.5 * 6 * L1 * 400, rel=5e-2)


def test_key_numbers_incomplete():
    with pytest.raises(ValueError):
        key_numbers(synthetic_map(complete=False), make_8_6())


def test_inductance_curves():
    r = synthetic_map()
    full = inductance_curves(r)
    assert full.shape == (len(r.angles), len(r.currents) - 1)
    assert full == pytest.approx(np.tile(L0 + L1 * np.cos(6 * r.angles)[:, None], (1, full.shape[1])))
    sel = inductance_curves(r, [r.currents[2], r.currents[-1]])
    assert sel.shape == (len(r.angles), 2)
    with pytest.raises(ValueError):
        inductance_curves(r, [1.2345])


def test_key_numbers_read_la_at_five_percent_of_i_max():
    r = synthetic_map(psi_sat=0.05, currents=current_grid(20.0, 8))
    k = key_numbers(r, make_8_6())
    i = 0.05 * 20.0
    assert k.la == pytest.approx(0.05 * np.tanh((L0 + L1) * i / 0.05) / i, rel=1e-9)
    assert k.psi_max == pytest.approx(0.05 * np.tanh((L0 + L1) * 20 / 0.05), rel=1e-12)
    assert abs(k.psi_max / 20 - k.la) > 0.05 * k.la  # I_max secant would differ
    assert k.la_lu == pytest.approx(k.la / k.lu)


def test_key_numbers_after_turns_rescale():
    r = synthetic_map(currents=current_grid(20.0, 8))
    r = dataclasses.replace(r, currents=r.currents / 3.0, psi=r.psi * 3.0)
    key_numbers(r, make_8_6())                         # must not raise


def test_key_numbers_without_la_current_raises():
    with pytest.raises(ValueError, match="0.05"):
        key_numbers(synthetic_map(currents=np.linspace(0, 20, 9), la_node=False), make_8_6())


def test_inductance_curves_rejects_zero_current():
    with pytest.raises(ValueError):
        inductance_curves(synthetic_map(), [0.0])
