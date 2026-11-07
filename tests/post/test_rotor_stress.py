"""Analytic rotor stress and the speed limit (spec R5 section 9)."""
import math

import numpy as np
import pytest
from scipy.optimize import brentq

from conftest import make_8_6
from srmcore.materials.library import load_material
from srmcore.materials.schema import MechanicalData, Provenance
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design, MeshSettings
from srmcore.model.iron import ImportedIron
from srmcore.physics.fem import triangle_areas
from srmcore.post import rotor_stress as rs
from srmcore.post.rotor_stress import (OVERSPEED, SAFETY_FACTOR, pole_force_per_depth, pole_half_width,
                                       root_stress_concentration, rotor_stress)

RHO = 7490.0
MECH = load_material("10JNEX900").mechanical
P = make_8_6()
OMEGA = OVERSPEED * 20000 * 2 * math.pi / 60


def _mech(**kw):
    base = dict(youngs_modulus=200e9, poisson_ratio=0.3, yield_strength=300e6,
                provenance=Provenance(source="test"), confidence="B", strength_confidence="A")
    return MechanicalData(**{**base, **kw})


def test_pole_half_width_without_taper():
    assert pole_half_width(P, P.rotor_yoke_outer_radius) == pytest.approx(P.rotor_outer_radius * math.sin(P.rotor_pole_arc / 2))


def test_pole_force_closed_form_without_taper():
    yc = P.rotor_outer_radius * math.sin(P.rotor_pole_arc / 2)
    expected = RHO * OMEGA**2 * yc * (P.rotor_outer_radius**2 - P.rotor_yoke_outer_radius**2)
    assert pole_force_per_depth(P, RHO, OMEGA) == pytest.approx(expected, rel=1e-9)


@pytest.mark.parametrize("taper", [0.0, 0.06])
def test_pole_force_matches_the_mesh(taper):
    machine = make_8_6(rotor_pole_taper=taper)
    static = build_machine_mesh(Design(machine=machine, mesh=MeshSettings(preset="screening")))
    part = static.rotor
    iron = np.array([static.region_kind[n] == "rotor_iron" for n in static.region_names])[part.region_ids]
    centroid = part.nodes[part.triangles].mean(axis=1)
    r = np.hypot(centroid[:, 0], centroid[:, 1])
    on_axis = np.abs(np.arctan2(centroid[:, 1], centroid[:, 0])) < math.pi / machine.n_rotor_poles
    pick = iron & on_axis & (r > machine.rotor_yoke_outer_radius)
    area = triangle_areas(part.nodes, part.triangles)
    from_mesh = RHO * OMEGA**2 * np.sum(centroid[pick, 0] * area[pick])
    assert pole_force_per_depth(machine, RHO, OMEGA) == pytest.approx(from_mesh, rel=0.01)


def test_bore_is_annulus_plus_relieved_rim_load_plus_ring_bending():
    # docs/r5-sources.md section 5 evaluated by a separate script: relief 0.967534, inner fibre 1.285504 MPa
    nu = MECH.poisson_ratio
    a, b, n = P.shaft_radius, P.rotor_yoke_outer_radius, P.n_rotor_poles
    p = n * pole_force_per_depth(P, RHO, OMEGA) / (2 * math.pi * b)
    expected = (RHO * OMEGA**2 / 4 * ((3 + nu) * b**2 + (1 - nu) * a**2) + 2 * b**2 / (b**2 - a**2) * p * 0.9675336390
                + 1.97 * 1.2855043102e6)
    assert rotor_stress(P, RHO, MECH, 20000).bore_stress == pytest.approx(expected, rel=1e-9)
    assert rotor_stress(P, RHO, MECH, 20000).bore_stress == pytest.approx(65050119.38, rel=1e-8)


def test_rim_relief():
    assert rs._rim_relief(P) == pytest.approx(0.9675336390, rel=1e-9)


def test_ring_bending_of_the_8_6():
    # separate script: half span 0.146581 rad, Winkler-Bach fibres of a 12 mm ring on a 16 mm mean radius
    assert rs._ring_half_span(P) == pytest.approx(0.14658054598, rel=1e-9)
    inner, outer = rs._ring_bending(P, pole_force_per_depth(P, RHO, OMEGA))
    assert inner == pytest.approx(1285504.3102, rel=1e-8)
    assert outer == pytest.approx(1516467.6993, rel=1e-8)


