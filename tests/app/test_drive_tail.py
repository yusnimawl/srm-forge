import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

from srmapp.drive import envelope as module
from srmapp.drive.envelope import _simulate, _tables, envelope, min_copper_stroke

MACHINE = make_8_6()
SPEEDS = np.array([100.0, 500.0, 1500.0, 3000.0, 6000.0, 12000.0])
# Best torques (N·m) of the rule in which every stroke ends at alignment (the drive model before the flux tail),
# on this map with 400 V and 0.1 ohm at SPEEDS, and with 100 V and 0.1 ohm at 12000 and 40000 rpm.
OLD_TORQUE = np.array([1.52771013, 1.52683981, 1.52131823, 1.51281672, 1.46507874, 1.33394455])
OLD_TORQUE_100V = np.array([0.57598647, 0.06004658])


def _map():
    return synthetic_map(n_angles=24)


def _env(volts=400.0, r=0.1, **kw):
    return envelope(_map(), MACHINE, volts, r, SPEEDS, **kw)


def test_tail_never_lowers_torque():
    assert np.all(_env().torque >= OLD_TORQUE * (1 - 1e-3))


def test_low_speed_unchanged():
    assert _env().torque[0] == pytest.approx(OLD_TORQUE[0], rel=0.005)


def test_off_axis_contains_the_old_axis():
    top = module.N_THETA - 1
    old = set(np.round(np.linspace(0.45, 0.995, module.N_OFF) * top).astype(int))
    on, off = module._stroke_pairs(module.N_THETA, module.N_ON, module.N_OFF)
    assert old <= set(off) and off.max() > 1.2 * top and off.max() <= 1.25 * top and np.all(off > on)


def test_tail_must_end_before_next_on():
    m = _map()
    t = _tables(m, 2 * np.pi / MACHINE.n_rotor_poles, 20.0, module.N_THETA)
    top = module.N_THETA - 1
    # still pulsing when the same phase would turn on again: the flux never returns to zero
    *_, valid = _simulate(t, 100.0 * 2 * np.pi / 60, 400.0, 0.1, np.array([45, 45]), np.array([top + 45, top]))
    assert not valid[0] and valid[1]


def test_high_speed_gains():
    new = envelope(_map(), MACHINE, 100.0, 0.1, np.array([12000.0, 40000.0]))
    assert new.torque[0] > 1.5 * OLD_TORQUE_100V[0]            # 0.58 -> 1.06 N·m
    assert new.torque[1] >= OLD_TORQUE_100V[1] * (1 - 1e-3)


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


@pytest.mark.parametrize("torque", [0.0, -1.0])
def test_min_copper_stroke_rejects_non_positive_torque(torque):
    with pytest.raises(ValueError, match="torque"):
        min_copper_stroke(_map(), MACHINE, 400.0, 0.1, 500.0, torque)
