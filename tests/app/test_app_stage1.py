import pytest
from conftest import make_8_6

from srmapp.requirements import Requirements
from srmapp.sizing import estimates as est
from srmapp.sizing.stage1 import stage1, torque_upper_bound


def _req(**kw):
    values = dict(peak_power_w=30_000.0, peak_torque_nm=95.5, base_speed_rpm=3000.0, max_speed_rpm=9000.0)
    values.update(kw)
    return Requirements(**values)


def test_bound_sits_above_the_fem_static_peak_of_the_example_machine():
    # Sanity check only: the FEM static peak of this 8/6 at 20 A is 12.42 N·m (tests/maps/goldens_8_6.json).
    # A static peak is not a revolution average, so this only shows the bound is not absurdly low.
    assert torque_upper_bound(make_8_6(), 20.0) >= 12.42


def test_bound_scales_linearly_with_current_and_stack():
    p = make_8_6()
    assert torque_upper_bound(p, 40.0) == pytest.approx(2 * torque_upper_bound(p, 20.0))
    q = make_8_6(stack_length=0.2)
    assert torque_upper_bound(q, 20.0) == pytest.approx(2 * torque_upper_bound(p, 20.0))


def test_bound_does_not_depend_on_turns_at_fixed_current_density():
    # ψ_sat ∝ turns and i_peak ∝ 1/turns, so the product is turn-independent
    a = make_8_6(turns_per_pole=40)
    b = make_8_6(turns_per_pole=80)
    ta = torque_upper_bound(a, est.peak_current(a))
    tb = torque_upper_bound(b, est.peak_current(b))
    assert ta == pytest.approx(tb)


def test_small_motor_fails_a_large_torque_requirement():
    s = stage1(_req(), make_8_6())
    assert not s.passes and "torque" in s.reason


def test_easy_requirement_passes():
    s = stage1(_req(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0), make_8_6())
    assert s.passes and s.reason == ""
    assert s.mass.total > 0 and s.i_peak > 0


def test_mass_limit():
    s = stage1(_req(peak_power_w=1000.0, peak_torque_nm=3.2, max_mass_kg=0.5), make_8_6())
    assert not s.passes and "mass" in s.reason


def test_current_density_raises_the_bound_and_the_current():
    lo, hi = stage1(_req(), make_8_6(), j_peak=10e6), stage1(_req(), make_8_6(), j_peak=30e6)
    assert hi.i_peak == pytest.approx(3 * lo.i_peak)
    assert hi.torque_upper == pytest.approx(3 * lo.torque_upper)


def test_margin_tightens_the_filter():
    req = _req(peak_power_w=1000.0, peak_torque_nm=3.2)
    assert stage1(req, make_8_6(), margin=1.0).passes
    assert not stage1(req, make_8_6(), margin=1e6).passes


def test_mass_precedence_over_torque():
    s = stage1(_req(max_mass_kg=0.5), make_8_6())
    assert not s.passes and "mass" in s.reason and "torque" not in s.reason


def test_narrow_rotor_pole_does_not_lower_the_bound():
    p = make_8_6()
    narrow = p.model_copy(update={"rotor_pole_arc": p.rotor_pole_arc / 2})
    assert torque_upper_bound(narrow, 20.0) == pytest.approx(torque_upper_bound(p, 20.0))
