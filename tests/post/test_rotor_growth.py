"""Rotor growth and gap closure (spec R5 section 9, Growth)."""
import math

import pytest

from conftest import make_8_6
from srmcore.materials.library import load_material
from srmcore.post.rotor_stress import _disc_rim_displacement, gap_closure

MECH = load_material("10JNEX900").mechanical
P = make_8_6()
RHO = 7490.0
ALPHA = 1.2e-5


def _closure(machine=P, rpm=20000.0, rotor_exp=ALPHA, stator_exp=ALPHA, rotor_c=100.0, stator_c=100.0):
    return gap_closure(machine, RHO, MECH, rotor_exp, stator_exp, rpm, rotor_c, stator_c)


def test_thin_ring_growth():
    b, omega = 0.04, 2000.0
    u = _disc_rim_displacement(0.03996, b, RHO, omega, 0.33, 200e9, 0.0)
    assert u == pytest.approx(RHO * omega**2 * b**3 / 200e9, rel=0.01)


def test_disc_rim_load_adds_lame_displacement():
    # at rest, bore a = 10 mm, b = 22 mm, p = 1 MPa: u = (b/E)(p (b^2 + a^2)/(b^2 - a^2) - nu p) = 7.8 nm hand value
    u = _disc_rim_displacement(0.01, 0.022, RHO, 0.0, 0.33, 200e9, 1e6)
    assert u == pytest.approx(0.022 / 200e9 * 1e6 * (584 / 384 - 0.33), rel=1e-12)


def test_uniform_pole_elongation():
    # taper 0 gives a constant pole width. The disc part is removed by evaluating the elongation as the
    # centrifugal total minus the disc displacement of the same case.
    omega = 20000 * 2 * math.pi / 60
    R, b = P.rotor_outer_radius, P.rotor_yoke_outer_radius
    expected = RHO * omega**2 / 200e9 * (R**2 * (R - b) / 2 - (R**3 - b**3) / 6)
    w = 2 * R * math.sin(P.rotor_pole_arc / 2)
    rim = P.n_rotor_poles * RHO * omega**2 * (w / 2) * (R**2 - b**2) / (2 * math.pi * b)
    disc = _disc_rim_displacement(P.shaft_radius, b, RHO, omega, 0.33, 200e9, rim)
    assert _closure().centrifugal - disc == pytest.approx(expected, rel=1e-6)


def test_end_to_end_centrifugal_literal():
    # 8/6, 10JNEX900, 20 000 r/min: disc 2.18502e-6 m plus pole 9.04822e-7 m, solved separately by Lame
    # coefficients and quadrature
    assert _closure().centrifugal == pytest.approx(3.089841e-6, rel=1e-6)


def test_thermal_growth_cancels_for_equal_temperature_and_alpha():
    c = _closure(rpm=1e-3)   # centrifugal part is not asserted
    dt = 80.0
    assert c.rotor_thermal == pytest.approx(ALPHA * dt * 0.04, rel=1e-12)
    assert c.stator_thermal == pytest.approx(ALPHA * dt * 0.0404, rel=1e-12)
    assert c.rotor_thermal - c.stator_thermal == pytest.approx(-3.84e-7, rel=1e-9)
    assert c.closure == pytest.approx(c.centrifugal - 3.84e-7, rel=1e-9)


def test_growth_scales_with_speed_squared():
    assert _closure(rpm=40000.0).centrifugal == pytest.approx(4 * _closure(rpm=20000.0).centrifugal, rel=1e-12)


@pytest.mark.parametrize("rotor_exp,stator_exp,missing", [(None, ALPHA, "rotor"), (ALPHA, None, "stator"),
                                                           (None, None, "rotor and stator")])
def test_missing_expansion_keeps_centrifugal(rotor_exp, stator_exp, missing):
    c = _closure(rotor_exp=rotor_exp, stator_exp=stator_exp)
    assert c.closure is None
    assert c.centrifugal == pytest.approx(3.089841e-6, rel=1e-6)
    assert (c.rotor_thermal is None) == (rotor_exp is None)
    assert (c.stator_thermal is None) == (stator_exp is None)
    assert missing in c.note


def test_rpm_must_be_positive():
    with pytest.raises(ValueError):
        _closure(rpm=0.0)