def test_ring_bending_point_load_limit():
    # a pole of almost no width: the ring moment between equal radial point loads, M = (W R / 2)(1/sin a - 1/a)
    m = make_8_6(rotor_pole_arc=1e-7, rotor_fillet_radius=0.0)
    a, b, alpha = m.shaft_radius, m.rotor_yoke_outer_radius, math.pi / m.n_rotor_poles
    t, mean = b - a, (a + b) / 2
    neutral = t / math.log(b / a)
    moment = 1.0 * mean / 2 * (1 / math.sin(alpha) - 1 / alpha)
    assert rs._ring_bending(m, 1.0)[0] == pytest.approx(moment * (neutral - a) / (t * (mean - neutral) * a), rel=1e-5)


def test_ring_bending_short_span_is_a_fixed_beam():
    # end moment twice the mid moment as the free arc gets short; the fibre factors are taken out
    m = make_8_6(rotor_pole_arc=math.radians(58.0), rotor_fillet_radius=0.0)
    a, b = m.shaft_radius, m.rotor_yoke_outer_radius
    neutral = (b - a) / math.log(b / a)
    inner, outer = rs._ring_bending(m, 1.0)
    assert (outer * b / (b - neutral)) / (inner * a / (neutral - a)) == pytest.approx(2.0, rel=0.02)


def test_corner_exponent_is_the_corner_eigenvalue():
    # symmetric mode of a free corner of solid angle w: sin(lambda w) = -lambda sin(w) (Williams 1952)
    def eigenvalue(w):
        return brentq(lambda x: math.sin(x * w) + x * math.sin(w), 0.3, 0.95)
    assert 1 - eigenvalue(1.5 * math.pi) == pytest.approx(rs._CORNER_EXPONENT, abs=1e-4)
    slope = (eigenvalue(1.5 * math.pi - 0.1) - eigenvalue(1.5 * math.pi + 0.1)) / 0.2
    assert slope == pytest.approx(rs._CORNER_EXPONENT_SLOPE, rel=0.2)


@pytest.mark.parametrize("taper, stem, shoulder", [(0.0, 0.86661706094, 2.62536813563),
                                                   (0.06, 0.82992760007, 2.71025375301)])
def test_root_factors(taper, stem, shoulder):
    # separate script, flank found by bisection
    got = rs._root_factors(make_8_6(rotor_pole_taper=taper))
    assert got == pytest.approx((stem, shoulder), rel=1e-8)


def test_root_stress_of_the_8_6():
    # separate script: 0.86662 x 26.40 MPa nominal + 2.62537 x (34.376 + 0.758) MPa
    assert rotor_stress(P, RHO, MECH, 20000).root_stress == pytest.approx(115119002.9, rel=1e-8)


def test_root_nominal_stress_without_fillet_effect():
    s = rotor_stress(make_8_6(rotor_fillet_radius=0.0), RHO, MECH, 20000)
    f = pole_force_per_depth(make_8_6(rotor_fillet_radius=0.0), RHO, OMEGA)
    assert s.root_stress == pytest.approx(f / (2 * pole_half_width(P, P.rotor_yoke_outer_radius)))


@pytest.mark.parametrize("x, t, expected", [
    (0.1, 0.5, 1.1674808672925463), (2.0, 0.5, 1.8469112363849454),
    (20.0, 0.5, 4.003273150927712), (0.1, 0.0, 1.3203575881449727), (20.0, 0.0, 4.572385178594575)])
def test_kt_from_the_cited_formula(x, t, expected):
    # expected values: the coefficient table of docs/r5-sources.md section 4 evaluated by hand
    assert rs._kt(x, t) == pytest.approx(expected, rel=1e-12)


def test_stress_concentration_of_the_8_6():
    # root peak over nominal, the ring stress included
    assert root_stress_concentration(P, MECH.poisson_ratio) == pytest.approx(4.360650534, rel=1e-8)


def test_stress_concentration_falls_with_radius():
    nu = MECH.poisson_ratio
    assert root_stress_concentration(make_8_6(rotor_fillet_radius=0.002), nu) < root_stress_concentration(P, nu)


@pytest.mark.parametrize("overrides, name", [
    (dict(rotor_fillet_radius=1e-4), "fillet ratio"), (dict(rotor_fillet_radius=0.005), "fillet ratio"),
    (dict(n_rotor_poles=18, rotor_pole_arc=math.radians(10.0), n_phases=3), "rotor poles"),
    (dict(shaft_diameter=0.016), "shaft ratio"), (dict(shaft_diameter=0.040, rotor_yoke_thickness=0.012), "shaft ratio"),
    (dict(rotor_pole_arc=math.radians(14.0)), "pole arc ratio"), (dict(rotor_pole_arc=math.radians(27.0)), "pole arc ratio"),
    (dict(rotor_yoke_thickness=0.007), "yoke ratio"), (dict(rotor_yoke_thickness=0.019), "yoke ratio"),
    (dict(rotor_pole_taper=math.radians(-6.0)), "taper"), (dict(rotor_pole_taper=math.radians(11.0)), "taper"),
    (dict(rotor_pole_taper=math.radians(10.0), rotor_fillet_radius=0.004, rotor_yoke_thickness=0.015), "free ring span"),
])
def test_outside_the_validity_box_is_not_clamped(overrides, name):
    m = make_8_6(**overrides)
    assert root_stress_concentration(m, MECH.poisson_ratio) is None
    s = rotor_stress(m, RHO, MECH, 20000)
    assert s.status == "kt_out_of_range" and s.safety_factor is None and s.stress_concentration is None
    assert name in s.note and s.bore_stress is not None
    omega = OVERSPEED * 20000 * 2 * math.pi / 60
    assert s.root_stress == pytest.approx(pole_force_per_depth(m, RHO, omega) / (2 * pole_half_width(m, m.rotor_yoke_outer_radius)))


