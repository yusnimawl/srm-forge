import math

import pytest

from srmcore.post.bearing_friction import BEARING_MU, bearing_friction


def test_deep_groove_matches_the_formula_and_the_table():
    r = bearing_friction("deep_groove_ball", 0.03, 200.0, 3000.0)
    assert r.mu == pytest.approx(0.00125)
    assert r.torque_nm == pytest.approx(0.00125 * 200.0 * 0.03 / 2)
    assert r.power_w == pytest.approx(r.torque_nm * 3000.0 * 2 * math.pi / 60)
    assert r.torque_low_nm == pytest.approx(0.0010 * 200.0 * 0.015)
    assert r.torque_high_nm == pytest.approx(0.0015 * 200.0 * 0.015)
    assert r.power_low_w < r.power_w < r.power_high_w


def test_table_8_1_values():
    assert BEARING_MU["tapered_roller"] == (0.0017, 0.0025)
    assert BEARING_MU["needle_full_complement"] == (0.0025, 0.0035)
    assert len(BEARING_MU) == 10


def test_zero_load_and_errors():
    assert bearing_friction("deep_groove_ball", 0.03, 0.0, 3000.0).power_w == 0.0
    with pytest.raises(ValueError):
        bearing_friction("plain", 0.03, 10.0, 1000.0)
    with pytest.raises(ValueError):
        bearing_friction("deep_groove_ball", 0.0, 10.0, 1000.0)
    with pytest.raises(ValueError):
        bearing_friction("deep_groove_ball", 0.03, -1.0, 1000.0)
