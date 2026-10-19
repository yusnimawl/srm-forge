import math
import re
from pathlib import Path

import numpy as np
import pytest
from sil_fixtures import analytic_motor

from srmsil import build, run as sil_run
from srmsil.run import PARAMS, SimError, run
from srmsil.scenario import Scenario
from srmsil.tables import ctrl_tables, write_header

N_R = 6


def el_deg(res, k, m):
    """Electrical degrees from unaligned of phase k at every trace sample."""
    th = np.mod(res.traces["theta"] - k * m.stroke, m.pole_pitch)
    return np.mod(np.degrees(th) * m.n_rotor_poles + 180.0, 360.0)


def i_ref_of(m, torque, on=0.0, off=150.0):
    """i*(theta, T) at the window centre, from the same table the controller gets."""
    ct = ctrl_tables(m)
    th = (math.radians(0.5 * (on + off) - 180.0) / m.n_rotor_poles) % m.pole_pitch
    x = th / m.pole_pitch * ct.i_of_t.shape[0]
    j = int(x)
    col = torque / ct.t_max * (ct.i_of_t.shape[1] - 1)
    c = int(col)
    row = lambda r: np.interp(col, [c, c + 1], ct.i_of_t[r % ct.i_of_t.shape[0], c:c + 2])  # noqa: E731
    return float((1 - (x - j)) * row(j) + (x - j) * row(j + 1))


def windows(el, on=0.0, off=150.0):
    """(start, stop) sample index pairs of each contiguous stretch inside the window."""
    inside = (el >= on) & (el < off)
    edges = np.flatnonzero(np.diff(inside.astype(int)))
    starts = [0] if inside[0] else []
    stops = []
    for e in edges:
        (starts if not inside[e] else stops).append(e + 1)
    if inside[-1]:
        stops.append(len(inside))
    return list(zip(starts, stops))


def test_hysteresis_stays_in_band(tmp_path):
    m = analytic_motor()
    t_cmd = 0.5 * float(ctrl_tables(m).t_max)
    isr = 50e3
    res = run(m, "hysteresis", Scenario(speed_rpm=300.0, duration=0.05, isr_hz=isr, command_value=t_cmd),
              cache_dir=tmp_path)
    i_ref = i_ref_of(m, t_cmd)
    band = 0.05 * float(m.currents[-1])
    # One ISR period of rise and the compute delay (one period) at the largest slope.
    slack = 2 * m.bus_voltage / float(ctrl_tables(m).l_min) / isr
    n_checked = 0
    for k in range(m.n_phases):
        i = res.traces["i"][k]
        for a, b in windows(el_deg(res, k, m)):
            seg = i[a:b]
            first = int(np.argmax(seg >= i_ref - band / 2))
            if seg.max() < i_ref - band / 2 or first >= len(seg) - 10:
                continue
            held = seg[first:]
            n_checked += 1
            assert held.max() <= i_ref + band / 2 + slack
            assert held.min() >= i_ref - band / 2 - slack
    assert n_checked >= 4


def test_pwm_current_tracks_step(tmp_path):
    m = analytic_motor()
    t_cmd = 0.5 * float(ctrl_tables(m).t_max)
    res = run(m, "pwm_current", Scenario(speed_rpm=300.0, duration=0.08, command_value=t_cmd), cache_dir=tmp_path)
    i_ref = i_ref_of(m, t_cmd)
    t = res.traces["t"]
    n_checked = 0
    for k in range(m.n_phases):
        i = res.traces["i"][k]
        for a, b in windows(el_deg(res, k, m)):
            if a == 0 or b == len(t):   # a window cut by the run's start or end
                continue
            seg_t, seg_i = t[a:b] - t[a], i[a:b]
            settled = seg_i[(seg_t > 1e-3) & (seg_t < seg_t[-1] - 0.3e-3)]
            assert settled.size > 0
            assert settled.mean() == pytest.approx(i_ref, rel=0.02)
            n_checked += 1
    assert n_checked >= 4


def test_speed_mode_reaches_speed(tmp_path):
    # A load is needed: the controllers only motor, so an overshoot is not braked.
    m = analytic_motor()
    res = run(m, "pwm_current",
              Scenario(mode="dynamic", speed_rpm=0.0, command_mode="speed", command_value=500.0, inertia=1e-4,
                       load=0.2, duration=0.3), cache_dir=tmp_path)
    omega = res.traces["omega"][-1]
    assert omega == pytest.approx(500.0 * 2 * math.pi / 60, rel=0.05)


def test_reference_controllers_target_check(tmp_path):
    m = analytic_motor()
    write_header(m, ctrl_tables(m), tmp_path / "srm_motor_tables.h")
    root = Path(sil_run.__file__).parent / "c"
    common = root / "controllers" / "common"
    for name in ("hysteresis", "pwm_current"):
        folder = root / "controllers" / name
        r = build.target_check([*build.controller_sources(folder), *build.controller_sources(common)],
                               [root, tmp_path, folder, common])
        assert r.ok, r.log


def test_unknown_param_rejected_by_reference(tmp_path):
    with pytest.raises(SimError, match="nope"):
        run(analytic_motor(), "hysteresis", Scenario(duration=0.001, params={"nope": 1.0}), cache_dir=tmp_path)


@pytest.mark.parametrize("name", sorted(PARAMS))
def test_readme_parameters_listed_in_params(name):
    readme = (Path(sil_run.__file__).parent / "c" / "controllers" / name / "README.md").read_text()
    documented = set(re.findall(r"^\| `(\w+)` \|", readme, re.M))
    assert documented and documented == {p[0] for p in PARAMS[name]}
