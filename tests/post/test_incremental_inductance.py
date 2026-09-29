"""L_inc = ∂ψ/∂i (spec §7.1): finite differences, symmetry, the linear limit, and both adapters."""
import dataclasses
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.maps.point import solve_point
from srmcore.materials.laws import VACUUM, LinearLaw
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import flux_linkage, incremental_inductance
from srmcore.solvers.settings import NewtonSettings
from srmcore.solvers.skfem_reference import SkfemReference

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
THETA = math.radians(10.0)


@pytest.fixture(scope="module")
def static():
    return build_machine_mesh(DESIGN)


def _l_inc(solver, problem):
    s = solver.solve(problem)
    return incremental_inductance(problem, solver.sensitivity(problem, s.a)), s


def test_linear_machine_l_inc_is_psi_over_i(static):
    p = machine_problem(mesh_at_angle(static, THETA), DESIGN, {"A": 5.0})
    p = dataclasses.replace(p, laws=tuple(law if law is VACUUM else LinearLaw(1000.0) for law in p.laws))
    l_inc, s = _l_inc(SkfemReference(), p)
    assert l_inc[0, 0] == pytest.approx(flux_linkage(p, s)[0] / 5.0, rel=1e-8)


def test_matches_central_differences_in_the_saturating_range(static):
    solver, base = SkfemReference(), 15.0
    mesh = mesh_at_angle(static, THETA)
    p = machine_problem(mesh, DESIGN, {"A": base})
    l_inc, _ = _l_inc(solver, p)
    h = 0.25
    hi = flux_linkage(p.with_currents([base + h, 0, 0, 0]), solver.solve(p.with_currents([base + h, 0, 0, 0])))
    lo = flux_linkage(p.with_currents([base - h, 0, 0, 0]), solver.solve(p.with_currents([base - h, 0, 0, 0])))
    assert np.allclose(l_inc[:, 0], (hi - lo) / (2 * h), rtol=1e-3, atol=1e-9)


def test_l_inc_is_symmetric_and_positive_definite(static):
    p = machine_problem(mesh_at_angle(static, THETA), DESIGN, {"A": 15.0})
    l_inc, _ = _l_inc(SkfemReference(), p)
    assert np.allclose(l_inc, l_inc.T, rtol=1e-6, atol=1e-12)
    assert np.all(np.linalg.eigvalsh(l_inc) > 0)


def test_l_inc_at_zero_current_is_defined(static):
    p = machine_problem(mesh_at_angle(static, THETA), DESIGN, {})
    solver = SkfemReference()
    l_inc = incremental_inductance(p, solver.sensitivity(p, np.zeros(len(p.nodes))))
    assert np.all(np.isfinite(l_inc)) and l_inc[0, 0] > 0


def test_ngsolve_sensitivity_agrees_with_skfem(static):
    pytest.importorskip("ngsolve")
    from srmcore.solvers.ngsolve_adapter import NgsolveAdapter
    p = machine_problem(mesh_at_angle(static, THETA), DESIGN, {"A": 15.0})
    ref, _ = _l_inc(SkfemReference(), p)
    ngs, _ = _l_inc(NgsolveAdapter(), p)
    assert np.allclose(ngs, ref, rtol=1e-4, atol=1e-4 * np.abs(ref).max())


def test_solve_point_l_inc_flag(static):
    solver = SkfemReference()
    assert solve_point(static, DESIGN, THETA, {"A": 5.0}, solver).l_inc is None
    result = solve_point(static, DESIGN, THETA, {"A": 5.0}, solver, with_l_inc=True)
    assert result.l_inc.shape == (4, 4)


def test_solve_point_withholds_l_inc_when_not_converged(static):
    stingy = SkfemReference(NewtonSettings(max_iterations=1, ramp_steps=1))
    result = solve_point(static, DESIGN, 0.0, {"A": 20.0}, stingy, with_l_inc=True)
    assert result.l_inc is None
