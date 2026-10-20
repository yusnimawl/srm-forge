"""A failed UMFPACK factorization is a non-converged solve, not an exception (spec §6)."""
import pytest

pytest.importorskip("ngsolve")

from fem_fixtures import toroid_problem
from netgen.libngpy._meshing import NgException
from srmcore.fields.solution import SolveStatus
from srmcore.materials.laws import LinearLaw, library_law
from srmcore.solvers import ngsolve_adapter as mod
from srmcore.solvers.settings import FactorizationFailed
from srmcore.solvers.settings import FactorizationFailed


def _fail_first(monkeypatch, n):
    real, calls = mod._factorize, {"n": 0}

    def flaky(mat, free):
        calls["n"] += 1
        if calls["n"] <= n:
            raise FactorizationFailed("UmfpackInverse: Numeric factorization failed.")
        return real(mat, free)

    monkeypatch.setattr(mod, "_factorize", flaky)


def _problem():
    return toroid_problem(library_law("M19"), 3000.0, n_theta=48, layers_per_mm=1)


def test_first_attempt_failure_recovers_through_damped_newton(monkeypatch):
    _fail_first(monkeypatch, 1)
    s = mod.NgsolveAdapter().solve(_problem())
    assert s.status is SolveStatus.OK_WITH_FALLBACK and s.fallbacks == ("damped",)


def test_every_factorization_failing_is_nonconverged(monkeypatch):
    _fail_first(monkeypatch, 10**6)
    s = mod.NgsolveAdapter().solve(_problem())
    assert s.status is SolveStatus.NONCONVERGED and "factorization" in s.fallbacks


def test_linear_path_failure_is_nonconverged(monkeypatch):
    _fail_first(monkeypatch, 10**6)
    s = mod.NgsolveAdapter().solve(toroid_problem(LinearLaw(1000.0), 100.0, n_theta=48, layers_per_mm=1))
    assert s.status is SolveStatus.NONCONVERGED and s.fallbacks == ("factorization",)


class _Mat:
    def __init__(self, message):
        self.message = message

    def Inverse(self, free, inverse):
        raise NgException(self.message)


def test_only_a_failed_factorization_is_translated():
    with pytest.raises(FactorizationFailed):
        mod._factorize(_Mat("UmfpackInverse: Numeric factorization failed."), None)
    with pytest.raises(NgException):
        mod._factorize(_Mat("something else"), None)
