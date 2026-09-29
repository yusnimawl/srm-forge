"""NgsolveAdapter behaviour: same contract as SkfemReference (spec §6)."""
import dataclasses

import numpy as np
import pytest

pytest.importorskip("ngsolve")

from fem_fixtures import toroid_problem
from srmcore.fields.solution import SolveStatus
from srmcore.materials.laws import LinearLaw, library_law
from srmcore.solvers.ngsolve_adapter import NgsolveAdapter
from srmcore.solvers.settings import NewtonSettings

M19 = library_law("M19")


def _small(law, current):
    return toroid_problem(law, current, n_theta=48, layers_per_mm=1)


def test_zero_current_gives_zero_field_without_iterating():
    p = _small(M19, 0.0)
    s = NgsolveAdapter().solve(p, initial=np.ones(len(p.nodes)))
    assert s.status is SolveStatus.OK and s.iterations == 0
    assert not np.any(s.a) and s.energy == 0.0 and s.coenergy == 0.0


def test_linear_problem_is_one_solve_with_equal_energies():
    s = NgsolveAdapter().solve(_small(LinearLaw(1000.0), 100.0))
    assert s.status is SolveStatus.OK and s.iterations == 1 and s.residual < 1e-10
    assert s.energy == pytest.approx(s.coenergy, rel=1e-12)


def test_nonlinear_solve_meets_both_tolerances():
    s = NgsolveAdapter().solve(_small(M19, 3000.0))
    assert s.status in (SolveStatus.OK, SolveStatus.OK_WITH_FALLBACK)
    assert s.residual < 1e-8 and s.delta_a < 1e-8


def test_bad_initial_guess_is_rejected():
    p = _small(M19, 100.0)
    with pytest.raises(ValueError, match="shape"):
        NgsolveAdapter().solve(p, initial=np.zeros(3))
    with pytest.raises(ValueError, match="finite"):
        NgsolveAdapter().solve(p, initial=np.full(len(p.nodes), np.nan))


def test_nonconvergence_is_a_status_not_an_exception():
    s = NgsolveAdapter(NewtonSettings(max_iterations=1)).solve(_small(M19, 20000.0))
    assert s.status is SolveStatus.NONCONVERGED


def test_clockwise_triangles_give_the_same_field():
    p = _small(M19, 3000.0)
    flipped = dataclasses.replace(p, triangles=np.ascontiguousarray(p.triangles[:, [0, 2, 1]]))
    a, b = NgsolveAdapter().solve(p).a, NgsolveAdapter().solve(flipped).a
    assert np.abs(a - b).max() <= 1e-9 * np.abs(a).max()


def test_one_adapter_solving_two_meshes_matches_fresh_adapters():
    p1, p2 = _small(M19, 3000.0), toroid_problem(M19, 3000.0, n_theta=64, layers_per_mm=1)
    shared = NgsolveAdapter()
    shared.solve(p1)
    a2 = shared.solve(p2).a
    assert np.abs(a2 - NgsolveAdapter().solve(p2).a).max() <= 1e-9 * np.abs(a2).max()
    assert np.abs(shared.solve(p1).a - NgsolveAdapter().solve(p1).a).max() <= 1e-9 * np.abs(a2).max()
