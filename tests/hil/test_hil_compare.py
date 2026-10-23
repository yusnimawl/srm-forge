"""run_hil on the fake rig, the matched SIL scenario and the HIL/SIL comparison bounds."""

import math
from dataclasses import replace

import numpy as np
import pytest
from sil_fixtures import analytic_motor

from srmsil.hil.compare import SETTLE_S, compare, match_plan, matched_scenario
from srmsil.hil.config import HilModes, write_hil_config
from srmsil.hil.fake import FakeRig
from srmsil.hil.proto import EMU_DT
from srmsil.hil.session import HilSession, run_hil
from srmsil.run import SimResult, SimSummary, make_config, run
from srmsil.scenario import Scenario

SCN = Scenario(speed_rpm=1000.0, duration=0.02, command_value=1.0)
R = 1.0125


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    return tmp_path_factory.mktemp("hil_compare")


def hil_run(cache, clock_ratio, scn=SCN):
    m = analytic_motor()
    s = HilSession(*FakeRig(m, clock_ratio=clock_ratio, cache_dir=cache))
    s.connect()
    return run_hil(s, m, "hysteresis", scn)


def matched(cache, res, clock_ratio, scn=SCN, end_s=True):
    """The comparison of res with its matched SIL at clock_ratio: the route's path (match_plan, the window shifted by
    its t0), or with end_s False the SIL from Start over the scenario's duration."""
    if end_s:
        plan = match_plan(replace(res, hil={**res.hil, "clock_ratio": clock_ratio}), HilModes(), analytic_motor())
        assert plan.scenario is not None, plan.reason
        return compare(res, run(analytic_motor(), "hysteresis", plan.scenario, cache_dir=cache), t0=plan.t0)
    ms = matched_scenario(scn, res.hil["latency_us"] * 1e-6, HilModes(), clock_ratio, m=analytic_motor(), end_s=None)
    return compare(replace(res, hil={**res.hil, "window_s": None}), run(analytic_motor(), "hysteresis", ms,
                                                                        cache_dir=cache))


