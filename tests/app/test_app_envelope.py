import math

import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import NR, PERIOD, synthetic_map

from srmapp.drive.envelope import envelope

MACHINE = make_8_6()          # Nr = 6, m = 4, matches the synthetic map
SPEEDS = np.array([100.0, 500.0, 1500.0, 3000.0, 6000.0, 12000.0])


def _env(volts=400.0, r=0.0, **kw):
    return envelope(synthetic_map(n_angles=24, **kw), MACHINE, volts, r, SPEEDS)


def test_low_speed_torque_matches_the_ideal_current_limited_stroke():
    env = _env()
    # ideal stroke at 20 A: ½ I² ΔL over the rising-inductance half pitch, ΔL ≈ 2 mH → 0.4 J
    ideal = 4 * NR * 0.4 / (2 * math.pi)
    assert 0.9 * ideal < env.torque[0] <= 1.02 * ideal


def test_power_is_torque_times_speed():
    env = _env()
    np.testing.assert_allclose(env.power, env.torque * env.speeds_rpm * 2 * math.pi / 60)


# The synthetic machine is small (3 mH, 20 A), so the voltage limit only binds at a low bus voltage.
def test_torque_falls_at_high_speed():
    env = _env(volts=100.0)
    assert env.torque[-1] < 0.5 * env.torque[0]


def test_more_bus_voltage_helps_at_high_speed():
    assert _env(volts=200.0).torque[-1] > _env(volts=100.0).torque[-1]


def test_resistance_costs_torque_and_gives_copper_loss():
    lossless, lossy = _env(r=0.0), _env(r=0.5)
    assert np.all(lossy.torque <= lossless.torque * (1 + 1e-6) + 1e-9)
    assert np.all(lossy.copper_loss > 0)
    assert np.all(lossy.efficiency < 1.0)


def test_loop_energy_matches_torque_work():
    env = _env()
    ok = env.work_torque > 0
    np.testing.assert_allclose(env.work_loop[ok], env.work_torque[ok], rtol=0.05)


def test_no_nan_or_infinite_values_even_when_flux_cannot_decay():
    env = _env(volts=5.0)      # a tiny bus voltage cannot demagnetise before alignment at speed
    for name in ("torque", "power", "copper_loss", "theta_on", "theta_off"):
        assert np.all(np.isfinite(getattr(env, name))), name
    assert np.all(env.torque >= 0)


def test_turn_off_comes_after_turn_on():
    env = _env()
    assert np.all(env.theta_off > env.theta_on)
    assert np.all((env.theta_on >= 0) & (env.theta_off <= PERIOD))


def test_only_phase_a_maps_are_accepted():
    with pytest.raises(ValueError, match="phase A"):
        envelope(synthetic_map(excited="B"), MACHINE, 400.0, 0.0, SPEEDS)


def test_incomplete_map_is_rejected():
    with pytest.raises(ValueError):
        envelope(synthetic_map(complete=False), MACHINE, 400.0, 0.0, SPEEDS)
