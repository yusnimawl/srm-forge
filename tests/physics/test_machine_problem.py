import dataclasses

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.materials.laws import VACUUM, library_law
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings, RegionMaterials
from srmcore.physics.build import machine_problem

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


@pytest.fixture(scope="module")
def mesh_8_6():
    return mesh_at_angle(build_machine_mesh(DESIGN), 0.0)


def test_laws_follow_region_kind(mesh_8_6):
    p = machine_problem(mesh_8_6, DESIGN)
    kind = np.array([mesh_8_6.region_kind[n] for n in mesh_8_6.region_names])[mesh_8_6.region_ids]
    law = np.array(p.laws, dtype=object)[p.element_law]
    assert all(x is library_law("M19") for x in law[(kind == "stator_iron") | (kind == "rotor_iron")])
    assert all(x is library_law("steel_1010") for x in law[kind == "shaft"])
    assert all(x is VACUUM for x in law[(kind == "air") | (kind == "coil")])


def test_problem_geometry_boundary_and_band(mesh_8_6):
    p = machine_problem(mesh_8_6, DESIGN, {"A": 10.0})
    assert p.nodes is mesh_8_6.nodes and p.triangles is mesh_8_6.triangles
    assert np.array_equal(p.dirichlet_nodes, np.unique(mesh_8_6.outer_edges))
    assert p.depth == DESIGN.machine.stack_length
    assert np.array_equal(p.band.elements, np.arange(len(p.triangles))[mesh_8_6.band_rows])
    assert (p.band.inner_radius, p.band.outer_radius) == (mesh_8_6.band_inner_radius, mesh_8_6.band_outer_radius)
    assert np.allclose(p.currents, [10.0, 0.0, 0.0, 0.0])


def test_current_density_only_in_excited_coils(mesh_8_6):
    p = machine_problem(mesh_8_6, DESIGN, {"B": 5.0})
    j = p.current_density()
    for rid, name in enumerate(mesh_8_6.region_names):
        rows = mesh_8_6.region_ids == rid
        info = mesh_8_6.coils.get(name)
        if info is not None and info.phase == "B":
            assert np.all(np.sign(j[rows]) == info.sign) and np.all(j[rows] != 0)
        else:
            assert np.all(j[rows] == 0)


def test_region_names_are_never_parsed(mesh_8_6):
    """Opaque region names must give the same problem: the builder reads region_kind and coils only."""
    new = {n: f"r{i}" for i, n in enumerate(mesh_8_6.region_names)}
    renamed = dataclasses.replace(
        mesh_8_6, region_names=tuple(new[n] for n in mesh_8_6.region_names),
        region_kind={new[k]: v for k, v in mesh_8_6.region_kind.items()},
        region_part={new[k]: v for k, v in mesh_8_6.region_part.items()},
        coils={new[k]: v for k, v in mesh_8_6.coils.items()})
    p1 = machine_problem(mesh_8_6, DESIGN, {"A": 10.0})
    p2 = machine_problem(renamed, DESIGN, {"A": 10.0})
    assert np.allclose(p1.current_density(), p2.current_density())
    assert [p1.laws[i] for i in p1.element_law] == [p2.laws[i] for i in p2.element_law]


def test_unknown_circuit_and_material_are_rejected(mesh_8_6):
    with pytest.raises(ValueError, match="unknown circuit"):
        machine_problem(mesh_8_6, DESIGN, {"E": 1.0})
    bad = DESIGN.model_copy(update={"machine": make_8_6(materials=RegionMaterials(stator="M270"))})
    with pytest.raises(KeyError, match="M270"):
        machine_problem(mesh_8_6, bad)


def test_with_currents_checks_length(mesh_8_6):
    p = machine_problem(mesh_8_6, DESIGN)
    assert np.allclose(p.with_currents([1.0, 2.0, 3.0, 4.0]).currents, [1, 2, 3, 4])
    with pytest.raises(ValueError, match="4 circuit currents"):
        p.with_currents([1.0])
