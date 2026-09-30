import math
from types import SimpleNamespace

import numpy as np
import pytest
from conftest import make_8_6, make_12_8
from map_fixtures import L0, L1, PERIOD, synthetic_map

from srmcore.maps.grids import aligned_angle
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


def test_key_numbers_linear_map():
    r = synthetic_map()
    k = key_numbers(r, make_8_6())
    assert k.i_max == 20
    assert k.aligned_angle == 0
    assert k.unaligned_angle == pytest.approx(PERIOD / 2)
    assert k.la == pytest.approx(L0 + L1, rel=1e-12)
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
