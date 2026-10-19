from pathlib import Path

import numpy as np
import pytest
from sil_fixtures import analytic_motor

from srmsil import build, run as sil_run
from srmsil.run import run
from srmsil.scenario import Scenario
from srmsil.tables import ctrl_tables, write_header


def share(el, q, theta_on=15.0, overlap=30.0):
    """numpy copy of the controller's share function."""
    stroke = 360.0 / q
    x = np.mod(el - theta_on, 360.0)
    s = lambda u: u * u * (3 - 2 * u)  # noqa: E731
    return np.where(x < overlap, s(np.clip(x / overlap, 0, 1)),
                    np.where(x < stroke, 1.0,
                             np.where(x < stroke + overlap, 1 - s(np.clip((x - stroke) / overlap, 0, 1)), 0.0)))


@pytest.mark.parametrize("overlap", [0.0, 30.0, "stroke"])
@pytest.mark.parametrize("q", [3, 4])
def test_shares_sum_to_one(q, overlap):
    ov = 360.0 / q if overlap == "stroke" else overlap
    el = np.linspace(0, 360, 721)
    with np.errstate(divide="ignore", invalid="ignore"):
        total = sum(share(el - k * 360.0 / q, q, overlap=ov) for k in range(q))
    assert total == pytest.approx(1.0)


def test_tsf_lower_ripple_than_hysteresis(tmp_path):
    m = analytic_motor()
    t_cmd = 0.3 * float(ctrl_tables(m).t_max)
    kw = {"tsf": {"pwm_hz": 20e3}, "hysteresis": {"isr_hz": 50e3}}

    def go(name, cmd):
        return run(m, name, Scenario(speed_rpm=200.0, duration=0.1, command_value=cmd, **kw[name]),
                   cache_dir=tmp_path).summary

    s = {"tsf": go("tsf", t_cmd)}
    # The hysteresis command is the torque at the window centre, and its 150 degree window overlaps phases, so
    # its mean sits above the command; scale the command (secant steps) to compare ripple at equal mean torque.
    cmd = t_cmd
    for _ in range(3):
        s["hysteresis"] = go("hysteresis", cmd)
        if abs(s["hysteresis"].mean_torque / t_cmd - 1) < 0.02:
            break
        cmd *= t_cmd / s["hysteresis"].mean_torque
    for r in s.values():
        assert r.mean_torque == pytest.approx(t_cmd, rel=0.10)
    assert s["tsf"].ripple_pct < s["hysteresis"].ripple_pct


def test_tsf_target_check(tmp_path):
    m = analytic_motor()
    write_header(m, ctrl_tables(m), tmp_path / "srm_motor_tables.h")
    root = Path(sil_run.__file__).parent / "c"
    common = root / "controllers" / "common"
    folder = root / "controllers" / "tsf"
    r = build.target_check([*build.controller_sources(folder), *build.controller_sources(common)],
                           [root, tmp_path, folder, common])
    assert r.ok, r.log
