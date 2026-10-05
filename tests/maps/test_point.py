"""solve_point: one operating point, the chain every map point repeats (spec §7.2, §10)."""
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.fields.solution import FieldSolution, SolveStatus
from srmcore.maps.point import PointResult, area_quantile, solve_point
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import arkkio_torque, flux_linkage, virtual_work_torque
from srmcore.solvers.settings import NewtonSettings
from srmcore.solvers.skfem_reference import SkfemReference

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


@pytest.fixture(scope="module")
def static():
    return build_machine_mesh(DESIGN)


def test_matches_the_manual_chain(static):
    theta, solver = math.radians(10.0), SkfemReference()
    result = solve_point(static, DESIGN, theta, {"A": 5.0}, solver)
    problem = machine_problem(mesh_at_angle(static, theta), DESIGN, {"A": 5.0})
    solution = solver.solve(problem)
    assert isinstance(result, PointResult)
    assert result.circuits == ("A", "B", "C", "D")
    assert np.array_equal(result.currents, [5.0, 0.0, 0.0, 0.0])
    assert result.angle == pytest.approx(theta)
    assert np.allclose(result.psi, flux_linkage(problem, solution), rtol=1e-12, atol=1e-15)
    assert result.torque_arkkio == pytest.approx(arkkio_torque(problem, solution), rel=1e-12)
    assert result.torque_virtual_work == pytest.approx(virtual_work_torque(problem, solution), rel=1e-12)
    assert result.energy == solution.energy and result.coenergy == solution.coenergy
    assert result.status is SolveStatus.OK and result.iterations == solution.iterations
    assert result.field is None
    kind = np.array([problem.region_kind[n] for n in problem.region_names])[problem.element_region]
    iron = (kind == "stator_iron") | (kind == "rotor_iron")
    t = problem.nodes[problem.triangles[iron]]
    area = 0.5 * np.abs((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1])
                        - (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1]))
    b = np.hypot(solution.b[iron, 0], solution.b[iron, 1])
    assert result.b_peak == pytest.approx(area_quantile(b, area), rel=1e-12)
    assert result.b_peak < b.max()


def test_area_quantile_ignores_a_tiny_hot_element():
    values = np.array([1.0] * 999 + [9.0])
    areas = np.array([1.0] * 999 + [1e-6])
    assert area_quantile(values, areas) == 1.0


def test_area_quantile_of_a_uniform_field_is_that_field():
    assert area_quantile(np.full(5, 2.0), np.arange(1.0, 6.0)) == 2.0


def test_area_quantile_sees_a_hot_region_with_real_area():
    assert area_quantile(np.array([1.0, 3.0]), np.array([0.5, 0.5])) == 3.0


def test_keep_field_returns_the_field(static):
    result = solve_point(static, DESIGN, 0.0, {"A": 5.0}, SkfemReference(), keep_field=True)
    assert isinstance(result.field, FieldSolution)
    assert result.field.a.shape == (len(mesh_at_angle(static, 0.0).nodes),)


def test_zero_current_point(static):
    result = solve_point(static, DESIGN, 0.0, {}, SkfemReference())
    assert result.iterations == 0 and result.status is SolveStatus.OK
    assert np.all(result.psi == 0.0) and result.torque_arkkio == 0.0


def test_angle_wraps_like_mesh_at_angle(static):
    solver = SkfemReference()
    direct = solve_point(static, DESIGN, math.radians(3.0), {"A": 5.0}, solver)
    wrapped = solve_point(static, DESIGN, math.radians(3.0) + 2 * math.pi, {"A": 5.0}, solver)
    negative = solve_point(static, DESIGN, math.radians(3.0) - 2 * math.pi, {"A": 5.0}, solver)
    for other in (wrapped, negative):
        assert other.angle == pytest.approx(direct.angle)
        assert np.allclose(other.psi, direct.psi, rtol=1e-9)


def test_unknown_circuit_is_rejected(static):
    with pytest.raises(ValueError, match="circuits are"):
        solve_point(static, DESIGN, 0.0, {"Z": 1.0}, SkfemReference())


def test_nonconvergence_is_reported_not_raised(static):
    stingy = SkfemReference(NewtonSettings(max_iterations=1, ramp_steps=1))
    result = solve_point(static, DESIGN, 0.0, {"A": 20.0}, stingy)
    assert result.status is SolveStatus.NONCONVERGED
    assert result.load_fraction <= 1.0


def test_ngsolve_agrees_with_skfem(static):
    pytest.importorskip("ngsolve")
    from srmcore.solvers.ngsolve_adapter import NgsolveAdapter
    theta = math.radians(10.0)
    ref = solve_point(static, DESIGN, theta, {"A": 5.0}, SkfemReference())
    ngs = solve_point(static, DESIGN, theta, {"A": 5.0}, NgsolveAdapter())
    assert np.allclose(ngs.psi, ref.psi, rtol=1e-4, atol=1e-4 * np.abs(ref.psi).max())
    scale = max(abs(ref.torque_arkkio), abs(ref.coenergy))
    assert abs(ngs.torque_arkkio - ref.torque_arkkio) <= 1e-4 * scale
