"""Cross-solver check (spec §8 test 3): NGSolve vs scikit-fem on the same problem, order, quadrature,
Newton tolerances and B-H. Required agreement is 1e-4."""
import math

import numpy as np
import pytest

pytest.importorskip("ngsolve")

from conftest import make_8_6
from fem_fixtures import toroid_problem
from srmcore.materials.laws import library_law
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import arkkio_torque, flux_linkage, virtual_work_torque
from srmcore.solvers.ngsolve_adapter import NgsolveAdapter
from srmcore.solvers.skfem_reference import SkfemReference

TOL = 1e-4
DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


def _rel(x, y):
    return abs(x - y) / max(abs(y), 1e-30)


def _agree(problem, check_torque=True):
    ref, ngs = SkfemReference().solve(problem), NgsolveAdapter().solve(problem)
    assert ref.status == ngs.status
    assert np.abs(ngs.a - ref.a).max() <= TOL * np.abs(ref.a).max()
    assert _rel(ngs.energy, ref.energy) <= TOL and _rel(ngs.coenergy, ref.coenergy) <= TOL
    psi_ref, psi_ngs = flux_linkage(problem, ref), flux_linkage(problem, ngs)
    assert np.allclose(psi_ngs, psi_ref, rtol=TOL, atol=TOL * np.abs(psi_ref).max())
    if check_torque:
        t_ref = arkkio_torque(problem, ref)
        assert abs(arkkio_torque(problem, ngs) - t_ref) <= TOL * abs(t_ref)
        v_ref = virtual_work_torque(problem, ref)
        assert abs(virtual_work_torque(problem, ngs) - v_ref) <= TOL * abs(v_ref)


def test_nonlinear_toroid_agrees():
    _agree(toroid_problem(library_law("M19"), 3000.0, n_theta=48, layers_per_mm=1), check_torque=False)


@pytest.fixture(scope="module")
def static():
    return build_machine_mesh(DESIGN)


def test_8_6_agrees_at_ten_degrees(static):
    _agree(machine_problem(mesh_at_angle(static, math.radians(10.0)), DESIGN, {"A": 20.0}))


@pytest.mark.slow
@pytest.mark.parametrize("theta", [0.0, math.radians(7.3), math.radians(30.0), -math.radians(4.0), 2 * math.pi + 0.1])
@pytest.mark.parametrize("amps", [5.0, 20.0])
def test_8_6_agrees_across_angles_and_currents(static, theta, amps):
    """Includes angles between band grid positions and angles that wrap past 2π."""
    _agree(machine_problem(mesh_at_angle(static, theta), DESIGN, {"A": amps}))