@pytest.mark.parametrize("r", [1.0, R])
def test_run_hil_on_fake_matches_sil(cache, r):
    res = hil_run(cache, r)
    h = res.hil
    assert h["valid"], h["reason"]
    assert h["clock_measured"] and h["clock_ratio"] == pytest.approx(r, rel=1e-6)
    assert h["clock_spread_ppm"] < 1.0
    assert h["overruns"] == h["isr_overruns"] == h["dropped"] == 0
    assert h["capture_clipped"] == 0.0
    for k in ("step_mean_us", "step_max_us", "edge_jitter_ns", "latency_us", "isr_mean_us", "isr_max_us"):
        assert math.isfinite(h[k]), k
    assert res.controller == "hysteresis"
    n = round(SCN.duration / EMU_DT)
    assert res.traces["i"].shape == (4, n)
    t0, t1 = h["window_s"]
    assert t0 > 0.2 and t1 - t0 == pytest.approx((n - n // 2) * EMU_DT)
    assert res.traces["t"][n // 2] == t0
    assert res.summary.mean_torque > 0.5
    c = matched(cache, res, h["clock_ratio"])
    assert c.passed, c
    assert c.clock_measured and c.clock_ratio == h["clock_ratio"]


def test_clock_ratio_matters(cache):
    res = hil_run(cache, R)
    good = matched(cache, res, res.hil["clock_ratio"])
    nominal = matched(cache, res, None)
    assert max(abs(nominal.d_torque_pct), abs(nominal.d_irms_pct)) > 2 * max(abs(good.d_torque_pct),
                                                                              abs(good.d_irms_pct))


def test_window_matches_a_changing_run(cache):
    """Dynamic run that accelerates: only the SIL from the controller's start over the HIL's window matches."""
    scn = Scenario(mode="dynamic", speed_rpm=200.0, inertia=2e-3, duration=0.02, command_value=1.0)
    res = hil_run(cache, 1.0, scn)
    w = res.traces["omega"]
    assert w[-1] > 2 * 200.0 * 2 * math.pi / 60        # it has sped up well past the start speed by the capture
    good = matched(cache, res, 1.0, scn)
    assert good.passed, good
    old = matched(cache, res, 1.0, scn, end_s=False)
    assert not old.passed
    assert abs(old.d_torque_pct) + abs(old.d_irms_pct) > 10 * (abs(good.d_torque_pct) + abs(good.d_irms_pct))


def test_matched_scenario():
    m = analytic_motor()
    scn = matched_scenario(SCN, 8e-6, HilModes(), 1.011, m=m, end_s=0.25)
    assert scn.sensors.delay == 8e-6
    assert scn.controller_clock == 1.011
    assert scn.compute_delay == pytest.approx(1 / (20000.0 * 1.011))
    assert scn.duration == 0.25
    one = matched_scenario(SCN, 0.0, HilModes(current_sense="internal"), m=m, end_s=None)
    assert one.sensors.delay == 0.0 and one.controller_clock == 1.0 and one.compute_delay == pytest.approx(5e-5)
    assert one.command_value == SCN.command_value and one.duration == SCN.duration


@pytest.mark.parametrize("modes", [HilModes(), HilModes(current_sense="internal"),
                                   HilModes(current_sense="internal", dac="mcp4921x4")])
def test_matched_adc_equals_hil_config(tmp_path, modes):
    """The matched SIL hands the controller the HAL ADC constants that hil_config.h gives it on the Nucleo."""
    m = analytic_motor()
    scn = Scenario(bus_voltage=36.0)
    write_hil_config(modes, scn, m, tmp_path / "hil_config.h")
    h = {}
    for line in (tmp_path / "hil_config.h").read_text().splitlines():
        if line.startswith("#define HIL_ADC"):
            _, name, value = line.split()
            h[name] = float(value.rstrip("f"))
    cfg = make_config(m, matched_scenario(scn, 0.0, modes, m=m, end_s=None), None, 0, 1)
    assert cfg.adc_bits == h["HIL_ADC_BITS"]
    assert cfg.adc_offset_counts == h["HIL_ADC_OFFSET_COUNTS"]
    assert np.float32(cfg.adc_amps_per_count) == np.float32(h["HIL_ADC_AMPS_PER_COUNT"])
    vfs = cfg.volt_full_scale
    sil_volts = 2 * vfs / (2**cfg.adc_bits - 1) if vfs else 0.0      # srm_sim.c: the HAL's adc_volts_per_count
    assert np.float32(sil_volts) == np.float32(h["HIL_ADC_VOLTS_PER_COUNT"])
    if vfs:
        assert h["HIL_ADC_VOLT_OFFSET_COUNTS"] == 2 ** (cfg.adc_bits - 1)


def result(torque, irms, ripple, valid=True, clipped=0.0):
    s = SimSummary(mean_torque=torque, ripple_pct=ripple, i_rms=np.full(4, irms), copper_loss=0.0, power_in=0.0,
                   power_mech=0.0, beyond_map_fraction=0.0, energy_error=0.0, roundtrip_error=0.0)
    return SimResult({}, s, SCN, "hysteresis", "", "", hil={"valid": valid, "clock_ratio": 1.01,
                                                            "clock_measured": True, "capture_clipped": clipped})


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
    assert compare(result(2.0, 10.0, 40.0), sil).reason == ""
    assert "mean torque +3.10 %" in c.reason and "ripple +5.10 points" in c.reason
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


def test_clipped_capture_fails_comparison():
    c = compare(result(2.0, 10.0, 40.0, clipped=0.0123), result(2.0, 10.0, 40.0))
    assert not c.passed and c.reason == "capture clipped (1.2 % of samples)"
    assert c.d_torque_pct == 0.0


def test_compare_sil_short_of_window():
    """A SIL run that ends before (or has no samples in) the HIL window gives passed False, never an exception."""
    t = np.arange(100) * 1e-4
    sil = SimResult({"t": t, "torque": np.full(100, 2.0), "i": np.full((4, 100), 10.0, np.float32)},
                    result(2.0, 10.0, 0.0).summary, SCN, "hysteresis", "", "")
    hil = replace(result(2.0, 10.0, 0.0), hil={"valid": True, "window_s": (0.02, 0.03)})
    c = compare(hil, sil)
    assert not c.passed and c.reason == "SIL does not cover the HIL window"
    partial = replace(hil, hil={"valid": True, "window_s": (0.005, 0.02)})
    assert compare(partial, sil).reason == "SIL does not cover the HIL window"
    assert compare(replace(hil, hil={"valid": True, "window_s": (0.002, 0.008)}), sil).passed


def test_matched_scenario_end_s_is_required():
    with pytest.raises(TypeError):
        matched_scenario(SCN, 0.0, HilModes(), m=analytic_motor())


def captured(scn, t_start=1.0, n=2000, **hil):
    """A valid live capture of n emulator steps from t_start s after Start."""
    t = t_start + np.arange(n) * EMU_DT
    tr = {"t": t, "torque": np.ones(n), "i": np.ones((4, n), np.float32)}
    h = {"valid": True, "latency_us": 8.0, "clock_ratio": 1.0, "clock_measured": True,
         "window_s": (float(t[n // 2]), float(t[-1]) + EMU_DT), **hil}
    return SimResult(tr, result(1.0, 1.0, 0.0).summary, scn, "hysteresis", "", "", hil=h)


def test_match_plan_fixed_starts_settle_before_capture():
    scn = Scenario(speed_rpm=600.0, theta0=0.3, duration=0.02)
    cap = captured(scn, last_change_s=0.5)
    plan = match_plan(cap, HilModes(), analytic_motor())
    assert plan.reason == "" and plan.t0 == pytest.approx(1.0 - SETTLE_S)
    w = cap.hil["window_s"]
    assert plan.scenario.duration == pytest.approx(w[1] - plan.t0)
    turn = 600.0 / 60 * plan.t0 * 2 * math.pi
    assert math.cos(plan.scenario.theta0) == pytest.approx(math.cos(0.3 + turn))
    assert math.sin(plan.scenario.theta0) == pytest.approx(math.sin(0.3 + turn))
    early = match_plan(captured(scn, t_start=0.1), HilModes(), analytic_motor())
    assert early.t0 == 0.0 and early.scenario.theta0 == pytest.approx(0.3)


def test_match_plan_refusals():
    m, fixed = analytic_motor(), Scenario(speed_rpm=600.0)
    late = match_plan(captured(fixed, last_change_s=0.85), HilModes(), m)
    assert late.scenario is None and late.reason == "parameters or command changed within 0.2 s before the capture"
    dyn = Scenario(mode="dynamic", speed_rpm=200.0)
    assert "changed while running" in match_plan(captured(dyn, t_start=0.1, last_change_s=0.05), HilModes(), m).reason
    assert match_plan(captured(dyn, t_start=1.2), HilModes(), m).reason == (
        "dynamic run captured too late for the matched SIL (capture within 1 s of Start)")
    assert match_plan(captured(dyn, t_start=0.5), HilModes(), m).scenario is not None
    long = match_plan(captured(fixed, n=200_000), HilModes(), m)
    assert long.scenario is None and "too long" in long.reason
    assert "latency" in match_plan(captured(fixed, latency_us=None), HilModes(), m).reason
    bad = match_plan(captured(fixed, latency_us=1e6), HilModes(), m)
    assert bad.scenario is None and bad.reason.startswith("no matched SIL scenario")


def test_compare_shifts_the_window_by_t0():
    t = np.arange(100) * 1e-4
    sil = SimResult({"t": t, "torque": np.full(100, 2.0), "i": np.full((4, 100), 10.0, np.float32)},
                    result(2.0, 10.0, 0.0).summary, SCN, "hysteresis", "", "")
    hil = replace(result(2.0, 10.0, 0.0), hil={"valid": True, "window_s": (1.002, 1.008)})
    assert compare(hil, sil, t0=1.0).passed
    assert compare(hil, sil).reason == "SIL does not cover the HIL window"
