import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import PERIOD, synthetic_map

from srmapp.drive.envelope import envelope, line_current, power_factor

MACHINE = make_8_6()
SPEEDS = np.array([100.0, 500.0, 1500.0, 3000.0, 6000.0, 12000.0])


def _env(volts=400.0, r=0.0, **kw):
    return envelope(synthetic_map(n_angles=24, **kw), MACHINE, volts, r, SPEEDS)


def test_waveform_shapes_and_grid():
    env = _env(r=0.5); w = env.waveforms
    assert w.theta.shape == (180,) and w.theta[0] == 0.0
    assert w.theta[1] == pytest.approx(PERIOD / 180)
    for name in ("current", "psi", "voltage", "torque", "line"):
        assert getattr(w, name).shape == (len(SPEEDS), 180), name


def test_waveforms_integrate_back_to_the_envelope():
    env = _env(r=0.5); w = env.waveforms
    np.testing.assert_allclose(4 * w.torque.mean(axis=1), env.torque, rtol=1e-3, atol=1e-9)
    np.testing.assert_allclose(4 * 0.5 * (w.current**2).mean(axis=1), env.copper_loss, rtol=1e-3, atol=1e-9)
    np.testing.assert_allclose(np.sqrt((w.current**2).mean(axis=1)), env.i_rms, rtol=1e-3, atol=1e-9)


def test_line_current_mean_times_bus_voltage_is_the_input_power():
    env = _env(r=0.5); ok = env.torque > 0
    np.testing.assert_allclose(env.line_mean[ok] * 400.0, (env.power + env.copper_loss)[ok], rtol=0.05)
    np.testing.assert_allclose(env.line_mean, env.waveforms.line.mean(axis=1))
    np.testing.assert_allclose(env.line_rms, np.sqrt((env.waveforms.line**2).mean(axis=1)))


def test_line_current_of_one_phase_is_its_bus_current():
    p = np.sin(np.linspace(0, 2 * np.pi, 180, endpoint=False))
    np.testing.assert_allclose(line_current(p, 1), p)


def test_line_current_sums_shifted_phases_for_any_phase_count():
    rng = np.random.default_rng(0); p = rng.random(180)
    for q in (3, 4, 7):                     # 180 / 7 is not an integer: interpolated shift
        out = line_current(p, q)
        assert out.mean() == pytest.approx(q * p.mean(), rel=1e-12)
    np.testing.assert_allclose(line_current(p, 4), sum(np.roll(p, 45 * j) for j in range(4)))


def test_power_factor_is_one_for_in_phase_sinusoids():
    v = 10 * np.sin(np.linspace(0, 2 * np.pi, 180, endpoint=False)); i = 2 * v / 10
    power = np.array([3 * np.mean(v * i)])
    assert power_factor(power, v[None], i[None], 3)[0] == pytest.approx(1.0, rel=1e-12)


def test_envelope_power_factor_is_output_over_phase_volt_amperes():
    env = _env(r=0.5); w = env.waveforms; ok = env.torque > 0
    rms = lambda x: np.sqrt((x**2).mean(axis=1))
    np.testing.assert_allclose(env.power_factor[ok], (env.power / (4 * rms(w.voltage) * rms(w.current)))[ok])
    assert np.all((env.power_factor[ok] > 0) & (env.power_factor[ok] <= 1))


def test_no_stroke_rows_are_zero_with_nan_power_factor():
    env = _env(volts=0.5, l1=0.0)
    for name in ("current", "psi", "voltage", "torque", "line"):
        assert np.all(getattr(env.waveforms, name) == 0), name
    assert np.all(np.isnan(env.power_factor)) and np.all(env.line_mean == 0)
