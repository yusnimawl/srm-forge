import dataclasses

import numpy as np
import pytest

from fem_fixtures import toroid_problem
from srmcore.fields.solution import SolveStatus
from srmcore.materials.laws import LinearLaw, library_law
from srmcore.solvers import skfem_reference
from srmcore.solvers.settings import NewtonSettings
from srmcore.solvers.skfem_reference import SkfemReference

M19 = library_law("M19")


def _small(law, current):
    return toroid_problem(law, current, n_theta=48, layers_per_mm=1)


def test_zero_current_gives_zero_field_without_iterating():
    s = SkfemReference().solve(_small(M19, 0.0), initial=np.ones(len(_small(M19, 0.0).nodes)))
    assert s.status is SolveStatus.OK and s.iterations == 0
    assert not np.any(s.a) and s.energy == 0.0 and s.coenergy == 0.0


def test_linear_problem_is_one_solve_with_equal_energies():
    s = SkfemReference().solve(_small(LinearLaw(1000.0), 100.0))
    assert s.status is SolveStatus.OK and s.iterations == 1 and s.residual < 1e-10
    assert s.energy == pytest.approx(s.coenergy, rel=1e-12)


def test_nonlinear_solve_meets_both_tolerances():
    s = SkfemReference().solve(_small(M19, 20000.0))
    assert s.status is SolveStatus.OK and not s.fallbacks
    assert s.residual < 1e-8 and s.delta_a < 1e-8


def test_initial_guess_from_another_mesh_is_rejected():
    with pytest.raises(ValueError, match="initial guess"):
        SkfemReference().solve(_small(M19, 100.0), initial=np.zeros(7))


def test_non_finite_initial_guess_is_rejected():
    p = _small(M19, 100.0)
    guess = np.zeros(len(p.nodes))
    guess[0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        SkfemReference().solve(p, initial=guess)


def test_continuation_from_a_nearby_solution_converges():
    solver = SkfemReference()
    p = _small(M19, 2000.0)
    first = solver.solve(p)
    again = solver.solve(p.with_currents([2100.0]), initial=first.a)
    assert again.status is SolveStatus.OK


def test_tangent_matches_finite_differences():
    p = _small(M19, 20000.0)
    solver = SkfemReference()
    a = 0.7 * solver.solve(p).a
    r0, tangent = solver.linearize(p, a)
    rng = np.random.default_rng(0)
    v = rng.standard_normal(len(a))
    v[p.dirichlet_nodes] = 0.0
    v *= np.linalg.norm(a) / np.linalg.norm(v)
    eps = 1e-5
    fd = (solver.linearize(p, a + eps * v)[0] - solver.linearize(p, a - eps * v)[0]) / (2 * eps)
    free = np.setdiff1d(np.arange(len(a)), p.dirichlet_nodes)
    assert np.linalg.norm((fd - tangent @ v)[free]) / np.linalg.norm((tangent @ v)[free]) < 1e-5


def test_nonconvergence_is_a_status_not_an_exception():
    s = SkfemReference(NewtonSettings(max_iterations=1)).solve(_small(M19, 20000.0))
    assert s.status is SolveStatus.NONCONVERGED
    assert s.fallbacks == ("damped", "ramp")
    assert s.load_fraction == 1 / NewtonSettings().ramp_steps     # the ramp stopped at its first step
    assert np.all(np.isfinite(s.a))


def test_stalled_line_search_is_not_converged(monkeypatch):
    """If no step reduces the residual, the iterate is not accepted and the solve reports NONCONVERGED."""
    real = skfem_reference._System.residual
    calls = [0]

    def growing(self, a, f):
        r, nu, dnu = real(self, a, f)
        calls[0] += 1
        return r * (1.0 + calls[0]), nu, dnu

    monkeypatch.setattr(skfem_reference._System, "residual", growing)
    s = SkfemReference(NewtonSettings(max_halvings=3, ramp_steps=1)).solve(_small(M19, 20000.0))
    assert s.status is SolveStatus.NONCONVERGED
    assert not np.any(s.a)                  # nothing was accepted from the zero start
    assert np.isfinite(s.residual)


@pytest.mark.parametrize("failures,status,fallbacks", [
    (1, SolveStatus.OK_WITH_FALLBACK, ("damped",)),
    (2, SolveStatus.OK_WITH_FALLBACK, ("damped", "ramp")),
])
def test_fallback_chain_order(monkeypatch, failures, status, fallbacks):
    real = skfem_reference._newton
    calls = []

    def flaky(*args, **kwargs):
        out = real(*args, **kwargs)
        calls.append(out)
        return dataclasses.replace(out, converged=False) if len(calls) <= failures else out

    monkeypatch.setattr(skfem_reference, "_newton", flaky)
    s = SkfemReference().solve(_small(M19, 20000.0))
    assert s.status is status and s.fallbacks == fallbacks and s.load_fraction == 1.0
    assert len(calls) == (2 if failures == 1 else 2 + NewtonSettings().ramp_steps)
