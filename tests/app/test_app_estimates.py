import math

import pytest
from conftest import make_8_6, make_24_16

from srmapp.sizing import estimates as est


def test_pole_chord():
    assert est.pole_chord(0.05, math.pi) == pytest.approx(0.1)


def test_mass_parts_positive_and_total():
    m = est.active_mass(make_8_6())
    assert m.stator_iron > 0 and m.rotor_iron > 0 and m.copper > 0
    assert m.total == pytest.approx(m.stator_iron + m.rotor_iron + m.copper)


def test_iron_mass_scales_with_stack_length():
    a = est.active_mass(make_8_6(stack_length=0.1))
    b = est.active_mass(make_8_6(stack_length=0.2))
    assert b.stator_iron == pytest.approx(2 * a.stator_iron)
    assert b.rotor_iron == pytest.approx(2 * a.rotor_iron)


def test_8_6_mass_is_plausible():
    # 160 mm OD, 100 mm stack: a few kg of iron, a few kg of copper
    m = est.active_mass(make_8_6())
    assert 3.0 < m.stator_iron + m.rotor_iron < 12.0
    assert 0.2 < m.copper < 5.0


def test_current_and_resistance_relations():
    p = make_8_6()
    a = est.conductor_area(p)
    assert est.peak_current(p) == pytest.approx(est.J_PEAK * a)
    # doubling the turns halves the conductor area and doubles the current-carrying length
    q = make_8_6(turns_per_pole=120)
    assert est.conductor_area(q) == pytest.approx(a / 2)
    assert est.phase_resistance(q) == pytest.approx(4 * est.phase_resistance(p))


def test_resistance_rises_with_temperature():
    p = make_8_6()
    assert est.phase_resistance(p, 100.0) > est.phase_resistance(p, 20.0)
    assert est.phase_resistance(p, 20.0) > 0


def test_copper_mass_equals_volume_from_resistance_geometry():
    # copper volume = phases × (turns per phase × turn length × conductor area)
    p = make_24_16()
    turns_phase = p.turns_per_pole * p.n_stator_poles / p.n_phases
    volume = p.n_phases * turns_phase * est.mean_turn_length(p) * est.conductor_area(p)
    assert est.active_mass(p).copper == pytest.approx(8890.0 * volume, rel=1e-6)


@pytest.mark.slow
def test_areas_agree_with_the_mesh():
    pytest.importorskip("gmsh")
    import numpy as np

    from srmcore.mesh import build_machine_mesh
    from srmcore.model.design import Design, MeshSettings
    from srmcore.physics.fem import triangle_areas

    p = make_8_6()
    mesh = build_machine_mesh(Design(machine=p, mesh=MeshSettings(preset="screening")))

    def area(part, kind):
        a = triangle_areas(part.nodes, part.triangles)
        ids = [i for i, n in enumerate(mesh.region_names) if mesh.region_kind[n] == kind]
        return float(a[np.isin(part.region_ids, ids)].sum())

    stator_area = area(mesh.stator, "stator_iron")
    rotor_area = area(mesh.rotor, "rotor_iron")
    coil_area = area(mesh.stator, "coil")
    m = est.active_mass(p)
    rho = 7650.0   # M19 provisional density
    from srmcore.materials.library import load_material
    k = load_material("M19").stacking_factor
    assert m.stator_iron == pytest.approx(rho * k * stator_area * p.stack_length, rel=0.08)
    assert m.rotor_iron == pytest.approx(rho * k * rotor_area * p.stack_length, rel=0.08)
    assert 2 * p.n_stator_poles * est.coil_side_area(p) == pytest.approx(coil_area, rel=0.15)
