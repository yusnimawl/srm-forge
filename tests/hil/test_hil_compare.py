"""run_hil on the fake rig, the matched SIL scenario and the HIL/SIL comparison bounds."""

import math
from dataclasses import replace

import numpy as np
import pytest
from sil_fixtures import analytic_motor

from srmsil.hil.compare import compare, matched_scenario, sense_latency
from srmsil.hil.config import HilModes
from srmsil.hil.fake import FakeRig
from srmsil.hil.session import HilSession, run_hil
from srmsil.run import SimResult, SimSummary, run
from srmsil.scenario import Scenario

SCN = Scenario(speed_rpm=1000.0, duration=0.02, command_value=1.0)
R = 1.0125


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    return tmp_path_factory.mktemp("hil_compare")


def hil_run(cache, clock_ratio):
    m = analytic_motor()
    s = HilSession(*FakeRig(m, clock_ratio=clock_ratio, cache_dir=cache))
    s.connect()
    return run_hil(s, m, "hysteresis", SCN)


def matched(cache, res, clock_ratio):
    scn = matched_scenario(SCN, res.hil["latency_us"] * 1e-6, HilModes(), clock_ratio)
    return run(analytic_motor(), "hysteresis", scn, cache_dir=cache)


@pytest.mark.parametrize("r", [1.0, R])
def test_run_hil_on_fake_matches_sil(cache, r):
    res = hil_run(cache, r)
    h = res.hil
    assert h["valid"], h["reason"]
    assert h["clock_measured"] and h["clock_ratio"] == pytest.approx(r, rel=1e-6)
    assert h["clock_spread_ppm"] < 1.0
    assert h["overruns"] == h["isr_overruns"] == h["dropped"] == 0
    for k in ("step_mean_us", "step_max_us", "edge_jitter_ns", "latency_us", "isr_mean_us", "isr_max_us"):
        assert math.isfinite(h[k]), k
    assert res.controller == "hysteresis"
    assert res.traces["i"].shape == (4, 4000)
    assert res.summary.mean_torque > 0.5
    c = compare(res, matched(cache, res, h["clock_ratio"]))
    assert c.passed, c
    assert c.clock_measured and c.clock_ratio == h["clock_ratio"]


def test_clock_ratio_matters(cache):
    res = hil_run(cache, R)
    good = compare(res, matched(cache, res, res.hil["clock_ratio"]))
    nominal = compare(res, matched(cache, res, None))
    assert max(abs(nominal.d_torque_pct), abs(nominal.d_irms_pct)) > 2 * max(abs(good.d_torque_pct),
                                                                              abs(good.d_irms_pct))


def test_matched_scenario():
    scn = matched_scenario(SCN, 8e-6, HilModes(), 1.011)
    assert scn.sensors.delay == pytest.approx(8e-6 + 4.15e-6 + 128 / 12.5e6)
    assert scn.controller_clock == 1.011
    assert sense_latency("internal") == 0.0
    assert sense_latency(HilModes()) == pytest.approx(4.15e-6 + 128 / 12.5e6)
    one = matched_scenario(SCN, 0.0, HilModes(current_sense="internal"))
    assert one.sensors.delay == 0.0 and one.controller_clock == 1.0
    assert one.command_value == SCN.command_value and one.duration == SCN.duration


def result(torque, irms, ripple, valid=True):
    s = SimSummary(mean_torque=torque, ripple_pct=ripple, i_rms=np.full(4, irms), copper_loss=0.0, power_in=0.0,
                   power_mech=0.0, beyond_map_fraction=0.0, energy_error=0.0, roundtrip_error=0.0)
    return SimResult({}, s, SCN, "hysteresis", "", "", hil={"valid": valid, "clock_ratio": 1.01,
                                                            "clock_measured": True})


def test_compare_bounds():
    sil = result(2.0, 10.0, 40.0)
    assert compare(result(2.0 * 1.029, 10.0, 40.0), sil).passed
    assert not compare(result(2.0 * 1.031, 10.0, 40.0), sil).passed
    assert compare(result(2.0, 10.0 * 0.971, 40.0), sil).passed
    assert not compare(result(2.0, 10.0 * 0.969, 40.0), sil).passed
    assert compare(result(2.0, 10.0, 44.9), sil).passed
    assert not compare(result(2.0, 10.0, 45.1), sil).passed
    c = compare(result(2.0 * 1.031, 10.0 * 0.98, 45.1), sil)
    assert c.d_torque_pct == pytest.approx(3.1) and c.d_irms_pct == pytest.approx(-2.0)
    assert c.d_ripple_pts == pytest.approx(5.1)
    assert c.clock_ratio == 1.01 and c.clock_measured
    assert not compare(result(2.0, 10.0, 40.0, valid=False), sil).passed
    assert not compare(replace(result(2.0, 10.0, 40.0), hil=None), sil).passed
    assert not compare(result(math.nan, 10.0, 40.0), sil).passed


def test_hil_block_survives_save(tmp_path):
    from srmsil.run import load, save

    r = replace(result(2.0, 10.0, 40.0), hil={"valid": True, "edge_jitter_ns": math.nan, "errors": ["x"]})
    save(r, tmp_path / "r.npz")
    assert load(tmp_path / "r.npz").hil == {"valid": True, "edge_jitter_ns": None, "errors": ["x"]}
    save(replace(r, hil=None), tmp_path / "p.npz")
    assert load(tmp_path / "p.npz").hil is None
