import math
from pathlib import Path

import numpy as np
import pytest
from sil_fixtures import analytic_motor

from srmsil.run import REFERENCE, SimError, controller_dir, decimate, load, run, save
from srmsil.scenario import Scenario

CTRL = Path(__file__).parent / "controllers"
TAU = analytic_motor().pole_pitch
PARAMS = {"theta_on": 0.5 * TAU, "theta_off": 0.65 * TAU}


def go(tmp_path, name="open_loop", timeout_s=300.0, duration=0.005):
    return run(analytic_motor(), str(CTRL / name), Scenario(duration=duration, speed_rpm=1000.0, params=PARAMS),
               cache_dir=tmp_path, timeout_s=timeout_s)


def test_run_open_loop_end_to_end(tmp_path):
    a = go(tmp_path)
    assert all(np.isfinite(v).all() for v in a.traces.values())
    assert a.compile_log is not None and a.controller == str(CTRL / "open_loop")
    b = go(tmp_path)
    assert a.source_hash == b.source_hash and b.compile_log == ""


def test_crash_is_sim_error(tmp_path):
    with pytest.raises(SimError, match="crashed"):
        go(tmp_path, "crash")
    go(tmp_path, duration=0.001)


def test_hang_times_out(tmp_path):
    with pytest.raises(SimError, match="timed out"):
        go(tmp_path, "hang", timeout_s=5)
    go(tmp_path, duration=0.001)


def test_link_error_carries_log(tmp_path):
    with pytest.raises(SimError) as e:
        go(tmp_path, "broken")
    assert "ctrl_isr" in e.value.log
    go(tmp_path, duration=0.001)


def test_bad_folder_is_value_error(tmp_path):
    with pytest.raises(ValueError):
        go(tmp_path / "x", "no_such_controller")


def test_reference_names_map_to_folders():
    for name in REFERENCE:
        assert controller_dir(name).name == name and controller_dir(name).parent.name == "controllers"


def test_save_load_roundtrip(tmp_path):
    a = go(tmp_path, duration=0.002)
    save(a, tmp_path / "r.npz")
    b = load(tmp_path / "r.npz")
    assert b.scenario == a.scenario and b.controller == a.controller and b.source_hash == a.source_hash
    assert b.summary.mean_torque == a.summary.mean_torque
    assert np.array_equal(b.summary.i_rms, a.summary.i_rms)
    assert b.traces.keys() == a.traces.keys()
    assert all(np.array_equal(a.traces[k], b.traces[k]) for k in a.traces)


def test_decimate_keeps_extremes():
    n = 1_000_000
    t = np.arange(n) * 1e-6
    y = (np.arange(n) % 1000).astype(float)
    y[123_456] = -5.0
    y[654_321] = 2000.0
    dt, dy = decimate(t, y, 1000)
    assert dy.min() == -5.0 and dy.max() == 2000.0 and len(dt) <= 2000
    assert np.all(np.diff(dt) > 0)
    t2, y2 = decimate(t[:100], y[:100], 1000)
    assert t2 is not None and len(t2) == 100 and math.isfinite(y2[0])
