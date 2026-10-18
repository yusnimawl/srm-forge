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
    assert 0.98 * ideal < env.torque[0] <= 1.02 * ideal


def test_power_and_torque_follow_the_stroke_work():
    env = _env()
    np.testing.assert_allclose(env.torque, 4 * NR * env.work_torque / (2 * math.pi))
    assert env.power[0] == pytest.approx(env.torque[0] * 2 * math.pi * 100.0 / 60)


def test_no_torque_rise_with_speed_when_current_limited():
    env = _env()
    assert env.torque[0] >= 0.99 * env.torque[3]     # 100 rpm vs 3000 rpm


# The synthetic machine is small (3 mH, 20 A), so the voltage limit only binds at a low bus voltage.
def test_torque_falls_at_high_speed():
    env = _env(volts=100.0)
    assert env.torque[-1] < 0.75 * env.torque[0]


def test_more_bus_voltage_helps_at_high_speed():
    assert _env(volts=200.0).torque[-1] > _env(volts=100.0).torque[-1]


def test_resistance_costs_torque_and_gives_copper_loss():
    lossless, lossy = _env(r=0.0), _env(r=0.5)
    assert np.all(lossy.torque <= lossless.torque * (1 + 1e-3) + 1e-9)
    assert np.all(lossy.copper_loss > 0)
    assert np.all(lossy.efficiency < 1.0)


def test_loop_energy_matches_torque_work():
    env = _env()
    ok = env.work_torque > 0
    np.testing.assert_allclose(env.work_loop[ok], env.work_torque[ok], rtol=0.05)


def test_no_nan_or_infinite_values_when_no_stroke_produces_torque():
    env = _env(volts=0.5, l1=0.0)      # no saliency: no stroke produces torque, so the fallback row is used
    assert np.all(env.torque == 0)
    for name in ("torque", "power", "copper_loss", "theta_on", "theta_off"):
        assert np.all(np.isfinite(getattr(env, name))), name
    assert np.all(env.torque >= 0)
    assert np.all(env.theta_off > env.theta_on)


def test_turn_off_comes_after_turn_on():
    env = _env()
    assert np.all(env.theta_off > env.theta_on)
    assert np.all((env.theta_on >= 0) & (env.theta_off <= 1.25 * PERIOD))


def test_only_phase_a_maps_are_accepted():
    with pytest.raises(ValueError, match="phase A"):
        envelope(synthetic_map(excited="B"), MACHINE, 400.0, 0.0, SPEEDS)


def test_incomplete_map_is_rejected():
    with pytest.raises(ValueError):
        envelope(synthetic_map(complete=False), MACHINE, 400.0, 0.0, SPEEDS)


def test_current_limit_scales_the_low_speed_torque_with_the_square_of_the_current():
    full, half = _env(), _env_limited(10.0)
    assert half.torque[0] == pytest.approx(0.25 * full.torque[0], rel=0.03)


def _env_limited(limit, volts=400.0, r=0.0):
    return envelope(synthetic_map(n_angles=24), MACHINE, volts, r, SPEEDS, current_limit=limit)


@pytest.mark.parametrize("limit", [0.0, -1.0, 20.5])
def test_current_limit_outside_the_map_is_rejected(limit):
    with pytest.raises(ValueError, match="current limit"):
        _env_limited(limit)


def test_finer_drive_discretisation_agrees_at_low_speed():
    coarse = _env()
    fine = envelope(synthetic_map(n_angles=24), MACHINE, 400.0, 0.0, SPEEDS, n_theta=361, n_on=80, n_off=80)
    assert fine.torque[0] == pytest.approx(coarse.torque[0], rel=0.02)


def _env_rms(rms_limit, r=0.0):
    return envelope(synthetic_map(n_angles=24), MACHINE, 400.0, r, SPEEDS, rms_limit=rms_limit)


def test_i_rms_matches_the_copper_loss():
    env = _env(r=0.5)
    np.testing.assert_allclose(env.copper_loss, 4 * 0.5 * env.i_rms**2, rtol=1e-12)


def test_i_rms_of_a_flat_low_speed_stroke():
    env = _env()      # at 100 rpm the current reaches the 20 A limit almost at once and stays flat
    expected = 20.0 * math.sqrt((env.theta_off[0] - env.theta_on[0]) / PERIOD)
    assert env.i_rms[0] == pytest.approx(expected, rel=0.03)


def test_rms_limit_above_the_free_rms_changes_nothing():
    free = _env()
    loose = _env_rms(1.01 * float(np.max(free.i_rms)))
    np.testing.assert_array_equal(loose.torque, free.torque)


def test_binding_rms_limit_lowers_low_speed_torque():
    free = _env()
    limit = 0.7 * float(free.i_rms[0])
    capped = _env_rms(limit)
    assert capped.torque[0] < free.torque[0]
    assert np.all(capped.i_rms <= limit * (1 + 1e-9))


def test_rms_limit_with_no_valid_stroke_gives_zero_torque():
    env = _env_rms(1e-9)
    assert np.all(env.torque == 0) and np.all(env.i_rms == 0)
    for name in ("torque", "power", "copper_loss", "theta_on", "theta_off", "i_rms"):
        assert np.all(np.isfinite(getattr(env, name))), name


@pytest.mark.parametrize("limit", [0.0, -1.0])
def test_non_positive_rms_limit_is_rejected(limit):
    with pytest.raises(ValueError, match="rms limit"):
        _env_rms(limit)


def test_default_on_off_grid_is_80_by_80():
    from srmapp.drive import envelope as module
    assert (module.N_ON, module.N_OFF) == (80, 80)
