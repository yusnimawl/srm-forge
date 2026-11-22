import dataclasses
import json
import math

import pytest

from srmapp import thermal_summary as ts
from srmapp.cooling import ROWS, CoolingSetup
from srmapp.thermal import (BIG_K, HOT_SPOT_ABOVE, NO_STROKE, BudgetShare, Rating, RequirementCheck, SpeedRating)
from srmcore.post.rotor_stress import RotorStress
from srmcore.thermal.solve import HotSpot


class Req:
    base_speed_rpm = 2000.0
    max_speed_rpm = 6000.0
    continuous_power_w = 5000.0
    peak_power_w = 12000.0
    peak_torque_nm = 40.0
    hot_spot_limit_c = 160.0


def sr(rpm, cont, peak, env=50.0, hot=(150.0, "end_A1")):
    return SpeedRating(rpm, env, cont, peak, HotSpot(*hot), HotSpot(160.0, "coil_A1+"), 90.0, 95.0, 80.0, 85.0, 3, 10)


def rating(rated, shares=()):
    stress = RotorStress("ok", "", 7200.0, 1e8, 2e8, 1.5, "pole_root", "von_mises", 5e8, 2.4, 9000.0)
    return Rating(tuple(rated), tuple(rated), tuple(shares), 160.0, "H", CoolingSetup(), stress, {}, 1.0, 1, (), "x")


def check(holds=True, rpm=None, cont=(), peak=(), reason="", which="", hot_c=float("nan")):
    return RequirementCheck(holds, rpm, tuple(cont), tuple(peak), (), reason, which, hot_c)


def need(rpm):
    from srmapp.thermal import required_torques
    return required_torques(Req, rpm)


def test_binds_em_at_envelope():
    assert ts.binds(sr(2000.0, 50.0, 10.0), "continuous") == ts.BINDS_EM


def test_binds_heat_below_envelope():
    s = sr(2000.0, 30.0, 50.0)
    assert ts.binds(s, "continuous") == ts.BINDS_HEAT and ts.binds(s, "peak") == ts.BINDS_EM


def test_labels_cover_rows():
    assert set(ts.ROW_LABELS) == set(ROWS)
    assert ts.ROW_LABELS["em_torque"] == "EM torque uncertainty"
    assert set(ts.HINTS) <= set(ROWS) and ts.hint("nope") is None and ts.hint("liner")


def test_location_text():
    assert ts.location_text("end_coil_A1+") == "end winding, phase A"
    assert ts.location_text("coil_A1+") == "slot winding, phase A"
    assert ts.location_text("end_A1") == "end winding, phase A"
    assert ts.location_text("none") == "no steady state"


def _rated(k_cont, k_peak):
    out = []
    for rpm in (2000.0, 6000.0):
        c, p = need(rpm)
        out.append(sr(rpm, c * k_cont[rpm], p * k_peak[rpm], env=1e3))
    return out


def test_verdict_holds_smallest_margin():
    r = rating(_rated({2000.0: 1.20, 6000.0: 1.04}, {2000.0: 1.5, 6000.0: 1.3}))
    v = ts.verdict(r, check(), Req)
    assert v.holds and v.rpm == 6000.0 and v.which == "continuous" and v.binds == "heat"
    assert v.margin_pct == pytest.approx(4.0)
    assert v.text == "✓ Meets the requirement · smallest margin +4 % at 6000 r/min (continuous, binds heat)"


def test_verdict_failing_hot_spot():
    v = ts.verdict(None, check(False, 6000.0, reason=HOT_SPOT_ABOVE, which="continuous", hot_c=159.0), Req)
    assert v.holds is False and v.hot_spot_c == 159.0 and v.which == "continuous"
    assert v.text == "✗ Short at 6000 r/min: hot spot above the limit (159 °C of 160 °C) · binds heat"


def test_verdict_failing_peak_runaway_has_no_temperature():
    v = ts.verdict(None, check(False, 6000.0, reason=HOT_SPOT_ABOVE, which="peak"), Req)
    assert v.which == "peak" and v.hot_spot_c is None
    assert v.text == "✗ Short at 6000 r/min: hot spot above the limit · binds heat"


