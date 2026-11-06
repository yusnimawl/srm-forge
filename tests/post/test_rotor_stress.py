"""Analytic rotor stress and the speed limit (spec R5 section 9)."""
import math

import numpy as np
import pytest

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


def test_bore_hoop_formula():
    nu = MECH.poisson_ratio
    a, b, n = P.shaft_radius, P.rotor_yoke_outer_radius, P.n_rotor_poles
    f = pole_force_per_depth(P, RHO, OMEGA)
    p = n * f / (2 * math.pi * b)
    expected = RHO * OMEGA**2 / 4 * ((3 + nu) * b**2 + (1 - nu) * a**2) + 2 * b**2 / (b**2 - a**2) * p
    assert rotor_stress(P, RHO, MECH, 20000).bore_stress == pytest.approx(expected, rel=1e-12)


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


def test_kt_of_the_8_6():
    # pole half width 40 mm sin 11 deg, D = 2 pi 22 mm / 6, r = 1 mm: h/r 3.8868, 2h/D 0.33742, hand-evaluated
    assert root_stress_concentration(P) == pytest.approx(2.5502925444339035, rel=1e-9)


def test_kt_falls_with_radius():
    assert root_stress_concentration(make_8_6(rotor_fillet_radius=0.002)) < root_stress_concentration(P)


def test_kt_out_of_range_is_not_clamped():
    m = make_8_6(rotor_fillet_radius=1e-4)    # h/r about 39, past the printed 20
    assert root_stress_concentration(m) is None
    s = rotor_stress(m, RHO, MECH, 20000)
    assert s.status == "kt_out_of_range" and s.safety_factor is None and s.stress_concentration is None
    assert s.root_stress == pytest.approx(pole_force_per_depth(m, RHO, OMEGA) / (2 * pole_half_width(m, m.rotor_yoke_outer_radius)))
    assert "h/r" in s.note and s.bore_stress is not None


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


def test_bore_governs_with_a_large_fillet():
    m = make_8_6(rotor_fillet_radius=0.002)
    s = rotor_stress(m, RHO, MECH, 20000)
    assert s.bore_stress > s.root_stress and s.governing == "bore"
    assert s.safety_factor == pytest.approx(s.usable_strength / s.bore_stress)
    assert s.safety_factor == pytest.approx(8.65, abs=0.01)


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