def test_speed_limit_gives_exactly_the_safety_factor():
    s = rotor_stress(P, RHO, MECH, 20000)
    again = rotor_stress(P, RHO, MECH, s.speed_limit_rpm)
    assert again.safety_factor == pytest.approx(SAFETY_FACTOR)


def test_safety_factor_is_strength_over_governing_stress():
    s = rotor_stress(P, RHO, MECH, 20000)
    assert s.safety_factor == pytest.approx(s.usable_strength / max(s.bore_stress, s.root_stress))
    assert s.governing == ("bore" if s.bore_stress >= s.root_stress else "pole_root")
    assert s.root_stress == pytest.approx(s.stress_concentration * pole_force_per_depth(P, RHO, OMEGA)
                                          / (2 * pole_half_width(P, P.rotor_yoke_outer_radius)))


def test_bore_governs_on_a_short_pole():
    m = make_8_6(n_rotor_poles=4, n_phases=3, rotor_pole_arc=math.radians(36.0), shaft_diameter=0.024,
                 rotor_yoke_thickness=0.022, rotor_fillet_radius=0.003)
    s = rotor_stress(m, RHO, MECH, 20000)
    assert s.status == "ok" and s.bore_stress > s.root_stress and s.governing == "bore"
    assert s.safety_factor == pytest.approx(s.usable_strength / s.bore_stress)
    assert s.bore_stress == pytest.approx(60985617.61924025, rel=1e-8)   # separate script


def test_spec_constants():
    assert OVERSPEED == 1.2 and SAFETY_FACTOR == 1.5
    assert rotor_stress(P, RHO, MECH, 20000).check_speed_rpm == pytest.approx(24000)


def test_grade_b_lowers_strength():
    assert rotor_stress(P, RHO, _mech(strength_confidence="C"), 20000).usable_strength == pytest.approx(300e6 * 0.90)
    s = rotor_stress(P, RHO, _mech(strength_confidence="B"), 20000)
    assert s.usable_strength == pytest.approx(300e6 * 0.97)
    assert rotor_stress(P, RHO, MECH, 20000).usable_strength == pytest.approx(570e6 * 0.97)


def test_brittle_uses_tensile():
    s = rotor_stress(P, RHO, _mech(brittle=True, tensile_strength=250e6, yield_strength=None), 20000)
    assert s.usable_strength == pytest.approx(250e6) and s.criterion == "max_principal"
    assert rotor_stress(P, RHO, MECH, 20000).criterion == "von_mises"


def test_no_data_reads_no_strength():
    s = rotor_stress(P, RHO, None, 20000)
    assert s.status == "no_strength_data" and s.safety_factor is None and s.bore_stress is None


def test_zero_fillet_gives_no_factor():
    s = rotor_stress(make_8_6(rotor_fillet_radius=0.0), RHO, MECH, 20000)
    assert s.status == "no_fillet" and s.safety_factor is None and s.stress_concentration is None
    assert s.root_stress is not None and s.bore_stress is not None


def test_imported_iron_not_available():
    iron = P.model_copy(update={"iron": ImportedIron.model_construct()})
    s = rotor_stress(iron, RHO, MECH, 20000)
    assert s.status == "imported_iron" and "FE stress is R10" in s.note
    assert s.bore_stress is None and s.root_stress is None and s.safety_factor is None


def test_temperature_note():
    assert "temperature" in rotor_stress(P, RHO, MECH, 20000, rotor_temperature_c=90).note   # block states none
    assert "temperature" not in rotor_stress(P, RHO, MECH, 20000).note
    m = _mech(temperature_c=100.0)
    assert "temperature" in rotor_stress(P, RHO, m, 20000, rotor_temperature_c=120).note
    assert "temperature" not in rotor_stress(P, RHO, m, 20000, rotor_temperature_c=80).note


def test_speed_must_be_positive():
    with pytest.raises(ValueError):
        rotor_stress(P, RHO, MECH, 0)