def test_verdict_failing_no_stroke():
    v = ts.verdict(None, check(False, 6000.0, reason=NO_STROKE, which="peak"), Req)
    assert v.text == "✗ Short at 6000 r/min: no stroke reaches the required torque · binds EM"
    assert v.hot_spot_c is None and v.which == "peak"


def test_verdict_failing_without_continuous_requirement():
    v = ts.verdict(None, check(False, 3000.0, reason=HOT_SPOT_ABOVE, which="peak", hot_c=171.0), Req)
    assert v.which == "peak" and "171 °C of 160 °C" in v.text


def test_verdict_no_check_is_none():
    v = ts.verdict(None, None, Req)
    assert v.holds is None and v.text


def test_no_continuous_requirement_skips_continuous():
    class R(Req):
        continuous_power_w = None
    out = []
    for rpm in (2000.0, 6000.0):
        out.append(sr(rpm, 0.0, R.peak_torque_nm * 2 if rpm == 2000.0 else 12000 / (6000 * math.pi / 30) * 1.1,
                      env=1e3))
    v = ts.verdict(rating(out), check(), R)
    assert v.which == "peak" and v.binds == "heat"
    assert ts.summary(rating(out), check(), R, 6)["speeds"][0]["need_continuous_nm"] is None


def test_shares_sorted_and_runaway():
    shares = [BudgetShare("liner", 2000.0, 5.0), BudgetShare("thermal_mesh", 2000.0, 0.0),
              BudgetShare("contact", 2000.0, BIG_K), BudgetShare("iron", 2000.0, 9.0),
              BudgetShare("end_winding_model", 2000.0, 0.0), BudgetShare("iron", 6000.0, 99.0)]
    out = ts.shares_at(rating(_rated({2000.0: 1, 6000.0: 1}, {2000.0: 1, 6000.0: 1}), shares), 2000.0)
    assert [d["row"] for d in out] == ["contact", "iron", "liner"]
    assert out[0]["runaway"] is True and out[1]["runaway"] is False and out[1]["label"] == ts.ROW_LABELS["iron"]


def test_summary_shares_carry_hints():
    shares = [BudgetShare("liner", 2000.0, 5.0), BudgetShare("iron", 2000.0, 9.0), BudgetShare("contact", 6000.0, 1.0),
              BudgetShare("air_gap", 6000.0, 0.5)]
    out = ts.summary(rating(_rated({2000.0: 1, 6000.0: 1}, {2000.0: 1, 6000.0: 1}), shares), check(), Req, 6)["shares"]
    assert [e["rpm"] for e in out] == [2000.0, 6000.0]
    assert out[0]["rows"][0]["row"] == "iron" and out[0]["rows"][0]["hint"] == ts.HINTS["iron"]
    assert out[1]["rows"][1]["hint"] is None
    assert ts.summary(None, check(), Req, 6)["shares"] == []


def test_nan_speed_is_null_safe():
    from srmweb.serialize import to_json
    nan = sr(2000.0, 0.0, 10.0, hot=(float("nan"), "none"))
    out = ts.summary(rating([nan]), check(False, 2000.0, reason=NO_STROKE), Req, 6)
    assert out["speeds"][0]["hot_spot_text"] == "no steady state"
    json.dumps(to_json(out), allow_nan=False)
    assert dataclasses.is_dataclass(ts.Verdict)


def test_iron_band_spans_the_rated_speeds():
    r = rating(_rated({2000.0: 1, 6000.0: 1}, {2000.0: 1, 6000.0: 1}))
    assert ts.iron_band(r, 6) == (3.2, 3.2)               # 200 and 600 Hz, under the first measured point
    assert ts.iron_band(r, 48) == (pytest.approx(3.4969, abs=1e-4), 7.0)   # 1600 Hz and 4800 Hz (held above the last point)
    assert ts.summary(r, check(), Req, 6)["iron_band"] == [3.2, 3.2]
