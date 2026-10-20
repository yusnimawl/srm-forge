from pathlib import Path

import numpy as np
import pytest
from sil_fixtures import analytic_motor

from srmsil.emumodel import edges_from_trace, run_model
from srmsil.run import run
from srmsil.scenario import ConverterSettings, Scenario

CTRL = Path(__file__).parents[1] / "sil" / "controllers"
ZERO = ConverterSettings(dead_time=0.0, turn_on_delay=0.0, turn_off_delay=0.0)
CASES = [("open_loop", {"theta_on": 0.1, "theta_off": 0.45}), pytest.param("pwm_fixed", {}, marks=pytest.mark.xfail(
        strict=True, reason="hard chop at 25 % duty: i_rms is sampled once per 5 us step against ~6 us current pulses (1.3 % low)")),
    ("pwm_fixed", {"soft": 1})]


@pytest.mark.parametrize("name, params", CASES)
def test_emulator_model_within_1pct(tmp_path, name, params):
    m = analytic_motor()
    kw = dict(speed_rpm=1000.0, duration=0.04, params=params)
    sil = run(m, str(CTRL / name), Scenario(**kw), cache_dir=tmp_path)
    cmd = run(m, str(CTRL / name), Scenario(**kw, converter=ZERO), cache_dir=tmp_path)
    edges = edges_from_trace(cmd.traces, 0.5e-6)
    got = run_model(m, edges, Scenario(**kw), tick_s=0.5e-6, cache_dir=tmp_path)
    a, b = sil.summary, got
    dt_ = abs(b.mean_torque - a.mean_torque) / abs(a.mean_torque)
    live = a.i_rms > 1e-9      # pwm_fixed drives phase 0 only
    assert np.all(b.i_rms[~live] == 0)
    di = np.abs(b.i_rms - a.i_rms)[live] / a.i_rms[live]
    print(f"{name}: mean torque SIL {a.mean_torque:.5f} model {b.mean_torque:.5f} err {dt_:.3%}; "
          f"i_rms err {np.array2string(di, formatter={'float': lambda x: f'{x:.3%}'})}")
    assert dt_ <= 0.01
    assert np.all(di <= 0.01)


def test_model_rejects_dynamic_and_odd_step(tmp_path):
    m = analytic_motor()
    e = np.zeros(0, [("t", "<u8"), ("gates", "<u2")])
    with pytest.raises(ValueError, match="fixed-speed"):
        run_model(m, e, Scenario(mode="dynamic", duration=0.001), tick_s=0.5e-6, cache_dir=tmp_path)
    with pytest.raises(ValueError, match="whole number"):
        run_model(m, e, Scenario(duration=0.001), tick_s=0.5e-6, step=5.2e-6, cache_dir=tmp_path)


def test_edges_from_trace():
    t = np.arange(6) * 0.5e-6
    tr = {"t": t, "gate_u": np.array([[0, 1, 1, 0, 0, 1]], np.uint8), "gate_l": np.array([[0, 0, 1, 1, 0, 0]], np.uint8)}
    e = edges_from_trace(tr, 0.5e-6)
    assert list(e["t"]) == [1, 2, 3, 4, 5] and list(e["gates"]) == [1, 0x101, 0x100, 0, 1]
    with pytest.raises(ValueError, match="stride"):
        edges_from_trace({**tr, "t": t * 2}, 0.5e-6)
