"""The numpy tangent kernel equals the tangent NGSolve assembles, and the solver's scatter into NGSolve's
matrix gives the same solves as NGSolve's own assembly."""
import numpy as np
import pytest

pytest.importorskip("ngsolve")

import ngsolve as ng
import scipy.sparse as sp

from conftest import make_8_6
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.physics.fem import tangent_element_matrices
from srmcore.solvers.ngsolve_adapter import NgsolveAdapter

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


@pytest.fixture(scope="module")
def setup():
    problem = machine_problem(mesh_at_angle(build_machine_mesh(DESIGN), 0.0), DESIGN, {"A": 20.0})
    adapter = NgsolveAdapter()
    system = adapter._bind(problem)
    a = np.random.default_rng(1).normal(scale=1e-3, size=len(problem.nodes))
    _, nu, dnu = system.material(a)
    return problem, system, a, nu, dnu


def _bind_form(disc, a, nu, dnu):
    disc.nu.vec.FV().NumPy()[:] = nu
    disc.dnu.vec.FV().NumPy()[:] = dnu
    disc.u.vec.FV().NumPy()[:] = a


def test_kernel_matches_ngsolve_assembly(setup):
    problem, system, a, nu, dnu = setup
    disc = system.disc
    _bind_form(disc, a, nu, dnu)
    disc.tangent.Assemble()
    rows, cols, vals = disc.tangent.mat.COO()
    n = len(problem.nodes)
    reference = sp.csr_matrix((vals, (rows, cols)), shape=(n, n))
    k = tangent_element_matrices(disc.grads, disc.areas, disc.triangles, nu, dnu, a)
    tri = disc.triangles
    ours = sp.csr_matrix((k.ravel(), (np.repeat(tri, 3, axis=1).ravel(), np.tile(tri, (1, 3)).ravel())), shape=(n, n))
    diff = abs(ours - reference).max()
    assert diff <= 1e-10 * abs(reference).max()


def test_scatter_solve_matches_ngsolve_assembly(setup):
    problem, system, a, nu, dnu = setup
    rhs = np.random.default_rng(2).normal(size=system.n)
    ours = system.solve_tangent(a, nu, dnu, rhs)
    _bind_form(system.disc, a, nu, dnu)
    system.disc.tangent.Assemble()
    inverse = system.disc.tangent.mat.Inverse(system.freedofs, inverse="umfpack")
    b = ng.BaseVector(system.n)
    b.FV().NumPy()[:] = rhs
    x = b.CreateVector()
    x.data = inverse * b
    ref = x.FV().NumPy().copy()
    ref[problem.dirichlet_nodes] = 0.0
    assert np.linalg.norm(ours - ref) <= 1e-9 * np.linalg.norm(ref)
