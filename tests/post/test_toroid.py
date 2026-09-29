"""Current-sheet toroid (spec §8.2 suite 2): between the sheets H = I/(2πr) exactly, so B, A and ψ are
known in closed form up to a 1D integral, deep into saturation."""
import math

import numpy as np
import pytest

import fem_fixtures as F
from srmcore.fields.solution import SolveStatus
from srmcore.materials.bh import process_bh
from srmcore.materials.laws import library_law
from srmcore.materials.schema import BHTable
from srmcore.model.constants import MU0
from srmcore.post.quantities import flux_linkage
from srmcore.solvers.skfem_reference import SkfemReference


def _cofe_like():
    """Synthetic CoFe-like curve: μr ≈ 20000 initially, sharp knee at 2.35 T."""
    h = np.logspace(-1, 5.5, 40)
    b = 2.35 * np.tanh(MU0 * 20000 * h / 2.35) + MU0 * h
    curve, report = process_bh(BHTable(h=tuple(h), b=tuple(b)), 1.0, 2.40)
    assert report.initial_relative_permeability > 15000
    return curve


def _b_of_h(curve, h):
    grid = np.linspace(0.0, 10.0, 400_001)
    return np.interp(h, curve.h_of_b(grid), grid)


def _exact_psi(curve, current):
    """ψ = L·[mean A over the inner sheet - mean A over the outer sheet], A(r) = ∫_r^R B_θ ds."""
    r = np.linspace(1e-6, F.R_OUTER, 400_001)
    (a1, b1), (a2, b2) = F.SHEET_IN, F.SHEET_OUT
    enclosed = current * np.clip((r**2 - a1**2) / (b1**2 - a1**2), 0, 1) \
        - current * np.clip((r**2 - a2**2) / (b2**2 - a2**2), 0, 1)
    h = enclosed / (2 * math.pi * r)
    iron = (r > F.IRON[0]) & (r < F.IRON[1])
    b = np.where(iron, _b_of_h(curve, h), MU0 * h)
    seg = 0.5 * (b[1:] + b[:-1]) * np.diff(r)
    a = np.concatenate([np.cumsum(seg[::-1])[::-1], [0.0]])      # A(R_OUTER) = 0

    def mean_a(lo, hi):
        m = (r >= lo) & (r <= hi)
        return np.trapezoid(a[m] * r[m], r[m]) / np.trapezoid(r[m], r[m])

    return F.DEPTH * (mean_a(a1, b1) - mean_a(a2, b2))


def _solve(curve, current):
    p = F.toroid_problem(curve, current, n_theta=96, layers_per_mm=2)
    s = SkfemReference().solve(p)
    return p, s


@pytest.mark.parametrize("current", [50.0, 2000.0, 20000.0, 200000.0], ids=["1.4T", "1.9T", "2.3T", "5T"])
def test_m19_toroid_b_and_flux_linkage(current):
    curve = library_law("M19")
    p, s = _solve(curve, current)
    assert s.status is SolveStatus.OK
    iron = p.element_law == 1
    r = np.hypot(*p.nodes[p.triangles[iron]].mean(axis=1).T)
    b_exact = _b_of_h(curve, current / (2 * math.pi * r))
    assert np.max(np.abs(np.hypot(*s.b[iron].T) - b_exact) / b_exact) < 0.01
    psi = flux_linkage(p, s)[0]
    assert psi == pytest.approx(_exact_psi(curve, current), rel=1e-2)
    # Energy identity W + W' = ψ·i (spec §7.3), with W and W' integrated independently of ψ.
    assert s.energy + s.coenergy == pytest.approx(psi * current, rel=1e-8)


@pytest.mark.parametrize("current", [1.0, 5.0, 50.0, 500.0, 5000.0])
def test_high_initial_permeability_stiffness(current):
    """Spec §6: initial-permeability stiffness (CoFe) must converge, including through the knee."""
    curve = _cofe_like()
    p, s = _solve(curve, current)
    assert s.status in (SolveStatus.OK, SolveStatus.OK_WITH_FALLBACK)
    assert s.residual < 1e-8
    iron = p.element_law == 1
    r = np.hypot(*p.nodes[p.triangles[iron]].mean(axis=1).T)
    b_exact = _b_of_h(curve, current / (2 * math.pi * r))
    assert np.max(np.abs(np.hypot(*s.b[iron].T) - b_exact) / b_exact) < 0.02


def test_cofe_current_sweep_with_continuation():
    curve = _cofe_like()
    p = F.toroid_problem(curve, 0.0, n_theta=96, layers_per_mm=2)
    solver, a = SkfemReference(), None
    for current in (1.0, 5.0, 20.0, 50.0, 200.0, 500.0):
        s = solver.solve(p.with_currents([current]), initial=a)
        assert s.status is SolveStatus.OK
        a = s.a
