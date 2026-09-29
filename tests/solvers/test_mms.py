"""Method of manufactured solutions on the nonlinear PDE (spec §8.2 suite 2): A = sin(πx)·sin(πy),
ν = ν0·(1 + α·B²). P1 elements must converge at rate 2 in L2 and rate 1 in the H1 seminorm."""
import math

import numpy as np
import pytest

from fem_fixtures import QuadraticLaw, mms_exact, mms_problem
from srmcore.fields.solution import SolveStatus
from srmcore.physics.fem import triangle_areas
from srmcore.solvers.skfem_reference import SkfemReference


def _errors(n: int) -> tuple[float, float]:
    law = QuadraticLaw(nu0=1.0, alpha=1.0)
    p = mms_problem(law, n)
    s = SkfemReference().solve(p)
    assert s.status is SolveStatus.OK
    area = triangle_areas(p.nodes, p.triangles)
    err = s.a - mms_exact(p.nodes[:, 0], p.nodes[:, 1])
    l2 = math.sqrt(float(area @ (err[p.triangles] ** 2).mean(axis=1)))
    c = p.nodes[p.triangles].mean(axis=1)
    ax = math.pi * np.cos(math.pi * c[:, 0]) * np.sin(math.pi * c[:, 1])
    ay = math.pi * np.sin(math.pi * c[:, 0]) * np.cos(math.pi * c[:, 1])
    h1 = math.sqrt(float(area @ ((s.b[:, 0] - ay) ** 2 + (s.b[:, 1] + ax) ** 2)))
    return l2, h1


def test_mms_convergence_rates():
    errors = [_errors(n) for n in (8, 16, 32)]
    for (l2a, h1a), (l2b, h1b) in zip(errors[:-1], errors[1:]):
        assert math.log2(l2a / l2b) == pytest.approx(2.0, abs=0.15)
        assert math.log2(h1a / h1b) == pytest.approx(1.0, abs=0.1)
