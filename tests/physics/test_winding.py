import numpy as np
import pytest

from conftest import make_8_6, make_12_8
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import InputError
from srmcore.physics.fem import element_flux_density, triangle_areas
from srmcore.physics.winding import phase_winding


@pytest.fixture(scope="module")
def mesh_8_6():
    return mesh_at_angle(build_machine_mesh(Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))), 0.0)


def test_triangle_areas_and_flux_density_of_a_linear_field():
    nodes = np.array([[0.0, 0.0], [2.0, 0.0], [0.0, 1.0]])
    tris = np.array([[0, 1, 2]])
    assert triangle_areas(nodes, tris)[0] == pytest.approx(1.0)
    a = 3.0 * nodes[:, 0] - 5.0 * nodes[:, 1]            # A = 3x - 5y  ->  B = (∂A/∂y, -∂A/∂x) = (-5, -3)
    assert np.allclose(element_flux_density(nodes, tris, a), [[-5.0, -3.0]])


def test_phase_winding_8_6(mesh_8_6):
    w = phase_winding(mesh_8_6, turns_per_pole=60)
    assert w.circuits == ("A", "B", "C", "D")
    assert w.coil_sides == tuple(sorted(mesh_8_6.coils))
    assert not w.equal_path_split_assumed
    areas = triangle_areas(mesh_8_6.nodes, mesh_8_6.triangles)
    for s, name in enumerate(w.coil_sides):
        info = mesh_8_6.coils[name]
        k = w.circuits.index(info.phase)
        area = areas[mesh_8_6.region_ids == mesh_8_6.region_names.index(name)].sum()
        assert w.matrix[s, k] == pytest.approx(info.sign * 60 / area)
        assert np.count_nonzero(w.matrix[s]) == 1          # block-diagonal: one circuit per coil side
    # A conventional phase is a closed series loop: its + and - sides carry equal and opposite ampere-turns.
    for k in range(4):
        col = w.matrix[:, k]
        side_area = np.array([areas[mesh_8_6.region_ids == mesh_8_6.region_names.index(n)].sum() for n in w.coil_sides])
        assert (col * side_area).sum() == pytest.approx(0.0, abs=1e-9)
        assert np.abs(col * side_area).sum() == pytest.approx(4 * 60)


def test_parallel_paths(mesh_8_6):
    w = phase_winding(mesh_8_6, turns_per_pole=60, parallel_paths=2)
    assert w.equal_path_split_assumed
    assert np.allclose(w.matrix, phase_winding(mesh_8_6, 60).matrix / 2)
    with pytest.raises(InputError) as info:
        phase_winding(mesh_8_6, turns_per_pole=60, parallel_paths=3)
    assert info.value.issues[0].parameter == "parallel_paths"


@pytest.mark.slow
def test_phase_winding_12_8_has_three_circuits():
    m = mesh_at_angle(build_machine_mesh(Design(machine=make_12_8(), mesh=MeshSettings(preset="screening"))), 0.0)
    w = phase_winding(m, turns_per_pole=30)
    assert w.circuits == ("A", "B", "C")
    assert all(np.count_nonzero(w.matrix[:, k]) == 8 for k in range(3))
