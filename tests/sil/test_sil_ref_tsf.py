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


@pytest.mark.parametrize("q", [3, 4])
def test_shares_sum_to_one(q):
    el = np.linspace(0, 360, 721)
    total = sum(share(el - k * 360.0 / q, q) for k in range(q))
    assert total == pytest.approx(1.0)


def test_tsf_lower_ripple_than_hysteresis(tmp_path):
    m = analytic_motor()
    t_cmd = 0.3 * float(ctrl_tables(m).t_max)
    s = {}
    for name, kw in (("tsf", {"pwm_hz": 20e3}), ("hysteresis", {"isr_hz": 50e3})):
        s[name] = run(m, name, Scenario(speed_rpm=200.0, duration=0.1, command_value=t_cmd, **kw),
                      cache_dir=tmp_path).summary
    # The hysteresis controller regulates i_ref at the window centre, so with its 150 degree window its mean
    # torque is about 20 % above the command here; only TSF is held to 10 %.
    assert s["tsf"].mean_torque == pytest.approx(t_cmd, rel=0.10)
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
