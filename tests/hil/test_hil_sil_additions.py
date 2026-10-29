import numpy as np
import pytest
from sil_fixtures import analytic_motor
from test_sil_core import IDEAL, run

from srmsil.run import SimError
from srmsil.run import run as sil_run
from srmsil.scenario import ParamStep, Scenario, SensorSettings


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    return tmp_path_factory.mktemp("hil_sil_additions")


def test_sensor_delay_shifts_adc_trace(cache):
    kw = dict(speed_rpm=1000.0, duration=0.002, dt=0.5e-6, isr_hz=1e6)
    m = analytic_motor()
    base = run(cache, "pwm_fixed", m, "d", **kw).traces["adc_i"][0]
    late = run(cache, "pwm_fixed", m, "d", sensors={"delay": 10e-6}, **kw).traces["adc_i"][0]
    lsb = 25.0 / 4095
    assert base.max() > 10 * lsb
    assert np.abs(late[20:] - base[:-20]).max() <= lsb + 1e-6
    assert np.abs(late[:20]).max() == 0.0


def test_voltage_channels_read_phase_voltage(cache):
    m = analytic_motor(resistance=5.0, saturating=False)
    res = run(cache, "volt_step", m, "v", speed_rpm=0.0, duration=0.002, dt=1e-6, bus_voltage=12.0, isr_hz=1e5,
              converter=IDEAL, adc={"volt_full_scale": 100.0, "volt_rc_tau": 0.0})
    per_count = 200.0 / 4095
    codes = 2048 + res.traces["adc_v"][:, -1] / per_count
    assert codes[0] == pytest.approx(2048 + round(12.0 / 200.0 * 4095), abs=1)
    assert codes[1:] == pytest.approx(2048, abs=1)
    off = run(cache, "volt_step", m, "v", speed_rpm=0.0, duration=0.002, dt=1e-6, bus_voltage=12.0, isr_hz=1e5,
              converter=IDEAL)
    assert np.all(off.traces["adc_v"] == 0.0)


def test_live_param_changes_torque(cache):
    m = analytic_motor()
    kw = dict(speed_rpm=1000.0, duration=0.02, dt=0.5e-6, params={"theta_on": 0.1, "theta_off": 0.45})
    tail = lambda r: r.traces["torque"][r.traces["t"] >= 0.015].mean()  # noqa: E731
    base = tail(run(cache, "open_loop", m, "p", **kw))
    cut = tail(run(cache, "open_loop", m, "p", param_steps=[ParamStep(time=0.01, name="theta_off", value=0.30)], **kw))
    assert abs(cut) < 0.9 * abs(base)


def test_live_param_refused_is_error(cache):
    with pytest.raises(SimError) as e:
        sil_run(analytic_motor(), "hysteresis",
                Scenario(mode="dynamic", speed_rpm=300.0, duration=0.01, command_value=0.5,
                         param_steps=[ParamStep(time=0.002, name="resolver_pole_pairs", value=2.0)]), cache_dir=cache)
    assert "refused live parameter resolver_pole_pairs (code -2)" in str(e.value)


def test_scenario_validation():
    with pytest.raises(ValueError, match="2048"):
        Scenario(dt=0.1e-6, sensors=SensorSettings(delay=1e-3))
    with pytest.raises(ValueError):
        ParamStep(time=0.0, name="x" * 24, value=1.0)


@pytest.mark.parametrize("ctrl, names", [("hysteresis", ["band", "soft", "theta_off", "torque_limit"]),
                                         ("pwm_current", ["kp", "ki", "f_bw", "theta_on"]),
                                         ("tsf", ["theta_on", "overlap", "kp", "speed_kp"])])
def test_reference_controllers_accept_live_params(cache, ctrl, names):
    steps = [ParamStep(time=0.002 + 1e-4 * i, name=n, value=v) for i, (n, v) in
             enumerate(zip(names, [1.0, 1.0, 120.0, 5.0]))]
    scn = Scenario(mode="dynamic", speed_rpm=300.0, duration=0.006, command_value=0.5, param_steps=steps)
    assert sil_run(analytic_motor(), ctrl, scn, cache_dir=cache).summary.energy_error < 0.05


def test_torque_limit_is_live(cache):
    scn = dict(speed_rpm=1000.0, duration=0.03, command_value=1.0)
    m = analytic_motor()
    r = sil_run(m, "hysteresis", Scenario(**scn, param_steps=[ParamStep(time=0.015, name="torque_limit", value=0.3)]),
                cache_dir=cache)
    t = r.traces["t"]
    before = r.traces["torque"][(t >= 0.008) & (t < 0.015)].mean()
    after = r.traces["torque"][t >= 0.02].mean()
    assert before > 0.6 and after < 0.5 * before


def test_delay_step_rounding_boundary():
    Scenario(dt=1e-3 / 2048.4, sensors=SensorSettings(delay=1e-3))          # rounds to 2048 steps
    with pytest.raises(ValueError, match="2049 steps"):
        Scenario(dt=1e-3 / 2048.6, sensors=SensorSettings(delay=1e-3))      # rounds to 2049 steps
