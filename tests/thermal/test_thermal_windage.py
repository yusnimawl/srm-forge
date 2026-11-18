import math

import pytest

from srmcore.thermal import windage as w

# The rig of NASA TM X-52851: cylinder 12.005 in diameter, 5.9 in long, gap 0.0565 in (inches to metres).
R, L, GAP = 12.005 / 2 * 0.0254, 5.9 * 0.0254, 0.0565 * 0.0254


def test_drag_coefficient_reproduces_the_printed_rows():
    for re, lam in w.TABLE_I:
        assert w.drag_coefficient(re) == pytest.approx(lam * 1e-3, rel=1e-12)


def test_extrapolation_is_continuous_and_follows_the_report_slopes():
    lo, hi = w.TABLE_I[0], w.TABLE_I[-1]
    assert w.drag_coefficient(lo[0] * (1 - 1e-9)) == pytest.approx(lo[1] * 1e-3, rel=1e-6)
    assert w.drag_coefficient(hi[0] * (1 + 1e-9)) == pytest.approx(hi[1] * 1e-3, rel=1e-6)
    assert w.drag_coefficient(lo[0] / 10) == pytest.approx(lo[1] * 1e-3 * 10 ** 0.5, rel=1e-9)
    assert w.drag_coefficient(hi[0] * 10) == pytest.approx(hi[1] * 1e-3 * 10 ** -0.22, rel=1e-9)


@pytest.mark.parametrize("rpm, air_c, measured_w", [(3700, 25.0, 44.655), (6410, 26.7, 212.34)])
def test_rig_windage_inside_the_band(rpm, air_c, measured_w):
    r = w.windage_loss(R, GAP, L, rpm, air_c)
    assert r.in_range
    assert abs(r.power_w / measured_w - 1.0) < w.BAND_REL


def test_band_is_the_gap_spread_plus_the_torque_accuracy():
    assert 0.05 < w.GAP_SPREAD < 0.6
    assert w.BAND_REL == pytest.approx(w.GAP_SPREAD + w.TORQUE_ACCURACY)


def test_power_scales_with_length_and_rises_with_speed():
    a = w.windage_loss(0.05, 5e-4, 0.1, 6000)
    assert w.windage_loss(0.05, 5e-4, 0.2, 6000).power_w == pytest.approx(2 * a.power_w)
    assert w.windage_loss(0.05, 5e-4, 0.1, 12000).power_w > 4 * a.power_w   # more than speed squared


def test_zero_speed_and_bad_input():
    assert w.windage_loss(0.05, 5e-4, 0.1, 0).power_w == 0.0
    with pytest.raises(ValueError):
        w.windage_loss(0.05, 0.0, 0.1, 1000)
    with pytest.raises(ValueError):          # air properties are cited for 20 to 60 degC only
        w.windage_loss(0.05, 5e-4, 0.1, 1000, air_c=80.0)


def test_notes_name_the_limits():
    r = w.windage_loss(0.05, 5e-4, 0.1, 6000)
    assert any("salient" in n for n in r.notes) and any("end-face" in n for n in r.notes)
    far = w.windage_loss(0.05, 5e-3, 0.1, 6000)     # gap/radius 0.1: outside the tested range
    assert not far.in_range and any("gap/radius" in n for n in far.notes)
    assert math.isfinite(far.power_w)
