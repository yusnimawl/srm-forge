import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

from srmapp.drive import envelope as module
from srmapp.drive.envelope import _simulate, _tables, envelope, min_copper_stroke

MACHINE = make_8_6()
SPEEDS = np.array([100.0, 500.0, 1500.0, 3000.0, 6000.0, 12000.0])
OLD_OFF_RANGE = (0.45, 0.995)       # the stroke ends at alignment


def _map():
    return synthetic_map(n_angles=24)


def _env(volts=400.0, r=0.1, **kw):
    return envelope(_map(), MACHINE, volts, r, SPEEDS, **kw)


def test_tail_never_lowers_torque():
    # n_off=200 puts a turn-off on every table index, so the new grid contains the old one
    new, old = _env(n_off=200), _env(_off_range=OLD_OFF_RANGE)
    assert np.all(new.torque >= old.torque * (1 - 1e-3))


def test_low_speed_unchanged():
    assert _env().torque[0] == pytest.approx(_env(_off_range=OLD_OFF_RANGE).torque[0], rel=0.005)


def test_tail_must_end_before_next_on():
    m = _map()
    t = _tables(m, 2 * np.pi / MACHINE.n_rotor_poles, 20.0, module.N_THETA)
    top = module.N_THETA - 1
    # still pulsing when the same phase would turn on again: the flux never returns to zero
    *_, valid = _simulate(t, 100.0 * 2 * np.pi / 60, 400.0, 0.1, np.array([45, 45]), np.array([top + 45, top]))
    assert not valid[0] and valid[1]


def test_high_speed_gains():
    fast = np.array([40000.0])
    new = envelope(_map(), MACHINE, 100.0, 0.1, fast, n_off=200)
    old = envelope(_map(), MACHINE, 100.0, 0.1, fast, _off_range=OLD_OFF_RANGE)
    assert new.torque[0] > 1.005 * old.torque[0]
    assert new.theta_off[0] > module.OFF_RANGE[0] * 2 * np.pi / MACHINE.n_rotor_poles


def test_waveforms_stay_one_period_and_integrate():
    env = _env(volts=100.0)
    w = env.waveforms
    assert w.current.shape == (len(SPEEDS), module.N_THETA - 1)
    np.testing.assert_allclose(4 * w.torque.mean(axis=1), env.torque, rtol=1e-3, atol=1e-9)
    np.testing.assert_allclose(np.sqrt((w.current**2).mean(axis=1)), env.i_rms, rtol=1e-3, atol=1e-9)


def test_min_copper_stroke():
    env = _env()
    target = 0.5 * env.torque[1]
    s = min_copper_stroke(_map(), MACHINE, 400.0, 0.1, SPEEDS[1], target)
    assert s is not None
    assert s.torque_avg >= target
    assert s.copper_dc_w <= env.copper_loss[1] * (1 + 1e-9)
    assert s.copper_dc_w == pytest.approx(4 * 0.1 * s.i_rms**2)
    assert s.current.shape == s.psi.shape == (module.N_THETA - 1,)
    assert s.theta_off > s.theta_on
    assert min_copper_stroke(_map(), MACHINE, 400.0, 0.1, SPEEDS[1], 2 * env.torque[1]) is None
